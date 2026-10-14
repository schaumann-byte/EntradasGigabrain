#!/usr/bin/env bash
# Pipeline completo: dados → pares de teste → baselines → validações.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8

python scripts/download_data.py
python -m pureprep.cli --xml-dir data/raw/requirements-xml/XMLZIPFile --out output

mkdir -p output/baselines
for mode in context notes dialogue; do
  for kind in oracle naive; do
    python -m pureprep.baseline --pairs "output/pairs/$mode" --kind "$kind" --out "output/baselines/preds/$kind/$mode"
    python -m pureprep.evaluate --pairs "output/pairs/$mode" --pred "output/baselines/preds/$kind/$mode" \
      --out "output/baselines/eval_${kind}_${mode}.json" > /dev/null
  done
done
for variant in output/pairs/meetings/*/; do
  v=$(basename "$variant")
  for kind in oracle naive; do
    python -m pureprep.baseline --pairs "$variant" --kind "$kind" --out "output/baselines/preds/$kind/meetings/$v"
    python -m pureprep.evaluate --pairs "$variant" --pred "output/baselines/preds/$kind/meetings/$v"       --out "output/baselines/eval_${kind}_meetings_${v}.json" > /dev/null
  done
done

python -m pureprep.crosscheck --out output/crosscheck_reqfromsrs.json > /dev/null
python -m pureprep.scan_originals --out output/originals_scan.csv
python -m pytest -q
