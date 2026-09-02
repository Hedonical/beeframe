#!/usr/bin/env bash
set -euo pipefail

destination="${1:-site}"
shinylive_bin="${BEEFRAME_SHINYLIVE:-shinylive}"

case "$destination" in
  ""|"."|".."|"/")
    echo "Unsafe destination: $destination" >&2
    exit 1
    ;;
esac

destination_parent="$(dirname "$destination")"
destination_name="$(basename "$destination")"
mkdir -p "$destination_parent"
destination_parent="$(cd "$destination_parent" && pwd -P)"
destination="$destination_parent/$destination_name"

if [[ "$destination" == "$(pwd -P)" ]]; then
  echo "Refusing to replace the project directory." >&2
  exit 1
fi

staging="$(mktemp -d)"
staging_site="$(mktemp -d "$destination_parent/.${destination_name}.build.XXXXXX")"
rmdir "$staging_site"
backup=""

cleanup() {
  rm -rf "$staging"
  [[ ! -e "$staging_site" ]] || rm -rf "$staging_site"
  if [[ -n "$backup" && -e "$backup" && ! -e "$destination" ]]; then
    mv "$backup" "$destination"
  fi
}
trap cleanup EXIT

cp app.py requirements.txt "$staging/"
cp -R beeframe www "$staging/"
"$shinylive_bin" export "$staging" "$staging_site" --template-dir template --template-params '{"title":"Beeframe"}'
cp www/google-sheets-parent.js privacy.html "$staging_site/"
touch "$staging_site/.beeframe-build"

if [[ -e "$destination" ]]; then
  if [[ ! -d "$destination" || ! -f "$destination/app.json" ]]; then
    echo "Refusing to replace a destination that is not a generated Shinylive site: $destination" >&2
    exit 1
  fi
  backup="$destination.previous.$$"
  mv "$destination" "$backup"
fi

mv "$staging_site" "$destination"
if [[ -n "$backup" ]]; then
  rm -rf "$backup"
  backup=""
fi
