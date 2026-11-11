#!/usr/bin/env python3
"""Isolated non-root speaker prerequisites: no LAN interfaces, VIPs or secrets.

A setup-only NET_ADMIN container creates two veth interfaces inside a network=none
namespace. The tested UID 1000 process retains only NET_RAW and cannot alter links.
The real speaker also reads the config and creates ARP/NDP responders. This is
not a substitute for a post-rollout test of MetalLB's own ARP/NDP responders.
"""

from pathlib import Path
import tempfile
import time

from probe_commands import run_command

IMAGE = "quay.io/frrouting/frr:10.4.3"  # Existing local Python/ip diagnostic image.
SPEAKER = "quay.io/metallb/speaker:v0.16.1"
PROBE = (
    "\nimport os,socket,struct,subprocess\nfrom "
    "pathlib import Path\nassert "
    "os.getuid()==1000 and "
    "os.getgid()==1000\nstatus=Path('/proc/sel"
    "f/status').read_text()\nfor value in "
    "['CapEff:\\t0000000000002000','CapBnd:\\t0"
    "000000000002000','NoNewPrivs:\\t1','Secco"
    "mp:\\t2']:\n assert value in "
    "status,value\nassert "
    "Path('/fixture/group-readable.yaml').rea"
    "d_text()=='announcedInterfacesToExclude: "
    "[]\\n'\ntry: "
    "Path('/fixture/root-only.yaml').read_tex"
    "t()\nexcept PermissionError: pass\nelse: "
    "raise AssertionError('Root-only 0400 "
    "ConfigMap unexpectedly "
    "readable')\np=subprocess.run(['ip','link'"
    ",'set','fixture0','down'],capture_output"
    "=True)\nassert p.returncode!=0,'NET_ADMIN "
    "unexpectedly available'\n# ARP on a real "
    "veth pair, without touching host "
    "networking.\na=socket.socket(socket.AF_PA"
    "CKET,socket.SOCK_RAW,socket.htons(0x0806"
    "));a.bind(('fixture0',0));a.settimeout(3"
    ")\nb=socket.socket(socket.AF_PACKET,socke"
    "t.SOCK_RAW,socket.htons(0x0806));b.bind("
    "('fixture1',0));b.settimeout(3)\nmac0=byt"
    "es.fromhex(Path('/sys/class/net/fixture0"
    "/address').read_text().strip().replace('"
    ":',''))\nmac1=bytes.fromhex(Path('/sys/cl"
    "ass/net/fixture1/address').read_text().s"
    "trip().replace(':',''))\nip0=socket.inet_"
    "aton('192.0.2.1');vip=socket.inet_aton('"
    "192.0.2.42')\ndef "
    "arp(op,srcmac,srcip,dstmac,dstip):\n "
    "return struct.pack('!HHBBH',1,0x0800,6,4"
    ",op)+srcmac+srcip+dstmac+dstip\nrequest=b"
    "'\\xff'*6+mac1+b'\\x08\\x06'+arp(1,mac1,ip0"
    ",b'\\0'*6,vip)\nb.send(request);data=a.rec"
    "v(2048);assert data[20:22]==b'\\0\\1' and "
    "data[38:42]==vip\nreply=mac1+mac0+b'\\x08\\"
    "x06'+arp(2,mac0,vip,mac1,ip0)\na.send(rep"
    "ly);data=b.recv(2048);assert "
    "data[20:22]==b'\\0\\2' and "
    "data[28:32]==vip\n# IPv6 raw ICMP sockets "
    "and solicited-node multicast membership, "
    "as used by "
    "ndp.\ni0=socket.if_nametoindex('fixture0'"
    ");i1=socket.if_nametoindex('fixture1')\ns"
    "=socket.socket(socket.AF_INET6,socket.SO"
    "CK_RAW,socket.IPPROTO_ICMPV6)\nr=socket.s"
    "ocket(socket.AF_INET6,socket.SOCK_RAW,so"
    "cket.IPPROTO_ICMPV6)\ns.bind(('fe80::1',0"
    ",0,i0));r.bind(('fe80::2',0,0,i1));s.set"
    "timeout(3);r.settimeout(3)\ns.setsockopt("
    "socket.IPPROTO_IPV6,socket.IPV6_MULTICAS"
    "T_IF,i0)\ns.setsockopt(socket.IPPROTO_IPV"
    "6,socket.IPV6_MULTICAST_HOPS,255)\ns.sets"
    "ockopt(socket.IPPROTO_IPV6,socket.IPV6_U"
    "NICAST_HOPS,255)\ngroup=socket.inet_pton("
    "socket.AF_INET6,'ff02::1:ff00:42')+struc"
    "t.pack('@I',i0)\ns.setsockopt(socket.IPPR"
    "OTO_IPV6,socket.IPV6_JOIN_GROUP,group)\nv"
    "ip6=socket.inet_pton(socket.AF_INET6,'fd"
    "00::42')\n# Neighbor advertisement "
    "containing a synthetic VIP and target "
    "link-layer "
    "option.\nmessage=struct.pack('!BBHI',136,"
    "0,0,0x20000000)+vip6+bytes([2,1])+mac0\ns"
    ".sendto(message,('fe80::2',0,0,i0))\nfor "
    "_ in range(20):\n "
    "data,addr=r.recvfrom(2048)\n if "
    "data[0]==136 and "
    "data[8:24]==vip6:break\nelse:raise "
    "AssertionError('No IPv6 neighbor "
    "advertisement "
    "received')\ns.setsockopt(socket.IPPROTO_I"
    "PV6,socket.IPV6_LEAVE_GROUP,group)\n# "
    "High listeners used by memberlist and "
    "HTTPS metrics need no bind "
    "capability.\nfor port in [7946,9120]:\n "
    "with socket.socket() as listener: "
    "listener.bind(('127.0.0.1',port));listen"
    "er.listen(1)\nprint('PASS: UID/GID 1000, "
    "group-readable config, root-only "
    "negative, NET_RAW-only ARP/NDP, "
    "multicast join/leave, high listeners, "
    "NNP/seccomp, no NET_ADMIN')\n"
)


def run(*args, check=True):
    """Run the probe command and fail when its expected execution does not succeed."""
    result = run_command(["podman", *args], capture_output=True, text=True, timeout=90, check=False)
    if check:
        if not result.returncode == 0:
            raise AssertionError(result.stdout[-2500:] + result.stderr[-2500:])
        return result.stdout.strip()
    return result


def check_speaker(speaker, succeeds):
    """Require both network responders or the exact expected projected-file denial."""
    for _ in range(30):
        logs = run("logs", speaker)
        if (
            "created NDP responder for interface" in logs
            if succeeds
            else "permission denied" in logs
        ):
            break
        time.sleep(0.1)
    if succeeds:
        if not (
            "created ARP responder for interface" in logs
            and "created NDP responder for interface" in logs
        ):
            raise AssertionError(logs[-3000:])
        if not (
            "failed to create ARP responder" not in logs
            and "failed to create NDP responder" not in logs
        ):
            raise AssertionError
    else:
        if "excludel2.yaml: permission denied" not in logs:
            raise AssertionError(logs[-3000:])


def main():
    """Isolated non-root speaker prerequisites: no LAN interfaces, VIPs or secrets."""
    holder = None
    speakers = []
    with tempfile.TemporaryDirectory(prefix="speaker-nonroot-") as directory:
        directory = Path(directory)
        directory.chmod(0o755)
        (directory / "probe.py").write_text(PROBE)
        (directory / "kubeconfig").write_text(
            (
                "apiVersion: v1\nkind: Config\nclusters:\n- "
                "name: fixture\n  cluster:\n    server: "
                "http://127.0.0.1:18080\ncontexts:\n- name: "
                "fixture\n  context:\n    cluster: fixture\n "
                "   user: fixture\ncurrent-context: "
                "fixture\nusers:\n- name: fixture\n  user: "
                "{}\n"
            )
        )
        for name, mode in [("group-readable.yaml", 0o440), ("root-only.yaml", 0o400)]:
            path = directory / name
            path.write_text("announcedInterfacesToExclude: []\n")
            path.chmod(mode)
            run_command(
                ["podman", "unshare", "chown", "0:1000" if mode == 0o440 else "0:0", str(path)],
                check=True,
            )
        try:
            holder = run(
                "run",
                "-d",
                "--network=none",
                "--cap-drop=ALL",
                "--cap-add=NET_ADMIN",
                "--security-opt=no-new-privileges",
                "--entrypoint=/bin/sh",
                IMAGE,
                "-ec",
                "ip link set lo up; ip link add fixture0 type veth peer name fixture1; "
                "ip link set fixture0 up; ip link set fixture1 up; "
                "ip addr add fe80::1/64 dev fixture0 nodad; "
                "ip addr add fe80::2/64 dev fixture1 nodad; sleep 300",
            )
            for _ in range(20):
                if (
                    run("exec", holder, "ip", "link", "show", "fixture1", check=False).returncode
                    == 0
                ):
                    break
                time.sleep(0.1)
            args = [
                "run",
                "--rm",
                "--network=container:" + holder,
                "--user=1000:1000",
                "--read-only",
                "--cap-drop=ALL",
                "--cap-add=NET_RAW",
                "--security-opt=no-new-privileges",
                "-v",
                str(directory) + ":/fixture:ro,z",
            ]
            print(run(*args, "--entrypoint=python3", IMAGE, "/fixture/probe.py"))
            run(*args, "--entrypoint=/speaker", SPEAKER, "--help")
            print("PASS: pinned speaker CLI starts non-root with NET_RAW only and read-only root")
            # The real speaker reads the projected-mode fixture and opens its own
            # ARP/NDP responders. Kubernetes is deliberately unreachable (loopback
            # API): this proves pre-API initialization, not cache sync/readiness.
            # Hold API discovery open long enough for the interface-scan goroutine;
            # a refused connection can terminate main before it finishes scanning.
            api = run(
                "run",
                "-d",
                "--network=container:" + holder,
                "--user=1000:1000",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--entrypoint=python3",
                IMAGE,
                "-c",
                (
                    "from http.server import "
                    "BaseHTTPRequestHandler,ThreadingHTTPServ"
                    "er; import time\nclass "
                    "H(BaseHTTPRequestHandler):\n def "
                    "do_GET(self): time.sleep(30); "
                    "self.send_error(503)\n def "
                    "log_message(self,*a): "
                    'pass\nThreadingHTTPServer(("127.0.0.1",18'
                    "080),H).serve_forever()"
                ),
            )
            speakers.append(api)
            time.sleep(0.3)
            for config, succeeds in [("group-readable.yaml", True), ("root-only.yaml", False)]:
                speaker = run(
                    "run",
                    "-d",
                    "--network=container:" + holder,
                    "--user=1000:1000",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--cap-add=NET_RAW",
                    "--security-opt=no-new-privileges",
                    "-v",
                    str(directory) + ":/fixture:ro,z",
                    "-v",
                    str(directory / config) + ":/etc/metallb/excludel2.yaml:ro,z",
                    "-e",
                    "KUBECONFIG=/fixture/kubeconfig",
                    "--entrypoint=/speaker",
                    SPEAKER,
                    "--namespace=fixture",
                    "--node-name=fixture",
                    "--pod-name=fixture",
                    "--ml-bindaddr=127.0.0.1",
                    "--log-level=debug",
                )
                speakers.append(speaker)
                check_speaker(speaker, succeeds)
                run("rm", "-f", speaker)
                speakers.remove(speaker)
            print(
                (
                    "PASS: real speaker reads group-owned "
                    "config and creates ARP/NDP responders; "
                    "root-only config is rejected"
                )
            )
            negative = run(
                "run",
                "--rm",
                "--network=container:" + holder,
                "--user=1000:1000",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--entrypoint=python3",
                IMAGE,
                "-c",
                (
                    "import socket; "
                    "socket.socket(socket.AF_PACKET,socket.SO"
                    "CK_RAW,socket.htons(0x0806))"
                ),
                check=False,
            )
            if not (negative.returncode != 0 and "PermissionError" in negative.stderr):
                raise AssertionError("NET_RAW negative control failed")
            print("PASS: dropping NET_RAW prevents ARP raw socket creation")
        finally:
            for speaker in speakers:
                run("rm", "-f", speaker)
            if holder:
                run("rm", "-f", holder)
            # Restore rootless-user ownership before tempfile cleanup.
            run_command(["podman", "unshare", "chown", "-R", "0:0", str(directory)], check=True)


if __name__ == "__main__":
    main()
