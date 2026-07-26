#!/usr/bin/env bash
set -euo pipefail

# Verify that a deployed service is healthy and exposes the expected immutable
# release identifier. This prevents a manually promoted Ghaymah deployment from
# being reported as successful when it is still serving an older image.

app=""
url=""
expected_release=""
attempts="${DEPLOY_CHECK_ATTEMPTS:-30}"
interval_s="${DEPLOY_CHECK_INTERVAL_S:-2}"

usage() {
  echo "Usage: $0 --app <name> --url <base-url> --expected-release <git-sha>" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      app="$2"
      shift 2
      ;;
    --url)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      url="${2%/}"
      shift 2
      ;;
    --expected-release)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      expected_release="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
done

[[ -n "$app" && -n "$url" && -n "$expected_release" ]] || { usage; exit 64; }
[[ "$attempts" =~ ^[1-9][0-9]*$ ]] || { echo "DEPLOY_CHECK_ATTEMPTS must be a positive integer" >&2; exit 64; }
[[ "$interval_s" =~ ^[0-9]+$ ]] || { echo "DEPLOY_CHECK_INTERVAL_S must be a non-negative integer" >&2; exit 64; }

health_url="${url}/health"
echo "Verifying ${app} at ${health_url}"

for ((attempt = 1; attempt <= attempts; attempt++)); do
  body="$(curl --fail --silent --show-error --max-time 5 "$health_url" 2>/dev/null || true)"

  if [[ -n "$body" ]]; then
    status="$(sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' <<<"$body")"
    release="$(sed -n 's/.*"release"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' <<<"$body")"

    if [[ "$status" == "ok" && "$release" == "$expected_release" ]]; then
      echo "Deployment verified: status=ok release=${release}"
      if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        {
          echo "### Deployment verified"
          echo
          echo "- Application: \`${app}\`"
          echo "- URL: ${url}"
          echo "- Release: \`${release}\`"
        } >>"$GITHUB_STEP_SUMMARY"
      fi
      exit 0
    fi

    echo "Attempt ${attempt}/${attempts}: status=${status:-missing}, release=${release:-missing}"
  else
    echo "Attempt ${attempt}/${attempts}: health endpoint unavailable"
  fi

  ((attempt == attempts)) || sleep "$interval_s"
done

echo "Deployment verification failed for ${app}: expected release ${expected_release}" >&2
exit 1
