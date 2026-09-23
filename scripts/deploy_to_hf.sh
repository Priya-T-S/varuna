#!/usr/bin/env bash
# Publish the backend to a Hugging Face Space.
#
# Why a separate branch: a Space repo rejects files over 10 MB unless they are
# tracked with Git LFS, and rainfall_model_v1.pkl is 28 MB. This script rebuilds
# an orphan `space` branch whose first commit stores the model files as LFS
# objects, and prepends the YAML front matter a Space needs in its README.
#
# Usage (Git Bash, from the repo root):
#   scripts/deploy_to_hf.sh <hf-username> [space-name] [--dry-run]
#
# Re-run it after any change on main to redeploy.
set -euo pipefail

USER_NAME="${1:-}"
SPACE_NAME="${2:-varuna-backend}"
DRY_RUN="${3:-}"
[ "${SPACE_NAME}" = "--dry-run" ] && { DRY_RUN="--dry-run"; SPACE_NAME="varuna-backend"; }

if [ -z "${USER_NAME}" ]; then
  echo "usage: scripts/deploy_to_hf.sh <hf-username> [space-name] [--dry-run]" >&2
  exit 2
fi

command -v git-lfs >/dev/null 2>&1 || { echo "git-lfs is required: https://git-lfs.com" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "Commit or stash your changes first." >&2; exit 1; }

SOURCE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
REMOTE_URL="https://huggingface.co/spaces/${USER_NAME}/${SPACE_NAME}"
cleanup() { git checkout -q "${SOURCE_BRANCH}"; }
trap cleanup EXIT

echo "==> Rebuilding the 'space' branch from ${SOURCE_BRANCH}"
git branch -D space >/dev/null 2>&1 || true
git checkout -q --orphan space

# Track the model weights with LFS *before* staging, so they are stored as
# pointers and the 10 MB limit never applies.
cat > .gitattributes <<'ATTRS'
*.pkl filter=lfs diff=lfs merge=lfs -text
*.pt  filter=lfs diff=lfs merge=lfs -text
ATTRS

# A Space reads its configuration from this front matter.
python - "${SPACE_NAME}" <<'PY'
import sys
name = sys.argv[1]
body = open("README.md", encoding="utf-8").read()
front = (
    "---\n"
    f"title: {name}\n"
    "emoji: 🌧️\n"
    "colorFrom: blue\n"
    "colorTo: indigo\n"
    "sdk: docker\n"
    "app_port: 7860\n"
    "pinned: false\n"
    "short_description: Explainable extreme-rainfall early warning API\n"
    "---\n\n"
)
open("README.md", "w", encoding="utf-8").write(front + body)
PY

git add -A
# `git checkout --orphan` carries the index over, so the model files are still
# staged as plain blobs; re-staging them runs the LFS clean filter.
git add --renormalize .
git commit -q -m "Deploy VARUNA AI backend to Hugging Face Spaces"

# Fail loudly rather than pushing something a Space will reject.
BIG="$(git ls-tree -r -l HEAD | awk '$4 > 10485760 {print $5}')"
if [ -n "${BIG}" ]; then
  echo "These files exceed the 10 MB Space limit and are not LFS-tracked:" >&2
  echo "${BIG}" | sed 's/^/    /' >&2
  exit 1
fi

echo "==> Model files stored via LFS:"
git lfs ls-files | sed 's/^/    /'

if [ "${DRY_RUN}" = "--dry-run" ]; then
  echo "==> Dry run: branch 'space' built, nothing pushed."
  exit 0
fi

git remote remove hf >/dev/null 2>&1 || true
git remote add hf "${REMOTE_URL}"
echo "==> Pushing to ${REMOTE_URL}"
echo "    Username: ${USER_NAME}   Password: a write token from https://huggingface.co/settings/tokens"
git push -f hf space:main

echo
echo "Done. Build logs: ${REMOTE_URL}  (first build takes ~10 min)"
echo "Health check:    https://${USER_NAME}-${SPACE_NAME}.hf.space/api/v1/health"
