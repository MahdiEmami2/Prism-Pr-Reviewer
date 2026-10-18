#!/usr/bin/env bash
# Regenerate the committed example artefacts for the demonstration project.
#
# Usage: bash samples/sample_project/generate_diff.sh
#
# The script works on a throwaway copy so the sample project itself is never modified and no
# repository in your working tree is disturbed. It produces:
#
#   examples/sample_diff.patch    the diff PRISM analyses
#   examples/sample_report.md     the Markdown report of a real PRISM run
#   examples/sample_report.json   the JSON report of the same run
#
# The diff represents a pull request that first introduces the sample project, which is why
# the sample's own test file is part of it (so the "no test change" heuristic stays quiet).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${here}/../.." && pwd)"
workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

cd "${workdir}"
git init -q .
git config user.email "sample@example.invalid"
git config user.name "PRISM sample"
printf 'baseline\n' > .gitkeep
git add .gitkeep
git commit -qm "baseline"

mkdir -p samples/sample_project
cp -R "${here}/." samples/sample_project/
rm -f samples/sample_project/.gitkeep
git add -A
git diff --cached > "${repo_root}/examples/sample_diff.patch"

cd "${repo_root}"
python3 samples/sample_project/make_reports.py

echo "diff     -> examples/sample_diff.patch"
echo "markdown -> examples/sample_report.md"
echo "json     -> examples/sample_report.json"
