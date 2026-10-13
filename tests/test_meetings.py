"""Testes do modo ``meetings``: transformações, plano, realizador por regras,
gabarito schema 2.0 e avaliador."""

import json
import random
from pathlib import Path

import pytest

from pureprep import cli
from pureprep.baseline import oracle_meetings
from pureprep.dialogue import build_meetings, profiles
from pureprep.dialogue import transforms as T
from pureprep.dialogue.model import EXPECTED_IN_OUTPUT, VALID_ROLES
from pureprep.dialogue.plan import build_plan
from pureprep.dialogue.realize_rules import _fill, casual_need, contract
from pureprep.evaluate_meetings import evaluate_doc, load_texts, summarize
from pureprep.extract import extract
from pureprep.parse import load_document
from pureprep.textsim import containment, token_set

ROOT = Path(__file__).resolve().parents[1]
XML_DIR = ROOT / "data" / "raw" / "requirements-xml" / "XMLZIPFile"

# ----------------------------------------------------------------- transforms


def test_find_quantities_skips_years_sections_and_ids():
    qs = T.find_quantities("Since 2004, per section 3.2.1 and R12, stage 2 must answer within 5 seconds for 99.9% of 100 users.")
    assert [q["span"] for q in qs] == ["5 seconds", "99.9%", "100 users"]


def test_mutate_quantity_changes_only_the_value():
    text = "Search results shall appear in less than 2 seconds."
    for seed in range(20):
        m = T.mutate_quantity(text, random.Random(seed))
        assert m["original_value"] == "2 seconds" and m["proposed_value"] != "2 seconds"
        assert m["text"].replace(m["proposed_value"], "2 seconds") == text


def test_mutate_actor_ignores_compound_nouns():
    assert T.mutate_actor("The user interface shall be simple.", random.Random(0)) is None
    m = T.mutate_actor("The supervisor shall be able to select a thermostat.", random.Random(0))
    assert m["original_value"] == "The supervisor" and "supervisor" not in m["proposed_value"].lower()


def test_ambiguity_and_incompleteness_remove_detail():
    text = "The system shall lock the account after 3 attempts when the password is wrong."
    a = T.vague_quantity(text, random.Random(1))
    assert "3" not in a["text"] and a["removed"] == "3 attempts"
    c = T.missing_condition(text, random.Random(1))
    assert c["text"] == "The system shall lock the account after 3 attempts" and c["missing"].startswith("when")
    assert T.ambiguity("Nothing measurable here at all.", random.Random(0))["kind"] == "optionality"


def test_split_for_interruption_keeps_all_words():
    text = "The operator shall be able to export the monthly report, including all charts and the raw data."
    a, b = T.split_for_interruption(text)
    assert (a + " " + b).replace(",", "").split() == text.replace(",", "").split()


# ----------------------------------------------------------------- realizador


def test_contractions_keep_content_tokens():
    s = "It is important that the system does not delete data."
    out = contract(s, random.Random(0), p=1.0)
    assert out == "It's important that the system doesn't delete data."
    assert containment(token_set(s), token_set(out)) == 1.0


def test_casual_need_preserves_content():
    reqs = [
        "The system shall allow customers to add products to the cart.",
        "The administrator must be able to reset any password in order to restore access.",
        "Search results shall appear in less than 2 seconds.",
        "The database shall not store passwords in plain text.",
    ]
    for seed in range(10):
        for r in reqs:
            out = casual_need(r, random.Random(seed), speaker="Client")
            assert containment(token_set(r), token_set(out)) >= 0.8, out


def test_hedge_marks_optionality():
    out = casual_need("The report shall include a chart.", random.Random(0), flags={"hedge": True})
    assert any(w in out.lower() for w in ("maybe", "might", "nice if", "ideally", "could"))


def test_fill_adjusts_case():
    assert _fill("I'd say {x}", "We need it.") == "I'd say we need it."
    assert _fill("Wait. {x}", "we need it.") == "Wait. We need it."


# ----------------------------------------------------------------- plano/gabarito

TOPICS = ["Login", "Search", "Reports", "Payments", "Notifications", "Administration"]
TEMPLATES = [
    "The user shall be able to {v} the {o} within {n} seconds.",
    "The administrator must be able to {v} any {o} when the account is locked.",
    "The system shall {v} at most {n} {o} records per page, including archived ones and the drafts.",
    "The {o} module shall {v} data for at least {n} days.",
    "The system shall notify the supervisor if the {o} cannot be {v}ed.",
    "Each {o} shall be {v}ed by the operator before it is published.",
]


def _xml():
    body = []
    for i, tp in enumerate(TOPICS):
        reqs = "".join(f"<text_body>{t.format(v=['export', 'review', 'archive'][j % 3], o=tp.lower(), n=(i + 2) * (j + 3))}</text_body>"
                       for j, t in enumerate(TEMPLATES))
        body.append(f'<p id="3.{i + 1}"><title>{tp}</title><p id="3.{i + 1}.1"><title>Functional Requirements</title>{reqs}</p></p>')
    return ('<?xml version="1.0" encoding="UTF-8"?><req_document xmlns="req_document.xsd">'
            "<title>Software Requirements Specification for Test Portal</title>"
            '<p id="1"><title>Introduction</title><p id="1.1"><title>Purpose</title><text_body>Test Portal helps small teams share reports '
            "with their customers in a simple way.</text_body></p></p>"
            f'<p id="3"><title>System Features</title>{"".join(body)}</p></req_document>')


@pytest.fixture
def portal(tmp_path, monkeypatch):
    p = tmp_path / "2020 - test portal.xml"
    p.write_text(_xml(), encoding="utf-8")
    doc = load_document(p)
    ext = extract(doc)
    reqs = [r for r in ext.requirements if r.tier == "primary"]
    # perfil de teste com fenômenos frequentes para exercitar todos os caminhos
    monkeypatch.setitem(profiles.PROFILES, "stress", {**profiles.PROFILES["hard"], "meetings": (3, 3), "p_omit": 0.06,
                                                       "p_conflict": 0.2, "p_ambiguity": 0.15, "p_inconsistency": 0.15,
                                                       "p_incomplete": 0.15, "p_resolve_later": 0.6, "p_complete_later": 0.6})
    return doc, ext, reqs


def _check_invariants(plan, realized, gold):
    texts = {m.mid: t for m, t, _ in realized}
    seg_ids = {}
    for m, text, segs in realized:
        for s in segs:
            assert s["id"].startswith(m.mid + ":")
            body = text[s["start"] : s["end"]]
            assert body.strip(), s
            line_start = text.rfind("\n", 0, s["start"]) + 1
            assert text[line_start : s["start"]] == f"{s['speaker']}: "
            seg_ids[s["id"]] = s
    for r in gold["requirements"]:
        st = r["status"]
        assert r["expected_in_output"] == (st in EXPECTED_IN_OUTPUT)
        if st == "omitted":
            assert not r["trace"]["related_segments"] and not r["trace"]["reachable"]
            continue
        assert r["trace"]["input_segments"], r["id"]
        roles = {ref["role"] for sid in r["trace"]["input_segments"] for ref in seg_ids[sid].get("refs", []) if ref["rid"] == r["id"]}
        assert roles & set(VALID_ROLES), (r["id"], roles)
        if st == "clear" and not r["phenomena"]:
            assert r["trace"]["support_score"] >= 0.6, r["id"]
    issues_by_req = {i["requirement"]: i for i in gold["issues"]}
    for r in gold["requirements"]:
        if r["status"] in ("conflict_open", "ambiguous", "inconsistent", "incomplete"):
            assert issues_by_req[r["id"]]["segments"]
        else:
            assert r["id"] not in issues_by_req
    for d in gold["distractors"]:
        assert d["segments"] and all(seg_ids[s]["act"] in ("state", "counter") for s in d["segments"])
    for r in gold["requirements"]:
        for p in r["phenomena"]:
            meetings = {s.split(":")[0] for s in p["segments"]}
            if p["outcome"] in ("resolved_later", "dropped_later", "completed_later"):
                assert len(meetings) == 2, p
            if p["type"] == "inconsistency":
                assert len(p["segments"]) == 2
    return texts


def test_clean_profile_is_single_meeting_without_phenomena(portal):
    doc, ext, reqs = portal
    plan, realized, gold = build_meetings(doc, ext, reqs, profile="clean", realizer="rules", seed=1)
    _check_invariants(plan, realized, gold)
    assert gold["input"]["n_meetings"] == 1
    assert gold["input"]["meetings"][0]["participants"] == ["Analyst", "Client", "EndUser", "TechLead"]
    assert all(r["status"] == "clear" for r in gold["requirements"])
    assert not gold["issues"] and not gold["distractors"]


@pytest.mark.parametrize("seed", range(8))
def test_stress_profile_invariants(portal, seed):
    doc, ext, reqs = portal
    plan, realized, gold = build_meetings(doc, ext, reqs, profile="stress", realizer="rules", seed=seed)
    _check_invariants(plan, realized, gold)
    assert gold["input"]["n_meetings"] == 3


def test_stress_covers_every_phenomenon(portal):
    doc, ext, reqs = portal
    seen = set()
    for seed in range(8):
        _, _, gold = build_meetings(doc, ext, reqs, profile="stress", realizer="rules", seed=seed)
        seen |= {f"{p['type']}:{p['outcome']}" for r in gold["requirements"] for p in r["phenomena"]}
    for key in ("conflict:resolved", "conflict:open", "conflict:resolved_later", "ambiguity:unresolved",
                "inconsistency:unnoticed", "incompleteness:open", "incompleteness:completed_later", "omission:not_discussed"):
        assert key in seen, key


def test_plan_is_deterministic_and_independent_of_realizer(portal):
    doc, ext, reqs = portal
    a = build_plan(doc, ext, reqs, "stress", random.Random("x")).to_json()
    b = build_plan(doc, ext, reqs, "stress", random.Random("x")).to_json()
    assert a == b
    g1 = build_meetings(doc, ext, reqs, profile="stress", realizer="rules", seed=3)[2]
    g2 = build_meetings(doc, ext, reqs, profile="stress", realizer="rules", seed=3)[2]
    assert g1 == g2


# ----------------------------------------------------------------- avaliador


def _eval(gold, realized, preds, issues=()):
    texts = {m.mid: t for m, t, _ in realized}
    return summarize(evaluate_doc(gold, texts, preds, issues))


def test_oracle_is_perfect(portal):
    doc, ext, reqs = portal
    _, realized, gold = build_meetings(doc, ext, reqs, profile="stress", realizer="rules", seed=2)
    o = oracle_meetings(gold)
    s = _eval(gold, realized, o["requirements"], o["issues"])
    assert s["extraction"]["f1_expected"] == 1.0
    assert s["issues"]["f1"] == 1.0
    assert s["false_positives"]["distractor_hits"] == 0


def test_distractor_rejected_and_hallucinated_detail_are_penalized(portal):
    doc, ext, reqs = portal
    for seed in range(20):
        _, realized, gold = build_meetings(doc, ext, reqs, profile="stress", realizer="rules", seed=seed)
        amb = [r for r in gold["requirements"] if r["status"] == "ambiguous" and r["phenomena"][0]["kind"] == "vague_quantity"]
        rej = [r for r in gold["requirements"] if r["status"] == "rejected"]
        if gold["distractors"] and amb and rej:
            break
    else:
        pytest.skip("nenhuma semente gerou todos os casos")
    preds = [{"text": gold["distractors"][0]["text"], "class": "FR"},
             {"text": rej[0]["text"], "class": "FR"},
             {"text": amb[0]["text"], "class": amb[0]["class"]}]  # texto canônico traz o número que ninguém disse
    s = _eval(gold, realized, preds)
    assert s["false_positives"]["distractor_hits"] == 1
    assert s["false_positives"]["rejected_hits"] == 1
    assert s["detail_hallucination_rate"] == 1.0


def test_issue_detection_by_source_text(portal):
    doc, ext, reqs = portal
    _, realized, gold = build_meetings(doc, ext, reqs, profile="stress", realizer="rules", seed=4)
    texts = {m.mid: t for m, t, _ in realized}
    segs = {s["id"]: (m.mid, s) for m, _, ss in realized for s in ss}
    gi = gold["issues"][0]
    mid, s = segs[gi["segments"][0]]
    quote = texts[mid][s["start"] : s["end"]]
    ok = _eval(gold, realized, [], [{"type": gi["type"], "source_text": quote}])
    assert ok["issues"]["recall"] == round(1 / len(gold["issues"]), 4)
    wrong = _eval(gold, realized, [], [{"type": "nonsense", "source_text": quote}])
    assert wrong["issues"]["recall"] == 0.0 and wrong["issues"]["recall_untyped"] == ok["issues"]["recall"]


# ----------------------------------------------------------------- PURE real


@pytest.mark.skipif(not XML_DIR.exists(), reason="PURE não baixado")
def test_meetings_on_real_pure(tmp_path):
    cli.main(["--xml-dir", str(XML_DIR), "--out", str(tmp_path), "--profiles", "clean,realistic,hard"])
    base = tmp_path / "pairs" / "meetings"
    assert sorted(p.name for p in base.iterdir()) == ["rules-clean", "rules-hard", "rules-realistic"]
    for variant in base.iterdir():
        for d in variant.iterdir():
            gt = json.loads((d / "ground_truth_requirements.json").read_text(encoding="utf-8"))
            assert gt["schema_version"] == "2.0" and gt["variant"] == variant.name
            texts = load_texts(d, gt)
            for m in gt["input"]["meetings"]:
                # offsets valem também para o arquivo lido sem tradução de quebras de linha
                raw = (d / m["file"]).read_bytes().decode("utf-8")
                assert "\r" not in raw and raw == texts[m["id"]]
                for s in m["segments"]:
                    assert texts[m["id"]][s["start"] : s["end"]].strip()
            o = oracle_meetings(gt)
            s = summarize(evaluate_doc(gt, texts, o["requirements"], o["issues"]))
            if gt["stats"]["n_expected_in_output"]:
                assert s["extraction"]["f1_expected"] == 1.0, (variant.name, d.name)
    # mesma amostra de requisitos do dialogue v1 em todos os perfis
    for doc in ("2008-keepass", "2007-ertms"):
        v1 = json.loads((tmp_path / "pairs" / "dialogue" / doc / "ground_truth_requirements.json").read_text(encoding="utf-8"))
        ids = {r["id"] for r in v1["requirements"]}
        for variant in base.iterdir():
            g = json.loads((variant / doc / "ground_truth_requirements.json").read_text(encoding="utf-8"))
            assert {r["id"] for r in g["requirements"]} == ids
