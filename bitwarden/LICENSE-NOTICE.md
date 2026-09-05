# Bitwarden image licensing and source

The deployment uses the upstream `ghcr.io/bitwarden/lite:2026.8.1` image,
pinned by digest, from the [`bitwarden/self-host`](https://github.com/bitwarden/self-host)
project.

Upstream uses two licenses: GNU Affero General Public License 3.0 for code
without a different header, and Bitwarden License 1.0 for code in the upstream
`bitwarden_license` directory or otherwise marked with that license.

The previously maintained `harbor.andreybondarenko.com/library/bitwarden`
derivative is deprecated. Its custom entrypoint and runtime preparation became
unnecessary when upstream added native support for running rootless with a
read-only root filesystem.

Keep these notices with mirrored or rebuilt images and review upstream license
changes whenever the base-image version changes. Redistribution does not grant
rights to Bitwarden trademarks.
