"""Avalia a saída do sistema multiagente contra o gabarito gerado.

Formato esperado da predição (um JSON por documento, ``<pred_dir>/<doc_id>.json``)::

    {"requirements": [
        {"text": "The system shall ...", "class": "FR",
         "subtype": "PE",                 # opcional (RNF)
         "source_text": "trecho citado"}  # opcional (Trace to Source)
    ]}

(uma lista pura de requisitos também é aceita)

Métricas:
- Extração: pareamento 1-1 guloso por similaridade lexical (F1 de tokens de
  conteúdo ≥ ``--match``). Precisão contra TODO o gabarito (primário +
  secundário); revocação contra os primários (``recall_all``) e contra os
  primários rastreáveis na entrada (``recall_reachable``, a métrica justa
  no modo ``context``).
- Classificação FR/NFR nos pares casados (P/R/F1 por classe, macro-F1) e
  extração+classificação estrita (``strict_*``).
- Trace to Source: ``grounding_rate`` (o trecho citado existe na entrada) e
  ``trace_accuracy`` (o trecho citado cobre o segmento de origem do gabarito).
- ``unsupported_rate``: predições cujo conteúdo não tem suporte na entrada
  (proxy de alucinação), independentemente do gabarito.

Gabaritos schema 2.0 (modo ``meetings``) usam as métricas de
:mod:`pureprep.evaluate_meetings` (distratores, issues, recall por status).

Uso:
    python -m pureprep.evaluate --pairs output/pairs/context --pred preds/context [--out report.json]
    python -m pureprep.evaluate --pairs output/pairs/meetings/rules-realistic --pred preds/rules-realistic
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import evaluate_meetings as evm
from .textsim import containment, overlap_f1, token_set


def _prf(tp, n_pred, n_gold):
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 4), round(r, 4), round(f, 4)


def _load_pred(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["requirements"] if isinstance(data, dict) else data


def _windows(text, segments, size=3):
    toks = [token_set(text[s["start"] : s["end"]]) for s in segments]
    for i in range(len(segments)):
        acc = frozenset()
        for w in range(size):
            if i + w >= len(segments):
                break
            acc = acc | toks[i + w]
            yield [s["id"] for s in segments[i : i + w + 1]], acc


def _best_window(tokens, wins):
    best, ids = 0.0, []
    for sids, acc in wins:
        sc = containment(tokens, acc)
        if sc > best:
            best, ids = sc, sids
    return best, ids


def match(preds, gold, threshold):
    """Pareamento 1-1 guloso pelo maior score. Retorna [(i_pred, j_gold, score)]."""
    ptok = [token_set(p.get("text", "")) for p in preds]
    cands = []
    for i, pt in enumerate(ptok):
        for j, g in enumerate(gold):
            sc = overlap_f1(g["_tok"], pt)
            if sc >= threshold:
                cands.append((sc, i, j))
    cands.sort(reverse=True)
    used_p, used_g, pairs = set(), set(), []
    for sc, i, j in cands:
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        pairs.append((i, j, sc))
    return pairs


def evaluate_doc(gt, input_text, preds, threshold=0.5, grounding=0.8, unsupported=0.5):
    gold = gt["requirements"]
    for g in gold:
        g["_tok"] = token_set(g["text"])
    pairs = match(preds, gold, threshold)
    primary = [j for j, g in enumerate(gold) if g["tier"] == "primary"]
    reachable = [j for j in primary if gold[j]["trace"]["reachable"]]
    matched_g = {j for _, j, _ in pairs}

    c = Counter()
    c["n_pred"] = len(preds)
    c["n_gold_all"] = len(gold)
    c["n_gold_primary"] = len(primary)
    c["n_gold_reachable"] = len(reachable)
    c["tp_pred"] = len(pairs)
    c["tp_primary"] = len(matched_g & set(primary))
    c["tp_reachable"] = len(matched_g & set(reachable))

    for i, j, _ in pairs:
        pc = (preds[i].get("class") or "").upper()
        gc = gold[j]["class"]
        c[f"cls_gold_{gc}"] += 1
        c[f"cls_pred_{pc}"] += 1
        if pc == gc:
            c[f"cls_tp_{gc}"] += 1
            if gold[j]["tier"] == "primary":
                c["strict_tp_primary"] += 1
            if gold[j]["tier"] == "primary" and gold[j]["trace"]["reachable"]:
                c["strict_tp_reachable"] += 1
            c["strict_tp_pred"] += 1
            if gc == "NFR" and gold[j].get("subtype") and preds[i].get("subtype"):
                c["subtype_n"] += 1
                sub_ok = preds[i]["subtype"].upper() in {gold[j]["subtype"], gold[j].get("promise_subtype") or ""}
                c["subtype_tp"] += int(sub_ok)

    wins = list(_windows(input_text, gt["input"]["segments"]))
    pair_by_pred = {i: j for i, j, _ in pairs}
    for i, p in enumerate(preds):
        score, _ = _best_window(token_set(p.get("text", "")), wins)
        c["unsupported"] += int(score < unsupported)
        src = p.get("source_text")
        if src:
            c["with_source"] += 1
            gscore, gids = _best_window(token_set(src), wins)
            grounded = gscore >= grounding
            c["grounded"] += int(grounded)
            if i in pair_by_pred:
                gold_ids = set(gold[pair_by_pred[i]]["trace"]["input_segments"])
                if gold_ids:
                    c["trace_n"] += 1
                    c["trace_ok"] += int(grounded and bool(gold_ids & set(gids)))
    return c


def summarize(c):
    # Precisão conta casamentos com qualquer item do gabarito (primário ou
    # secundário); revocação conta só os primários.
    p = round(c["tp_pred"] / c["n_pred"], 4) if c["n_pred"] else 0.0
    r_all = round(c["tp_primary"] / c["n_gold_primary"], 4) if c["n_gold_primary"] else 0.0
    f_all = round(2 * p * r_all / (p + r_all), 4) if p + r_all else 0.0
    r_reach = round(c["tp_reachable"] / c["n_gold_reachable"], 4) if c["n_gold_reachable"] else 0.0
    f_reach = round(2 * p * r_reach / (p + r_reach), 4) if p + r_reach else 0.0
    sp = round(c["strict_tp_pred"] / c["n_pred"], 4) if c["n_pred"] else 0.0
    sr = round(c["strict_tp_reachable"] / c["n_gold_reachable"], 4) if c["n_gold_reachable"] else 0.0
    out = {
        "extraction": {"precision": p, "recall_all": r_all, "f1_all": f_all, "recall_reachable": r_reach, "f1_reachable": f_reach},
        "strict_extraction_classification": {"precision": sp, "recall_reachable": sr,
                                             "f1_reachable": round(2 * sp * sr / (sp + sr), 4) if sp + sr else 0.0},
        "classification_on_matched": {},
        "trace_to_source": {
            "predictions_with_source": c["with_source"],
            "grounding_rate": round(c["grounded"] / c["with_source"], 4) if c["with_source"] else None,
            "trace_accuracy": round(c["trace_ok"] / c["trace_n"], 4) if c["trace_n"] else None,
        },
        "unsupported_rate": round(c["unsupported"] / c["n_pred"], 4) if c["n_pred"] else None,
        "nfr_subtype_accuracy": round(c["subtype_tp"] / c["subtype_n"], 4) if c["subtype_n"] else None,
        "counts": dict(c),
    }
    f1s = []
    for cls in ("FR", "NFR"):
        cp, cr, cf = _prf(c[f"cls_tp_{cls}"], c[f"cls_pred_{cls}"], c[f"cls_gold_{cls}"])
        out["classification_on_matched"][cls] = {"precision": cp, "recall": cr, "f1": cf}
        f1s.append(cf)
    out["classification_on_matched"]["macro_f1"] = round(sum(f1s) / 2, 4)
    return out


def evaluate_dir(pairs_dir, pred_dir, threshold=0.5):
    """Avalia um diretório de pares. Gabaritos schema 2.0 (modo ``meetings``)
    são despachados para :mod:`pureprep.evaluate_meetings`."""
    total = Counter()
    per_doc = {}
    schema = "1"
    for d in sorted(Path(pairs_dir).iterdir()):
        gt_path = d / "ground_truth_requirements.json"
        pred_path = Path(pred_dir) / f"{d.name}.json"
        if not gt_path.exists() or not pred_path.exists():
            continue
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        if str(gt.get("schema_version", "1")).startswith("2"):
            schema = "2"
            raw = json.loads(pred_path.read_text(encoding="utf-8"))
            preds, issues = (raw.get("requirements", []), raw.get("issues", [])) if isinstance(raw, dict) else (raw, [])
            c = evm.evaluate_doc(gt, evm.load_texts(d, gt), preds, issues, threshold)
            per_doc[d.name] = evm.summarize(c)
        else:
            text = (d / "input_raw.txt").read_text(encoding="utf-8")
            c = evaluate_doc(gt, text, _load_pred(pred_path), threshold)
            per_doc[d.name] = summarize(c)
        total.update(c)
    if not per_doc:
        return None
    keys = ("precision", "recall_expected", "f1_expected") if schema == "2" else \
        ("precision", "recall_all", "f1_all", "recall_reachable", "f1_reachable")
    macro = {k: round(sum(v["extraction"][k] for v in per_doc.values()) / len(per_doc), 4) for k in keys}
    micro = evm.summarize(total) if schema == "2" else summarize(total)
    return {"schema": schema, "micro": micro, "macro_extraction": macro, "n_docs": len(per_doc), "per_doc": per_doc,
            "params": {"match_threshold": threshold}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", required=True, help="diretório output/pairs/<modo>")
    ap.add_argument("--pred", required=True, help="diretório com <doc_id>.json de predições")
    ap.add_argument("--match", type=float, default=0.5, help="limiar de similaridade para casar predição e gabarito")
    ap.add_argument("--out", help="salva o relatório completo em JSON")
    args = ap.parse_args(argv)
    rep = evaluate_dir(args.pairs, args.pred, args.match)
    if rep is None:
        sys.exit("Nenhum par (gabarito, predição) encontrado.")
    m = rep["micro"]
    print(json.dumps({k: m[k] for k in m if k != "counts"}, indent=2))
    print("macro (extração):", rep["macro_extraction"])
    if args.out:
        Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
