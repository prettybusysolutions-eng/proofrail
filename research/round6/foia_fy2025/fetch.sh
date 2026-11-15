#!/bin/sh
# Re-download the official FOIA.gov All Agency CSV ZIPs and verify hashes.
# Source page: https://www.foia.gov/foia-dataset-download.html
# (links resolved from /assets/js/foia_dataset_download.bundle.js)
set -eu
dir="${1:-raw}"; mkdir -p "$dir"
for y in 2021 2022 2023 2024 2025; do
  curl -fsS -o "$dir/all_agencies_csv_$y.zip" "https://www.foia.gov/downloads/all_agencies_csv_$y.zip"
done
(cd "$dir" && sha256sum -c ../SHA256SUMS)
