"""Avaliação do modo ``meetings`` (gabarito schema 2.0).

Predição esperada (``<pred_dir>/<doc_id>.json``)::

    {"requirements": [{"text": "...", "class": "FR", "subtype": null,
                       "source_text": "trecho citado"}],
     "issues": [{"type": "ambiguity|conflict|inconsistency|incompleteness",
                 "requirement_text": "requisito a que o problema se refere",
                 "source_text": "trecho citado", "question": "pergunta ao stakeholder"}]}

Métricas, além das do v1 (extração, classificação, Trace-to-Source,
``unsupported_rate``):

- ``recall_expected``: revocação sobre os requisitos que deveriam sair
  (``expected_in_output``), e ``recall_by_status`` / ``recall_by_phenomenon``.
- ``false_positives``: predições casadas com **distratores** (propostas
  rejeitadas num conflito), com requisitos **rejeitados** (retirados do
  escopo) ou **omitidos** (nunca discutidos), além das sem par.
- ``detail_hallucination_rate``: entre requisitos ambíguos/incompletos
  recuperados, fração em que a predição "inventou" o detalhe removido
  (ex.: o número exato que ninguém disse).
- ``issues``: P/R/F1 da detecção de problemas (tipada e sem tipo).
"""

from collections import Counter

from .textsim import containment, overlap_f1, token_set

ISSUE_ALIASES = {
    "conflict": "conflict", "conflicting": "conflict", "conflict_open": "conflict", "disagreement": "conflict",
    "ambiguity": "ambiguity", "ambiguous": "ambiguity", "vague": "ambiguity", "vagueness": "ambiguity",
    "inconsistency": "inconsistency", "inconsistent": "inconsistency", "contradiction": "inconsistency",
    "incompleteness": "incompleteness", "incomplete": "incompleteness", "missing": "incompleteness",
    "missing_information": "incompleteness", "tbd": "incompleteness",
}


def _windows(texts, gt, size=3):
    for m in gt["input"]["meetings"]:
        text, segs = texts[m["id"]], m["segments"]
        toks = [token_set(text[s["start"] : s["end"]]) for s in segs]
        for i in range(len(segs)):
            acc = frozenset()
            for w in range(size):
                if i + w >= len(segs):
                    break
                acc = acc | toks[i + w]
                yield [s["id"] for s in segs[i : i + w + 1]], acc


def _best(tokens, wins):
    best, ids = 0.0, []
    for sids, acc in wins:
        sc = containment(tokens, acc)
        if sc > best:
            best, ids = sc, sids
    return best, ids


def _match(preds_tok, cands, threshold):
    """1-1 guloso; empate favorece requisitos sobre distratores."""
    pairs = []
    for i, pt in enumerate(preds_tok):
        for j, c in enumerate(cands):
            sc = overlap_f1(c["_tok"], pt)
            if sc >= threshold:
                pairs.append((sc, c["_kind"] == "req", i, j))
    pairs.sort(key=lambda x: (x[0], x[1]), reverse=True)
    used_p, used_c, out = set(), set(), []
    for sc, _, i, j in pairs:
        if i in used_p or j in used_c:
            continue
        used_p.add(i)
        used_c.add(j)
        out.append((i, j, sc))
    return out


def evaluate_doc(gt, texts, preds, pred_issues=(), threshold=0.5, grounding=0.8, unsupported=0.5):
    gold = gt["requirements"]
    cands = [{**g, "_tok": token_set(g["text"]), "_kind": "req"} for g in gold]
    cands += [{**d, "_tok": token_set(d["text"]), "_kind": "distractor"} for d in gt.get("distractors", [])]
    ptok = [token_set(p.get("text", "")) for p in preds]
    pairs = _match(ptok, cands, threshold)
    wins = list(_windows(texts, gt))
    all_input = frozenset().union(*(token_set(t) for t in texts.values()))

    c = Counter()
    c["n_pred"] = len(preds)
    expected = [g for g in gold if g["expected_in_output"]]
    c["n_expected"] = len(expected)
    for g in expected:
        c[f"status_n_{g['status']}"] += 1
        for p in g["phenomena"]:
            c[f"phen_n_{p['type']}:{p['outcome']}"] += 1

    matched = {}
    for i, j, _ in pairs:
        cand = cands[j]
        if cand["_kind"] == "distractor":
            c["fp_distractor"] += 1
            continue
        if not cand["expected_in_output"]:
            c[f"fp_{cand['status']}"] += 1
            continue
        matched[i] = cand
        c["tp"] += 1
        c[f"status_tp_{cand['status']}"] += 1
        for p in cand["phenomena"]:
            c[f"phen_tp_{p['type']}:{p['outcome']}"] += 1
        pc, gc = (preds[i].get("class") or "").upper(), cand["class"]
        c[f"cls_gold_{gc}"] += 1
        c[f"cls_pred_{pc}"] += 1
        if pc == gc:
            c[f"cls_tp_{gc}"] += 1
            c["strict_tp"] += 1
        if cand["status"] in ("ambiguous", "incomplete"):
            p = next(p for p in cand["phenomena"] if p["type"] in ("ambiguity", "incompleteness"))
            removed = p["details"].get("removed") or p["details"].get("missing")
            if removed:
                c["detail_n"] += 1
                detail = token_set(removed) - all_input  # detalhe que não aparece em lugar nenhum da entrada
                c["detail_hallucinated"] += int(bool(detail & ptok[i]))
    c["fp_unmatched"] = len(preds) - len(pairs)

    for i, p in enumerate(preds):
        score, _ = _best(ptok[i], wins)
        c["unsupported"] += int(score < unsupported)
        src = p.get("source_text")
        if src:
            c["with_source"] += 1
            gscore, gids = _best(token_set(src), wins)
            grounded = gscore >= grounding
            c["grounded"] += int(grounded)
            if i in matched:
                gold_ids = set(matched[i]["trace"]["related_segments"])
                if gold_ids:
                    c["trace_n"] += 1
                    c["trace_ok"] += int(grounded and bool(gold_ids & set(gids)))

    # --- issues -------------------------------------------------------------
    gold_issues = gt.get("issues", [])
    req_by_id = {g["id"]: g for g in gold}
    c["issues_gold"] = len(gold_issues)
    c["issues_pred"] = len(pred_issues)
    for gi in gold_issues:
        c[f"issue_n_{gi['type']}"] += 1

    def issue_score(pi, gi):
        best = 0.0
        rt = pi.get("requirement_text")
        if rt:
            g = req_by_id[gi["requirement"]]
            d = gi["details"]
            stated = d.get("stated_text") or d.get("conflicting_text") or d.get("proposed_text") or ""
            best = max(overlap_f1(token_set(g["text"]), token_set(rt)), overlap_f1(token_set(stated), token_set(rt)) if stated else 0.0)
        src = pi.get("source_text")
        if src:
            gscore, gids = _best(token_set(src), wins)
            if gscore >= grounding and set(gids) & set(gi["segments"]):
                best = max(best, 1.0)
        return best

    for typed in (True, False):
        cand_pairs = []
        for a, pi in enumerate(pred_issues):
            ptype = ISSUE_ALIASES.get(str(pi.get("type", "")).lower().strip())
            for b, gi in enumerate(gold_issues):
                if typed and ptype != gi["type"]:
                    continue
                sc = issue_score(pi, gi)
                if sc >= threshold:
                    cand_pairs.append((sc, a, b))
        cand_pairs.sort(reverse=True)
        used_a, used_b = set(), set()
        for sc, a, b in cand_pairs:
            if a in used_a or b in used_b:
                continue
            used_a.add(a)
            used_b.add(b)
            if typed:
                c["issues_tp"] += 1
                c[f"issue_tp_{gold_issues[b]['type']}"] += 1
            else:
                c["issues_tp_untyped"] += 1
    return c


def _div(a, b):
    return round(a / b, 4) if b else None


def _f1(p, r):
    return round(2 * p * r / (p + r), 4) if p and r else 0.0


def summarize(c):
    p = _div(c["tp"], c["n_pred"]) or 0.0
    r = _div(c["tp"], c["n_expected"]) or 0.0
    sp = _div(c["strict_tp"], c["n_pred"]) or 0.0
    sr = _div(c["strict_tp"], c["n_expected"]) or 0.0
    ip = _div(c["issues_tp"], c["issues_pred"]) or 0.0
    ir = _div(c["issues_tp"], c["issues_gold"]) or 0.0
    out = {
        "extraction": {"precision": p, "recall_expected": r, "f1_expected": _f1(p, r)},
        "strict_extraction_classification": {"precision": sp, "recall_expected": sr, "f1_expected": _f1(sp, sr)},
        "recall_by_status": {k[len("status_n_"):]: _div(c["status_tp_" + k[len("status_n_"):]], v)
                             for k, v in sorted(c.items()) if k.startswith("status_n_")},
        "recall_by_phenomenon": {k[len("phen_n_"):]: _div(c["phen_tp_" + k[len("phen_n_"):]], v)
                                 for k, v in sorted(c.items()) if k.startswith("phen_n_")},
        "false_positives": {
            "distractor_hits": c["fp_distractor"],
            "rejected_hits": c["fp_rejected"],
            "omitted_hits": c["fp_omitted"],
            "unmatched": c["fp_unmatched"],
            "distractor_rate": _div(c["fp_distractor"], c["n_pred"]),
        },
        "detail_hallucination_rate": _div(c["detail_hallucinated"], c["detail_n"]),
        "classification_on_matched": {},
        "trace_to_source": {
            "predictions_with_source": c["with_source"],
            "grounding_rate": _div(c["grounded"], c["with_source"]),
            "trace_accuracy": _div(c["trace_ok"], c["trace_n"]),
        },
        "unsupported_rate": _div(c["unsupported"], c["n_pred"]),
        "issues": {
            # sem issues no gabarito nem na predição a métrica não se aplica
            "precision": ip if c["issues_pred"] or c["issues_gold"] else None,
            "recall": ir if c["issues_gold"] else None,
            "f1": _f1(ip, ir) if c["issues_pred"] or c["issues_gold"] else None,
            "recall_untyped": _div(c["issues_tp_untyped"], c["issues_gold"]),
            "recall_by_type": {k[len("issue_n_"):]: _div(c["issue_tp_" + k[len("issue_n_"):]], v)
                               for k, v in sorted(c.items()) if k.startswith("issue_n_")},
        },
        "counts": dict(c),
    }
    f1s = []
    for cls in ("FR", "NFR"):
        cp = _div(c[f"cls_tp_{cls}"], c[f"cls_pred_{cls}"]) or 0.0
        cr = _div(c[f"cls_tp_{cls}"], c[f"cls_gold_{cls}"]) or 0.0
        out["classification_on_matched"][cls] = {"precision": cp, "recall": cr, "f1": _f1(cp, cr)}
        f1s.append(_f1(cp, cr))
    out["classification_on_matched"]["macro_f1"] = round(sum(f1s) / 2, 4)
    return out


def load_texts(pair_dir, gt):
    return {m["id"]: (pair_dir / m["file"]).read_text(encoding="utf-8") for m in gt["input"]["meetings"]}
