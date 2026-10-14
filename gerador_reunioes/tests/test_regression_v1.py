"""Garante que o modo ``dialogue`` continua gerando exatamente o dataset v1
publicado em ``Entradas`` (tag v1.0). Hashes calculados sobre o texto
decodificado (independe de CRLF/LF)."""

import hashlib
import json
from pathlib import Path

import pytest

from pureprep import cli

ROOT = Path(__file__).resolve().parents[1]
XML_DIR = ROOT / "data" / "raw" / "requirements-xml" / "XMLZIPFile"
GOLDEN = json.loads((Path(__file__).parent / "golden" / "v1_dialogue_sha256.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(not XML_DIR.exists(), reason="PURE não baixado")
def test_dialogue_v1_is_frozen(tmp_path):
    cli.main(["--xml-dir", str(XML_DIR), "--out", str(tmp_path), "--profiles", ""])
    base = tmp_path / "pairs" / "dialogue"
    assert sorted(p.name for p in base.iterdir()) == sorted(GOLDEN)
    for doc_id, files in GOLDEN.items():
        for name, digest in files.items():
            got = hashlib.sha256((base / doc_id / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            assert got == digest, f"{doc_id}/{name} mudou em relação ao v1"
