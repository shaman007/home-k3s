#!/usr/bin/env python3
"""Offline Plex startup/preferences/media probe on disposable data; no account claim.

No production media, configuration, credentials or GPU devices are mounted.
"""

from pathlib import Path
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import yaml

ROOT = Path(__file__).resolve().parents[2]
CAPS = ["CHOWN", "DAC_OVERRIDE", "FOWNER", "FSETID", "KILL", "SETGID", "SETUID"]


def run(args, timeout=90):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if not result.returncode == 0:
        raise AssertionError(result.stdout[-2000:] + result.stderr[-2000:])
    return result.stdout.strip()


def main():
    doc = yaml.safe_load((ROOT / "plex/deployment-plex.yaml").read_text())
    c = doc["spec"]["template"]["spec"]["containers"][0]
    if not c["securityContext"]["capabilities"] == {"drop": ["ALL"], "add": CAPS}:
        raise AssertionError
    if not c["securityContext"]["allowPrivilegeEscalation"] is False:
        raise AssertionError
    if not all((p["containerPort"] >= 1024 for p in c["ports"])):
        raise AssertionError
    hook = yaml.safe_load((ROOT / "plex/config-map-plex-custom-init.yaml").read_text())["data"][
        "10-disable-scheduled-library-updates.sh"
    ]
    volume = run(["podman", "volume", "create"])
    cid = None
    try:
        with tempfile.TemporaryDirectory(prefix="plex-guard-") as directory:
            d = Path(directory)
            media = d / "media"
            media.mkdir(mode=0o755)
            (d / "hook").write_text(hook)
            (d / "hook").chmod(0o755)
            run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=160x90:rate=10",
                    "-t",
                    "1",
                    "-c:v",
                    "ffv1",
                    str(media / "fixture.mkv"),
                ]
            )
            args = [
                "podman",
                "run",
                "-d",
                "--network=none",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "-v",
                volume + ":/config",
                "-v",
                str(media) + ":/data:ro,Z",
                "-v",
                str(d / "hook")
                + ":/custom-cont-init.d/10-disable-scheduled-library-updates.sh:ro,Z",
            ]
            args += ["--cap-add=" + cap for cap in CAPS]
            for env in c["env"]:
                if env["name"] in ["PUID", "PGID", "ADVERTISE_IP"]:
                    args += ["-e", env["name"] + "=" + env["value"]]
            cid = run(args + [c["image"]])

            def identity():
                for _ in range(40):
                    p = subprocess.run(
                        ["podman", "exec", cid, "curl", "-fsS", "http://127.0.0.1:32400/identity"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if p.returncode == 0:
                        root = ET.fromstring(p.stdout)
                        if not root.tag == "MediaContainer":
                            raise AssertionError
                        return
                    time.sleep(1)
                raise RuntimeError("Plex identity endpoint did not become ready")

            identity()
            status = run(["podman", "exec", cid, "cat", "/proc/1/status"])
            for expected in ["CapBnd:\t00000000000000fb", "NoNewPrivs:\t1", "Seccomp:\t2"]:
                if not expected in status:
                    raise AssertionError(status)
            # Read a synthetic file and software-transcode as the real media user.
            run(
                [
                    "podman",
                    "exec",
                    "--user",
                    "1000:1000",
                    cid,
                    "/usr/lib/plexmediaserver/Plex Transcoder",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    "/data/fixture.mkv",
                    "-c:v",
                    "mjpeg",
                    "-an",
                    "-f",
                    "matroska",
                    "/tmp/guard-output.mkv",
                ]
            )
            if (
                not int(run(["podman", "exec", cid, "stat", "-c", "%s", "/tmp/guard-output.mkv"]))
                > 0
            ):
                raise AssertionError
            # Restart against the same preferences to exercise the non-empty hook branch.
            run(["podman", "restart", cid])
            identity()
            prefs = run(
                [
                    "podman",
                    "exec",
                    cid,
                    "cat",
                    "/config/Library/Application Support/Plex Media Server/Preferences.xml",
                ]
            )
            p = ET.fromstring(prefs)
            if not p.attrib["ScheduledLibraryUpdatesEnabled"] == "0":
                raise AssertionError
            if not p.attrib["FSEventLibraryUpdatesEnabled"] == "1":
                raise AssertionError
            if not p.attrib["FSEventLibraryPartialScanEnabled"] == "1":
                raise AssertionError
            advertised = next(e["value"] for e in c["env"] if e["name"] == "ADVERTISE_IP")
            if not p.attrib["customConnections"] == advertised:
                raise AssertionError
            print(
                "Plex: offline startup, HTTP identity, UID 1000 software MJPEG transcode and persistent-preference restart passed"
            )
            print(
                "Reduced capability bounding set, no-new-privileges and seccomp verified; GPU/playback not tested"
            )
    except Exception:
        if cid:
            result = subprocess.run(
                ["podman", "logs", "--tail=30", cid], capture_output=True, text=True, check=False
            )
            print((result.stdout + result.stderr)[-2500:])
        raise
    finally:
        if cid:
            run(["podman", "rm", "-f", cid])
        run(["podman", "volume", "rm", volume])


if __name__ == "__main__":
    main()
