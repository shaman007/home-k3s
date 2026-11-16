#!/usr/bin/env bash
set -Eeuo pipefail

# Keep scanner selection fixed and reports inside the mounted checkout.
case "$CODACY_TOOL" in
  bandit|opengrep|shellcheck|pylintpython3|prospector|remark-lint) ;;
  *) echo 'Unsupported Codacy scanner' >&2; exit 2 ;;
esac
[[ "$CODACY_OUTPUT" == "results-${CODACY_TOOL}.sarif" ]]
: "${GITHUB_WORKSPACE:?}"
commit_sha="$(/usr/bin/git rev-parse --verify HEAD)"
scan_container="codacy-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-${CODACY_TOOL}"
cleanup() {
  docker rm --force "$scan_container" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# The upstream shell wrapper drops host JVM settings. Pass them explicitly to
# the Java 8 CLI container so valid non-ASCII source can be read for SARIF hashes.
docker run --rm --name "$scan_container" \
  --env JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8 \
  --env LANG=C.UTF-8 \
  --env LC_ALL=C.UTF-8 \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume "$GITHUB_WORKSPACE:$GITHUB_WORKSPACE" \
  --volume /tmp:/tmp \
  codacy/codacy-analysis-cli:7.9.25@sha256:339e0103e28804f9d76aff34503e505440e5d5b42f5dd70dae73b592ea87826a -- \
  analyze \
  --skip-commit-uuid-validation \
  --commit-uuid "$commit_sha" \
  --directory "$GITHUB_WORKSPACE" \
  --tool "$CODACY_TOOL" \
  --tool-timeout 20minutes \
  --fail-if-incomplete \
  --format sarif \
  --output "$GITHUB_WORKSPACE/$CODACY_OUTPUT" \
  --gh-code-scanning-compat \
  --max-allowed-issues 2147483647
