import random

import pytest

from pureprep.extract import clean_req_text, extract
from pureprep.parse import load_document
from pureprep.synth import add_disfluency, deformalize, short_title
from pureprep.taxonomy import classify_title, resolve_role
from pureprep.textsim import containment, modal_strength, overlap_f1, split_sentences, token_set

# --------------------------------------------------------------------- textsim


def test_split_sentences_keeps_abbreviations():
    s = split_sentences("The system shall log errors, e.g. timeouts. Users shall log in.")
    assert s == ["The system shall log errors, e.g. timeouts.", "Users shall log in."]


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("The system shall encrypt passwords.", "strong"),
        ("Users must be able to log in.", "strong"),
        ("The page will display results.", "weak"),
        ("This document will describe the system.", None),
        ("The board is black.", None),
    ],
)
def test_modal_strength(sentence, expected):
    assert modal_strength(sentence) == expected


def test_similarity_bounds():
    a = "The system shall export reports to PDF"
    assert overlap_f1(a, a) == 1.0
    assert overlap_f1(a, "Completely unrelated sentence here") == 0.0
    assert containment(token_set("export reports"), token_set(a)) == 1.0


# -------------------------------------------------------------------- taxonomy


@pytest.mark.parametrize(
    "title,role,sub",
    [
        ("5.1 Performance Requirements", "nfr", "PE"),
        ("Security Requirements", "nfr", "SE"),
        ("Quality Attribute Requirements", "nfr", "OT"),
        ("2.1 Product Perspective", "context", None),
        ("1.2 Scope", "context", None),
        ("3.1.2 Stimulus/Response Sequences", "scenario", None),
        ("References", "meta", None),
        ("Definitions, Acronyms, and Abbreviations", "meta", None),
        ("3.1 Functional Requirements", "fr", None),
    ],
)
def test_classify_title(title, role, sub):
    assert classify_title(title) == (role, sub)


def test_resolve_role_inheritance_rules():
    # título sem regra herda do ancestral
    assert resolve_role(["System Features", "New Database"]) == ("fr", None)
    # RNF específico mais profundo vence o contêiner RF
    assert resolve_role(["Specific Requirements", "Performance"]) == ("nfr", "PE")
    # "Introduction" genérico dentro de capítulo RF herda RF (THEMAS)
    assert resolve_role(["Engineering Requirements", "Functional Requirements", "Monitor Temperature", "Introduction"]) == ("fr", None)
    # tudo sob "Product Perspective" é descritivo (IEEE 830 §2.1)
    assert resolve_role(["General Description", "Product Perspective", "User Interfaces"]) == ("context", None)


# --------------------------------------------------------------------- extract

XML = """<?xml version="1.0" encoding="UTF-8"?>
<req_document xmlns="req_document.xsd">
<title>Software Requirements Specification for Demo Shop</title>
<p id="1"><title>Introduction</title>
  <p id="1.1"><title>Purpose</title><text_body>Demo Shop lets small retailers sell online. The system shall support credit cards.</text_body></p>
  <p id="1.2"><title>References</title><text_body>IEEE 830 shall be followed.</text_body></p>
</p>
<p id="2"><title>Overall Description</title>
  <p id="2.1"><title>Assumptions and Dependencies</title><req id="AS-1"><text_body>The hosting provider shall offer backups.</text_body></req></p>
</p>
<p id="3"><title>System Features</title>
  <p id="3.1"><title>Shopping Cart</title>
    <p id="3.1.1"><title>Functional Requirements</title>
      <req id="REQ-1"><text_body>REQ-1: The system shall allow customers to add products to the cart.</text_body></req>
      <text_body>The cart shall show the following:
        <itemize><item>product name</item><item>unit price</item></itemize>
      </text_body>
    </p>
  </p>
</p>
<p id="4"><title>Other Nonfunctional Requirements</title>
  <p id="4.1"><title>Performance Requirements</title><text_body>Search results shall appear in less than 2 seconds.</text_body></p>
</p>
</req_document>
"""


@pytest.fixture
def demo(tmp_path):
    p = tmp_path / "2020 - demo shop.xml"
    p.write_text(XML, encoding="utf-8")
    doc = load_document(p)
    return doc, extract(doc)


def test_extract_ground_truth(demo):
    doc, ext = demo
    assert doc.doc_id == "2020-demo-shop"
    by_text = {r.text: r for r in ext.requirements}
    add = by_text["The system shall allow customers to add products to the cart."]
    assert (add.cls, add.tier, add.original_req_id) == ("FR", "primary", "REQ-1")
    assert "The cart shall show the following: product name; unit price." in by_text
    perf = by_text["Search results shall appear in less than 2 seconds."]
    assert (perf.cls, perf.subtype) == ("NFR", "PE")
    # frase "shall" em seção de contexto → secundária (vai para a entrada)
    assert by_text["The system shall support credit cards."].tier == "secondary"
    # seção meta e premissas não geram requisitos
    assert not any("IEEE 830" in t or "hosting provider" in t for t in by_text)
    ctx = " ".join(u.text for u in ext.context)
    assert "small retailers" in ctx and "hosting provider" in ctx


def test_clean_req_text_strips_ids_and_marks():
    assert clean_req_text("REQ-2: Master Password has no limits.")[0] == "Master Password has no limits."
    assert clean_req_text("[SSS422] Control shall be provided.")[0] == "Control shall be provided."
    txt, mod = clean_req_text("2.2.2 All calls shall work. (M)")
    assert (txt, mod) == ("All calls shall work.", "M")


# ----------------------------------------------------------------------- synth


@pytest.mark.parametrize(
    "req",
    [
        "The system shall allow customers to add products to the cart.",
        "The User shall be able to choose a function by clicking the hyperlink.",
        "ETCS shall not release the emergency brake while the train is moving.",
        "If no results are found, a message shall be displayed.",
        "Block selection. Input: Leftclicked down on a block.",
    ],
)
def test_deformalize_preserves_content(req):
    for seed in range(5):
        out = deformalize(req, random.Random(seed))
        assert containment(token_set(req), token_set(out)) >= 0.9, out


def test_disfluency_is_additive():
    text = "we need the system to export monthly reports"
    noisy = add_disfluency(text, random.Random(3), rate=0.5)
    it = iter(noisy.split())
    assert all(any(w == n for n in it) for w in text.split()), noisy


def test_short_title():
    assert short_title("Software Requirements Specification for KeePass Password Safe") == "KeePass Password Safe"
