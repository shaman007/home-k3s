#!/usr/bin/env python3
"""Prove separate-container CDP/DOM with the actual Karakeep Patchright client."""

import uuid
from pathlib import Path

import yaml
from probe_commands import run_command

ROOT = Path(__file__).resolve().parents[2]


def run(arguments):
    """Run a bounded isolated-fixture command without an implicit shell."""
    result = run_command(arguments, timeout=120, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-2500:] + result.stdout[-1000:])
    return result.stdout.strip()


def main():
    """Use a private no-uplink network and remove only resources from this run."""
    name = "karakeep-cdp-" + uuid.uuid4().hex[:10]
    owned = []
    chrome_image = yaml.safe_load(
        (ROOT / "karakeep/deployment-chrome.yaml").read_text()
    )["spec"]["template"]["spec"]["containers"][0]["image"]
    web_image = yaml.safe_load(
        (ROOT / "karakeep/deployment-karakeep.yaml").read_text()
    )["spec"]["template"]["spec"]["containers"][0]["image"]
    try:
        run(["podman", "network", "create", "--internal", name])
        cid = run(
            [
                "podman",
                "run",
                "-d",
                "--network=" + name,
                "--network-alias=chrome",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--read-only",
                "--user=65534:65534",
                "--tmpfs",
                "/tmp:mode=1777",
                "--shm-size=256m",
                chrome_image,
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ]
        )
        owned.append(cid)
        code = """const {chromium}=require("patchright");
const dns=require("node:dns");
(async()=>{let a=await dns.promises.lookup("chrome");
let url="http://"+a.address+":9222";
let browser;
for(let i=0;
i<20;
i++){try{browser=await chromium.connectOverCDP(url,{timeout:3000});
break}catch(e){if(i===19)throw e;
await new Promise(r=>setTimeout(r,500))}}let page=await browser.newPage();
await page.setContent("<title>isolated-cdp-ok</title><p>fixture</p>");
if(await page.title()!=="isolated-cdp-ok")throw Error("wrong title");
await page.close();
await browser.close();
console.log("Remote separate-container Patchright CDP + DOM passed");
})().catch(e=>{console.error(e.message);
process.exit(1)})"""
        print(
            run(
                [
                    "podman",
                    "run",
                    "--rm",
                    "--network=" + name,
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--user=1000:1000",
                    "--workdir=/app/apps/workers",
                    "--entrypoint=node",
                    web_image,
                    "-e",
                    code,
                ]
            )
        )
    finally:
        for c in owned:
            run(["podman", "rm", "-f", "-v", c])
        run(["podman", "network", "rm", name])


if __name__ == "__main__":
    main()
