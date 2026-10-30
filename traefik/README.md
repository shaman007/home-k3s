
Private console OIDC, CrowdSec observation and the opt-in Mastodon media-cache
pilot are documented in [the rollout guide](../docs/traefik-security-plugins.md).

The `traefik-network-policy` Argo application also includes the
`block-external-env-probes` IngressRoute. On `websecure`, it sends requests for
`.env`, `.env.*`, and nested `.env` files to `noop@internal`, except for clients
in `192.168.1.0/24`. Its matchers use Traefik v3 syntax. Repository tests check
the application render and representative allowed and blocked requests;
live request verification is required after deployment.
