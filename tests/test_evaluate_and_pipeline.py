import json
from pathlib import Path

import pytest

from pureprep import cli
from pureprep.evaluate import evaluate_doc, summarize

ROOT = Path(__file__).resolve().parents[1]
XML_DIR = ROOT / "data" / "raw" / "requirements-xml" / "XMLZIPFile"


def _gt():
    text = "Customers want to add products to the cart. Search must be fast, under 2 seconds."
    return text, {
        "input": {"segments": [{"id": "S1", "start": 0, "end": 43}, {"id": "S2", "start": 44, "end": len(text)}]},
        "requirements": [
            {"text": "The system shall allow customers to add products to the cart.", "class": "FR", "subtype": None,
             "tier": "primary", "trace": {"input_segments": ["S1"], "reachable": True}},
            {"text": "Search results shall appear in less than 2 seconds.", "class": "NFR", "subtype": "PE",
             "tier": "primary", "trace": {"input_segments": ["S2"], "reachable": True}},
        ],
    }


def test_evaluate_oracle_is_perfect():
    text, gt = _gt()
    preds = [{"text": r["text"], "class": r["class"], "subtype": r["subtype"]} for r in gt["requirements"]]
    s = summarize(evaluate_doc(gt, text, preds))
    assert s["extraction"]["f1_reachable"] == 1.0
    assert s["classification_on_matched"]["macro_f1"] == 1.0


def test_evaluate_wrong_class_and_trace():
    text, gt = _gt()
    preds = [
        {"text": "The system shall allow customers to add products to the cart.", "class": "NFR",
         "source_text": "Customers want to add products to the cart."},
        {"text": "The system shall send weekly newsletters to all subscribers.", "class": "FR",
         "source_text": "totally invented quote about newsletters"},
    ]
    s = summarize(evaluate_doc(gt, text, preds))
    assert s["extraction"]["precision"] == 0.5
    assert s["extraction"]["recall_reachable"] == 0.5
    assert s["strict_extraction_classification"]["precision"] == 0.0
    assert s["trace_to_source"]["grounding_rate"] == 0.5
    assert s["trace_to_source"]["trace_accuracy"] == 1.0
    assert s["unsupported_rate"] == 0.5  # a newsletter não tem suporte na entrada


@pytest.mark.skipif(not XML_DIR.exists(), reason="PURE não baixado")
def test_pipeline_on_real_pure(tmp_path):
    cli.main(["--xml-dir", str(XML_DIR), "--out", str(tmp_path)])
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["documents"]) == 18
    for mode in cli.MODES:
        for d in (tmp_path / "pairs" / mode).iterdir():
            text = (d / "input_raw.txt").read_text(encoding="utf-8")
            gt = json.loads((d / "ground_truth_requirements.json").read_text(encoding="utf-8"))
            assert gt["mode"] == mode
            for seg in gt["input"]["segments"]:
                assert text[seg["start"] : seg["end"]].strip()
            for r in gt["requirements"]:
                assert r["class"] in ("FR", "NFR") and r["id"].startswith(gt["doc_id"])
                if mode != "context":
                    # entradas sintetizadas cobrem 100% do gabarito
                    assert r["trace"]["reachable"], (d.name, r["id"])
    # determinismo: mesma semente → mesma saída
    other = tmp_path / "again"
    cli.main(["--xml-dir", str(XML_DIR), "--out", str(other)])
    a = (tmp_path / "pairs" / "dialogue" / "2008-keepass" / "input_raw.txt").read_text(encoding="utf-8")
    b = (other / "pairs" / "dialogue" / "2008-keepass" / "input_raw.txt").read_text(encoding="utf-8")
    assert a == b
