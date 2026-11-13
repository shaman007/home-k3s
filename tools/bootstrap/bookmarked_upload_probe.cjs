"use strict";
const http = require("node:http");
const https = require("node:https");
const { performance } = require("node:perf_hooks");

function status(url, key, timeoutMs) {
  return new Promise((resolve) => {
    let request;
    let finished = false;
    const finish = (code) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (request) request.destroy();
      resolve(code);
    };
    const timer = setTimeout(() => finish(0), timeoutMs);
    try {
      const transport = url.startsWith("https:") ? https : http;
      request = transport.get(url, {headers: {"x-api-key": key}}, (response) => {
        finish(response.statusCode);
        response.destroy();
      });
      request.on("error", () => finish(0));
    } catch { finish(0); }
  });
}

async function wait({check, budgetMs = 300000, intervalMs = 5000,
  now = () => performance.now(), sleep = (ms) => new Promise((r) => setTimeout(r, ms))}) {
  const started = now();
  while (now() - started < budgetMs) {
    const code = await check(Math.min(5000, budgetMs - (now() - started)));
    if (code === 200 && now() - started <= budgetMs) return 0;
    if (code === 401 || code === 403) return 77;
    if (code === 404) return 78;
    const delay = Math.min(intervalMs, budgetMs - (now() - started));
    if (delay > 0) await sleep(delay);
  }
  return 75;
}

async function main() {
  const base = process.env.IMMICH_INSTANCE_URL;
  const key = process.env.IMMICH_API_KEY || "";
  if (base !== "https://immich.andreybondarenko.com/api" || !/^[a-zA-Z0-9+/.=_-]+$/.test(key)) return 78;
  const result = await wait({check: (timeout) => status(base + "/users/me", key, timeout)});
  console.log(JSON.stringify({event: "cron_dependencies", result: result === 0 ? "ready" : result === 75 ? "skipped" : "denied-or-invalid"}));
  return result;
}

module.exports = {status, wait};
if (require.main === module) {
  main().then((code) => {process.exitCode = code;}).catch(() => {process.exitCode = 78;});
}
