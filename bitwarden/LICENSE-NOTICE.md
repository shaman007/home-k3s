# Bitwarden image licensing and source

The image referenced by this deployment is a locally rebuilt derivative of
`ghcr.io/bitwarden/lite:2026.7.2` from the upstream
[`bitwarden/server`](https://github.com/bitwarden/server) project.

Upstream uses two licenses:

- GNU Affero General Public License 3.0 for code without a different header.
- Bitwarden License 1.0 for code under the upstream `bitwarden_license`
  directory or otherwise marked with that license.

The corresponding Dockerfile embeds the upstream general notice and both full
license texts in `/usr/share/licenses/bitwarden/`, and publishes OCI source,
version, and license labels. The locally maintained Dockerfile and runtime
scripts are available in the `shaman007/Dockerfiles` repository under
`bitwarden/`.

Redistribution of the image does not grant rights to Bitwarden trademarks. Keep
the embedded notices with every mirrored or rebuilt image, and review upstream
license changes whenever the base-image version changes.
