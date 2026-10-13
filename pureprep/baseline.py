"""Baselines de referência para calibrar o benchmark (sem LLM).

- ``oracle``: devolve o próprio gabarito (teto; valida o avaliador → F1 = 1).
- ``naive`` : toda frase da entrada com modal/expressão de necessidade vira
  requisito; classe por pistas lexicais; cita a própria frase como fonte.

Uso:
    python -m pureprep.baseline --pairs output/pairs/notes --kind naive --out preds/naive/notes
"""

import argparse
import json
import re
from pathlib import Path

from .extract import keyword_hint
from .textsim import modal_strength, split_sentences

_NEED = re.compile(r"\b(need|needs|want|wants|would like|I'd like|important that|ought to|supposed to|able to)\b", re.I)
_SPEAKER = re.compile(r"^[A-Za-z]+:\s*")


def naive(text):
    preds = []
    for line in text.splitlines():
        line = _SPEAKER.sub("", line.strip().lstrip("- "))
        for s in split_sentences(line):
            if modal_strength(s) or _NEED.search(s):
                hint = keyword_hint(s)
                preds.append({"text": s, "class": "NFR" if hint else "FR", "subtype": hint, "source_text": s})
    return preds


def oracle(gt):
    return [{"text": r["text"], "class": r["class"], "subtype": r.get("subtype")} for r in gt["requirements"]]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--kind", choices=("naive", "oracle"), default="naive")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for d in sorted(Path(args.pairs).iterdir()):
        gt = json.loads((d / "ground_truth_requirements.json").read_text(encoding="utf-8"))
        preds = oracle(gt) if args.kind == "oracle" else naive((d / "input_raw.txt").read_text(encoding="utf-8"))
        (out / f"{d.name}.json").write_text(json.dumps({"requirements": preds}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
