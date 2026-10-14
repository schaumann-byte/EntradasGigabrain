"""Valida os rótulos automáticos contra o ReqFromSRS (REQINONE, 2025).

O ReqFromSRS tem 200 requisitos (100 F + 100 NFR com subtipos PROMISE)
extraídos manualmente de 22 SRS do PURE, mas SEM indicar o documento de
origem. Aqui cada item é localizado nos 18 XMLs por cobertura lexical e, se
coincidir com um item do nosso gabarito, as classes são comparadas.

Uso:
    python -m pureprep.crosscheck --csv data/external/reqinone/reqFromSRS.csv --out output/crosscheck_reqfromsrs.json
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from .extract import extract
from .parse import load_document
from .taxonomy import NFR_SUBTYPES
from .textsim import containment, normalize_ws, split_sentences, token_set

PROMISE_TO_BINARY = {"F": "FR"}  # todo o resto é NFR


def run(csv_path, xml_dir, doc_threshold=0.8, req_threshold=0.6):
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8", errors="replace")))
    docs = []
    for f in sorted(Path(xml_dir).glob("*.xml")):
        doc = load_document(f)
        ext = extract(doc)
        sents = []
        for sec in doc.sections:
            for b in sec.blocks:
                sents.extend(split_sentences(b.text))
        docs.append((doc, ext, [token_set(s) for s in sents]))

    results = []
    for row in rows:
        text = normalize_ws(row["Requirement"])
        tok = token_set(text)
        gold_cls = PROMISE_TO_BINARY.get(row["class"].strip(), "NFR")
        best = (0.0, None)
        for doc, ext, stoks in docs:
            # cobertura por janela de até 4 frases consecutivas do documento
            for i in range(len(stoks)):
                acc = frozenset()
                for w in range(4):
                    if i + w >= len(stoks):
                        break
                    acc = acc | stoks[i + w]
                    sc = containment(tok, acc)
                    if sc > best[0]:
                        best = (sc, (doc, ext))
        rec = {"text": text[:200], "reqfromsrs_class": row["class"].strip(), "binary": gold_cls,
               "doc_id": None, "doc_score": round(best[0], 3), "in_our_gt": False}
        if best[0] >= doc_threshold:
            doc, ext = best[1]
            rec["doc_id"] = doc.doc_id
            cand = max(ext.requirements, key=lambda r: max(containment(r.tokens, tok), containment(tok, r.tokens)), default=None)
            if cand is not None:
                sc = max(containment(cand.tokens, tok), containment(tok, cand.tokens))
                if sc >= req_threshold:
                    rec.update(in_our_gt=True, our_id=cand.rid, our_class=cand.cls, our_subtype=cand.subtype,
                               our_tier=cand.tier, our_label_source=cand.label_source, match_score=round(sc, 3),
                               agree=cand.cls == gold_cls)
        results.append(rec)

    found = [r for r in results if r["doc_id"]]
    in_gt = [r for r in found if r["in_our_gt"]]
    agree = [r for r in in_gt if r["agree"]]
    conf = Counter((r["binary"], r["our_class"]) for r in in_gt)
    nfr_both = [r for r in in_gt if r["binary"] == "NFR" and r["our_class"] == "NFR"]
    sub_ok = [r for r in nfr_both if NFR_SUBTYPES.get(r["our_subtype"], (None, None))[1] == r["reqfromsrs_class"]]
    sub_conf = Counter((r["reqfromsrs_class"], r["our_subtype"]) for r in nfr_both)
    summary = {
        "n_reqfromsrs": len(results),
        "found_in_18_xml_docs": len(found),
        "docs_matched": dict(Counter(r["doc_id"] for r in found)),
        "found_in_our_ground_truth": len(in_gt),
        "coverage_of_found": round(len(in_gt) / max(1, len(found)), 3),
        "class_agreement": round(len(agree) / max(1, len(in_gt)), 3),
        "confusion_gold_vs_ours": {f"{g}->{o}": n for (g, o), n in sorted(conf.items())},
        "nfr_subtype_agreement_promise": round(len(sub_ok) / max(1, len(nfr_both)), 3),
        "nfr_subtype_confusion": {f"{g}->{o}": n for (g, o), n in sorted(sub_conf.items(), key=str)},
        "agreement_by_label_source": {
            src: round(sum(r["agree"] for r in in_gt if r["our_label_source"] == src)
                       / max(1, sum(1 for r in in_gt if r["our_label_source"] == src)), 3)
            for src in sorted({r["our_label_source"] for r in in_gt})
        },
    }
    return summary, results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="data/external/reqinone/reqFromSRS.csv")
    ap.add_argument("--xml-dir", default="data/raw/requirements-xml/XMLZIPFile")
    ap.add_argument("--out", default="output/crosscheck_reqfromsrs.json")
    args = ap.parse_args(argv)
    summary, results = run(args.csv, args.xml_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    Path(args.out).write_text(json.dumps({"summary": summary, "items": results}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
