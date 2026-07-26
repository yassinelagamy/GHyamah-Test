#!/usr/bin/env bash
set -euo pipefail

# Deployment adapter for the GitHub Actions workflow.
#
# Ghaymah publicly documents `gy resource app launch` for deploying a
# local Dockerfile/.ghaymah.json project. It does not currently document a
# non-interactive API-token login command. The current binary exposes
# email/password login flags and a generic `app update` command, but its public
# help does not identify an external-image field. This adapter therefore
# validates and prints the exact deployment handoff, then fails deliberately
# instead of reporting a deployment that did not happen.

app=""
image=""

usage() {
  echo "Usage: $0 --app <application-name> --image <registry/image:tag>" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      app="$2"
      shift 2
      ;;
    --image)
      [[ $# -ge 2 ]] || { usage; exit 64; }
      image="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 64
      ;;
  esac
done

[[ -n "$app" && -n "$image" ]] || { usage; exit 64; }

echo "Ghaymah deployment handoff"
echo "  Application: $app"
echo "  Image URL:   $image"
echo
echo "Update the target application's container image URL to the immutable tag"
echo "shown above in the Ghaymah dashboard, then validate its health endpoint."
echo
echo "Automated deployment is intentionally blocked because the public CLI docs"
echo "do not specify API-token authentication or the external-image field for"
echo "'gy resource app update'. Replace this adapter only with confirmed syntax."

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "### Ghaymah deployment requires confirmed integration"
    echo
    echo "- Application: \`$app\`"
    echo "- Image: \`$image\`"
    echo
    echo "The image was built and pushed, but no deployment was claimed. Confirm"
    echo "the supported API/CLI command or update this image URL in the dashboard."
  } >> "$GITHUB_STEP_SUMMARY"
fi

exit 78
