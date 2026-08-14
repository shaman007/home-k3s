# Bitwarden image licensing and source

The deployed image is a locally rebuilt derivative of
`ghcr.io/bitwarden/lite:2026.7.2` from the upstream
[`bitwarden/server`](https://github.com/bitwarden/server) project.

Upstream uses two licenses: GNU Affero General Public License 3.0 for code
without a different header, and Bitwarden License 1.0 for code in the upstream
`bitwarden_license` directory or otherwise marked with that license.

The corresponding Dockerfile embeds the upstream general notice and both full
license texts under `/usr/share/licenses/bitwarden/`, and publishes OCI source,
version, and license labels. Local Dockerfile and runtime-script source is kept
in the `shaman007/Dockerfiles` repository under `bitwarden/`.

Keep these notices with mirrored or rebuilt images and review upstream license
changes whenever the base-image version changes. Redistribution does not grant
rights to Bitwarden trademarks.
