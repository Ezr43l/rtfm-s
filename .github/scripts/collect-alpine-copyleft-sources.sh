#!/usr/bin/env bash
set -euo pipefail

BUILDER_IMAGE="python:3.12-alpine@sha256:d09d15e60962ca365d1cd544a48773bac9d33f2fb1b00f2aa0deec78ade7dc31"
BUILDER_PLATFORM="linux/amd64"
PLATFORMS=("linux/amd64" "linux/arm64")

die() {
  printf 'copyleft source gate: %s\n' "$*" >&2
  exit 1
}

validate_output_name() {
  [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid output filename: $1"
}

docker_host_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s\n' "$1"
  fi
}

docker_cli() {
  MSYS_NO_PATHCONV=1 docker "$@"
}

worker() {
  local manifest="$1" image_metadata="$2" output_dir="$3" output_name="$4"
  local bundle=/work/bundle aports=/work/aports checksums=/work/bundle-SHA256SUMS
  local platforms origin commit packages versions licenses path matches count recipe_root package_dir dist_dir index=0
  local alpine_release alpine_branch distfiles_mirror
  local -a commits=()

  test -s "$manifest" || die "empty package manifest"
  validate_output_name "$output_name"
  mkdir -p "$bundle/aports" "$bundle/distfiles" "$bundle/metadata" "$aports"
  cp "$manifest" "$bundle/metadata/alpine-copyleft-packages.tsv"
  cp "$image_metadata" "$bundle/metadata/image.txt"
  alpine_release="$(sed -n 's/^alpine_release=//p' "$image_metadata")"
  [[ "$alpine_release" =~ ^([0-9]+\.[0-9]+)\.[0-9]+$ ]] || die "invalid Alpine release metadata"
  alpine_branch="${BASH_REMATCH[1]}"
  distfiles_mirror="https://distfiles.alpinelinux.org/distfiles/v${alpine_branch}"

  git -C "$aports" init --quiet
  while IFS=$'\t' read -r platforms origin commit packages versions licenses; do
    [[ "$platforms" =~ ^linux/(amd64|arm64)(,linux/(amd64|arm64))?$ ]] || \
      die "invalid platform set for $origin"
    [[ "$origin" =~ ^[a-zA-Z0-9+._-]+$ ]] || die "invalid APK origin: $origin"
    [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || die "invalid aports commit for $origin"
  done < "$manifest"
  mapfile -t commits < <(cut -f3 "$manifest" | sort -u)
  test "${#commits[@]}" -gt 0 || die "manifest has no aports commits"
  local fetched=false remote
  for remote in \
      https://github.com/alpinelinux/aports.git \
      https://gitlab.alpinelinux.org/alpine/aports.git; do
    if git -C "$aports" remote get-url origin >/dev/null 2>&1; then
      git -C "$aports" remote set-url origin "$remote"
    else
      git -C "$aports" remote add origin "$remote"
    fi
    if git -C "$aports" -c maintenance.auto=false -c gc.auto=0 \
        fetch --quiet --depth=1 origin "${commits[@]}"; then
      fetched=true
      break
    fi
  done
  test "$fetched" = true || die "unable to fetch the required aports commits"

  while IFS=$'\t' read -r platforms origin commit packages versions licenses; do
    index=$((index + 1))
    matches="$(git -C "$aports" ls-tree -r --name-only "$commit" | \
      awk -F/ -v origin="$origin" 'NF == 3 && $2 == origin && $3 == "APKBUILD" { print }')"
    count="$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')"
    test "$count" = "1" || die "$origin@$commit resolves to $count APKBUILD paths"
    path="$matches"
    recipe_root="$bundle/aports/$(printf '%03d' "$index")-${origin}-${commit}"
    mkdir -p "$recipe_root"
    git -C "$aports" archive --format=tar "$commit" "${path%/APKBUILD}" | \
      tar -xf - -C "$recipe_root"
    package_dir="$recipe_root/${path%/APKBUILD}"
    dist_dir="$bundle/distfiles/$(printf '%03d' "$index")-${origin}-${commit}"
    mkdir -p "$dist_dir"
    (
      cd "$package_dir"
      DISTFILES_MIRROR="$distfiles_mirror" SRCDEST="$dist_dir" abuild fetch
      DISTFILES_MIRROR="$distfiles_mirror" SRCDEST="$dist_dir" abuild verify
    )
    {
      printf 'platforms=%s\norigin=%s\ncommit=%s\npackages=%s\nversions=%s\nlicenses=%s\nrecipe=%s\n' \
        "$platforms" "$origin" "$commit" "$packages" "$versions" "$licenses" "${path%/APKBUILD}"
    } > "$bundle/metadata/$(printf '%03d' "$index")-${origin}.txt"
    test -n "$(find "$dist_dir" -type f -print -quit)" || \
      die "$origin did not yield corresponding source files"
  done < "$manifest"

  {
    printf '%s\n' 'ALPINE COPYLEFT CORRESPONDING SOURCE BUNDLE'
    printf '%s\n' ''
    printf '%s\n' 'This archive accompanies the exact OCI image identified in metadata/image.txt.'
    printf '%s\n' 'It contains each exact Alpine APKBUILD recipe, local patch and fetched distfile'
    printf '%s\n' 'for every installed package whose APK metadata declares a reciprocal source license.'
    printf '%s\n' 'Both linux/amd64 and linux/arm64 release variants are represented.'
    printf '%s\n' 'Each distfile was checked by abuild verify against the checksum in its recipe.'
    printf '%s\n' 'The package-to-source mapping is metadata/alpine-copyleft-packages.tsv.'
  } > "$bundle/README.txt"
  (
    cd "$bundle"
    find . -type f -print0 | sort -z | xargs -0 sha256sum > "$checksums"
  )
  mv "$checksums" "$bundle/SHA256SUMS"
  mkdir -p "$output_dir"
  tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    --format=posix --pax-option=delete=atime,delete=ctime -C "$bundle" -cf - . | \
    gzip -n -9 > "$output_dir/$output_name"
  test -s "$output_dir/$output_name" || die "source archive was not created"
  printf 'created %s with %s Alpine source origins\n' "$output_dir/$output_name" "$index"
}

inside() {
  local manifest="$1" image_metadata="$2" output_dir="$3" output_name="$4"
  apk add --no-cache alpine-sdk bash git tar gzip ca-certificates >/dev/null
  test -s "$manifest" || die "missing mounted package manifest"
  test -s "$image_metadata" || die "missing mounted image metadata"
  mkdir -p /work
  adduser -D -h /work/home builder
  addgroup builder abuild
  mkdir -p /work/out "$output_dir"
  chown -R builder:abuild /work
  su -s /bin/bash builder -c \
    "/collector/collect-alpine-copyleft-sources.sh --worker '$manifest' '$image_metadata' /work/out '$output_name'"
  cp "/work/out/$output_name" "$output_dir/"
}

if [ "${1:-}" = "--worker" ]; then
  shift
  test "$#" -eq 4 || die "worker expects manifest, image metadata, output directory and filename"
  worker "$@"
  exit 0
fi

if [ "${1:-}" = "--inside" ]; then
  shift
  test "$#" -eq 4 || die "inside mode expects manifest, image metadata, output directory and filename"
  inside "$@"
  exit 0
fi

manifest_only=false
if [ "${1:-}" = "--manifest-only" ]; then
  manifest_only=true
  shift
fi
test "$#" -eq 2 || die "usage: $0 [--manifest-only] IMAGE OUTPUT"

image="$1"
output="$2"
[[ "$image" != *$'\n'* && "$image" != *$'\r'* && -n "$image" ]] || \
  die "invalid image reference"
test ! -e "$output" || \
  die "refusing to overwrite an existing source artifact"
script_path="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
manifest_script="$(cd "$(dirname "$0")" && pwd)/collect-alpine-copyleft-manifest.py"
test -f "$manifest_script" || die "missing manifest collector: $manifest_script"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/rtfm-copyleft.XXXXXXXX")"
container_ids=()
cleanup() {
  local cleanup_id
  for cleanup_id in "${container_ids[@]}"; do
    docker_cli container rm "$cleanup_id" >/dev/null 2>&1 || true
  done
  case "$tmp" in
    "${TMPDIR:-/tmp}"/rtfm-copyleft.*) rm -rf -- "$tmp" ;;
  esac
}
trap cleanup EXIT

manifest_mounts=(
  -v "$(docker_host_path "$manifest_script"):/collector/collect-alpine-copyleft-manifest.py:ro"
  -v "$(docker_host_path "$tmp"):/output"
)
manifest_inputs=()
first_version=""
first_revision=""
first_source=""
first_alpine_release=""
{
  printf 'image_reference=%s\n' "$image"
  printf 'platforms=linux/amd64,linux/arm64\n'
} > "$tmp/image.txt"
for platform in "${PLATFORMS[@]}"; do
  arch="${platform#*/}"
  platform_image="$image"
  case "$arch" in
    amd64) platform_image="${RTFM_SOURCE_IMAGE_AMD64:-$platform_image}" ;;
    arm64) platform_image="${RTFM_SOURCE_IMAGE_ARM64:-$platform_image}" ;;
    *) die "unsupported platform: $platform" ;;
  esac
  local_architecture="$(docker_cli image inspect "$platform_image" --format '{{.Architecture}}' 2>/dev/null || true)"
  if [ "$local_architecture" != "$arch" ]; then
    docker_cli pull --platform "$platform" "$platform_image" >/dev/null
  fi
  container_id="$(docker_cli create --platform "$platform" "$platform_image")"
  container_ids+=("$container_id")
  docker_cli cp "$container_id:/lib/apk/db/installed" \
    "$(docker_host_path "$tmp/$arch-installed")"
  docker_cli cp "$container_id:/etc/alpine-release" \
    "$(docker_host_path "$tmp/$arch-alpine-release")"
  test -s "$tmp/$arch-installed" || die "$platform image lacks the Alpine installed database"
  test -s "$tmp/$arch-alpine-release" || die "$platform image lacks the Alpine release"
  image_id="$(docker_cli container inspect "$container_id" --format '{{.Image}}')"
  version="$(docker_cli container inspect "$container_id" --format '{{index .Config.Labels "org.opencontainers.image.version"}}')"
  revision="$(docker_cli container inspect "$container_id" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
  source="$(docker_cli container inspect "$container_id" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')"
  alpine_release="$(tr -d ' \r\n' < "$tmp/$arch-alpine-release")"
  [[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || die "invalid image ID for $platform"
  test -n "$version" && test -n "$revision" && test -n "$source" || \
    die "incomplete OCI identity for $platform"
  if [ -z "$first_version" ]; then
    first_version="$version"
    first_revision="$revision"
    first_source="$source"
    first_alpine_release="$alpine_release"
  else
    test "$version" = "$first_version" || die "version differs between release platforms"
    test "$revision" = "$first_revision" || die "revision differs between release platforms"
    test "$source" = "$first_source" || die "source differs between release platforms"
    test "$alpine_release" = "$first_alpine_release" || die "Alpine release differs between platforms"
  fi
  {
    printf '%s_reference=%s\n' "$arch" "$platform_image"
    printf '%s_image_id=%s\n' "$arch" "$image_id"
    printf '%s_alpine_release=%s\n' "$arch" "$alpine_release"
  } >> "$tmp/image.txt"
  manifest_mounts+=(
    -v "$(docker_host_path "$tmp/$arch-installed"):/input/$arch-installed:ro"
  )
  manifest_inputs+=("$platform=/input/$arch-installed")
done
{
  printf 'version=%s\n' "$first_version"
  printf 'revision=%s\n' "$first_revision"
  printf 'source=%s\n' "$first_source"
  printf 'alpine_release=%s\n' "$first_alpine_release"
} >> "$tmp/image.txt"

docker_cli run --rm --platform "$BUILDER_PLATFORM" --entrypoint python \
  "${manifest_mounts[@]}" \
  "$BUILDER_IMAGE" \
  /collector/collect-alpine-copyleft-manifest.py /output/manifest.tsv "${manifest_inputs[@]}"

test -s "$tmp/manifest.tsv" || die "empty copyleft source manifest"
if [ "$manifest_only" = true ]; then
  mkdir -p "$(dirname "$output")"
  cp "$tmp/manifest.tsv" "$output"
  printf 'wrote %s\n' "$output"
  exit 0
fi

mkdir -p "$(dirname "$output")"
output_dir="$(cd "$(dirname "$output")" && pwd)"
output_name="$(basename "$output")"
validate_output_name "$output_name"
docker_cli run --rm --platform "$BUILDER_PLATFORM" --entrypoint sh \
  -v "$(docker_host_path "$script_path"):/collector/collect-alpine-copyleft-sources.sh:ro" \
  -v "$(docker_host_path "$tmp/manifest.tsv"):/input/manifest.tsv:ro" \
  -v "$(docker_host_path "$tmp/image.txt"):/input/image.txt:ro" \
  -v "$(docker_host_path "$output_dir"):/output" \
  "$BUILDER_IMAGE" \
  -c 'apk add --no-cache bash >/dev/null && exec bash /collector/collect-alpine-copyleft-sources.sh "$@"' \
  collector --inside /input/manifest.tsv /input/image.txt /output "$output_name"
test -s "$output" || die "missing output archive"
tar -tzf "$output" >/dev/null
