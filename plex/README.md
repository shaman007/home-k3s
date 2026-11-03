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

`python3 tools/security/test-plex-capability-guards.py` passed offline image
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

## Follow-up: forwarded discovery and further capability reduction

After the LAN-subnet correction, a real LAN GDM request through the GPU node
192.168.30.242 returned HTTP/1.0 200 OK. The advertised w386 endpoint still
timed out. Cilium observed its request being dropped by policy with translated
source `10.42.0.196`, destination `10.42.2.163:32414/UDP`. CiliumNode metadata
confirms `10.42.0.196` is w386's CiliumInternalIP. The prepared correction admits
only this exact /32 source on the existing six UDP discovery ports. No TCP
permissions, Service, NodePorts or advertised endpoint change. SNAT hides the
original client's source, so this rule trusts UDP forwarded by w386. Recheck
this address if Cilium node IPAM is reset, and repeat LAN discovery through
192.168.30.209 after publication.

The next prepared capability set removes AUDIT_WRITE and NET_BIND_SERVICE,
retaining eight capabilities. Plex has no configured port below 1024; UDP
discovery sockets do not need either removed capability. The updated offline
probe passed startup, software MJPEG transcoding and preference persistence
through restart, with bounding set `0x400fb`, no-new-privileges and seccomp.
GPU runtime/resources and all UDP ports remain unchanged. Verify real playback,
NVENC and LAN discovery again after rollout; no capability exception was added.
