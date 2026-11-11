# Plex connectivity

The `plex` Service keeps NodePort `32355` forwarding to TCP `32400`, with
`externalTrafficPolicy` left at its default (`Cluster`). The advertised LAN
endpoint is `http://192.168.30.209:32355/`; that IP belongs to node `w386`.
The backend can run on its existing GPU node because NodePort forwards across
nodes. HTTPS remains `https://plex.andreybondarenko.com:443/`, using Traefik
and the Service's TCP `32400` port.

The deprecated Service `externalIPs` entry is unnecessary for these two
endpoints and has been removed. The existing Service ports, protocols,
selector, and advertised addresses are preserved. Do not allocate
`192.168.30.209` to MetalLB: it is a node address.

Before this repository change, both advertised endpoints returned HTTP 200
for `/identity`. Direct access to `192.168.30.209:32400` failed that check;
it is not an advertised endpoint. Verify the NodePort and HTTPS endpoints
again after deployment, along with playback and any discovery clients in use.

## Capability reduction and GPU checks (2026-11-03)

The prepared container guard drops ALL capabilities and re-adds the ten existing
defaults CHOWN, DAC_OVERRIDE, FOWNER, FSETID, KILL, SETGID, SETUID,
NET_BIND_SERVICE, SYS_CHROOT and AUDIT_WRITE. It removes NET_RAW, MKNOD, SETFCAP
and SETPCAP conservatively; it does not claim this is the minimum possible set.
Root startup and UID/GID 1000 media handling remain intact. No new Kyverno
exception is added, so the strict capability finding remains visible.

NVIDIA runtime, GPU resource allocation, driver capabilities and all existing
TCP/UDP ports are unchanged. Normal UDP discovery uses datagram sockets, which
do not require NET_RAW. The live service has UDP sockets on 1900, 32410, 32412,
32413 and 32414; existing Plex application processes run as UID/GID 1000 with
zero effective capabilities. Port 5353 is declared but was not listening in the
pre-change snapshot.

`python3 tools/security/test_plex_capability_guards.py` passed offline image
startup, HTTP identity, FFV1-to-MJPEG software transcoding as UID 1000, and restart
against persisted test preferences through the repository's real init hook.
It checks the proposed bounding set, no-new-privileges and seccomp. The test
mounts no production configuration/media, claims no account and has no network.

A separate diagnostic in the live GPU Pod dropped the same four capabilities
for one subprocess, switched it to UID/GID 1000 and successfully encoded a
one-second synthetic 640x360 video with h264_nvenc to a null output. It used no
production media or credentials and did not alter the running service. This
checks GPU encoding under the proposed bounding set, not a production rollout.
After publication, verify replacement readiness, HTTP identity, real client
playback/hardware transcoding and cross-LAN UDP discovery.

Revision `44d89045` rolled out with the proposed capability set, Ready and zero
restarts. HTTPS identity and a live synthetic NVENC encoding passed. A loopback
GDM UDP discovery request returned HTTP/1.0 200 OK; ports 1900 and
32410/32412/32413/32414 remain bound. External UDP NodePort requests from
192.168.30.79 timed out. The existing LAN policies only cover 192.168.1.0/24,
omitting the actual 192.168.30.0/24 node/client network. The next prepared fix
adds that subnet to the existing LAN ingress and discovery egress rules, keeping
their existing port restrictions. No Service or NodePort is changed. Repeat the
external UDP test after publication; multicast traversal across LANs is not
established by a successful unicast GDM response.

Other GPU applications were checked separately: Immich server completed synthetic
NVENC encoding; Immich ML completed ONNX CUDA inference with CPU fallback
disabled; NLLB completed a CUDA tensor calculation. Both Ollama Pods expose the
RTX 4070 Ti, but no model was loaded during the check, so generation was not
exercised. ComfyUI is explicitly configured with `--cpu` and no GPU allocation;
this is its existing manifest configuration, not a consequence of these guards.

## UDP discovery entry point

Use the GPU node `talos-d4h-k5m` (`192.168.30.242`) for UDP discovery. Keep
w386's `http://192.168.30.209:32355/` TCP endpoint and public HTTPS unchanged.
The Service now pins its existing UDP NodePorts, without reallocating any ports:

| Function | Container UDP port | GPU-node UDP NodePort |
| --- | --- | --- |
| DLNA/SSDP | 1900 | 30524 |
| mDNS (declared, not currently listening) | 5353 | 30670 |
| GDM | 32410 | 30726 |
| GDM | 32412 | 31606 |
| GDM | 32413 | 30265 |
| GDM server discovery | 32414 | 32521 |

A real unicast GDM request from the LAN to `192.168.30.242:32521` returned
HTTP/1.0 200 OK after revision `dc9532e9`. This does not establish automatic
multicast discovery across LAN segments; real client discovery/playback remains
a separate check. The other declared UDP ports were not protocol-tested here.

The request through w386 was dropped with source `10.42.0.196` and security
identity `world-ipv4`, including after the exact /32 allowance was published.
[Cilium documents that tunneled north/south traffic uses the world identity](https://docs.cilium.io/en/stable/security/policy/caveats/),
and [CIDR rules normally exclude managed node addresses](https://docs.cilium.io/en/stable/security/policy/layer3/#ip-cidr-based).
The ineffective /32 rule is removed. As explicitly chosen, preserve the existing
LAN-only rules rather than adding a world-identity UDP allowance or changing
cluster-wide routing. No new policy exception, public CIDR or UDP port is added.

## Further capability reduction

Revision `dc9532e9` removes AUDIT_WRITE and NET_BIND_SERVICE, retaining eight
capabilities. Plex has no configured port below 1024; its main media processes
run as UID 1000 with zero effective capabilities. GPU allocation/runtime and
all UDP ports remain intact.

The next prepared guard also removes SYS_CHROOT, retaining seven capabilities.
The offline startup, UID 1000 software MJPEG transcode and persistent-preference
restart probe passed with bounding set `0xfb`, no-new-privileges and seccomp.
Verify replacement readiness, NVENC, playback and GPU-node LAN discovery after
this new guard is published.
