"""Triagem dos 79 documentos originais do PURE (PDF/DOC/HTML/RTF).

Só 18 dos 79 têm versão XML. Esta triagem converte os originais em texto
(pdftotext quando disponível; extração crua para .doc/.rtf/.html) e procura
cabeçalhos típicos de contexto, RF e RNF, além de contar declarações
"shall/must", para estimar quantos documentos valeriam a conversão manual.

Uso:
    python -m pureprep.scan_originals --req-dir data/raw/requirements/req --out output/originals_scan.csv
"""

import argparse
import csv
import html
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from . import utf8_stdio
from .parse import slugify

CONTEXT_H = re.compile(r"\b(scope|purpose|product perspective|overall description|general description|system overview|user (classes|characteristics)|operating environment|vision)\b", re.I)
FR_H = re.compile(r"\b(functional requirements?|system features?|functional specification|system capabilit(y|ies)|use cases?)\b", re.I)
NFR_H = re.compile(r"\b(non-?\s?functional|performance requirements?|security requirements?|quality attributes?|software system attributes|usability|reliability|availability|maintainability|portability)\b", re.I)
STRONG = re.compile(r"\b(shall|must)\b", re.I)
# Muitos SRS acadêmicos (template Wiegers) usam "will/should" em vez de "shall".
ANY_MODAL = re.compile(r"\b(shall|must|should|will)\b", re.I)
# Nomes dos XMLs que diferem do original.
XML_ALIASES = {"2007-eirene-fun-7": "2007-eirene-fun-7-2", "2009-peppol": "2009-peppol-approved", "2010-blit-draft": "2010-blitdraft"}


def to_text(path):
    ext = path.suffix.lower()
    if ext == ".pdf" and shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True)
        return r.stdout.decode("utf-8", errors="replace")
    raw = path.read_bytes()
    if ext in (".htm", ".html"):
        t = raw.decode("utf-8", errors="replace")
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
        t = re.sub(r"(?i)<br\s*/?>|</(p|h\d|li|tr|div)>", "\n", t)
        return html.unescape(re.sub(r"<[^>]+>", " ", t))
    if ext == ".rtf":
        t = raw.decode("latin-1", errors="replace")
        t = re.sub(r"\\par[d]?", "\n", t)
        return re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", t)
    # .doc (Word 97-2003): sequências de texto ASCII/UTF-16LE legíveis
    a = re.findall(rb"[\x20-\x7e\r\n\t]{4,}", raw)
    u = re.findall(rb"(?:[\x20-\x7e]\x00){4,}", raw)
    return "\n".join(x.decode("ascii", "ignore") for x in a) + "\n" + "\n".join(x.decode("utf-16le", "ignore") for x in u)


def heading_lines(text):
    """Linhas curtas que parecem título (numeradas ou em caixa-alta/título)."""
    for line in text.splitlines():
        s = line.strip()
        if 3 <= len(s) <= 90 and (re.match(r"^(\d+(\.\d+)*\.?|[A-Z]\.)\s+\S", s) or s.isupper() or s.istitle()):
            yield s


def scan(req_dir, xml_dir):
    xml_ids = {slugify(p.name) for p in Path(xml_dir).glob("*.xml")}
    rows = []
    for p in sorted(Path(req_dir).iterdir()):
        if p.is_dir():
            continue
        text = to_text(p)
        heads = list(heading_lines(text))
        ctx = sorted({m.group(0).lower() for h in heads for m in [CONTEXT_H.search(h)] if m})
        fr = sorted({m.group(0).lower() for h in heads for m in [FR_H.search(h)] if m})
        nfr = sorted({m.group(0).lower() for h in heads for m in [NFR_H.search(h)] if m})
        n_shall = len(STRONG.findall(text))
        n_modal = len(ANY_MODAL.findall(text))
        words = len(text.split())
        doc_id = slugify(p.name)
        has = (bool(ctx), bool(fr), bool(nfr))
        if all(has) and n_modal >= 40:
            tier = "A"
        elif has[0] and (has[1] or has[2]) and n_modal >= 15:
            tier = "B"
        else:
            tier = "C"
        rows.append({
            "file": p.name, "format": p.suffix.lower().lstrip("."), "doc_id": doc_id,
            "has_xml": XML_ALIASES.get(doc_id, doc_id) in xml_ids,
            "words": words, "n_shall_must": n_shall, "n_modal": n_modal,
            "context_headings": "; ".join(ctx), "fr_headings": "; ".join(fr), "nfr_headings": "; ".join(nfr),
            "tier_estimate": tier, "text_extracted": words > 200,
        })
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--req-dir", default="data/raw/requirements/req")
    ap.add_argument("--xml-dir", default="data/raw/requirements-xml/XMLZIPFile")
    ap.add_argument("--out", default="output/originals_scan.csv")
    args = ap.parse_args(argv)
    rows = scan(args.req_dir, args.xml_dir)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print("documentos:", len(rows), "| formatos:", dict(Counter(r["format"] for r in rows)))
    print("tier estimado (todos):", dict(Counter(r["tier_estimate"] for r in rows)))
    print("tier estimado (sem XML):", dict(Counter(r["tier_estimate"] for r in rows if not r["has_xml"])))
    print("com XML:", sum(r["has_xml"] for r in rows), "| texto extraído:", sum(r["text_extracted"] for r in rows))


if __name__ == "__main__":
    utf8_stdio()
    main()
