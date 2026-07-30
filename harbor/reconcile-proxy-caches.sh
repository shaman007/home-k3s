#!/bin/sh
set -eu

: "${HARBOR_USERNAME:?set HARBOR_USERNAME to a Harbor administrator}"
: "${HARBOR_PASSWORD:?set HARBOR_PASSWORD to the Harbor administrator password}"

HARBOR_URL="${HARBOR_URL:-https://harbor.andreybondarenko.com}"
HARBOR_API="${HARBOR_URL%/}/api/v2.0"

command -v curl >/dev/null
command -v jq >/dev/null

api_get() {
  curl --fail --silent --show-error \
    --user "$HARBOR_USERNAME:$HARBOR_PASSWORD" \
    "$HARBOR_API$1"
}

api_post() {
  path="$1"
  payload="$2"
  curl --fail --silent --show-error \
    --user "$HARBOR_USERNAME:$HARBOR_PASSWORD" \
    --header 'Content-Type: application/json' \
    --data "$payload" \
    "$HARBOR_API$path" >/dev/null
}

reconcile_proxy() {
  endpoint_name="$1"
  project_name="$2"
  upstream_url="$3"

  registries="$(api_get '/registries?page_size=100')"
  registry_id="$(printf '%s' "$registries" | jq -r --arg name "$endpoint_name" \
    '.[] | select(.name == $name) | .id' | head -n 1)"

  if [ -z "$registry_id" ]; then
    ping_payload="$(jq -cn --arg url "$upstream_url" \
      '{type:"docker-registry",url:$url,credential_type:"basic",access_key:"",access_secret:"",insecure:false}')"
    api_post '/registries/ping' "$ping_payload"

    registry_payload="$(jq -cn --arg name "$endpoint_name" --arg url "$upstream_url" \
      '{name:$name,url:$url,type:"docker-registry",insecure:false,credential:{type:"basic",access_key:"",access_secret:""}}')"
    api_post '/registries' "$registry_payload"

    registries="$(api_get '/registries?page_size=100')"
    registry_id="$(printf '%s' "$registries" | jq -r --arg name "$endpoint_name" \
      '.[] | select(.name == $name) | .id' | head -n 1)"
    printf 'created registry endpoint %s (%s)\n' "$endpoint_name" "$registry_id"
  else
    actual_url="$(printf '%s' "$registries" | jq -r --arg name "$endpoint_name" \
      '.[] | select(.name == $name) | .url' | head -n 1)"
    if [ "$actual_url" != "$upstream_url" ]; then
      printf 'endpoint %s points to %s, expected %s\n' \
        "$endpoint_name" "$actual_url" "$upstream_url" >&2
      exit 1
    fi
    printf 'registry endpoint %s already exists (%s)\n' "$endpoint_name" "$registry_id"
  fi

  projects="$(api_get '/projects?page_size=100')"
  project_registry_id="$(printf '%s' "$projects" | jq -r --arg name "$project_name" \
    '.[] | select(.name == $name) | .registry_id' | head -n 1)"

  if [ -z "$project_registry_id" ]; then
    project_payload="$(jq -cn --arg name "$project_name" --argjson registry_id "$registry_id" \
      '{project_name:$name,registry_id:$registry_id,metadata:{public:"true"}}')"
    api_post '/projects' "$project_payload"
    printf 'created proxy project %s\n' "$project_name"
  elif [ "$project_registry_id" != "$registry_id" ]; then
    printf 'project %s uses registry %s, expected %s\n' \
      "$project_name" "$project_registry_id" "$registry_id" >&2
    exit 1
  else
    printf 'proxy project %s already exists\n' "$project_name"
  fi
}

reconcile_proxy kubernetes k8s https://registry.k8s.io
reconcile_proxy elastic elastic https://docker.elastic.co
reconcile_proxy nvidia nvidia https://nvcr.io
reconcile_proxy ecr-public ecr https://public.ecr.aws
