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
