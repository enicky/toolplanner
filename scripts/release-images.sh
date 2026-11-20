#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

usage() {
  printf 'Usage: %s initial|patch|minor|major\n' "$0"
  printf '  initial: tag the current Helm appVersion (only before the first version tag)\n'
  printf '  patch/minor/major: increment the latest vMAJOR.MINOR.PATCH tag\n'
}

if [[ "$#" -ne 1 ]]; then
  usage >&2
  exit 2
fi

bump_type="$1"
case "$bump_type" in
  initial|patch|minor|major) ;;
  *)
    usage >&2
    exit 2
    ;;
esac

if [[ "$(git branch --show-current)" != "main" ]]; then
  printf 'Error: run this script from the main branch.\n' >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  printf 'Error: commit or remove all tracked and untracked changes before releasing.\n' >&2
  exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  printf 'Error: the origin remote is not configured.\n' >&2
  exit 1
fi

printf 'Fetching main and release tags from origin...\n'
git fetch origin --tags

if ! git rev-parse --verify --quiet origin/main >/dev/null; then
  printf 'Error: origin/main was not found after fetching origin.\n' >&2
  exit 1
fi

head_sha="$(git rev-parse HEAD)"
origin_main_sha="$(git rev-parse origin/main)"
if [[ "$head_sha" != "$origin_main_sha" ]]; then
  printf 'Error: local main is not at origin/main. Pull the latest main and retry.\n' >&2
  printf 'Local:  %s\nRemote: %s\n' "$head_sha" "$origin_main_sha" >&2
  exit 1
fi

latest_tag=""
while IFS= read -r candidate; do
  if [[ "$candidate" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    latest_tag="$candidate"
    break
  fi
done < <(git tag --list 'v*' --sort=-version:refname)

if [[ "$bump_type" == "initial" ]]; then
  if [[ -n "$latest_tag" ]]; then
    printf 'Error: %s already exists; use patch, minor, or major.\n' "$latest_tag" >&2
    exit 1
  fi
  version="$(sed -nE 's/^appVersion: "([^"]+)"$/\1/p' deploy/helm/tool-planner/Chart.yaml)"
  if [[ ! "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
    printf 'Error: Chart.yaml appVersion must be a quoted MAJOR.MINOR.PATCH value.\n' >&2
    exit 1
  fi
else
  if [[ -z "$latest_tag" ]]; then
    printf 'Error: no version tag exists; use "initial" to tag the current Helm appVersion first.\n' >&2
    exit 1
  fi

  IFS=. read -r major minor patch <<< "${latest_tag#v}"
  case "$bump_type" in
    major)
      major=$((major + 1))
      minor=0
      patch=0
      ;;
    minor)
      minor=$((minor + 1))
      patch=0
      ;;
    patch)
      patch=$((patch + 1))
      ;;
  esac
  version="${major}.${minor}.${patch}"
fi

new_tag="v${version}"
if git show-ref --verify --quiet "refs/tags/$new_tag"; then
  printf 'Error: tag %s already exists locally or on origin.\n' "$new_tag" >&2
  exit 1
fi

printf '\nRelease tag: %s\nCommit:      %s\n' "$new_tag" "$head_sha"
printf 'This will push the tag to origin and trigger the ARM64 GHCR image build.\n'
read -r -p 'Continue? [y/N] ' confirmation
case "$confirmation" in
  y|Y|yes|YES) ;;
  *)
    printf 'Cancelled; no tag was created.\n'
    exit 0
    ;;
esac

git tag -a "$new_tag" -m "Release $new_tag" "$head_sha"
if ! git push origin "refs/tags/$new_tag"; then
  printf 'Error: pushing %s failed. The local tag remains; after resolving the error, run: git push origin %s\n' \
    "$new_tag" "$new_tag" >&2
  exit 1
fi

printf 'Pushed %s. GitHub Actions will build and publish the API and web images to GHCR.\n' "$new_tag"
