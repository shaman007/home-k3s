# Traefik QUIC / HTTP/3

HTTP/3 is configured on the TLS `websecure` entrypoint using UDP/443.
The chart exposes TCP/443 and UDP/443 in one Service at the existing MetalLB
VIP, `192.168.1.210`. The public entrypoint NetworkPolicy permits both protocols.
The authoritative Helm values are in `argocd/application-traefik.yaml`;
`traefik/values.yaml` carries the matching standalone configuration.

For Internet access, forward WAN **UDP/443** to **192.168.1.210:443** on the
router, alongside the existing TCP/443 forward. TCP forwarding alone does not
carry QUIC. Any intervening firewall must also permit UDP/443.

After deploying the Traefik and traefik-network-policy Argo CD applications,
verify a real HTTP/3 response directly against the VIP:

```sh
curl --http3-only --noproxy '*' --max-time 15 \
  --resolve andreybondarenko.com:443:192.168.1.210 \
  --output /dev/null --silent --show-error \
  --write-out 'HTTP %{http_version} status %{http_code}\n' \
  https://andreybondarenko.com/
```

Expect HTTP version `3`. Repeat from outside the LAN without `--resolve` to
verify public DNS, forwarding, and firewall traversal. Check ordinary HTTPS
still works with `--http2`. An `Alt-Svc` header alone does not prove UDP
connectivity; `--http3-only` prevents a TCP fallback from hiding a failure.

Traefik uses one replica and the `Recreate` update strategy, so deploying the
entrypoint change causes a brief interruption while the pod restarts.
