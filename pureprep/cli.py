"""Gera os pares de teste a partir dos XMLs do PURE.

Uso:
    python -m pureprep.cli --xml-dir data/raw/requirements-xml/XMLZIPFile --out output

Saída:
    output/pairs/<modo>/<doc_id>/input_raw.txt
    output/pairs/<modo>/<doc_id>/ground_truth_requirements.json
    output/audit/section_roles/<doc_id>.json   (papel atribuído a cada seção)
    output/manifest.json                       (estatísticas e tiers por documento)
    output/summary.csv
"""

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .extract import extract
from .parse import load_document
from .synth import build_context, build_dialogue, build_notes, sample_reqs, support

MODES = ("context", "notes", "dialogue")
SCHEMA_VERSION = "1.0"


def tier_context(n_primary, n_fr, n_nfr, ctx_words, reach):
    """Adequação do documento para o modo ``context`` (entrada real)."""
    if n_primary >= 20 and n_fr >= 3 and n_nfr >= 3 and ctx_words >= 300 and reach >= 0.25:
        return "A"
    if n_primary >= 10 and ctx_words >= 150 and reach >= 0.10:
        return "B"
    return "C"


def tier_synthetic(n_primary, n_fr, n_nfr, label_quality):
    """Adequação para ``notes``/``dialogue`` (entrada sintetizada do gabarito)."""
    if n_primary >= 20 and n_fr >= 5 and n_nfr >= 5 and label_quality >= 0.7:
        return "A"
    if n_primary >= 10:
        return "B"
    return "C"


def _gt_payload(doc, mode, reqs, sup, input_text, segments, params, tau):
    items = []
    for r in reqs:
        score, sids = sup.get(r.rid, (0.0, []))
        j = r.to_json()
        j["trace"] = {"input_segments": sids, "support_score": score, "reachable": score >= tau}
        items.append(j)
    cls = Counter((r.tier, r.cls) for r in reqs)
    reach = [i for i in items if i["trace"]["reachable"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "doc_id": doc.doc_id,
        "doc_title": doc.title,
        "source_file": f"PURE/requirements-xml/{doc.source_file}",
        "mode": mode,
        "generator": {"tool": "pureprep", "version": __version__, "params": params},
        "input": {
            "file": "input_raw.txt",
            "n_chars": len(input_text),
            "n_words": len(input_text.split()),
            "segments": [s.to_json() for s in segments],
        },
        "stats": {
            "n_requirements": len(items),
            "n_primary_fr": cls[("primary", "FR")],
            "n_primary_nfr": cls[("primary", "NFR")],
            "n_secondary": cls[("secondary", "FR")] + cls[("secondary", "NFR")],
            "n_reachable": len(reach),
            "reachable_ratio_primary": round(
                sum(1 for i in reach if i["tier"] == "primary") / max(1, sum(1 for i in items if i["tier"] == "primary")), 3
            ),
            "support_threshold": tau,
        },
        "requirements": items,
    }


def _write_pair(out, mode, doc, text, payload):
    d = out / "pairs" / mode / doc.doc_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "input_raw.txt").write_text(text, encoding="utf-8")
    (d / "ground_truth_requirements.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def process(xml_path, out, seed, tau, dialogue_cap, noise):
    doc = load_document(xml_path)
    ext = extract(doc)
    primary = [r for r in ext.requirements if r.tier == "primary"]
    n_fr = sum(r.cls == "FR" for r in primary)
    n_nfr = len(primary) - n_fr
    label_quality = round(sum(r.label_source in ("section", "section+keyword", "ipo-structure") for r in primary) / max(1, len(primary)), 3)

    (out / "audit" / "section_roles").mkdir(parents=True, exist_ok=True)
    (out / "audit" / "section_roles" / f"{doc.doc_id}.json").write_text(
        json.dumps(ext.section_roles, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    row = {
        "doc_id": doc.doc_id,
        "source_file": doc.source_file,
        "n_primary": len(primary),
        "n_primary_fr": n_fr,
        "n_primary_nfr": n_nfr,
        "n_secondary": len(ext.requirements) - len(primary),
        "n_explicit_req_tags": sum(r.element == "req" for r in primary),
        "duplicates_removed": ext.duplicates_removed,
        "label_quality": label_quality,
    }

    # --- context ----------------------------------------------------------
    text, segs = build_context(doc, ext)
    sup = support(ext.requirements, text, segs)
    params = {"seed": seed, "support_threshold": tau, "support_window": 3}
    payload = _gt_payload(doc, "context", ext.requirements, sup, text, segs, params, tau)
    _write_pair(out, "context", doc, text, payload)
    ctx_words = sum(len(u.text.split()) for u in ext.context)
    reach = payload["stats"]["reachable_ratio_primary"]
    row.update(context_words=ctx_words, context_reachable_primary=reach,
               tier_context=tier_context(len(primary), n_fr, n_nfr, ctx_words, reach))

    # --- notes ------------------------------------------------------------
    rng = random.Random(f"{seed}:{doc.doc_id}:notes")
    text, segs = build_notes(doc, ext, primary, rng)
    sup = support(primary, text, segs)
    payload = _gt_payload(doc, "notes", primary, sup, text, segs, {"seed": seed, "merge_prob": 0.15}, tau)
    _write_pair(out, "notes", doc, text, payload)
    row["notes_words"] = payload["input"]["n_words"]
    row["notes_reachable"] = payload["stats"]["reachable_ratio_primary"]

    # --- dialogue ---------------------------------------------------------
    rng = random.Random(f"{seed}:{doc.doc_id}:dialogue")
    chosen = sample_reqs(primary, dialogue_cap, rng)
    text, segs = build_dialogue(doc, ext, chosen, rng, noise=noise)
    sup = support(chosen, text, segs)
    payload = _gt_payload(doc, "dialogue", chosen, sup, text, segs,
                          {"seed": seed, "noise_rate": noise, "max_requirements": dialogue_cap}, tau)
    _write_pair(out, "dialogue", doc, text, payload)
    row["dialogue_words"] = payload["input"]["n_words"]
    row["dialogue_n_requirements"] = len(chosen)
    row["dialogue_reachable"] = payload["stats"]["reachable_ratio_primary"]
    row["tier_synthetic"] = tier_synthetic(len(primary), n_fr, n_nfr, label_quality)
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml-dir", default="data/raw/requirements-xml/XMLZIPFile")
    ap.add_argument("--out", default="output")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--support-threshold", type=float, default=0.6,
                    help="cobertura mínima de tokens para considerar um requisito rastreável na entrada")
    ap.add_argument("--dialogue-cap", type=int, default=60,
                    help="máximo de requisitos por transcrição (≈ 1 h de reunião)")
    ap.add_argument("--noise", type=float, default=0.08, help="taxa de ruído de fala no modo dialogue")
    args = ap.parse_args(argv)

    out = Path(args.out)
    files = sorted(Path(args.xml_dir).glob("*.xml"))
    if not files:
        sys.exit(f"Nenhum XML encontrado em {args.xml_dir}")
    rows = []
    for f in files:
        row = process(f, out, args.seed, args.support_threshold, args.dialogue_cap, args.noise)
        rows.append(row)
        print(f"{row['doc_id']:24s} primary={row['n_primary']:4d} (FR {row['n_primary_fr']}, NFR {row['n_primary_nfr']}) "
              f"ctx_reach={row['context_reachable_primary']:.2f} tier_ctx={row['tier_context']} tier_syn={row['tier_synthetic']}")

    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generator": {"tool": "pureprep", "version": __version__, "args": vars(args)},
        "dataset": {"name": "PURE", "doi": "10.5281/zenodo.1414117", "subset": "requirements-xml (18 docs)"},
        "documents": rows,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(rows)} documentos -> {out.resolve()}")


if __name__ == "__main__":
    main()
