/* Gate the s6 workers service only; web, migrations and the browser Deployment start independently. */
"use strict";
const http = require("node:http");
const { performance } = require("node:perf_hooks");

function probe(url, field, expected, timeoutMs = 5000, headers = {}) {
  return new Promise((resolve) => {
    let finished = false;
    let request;
    let response;
    const finish = (ready) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (response) response.destroy();
      if (request) request.destroy();
      resolve(ready);
    };
    // Covers DNS, connect, headers and body, not merely idle socket time.
    const timer = setTimeout(() => finish(false), timeoutMs);
    try {
      request = http.get(url, {headers}, (incoming) => {
        response = incoming;
        if (response.statusCode !== 200) return finish(false);
        let body = "";
        response.on("data", (part) => {
          body += part;
          if (body.length > 65536) finish(false);
        });
        response.on("end", () => {
          try {
            const value = JSON.parse(body)[field];
            finish(expected === null ? typeof value === "string" && value.length > 0 : value === expected);
          } catch { finish(false); }
        });
        response.on("error", () => finish(false));
      });
      request.on("error", () => finish(false));
    } catch { finish(false); }
  });
}

async function wait({ budgetMs = 300000, intervalMs = 5000, check, now = () => performance.now(), sleep = (ms) => new Promise((r) => setTimeout(r, ms)) }) {
  const started = now();
  while (now() - started < budgetMs) {
    const remaining = budgetMs - (now() - started);
    if (await check(Math.min(5000, remaining)) && now() - started <= budgetMs) return true;
    const delay = Math.min(intervalMs, budgetMs - (now() - started));
    if (delay > 0) await sleep(delay);
  }
  return false;
}

async function main() {
  // These addresses were inspected in the pinned image's deployed configuration.
  if (!["http://127.0.0.1:9222", "http://chrome.karakeep.svc.cluster.local:9222"].includes(process.env.BROWSER_WEB_URL) ||
      process.env.MEILI_ADDR !== "http://meilisearch.karakeep.svc.cluster.local:7700" ||
      typeof process.execve !== "function") {
    console.log('{"event":"karakeep_worker_dependencies","result":"invalid-config"}');
    return 78;
  }
  const ready = await wait({ check: async (timeout) => {
    const results = await Promise.all([
      // Chrome rejects DNS names in Host; this discovery probe does not use its WS address.
      probe(`${process.env.BROWSER_WEB_URL}/json/version`, "webSocketDebuggerUrl", null, timeout, {Host: "localhost"}),
      probe("http://meilisearch.karakeep.svc.cluster.local:7700/health", "status", "available", timeout),
    ]);
    return results.every(Boolean);
  }});
  console.log(JSON.stringify({event: "karakeep_worker_dependencies", result: ready ? "ready" : "unavailable"}));
  if (!ready) return 75; // s6 retries this service; never stop the entire Pod or UI.
  process.chdir("/app/apps/workers");
  process.execve(process.execPath, [process.execPath, "dist/index.js"], process.env);
  return 127;
}

module.exports = { probe, wait };
if (require.main === module) {
  main().then((code) => { process.exitCode = code; }).catch(() => {
    console.log('{"event":"karakeep_worker_dependencies","result":"failed"}');
    process.exitCode = 1;
  });
}
