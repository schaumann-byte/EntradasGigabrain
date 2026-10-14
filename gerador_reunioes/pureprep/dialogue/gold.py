"""Gabarito schema 2.0 do modo ``meetings``.

A rastreabilidade vem do *log do plano* (cada fala sabe quais requisitos
referencia e com que papel), não de similaridade lexical: com ambiguidade e
incompletude o texto da fala deixa, de propósito, de conter todos os tokens
do requisito. ``support_score`` continua sendo calculado (cobertura de
tokens do requisito pelas falas que carregam a versão válida) como
diagnóstico de quanto a superfície preservou do texto canônico.
"""

from collections import Counter, defaultdict
from dataclasses import asdict

from ..textsim import containment, token_set
from .model import EXPECTED_IN_OUTPUT, STATUSES, VALID_ROLES

SCHEMA_VERSION = "2.0"

ISSUE_TYPE = {
    "conflict_open": ("conflict", "resolve_with_stakeholders"),
    "ambiguous": ("ambiguity", "ask_clarification"),
    "inconsistent": ("inconsistency", "flag_inconsistency"),
    "incomplete": ("incompleteness", "request_missing_information"),
}


def meeting_file(m):
    return f"reuniao_{m.index:02d}.txt"


def build_gold(doc, plan, realized, reqs, *, variant, realizer, params):
    seg_text = {}
    by_rid = defaultdict(list)  # rid -> [(seg_id, role, pid)]
    meetings = []
    for m, text, segs in realized:
        for s in segs:
            seg_text[s["id"]] = text[s["start"] : s["end"]]
            for ref in s.get("refs", []):
                by_rid[ref["rid"]].append((s["id"], ref["role"], ref.get("pid")))
        meetings.append({
            "id": m.mid,
            "file": meeting_file(m),
            "kind": m.kind,
            "participants": m.participants,
            "topics": m.topics,
            "n_chars": len(text),
            "n_words": len(text.split()),
            "segments": segs,
        })

    def ids(entries, roles=None, pid=None):
        return list(dict.fromkeys(sid for sid, role, p in entries if (roles is None or role in roles) and (pid is None or p == pid)))

    phen_by_rid = defaultdict(list)
    for p in plan.phenomena:
        phen_by_rid[p.rid].append(p)

    items, distractors, issues = [], [], []
    for r in reqs:
        status = plan.status[r.rid]
        entries = by_rid.get(r.rid, [])
        valid = ids(entries, VALID_ROLES)
        toks = frozenset().union(*(token_set(seg_text[s]) for s in valid)) if valid else frozenset()
        j = r.to_json()
        j["status"] = status
        j["expected_in_output"] = status in EXPECTED_IN_OUTPUT
        j["phenomena"] = []
        for p in phen_by_rid[r.rid]:
            pj = {k: v for k, v in asdict(p).items() if k != "rid"}
            pj["segments"] = ids(entries, pid=p.pid)
            j["phenomena"].append(pj)
            if p.type == "conflict" and p.kind in ("value", "actor") and p.outcome in ("resolved", "resolved_later"):
                distractors.append({
                    "id": f"{doc.doc_id}:D{len(distractors) + 1:03d}",
                    "text": p.details["proposed_text"],
                    "requirement": r.rid,
                    "pid": p.pid,
                    "kind": "rejected_proposal",
                    "segments": ids(entries, ("distractor",), p.pid),
                })
        if status in ISSUE_TYPE:
            typ, action = ISSUE_TYPE[status]
            p = next(p for p in phen_by_rid[r.rid] if p.type == typ)
            issues.append({
                "id": f"{doc.doc_id}:I{len(issues) + 1:03d}",
                "type": typ,
                "kind": p.kind,
                "requirement": r.rid,
                "pid": p.pid,
                "expected_action": action,
                "segments": ids(entries, pid=p.pid),
                "details": p.details,
            })
        j["trace"] = {
            "input_segments": valid or ids(entries),
            "related_segments": ids(entries),
            "support_score": round(containment(r.tokens, toks), 3) if toks else 0.0,
            "reachable": status != "omitted",
        }
        items.append(j)

    st = Counter(i["status"] for i in items)
    ph = Counter(f"{p.type}:{p.outcome}" for p in plan.phenomena)
    cls = Counter((r.tier, r.cls) for r in reqs)
    expected = [i for i in items if i["expected_in_output"]]
    clear = [i for i in items if i["status"] == "clear"]
    return {
        "schema_version": SCHEMA_VERSION,
        "doc_id": doc.doc_id,
        "doc_title": doc.title,
        "source_file": f"PURE/requirements-xml/{doc.source_file}",
        "mode": "meetings",
        "variant": variant,
        "generator": {"tool": "pureprep", "realizer": realizer, "profile": plan.profile, "params": params},
        "input": {
            "n_meetings": len(meetings),
            "n_chars": sum(m["n_chars"] for m in meetings),
            "n_words": sum(m["n_words"] for m in meetings),
            "meetings": meetings,
        },
        "stats": {
            "n_requirements": len(items),
            "n_primary_fr": cls[("primary", "FR")],
            "n_primary_nfr": cls[("primary", "NFR")],
            "n_expected_in_output": len(expected),
            "n_reachable": sum(i["trace"]["reachable"] for i in items),
            "by_status": {s: st[s] for s in STATUSES if st[s]},
            "phenomena": dict(sorted(ph.items())),
            "n_distractors": len(distractors),
            "n_issues": len(issues),
            "messiness": plan.messiness,
            "mean_support_clear": round(sum(i["trace"]["support_score"] for i in clear) / len(clear), 3) if clear else None,
        },
        "requirements": items,
        "distractors": distractors,
        "issues": issues,
    }
