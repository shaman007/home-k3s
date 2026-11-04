#!/usr/bin/env python3
"""Disposable probes for reviewed images; no devices, production mounts or API writes."""
import subprocess
import time


def run(*args):
    p=subprocess.run(['podman',*args],capture_output=True,text=True,timeout=120)
    assert p.returncode==0,p.stderr[-2000:]
    return p.stdout.strip()


def base(user):
    return ['run','--rm','--network=none','--user='+user,'--cap-drop=ALL','--security-opt=no-new-privileges']


def main():
    run(*base('1000:1000'),'--entrypoint=gpu-operator','nvcr.io/nvidia/gpu-operator:v26.7.2','--help')
    run(*base('1000:1000'),'--entrypoint=longhorn-manager','docker.io/longhornio/longhorn-manager:v1.13.0','deploy-driver','--help')
    run(*base('1000:1000'),'--entrypoint=/statuscleaner','quay.io/metallb/frr-k8s:v0.0.25','--help')
    status="cat /proc/1/status | grep -E '^(Uid|Gid|CapEff|CapBnd|NoNewPrivs|Seccomp):'"
    outputs=[]
    outputs.append(run(*base('0:0'),'--tmpfs=/etc/frr_reloader:mode=0755','--tmpfs=/etc/frr_metrics:mode=0755','--tmpfs=/etc/frr_status:mode=0755','--entrypoint=/bin/sh','quay.io/metallb/frr-k8s:v0.0.25','-ec','cp -f /frr-reloader.sh /etc/frr_reloader/; cp -f /frr-metrics /etc/frr_metrics/; cp -f /frr-status /etc/frr_status/; test -x /etc/frr_reloader/frr-reloader.sh; test -x /etc/frr_metrics/frr-metrics; test -x /etc/frr_status/frr-status; '+status))
    outputs.append(run(*base('100:101'),'--tmpfs=/etc/frr:mode=0777','--tmpfs=/tmp/frr:mode=0777','--entrypoint=/bin/sh','quay.io/frrouting/frr:10.4.3','-ec','printf "fixture\\n" > /tmp/frr/daemons; cp -rLf /tmp/frr/* /etc/frr/; test "$(cat /etc/frr/daemons)" = fixture; '+status))
    mock=None
    try:
        mock=run('run','-d','--network=none','--user=65534:65534','--cap-drop=ALL','--security-opt=no-new-privileges','harbor.andreybondarenko.com/dockerhub/python:3.13-slim','python3','-c','from http.server import BaseHTTPRequestHandler,HTTPServer\nclass H(BaseHTTPRequestHandler):\n def do_GET(self): self.send_response(200);self.end_headers()\n def log_message(self,*args): pass\nHTTPServer(("127.0.0.1",9500),H).serve_forever()')
        time.sleep(1)
        outputs.append(run('run','--rm','--network=container:'+mock,'--user=1000:1000','--cap-drop=ALL','--security-opt=no-new-privileges','--entrypoint=sh','docker.io/longhornio/longhorn-manager:v1.13.0','-ec','for i in 1 2 3 4 5; do test "$(curl -m 1 -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9500/v1)" != 200 || break; sleep 1; done; test "$(curl -m 1 -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9500/v1)" = 200; '+status))
    finally:
        if mock:run('rm','-f',mock)
    for output in outputs:
        for expected in ['CapEff:\t0000000000000000','CapBnd:\t0000000000000000','NoNewPrivs:\t1','Seccomp:\t2']:
            assert expected in output,output
    print('PASS: three controller CLI startups, four real copy helpers and non-root curl/HTTP wait; capability/NNP/seccomp checks passed')


if __name__=='__main__':main()
