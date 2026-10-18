# Sample project with intentional review problems
#
# This directory is DEMONSTRATION DATA. The problems here are deliberately planted so
# PRISM has something to find. They are not real vulnerabilities in any third-party
# repository, and they are not meant to be copied into production code.
#
# `clean_module.py` contains the corrected variants so you can see which snippets PRISM
# correctly leaves alone.

## Files

| File | Purpose |
| --- | --- |
| `risky_module.py` | Planted problems: mutable defaults, `shell=True`, `eval`, `pickle.loads`, `yaml.load`, `os.system`, `tempfile.mktemp`, MD5, `verify=False`, bare `except`, `except: pass`, dead code after `return`, an assertion used as validation, a hard-coded credential, a PEM header |
| `clean_module.py` | The corrected counterpart of every planted problem: no rule should fire on this file |
| `config/settings.example.py` | Placeholder-only configuration that must NOT be flagged as a hard-coded secret |
| `tests/test_risky_module.py` | A minimal test file, so the "no test change" heuristic has something to compare against |
| `generate_diff.sh` | Regenerates `examples/sample_diff.patch` and re-runs PRISM |

## Reproduce

```bash
cd samples/sample_project
git init -q . && git add . && git commit -qm "baseline"
# plant the change, then:
git diff HEAD > ../../examples/sample_diff.patch
cd ../..
python3 -m prism review-diff --diff-file examples/sample_diff.patch \
    --markdown examples/sample_report.md --json examples/sample_report.json
```

A ready-made diff and the reports PRISM produced from it are committed under `examples/`.
