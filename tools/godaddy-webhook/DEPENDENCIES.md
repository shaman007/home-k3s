# Dependency scan review

## golang.org/x/text v0.42.0: CC-BY-SA findings

Observed in FOSSA on revision `4b18c2f8`, 2026-11-05. FOSSA reports
CC-BY-SA-1.0, CC-BY-SA-2.0, CC-BY-SA-2.5 and CC-BY-SA-3.0 for the module.
The module is an indirect dependency in this project's go.mod.

The upstream root LICENSE is BSD-style. CC-BY-SA references occur in quoted
multilingual test text in:

- `internal/testtext/text.go`
- `cases/map_test.go`
- `unicode/norm/normalize_test.go`

The production Go dependency graph contains 17 x/text packages with 73 ordinary
Go source files. None contains these CC-BY-SA references. `internal/testtext` is
not in that graph, and `_test.go` files are not compiled by `go build`.
The final scratch image copies only the built executable and system CA bundle;
it does not copy the module source tree or these test fixtures.

Recommended FOSSA disposition: review the detected file matches, then scope any
ignore to **this project**, **selected version v0.42.0**, and only these four
license findings. Suggested reason:

> The detected CC-BY-SA material is upstream test fixture text, excluded from the
> godaddy-webhook production dependency graph and final image. The production
> module uses its upstream BSD license. Re-review on dependency upgrades.

No FOSSA ignore rule, organization-wide license policy change, package downgrade
or source deletion was performed by this review. The separate security issue
must be evaluated independently; a license disposition does not clear it.

References:

- [Upstream LICENSE](https://github.com/golang/text/blob/v0.42.0/LICENSE)
- [Upstream test fixture](https://github.com/golang/text/blob/v0.42.0/internal/testtext/text.go)
- [FOSSA guidance on test material and narrow ignore scope](https://docs.fossa.com/docs/issues/ignoring-issues)

Reproduce the production source inventory from this directory with
`go list -deps -json .`; inspect each x/text package's `GoFiles` and `CgoFiles`,
excluding its `TestGoFiles` and `XTestGoFiles`.

## Security dependency update

The vulnerability screenshot identifies `golang.org/x/net v0.60.0` with
CVE-2026-78661 (GO-2026-6860) and CVE-2026-97045 (GO-2026-6866).
The source pins x/net v0.62.0, fixing both. The same audit identified module-only
GO-2026-5932 in the old x/crypto version; it is pinned to the exact official fixed
commit `v0.58.1-0.20261009181718-2f1f834330b2` because the latest stable v0.58.0
still precedes that fix. The solver did not import the vulnerable packages, but
the updated graph now reports no vulnerabilities at all with govulncheck v1.9.0.

Required companion updates are x/text v0.43.0, x/sys v0.49.0, x/term v0.47.0 and
x/sync v0.24.0. The x/text production-source audit was repeated on v0.43.0: its
17 production packages and 73 source files still exclude the CC-BY-SA test
fixtures. Any FOSSA disposition must refer to the version actually scanned:
v0.42.0 in the screenshot, and v0.43.0 after the dependency update is pushed.

- [GO-2026-6860](https://pkg.go.dev/vuln/GO-2026-6860)
- [GO-2026-6866](https://pkg.go.dev/vuln/GO-2026-6866)
- [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932)
