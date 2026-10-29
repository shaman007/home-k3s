# WordPress and Nextcloud static assets

The existing NGINX instances serve static files directly from their application
volumes. This change improves browser reuse and transfer size without adding a
proxy cache or changing PHP, session, DAV, or user-file authorization.

| Application | Asset | Cache-Control |
| --- | --- | --- |
| WordPress | Existing CSS, JS/MJS, fonts and public image files | `public, max-age=3600` |
| WordPress | The same files with nonempty `ver` | `public, max-age=604800` |
| Nextcloud | Existing application assets | Existing six-month lifetime retained |
| Nextcloud | Application assets with nonempty `v` | Existing six-month lifetime plus `immutable` retained |
| Nextcloud | Fonts without `v` | Existing seven-day lifetime retained |
| Nextcloud | Fonts with nonempty `v` | Six-month lifetime with `immutable` |

WordPress version parameters are not necessarily content hashes, so its assets
are not marked immutable. Changes to versioned assets should update their
version parameter. No new caching rule is applied to WordPress PDFs, OVPN
profiles, generic text/XML files, HTML pages, or PHP responses.

Both configurations negotiate gzip for CSS, JavaScript, SVG and, where served,
WebAssembly, with `Vary: Accept-Encoding`, a 1 KiB minimum response size and
compression level 4. Already compressed image and font formats are not added to
the gzip type list. MJS retains an explicit JavaScript MIME type. Nextcloud's
static matcher additionally covers JPEG, WebP and AVIF and its font matcher
covers TTF/OTF/EOT.

`add_header_inherit merge` preserves server security headers in locations that
add Cache-Control; this requires NGINX >= 1.29.3. Both deployed images were
verified as 1.31.8. Previously Nextcloud static responses lost those headers
because their location defined its own `add_header`. Full cache-control maps
also avoid the previous trailing comma on unversioned Nextcloud assets.

Only files that exist are served with static cache headers. Missing assets keep
the existing internal redirect to PHP, where application cache/privacy headers
apply. Nextcloud's earlier deny rules for data/config/lib/hidden paths and its
PHP handler for DAV and other authenticated routes retain precedence.

## Validation and rollout

Before this change, public CSS responses were verified to have no gzip encoding
on either service. WordPress CSS had no explicit cache lifetime. Nextcloud CSS
had `public, max-age=15778463,` and omitted inherited `nosniff` and other security
headers.

Behavior tests use isolated files and a fake FastCGI PHP backend with the full
production NGINX configuration:

```sh
STATIC_NGINX_BINARY=/path/to/nginx \
STATIC_NGINX_SOURCE=/path/to/matching/nginx-source \
  python3 -m unittest tests.test_static_assets_runtime
```

The source directory supplies `conf/mime.types` and `conf/fastcgi_params`.
Seven tests verify lifetimes, security-header inheritance, negotiated gzip and
identical decoded content, ETag/304 revalidation, modern asset types, PHP
fallback privacy and denial of physical Nextcloud private files. They passed
against NGINX 1.31.8.

Commit/push the two ConfigMaps and tests. Argo reconciles `wordpress` and
`nextcloud`; their existing ConfigMap Reloader annotations restart the workloads
so NGINX reads the new configuration. Both apps have a single web replica, so
use the existing rollout behavior and verify recovery before calling the change
live. No workload resource sizes, images, storage, ingress or database settings
are changed.

After reconciliation, require valid TLS and HTTP 200 for known public assets,
expected Cache-Control for versioned and unversioned requests, gzip with Vary,
identical decoded bytes, ETag/304, and retained security headers. Verify a normal
application page, Nextcloud status, DAV authorization and denied data/config
paths. Do not use private user files as test fixtures.

Rollback consists of reverting the ConfigMap changes through GitOps. Existing
browser entries can remain fresh until their cache lifetime expires; a version
parameter change is the normal way to publish replacement assets sooner.
