"""Leitura dos XMLs do PURE (schema ``req_document.xsd``).

Estrutura observada nos 18 XMLs:

    <req_document>
      <title/> <version/> <issue_date/> ...
      <p id="1"> <title/> <text_body> texto <itemize><item/></itemize> <req id=".."/> </text_body>
                 <req id=".."> <text_body/> <modifier>M</modifier> </req>
                 <p id="1.1"> ... </p>
      </p>

O conteúdo é achatado numa lista de seções (ordem do documento), cada uma
com seus blocos diretos: ``para`` (parágrafo), ``item`` (item de lista) e
``req`` (requisito marcado explicitamente com ``<req id>``).
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .textsim import normalize_ws

NS = "{req_document.xsd}"
LIST_TAGS = {"itemize", "enum", "description"}
SKIP_TAGS = {"glossary", "change_log", "modifier", "title"}


def _local(tag):
    return tag.split("}")[-1] if isinstance(tag, str) else ""


@dataclass
class Block:
    kind: str  # para | item | req
    text: str
    req_id: str = None
    modifier: str = None
    lead: str = None  # frase introdutória ("... the following:") de um item


@dataclass
class Section:
    sid: str
    title: str
    path: list
    blocks: list = field(default_factory=list)
    order: int = 0


@dataclass
class Document:
    doc_id: str
    source_file: str
    title: str
    sections: list


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def _text_of(el):
    return normalize_ws("".join(el.itertext()))


def _title_of(el):
    t = el.find(NS + "title")
    return _text_of(t) if t is not None else ""


class _Collector:
    """Percorre conteúdo misto acumulando parágrafos e emitindo blocos."""

    def __init__(self, blocks):
        self.blocks = blocks
        self.buf = []

    def add_text(self, txt):
        if txt:
            self.buf.append(txt)

    def flush(self):
        raw = "".join(self.buf)
        self.buf = []
        for para in re.split(r"\n\s*\n", raw):
            para = normalize_ws(para)
            if para:
                self.blocks.append(Block("para", para))

    def last_para_lead(self):
        for b in reversed(self.blocks):
            if b.kind == "para":
                return b.text if b.text.rstrip().endswith(":") else None
            break
        return None

    def add_list(self, el):
        self.flush()
        lead = self.last_para_lead()
        for item in el:
            if _local(item.tag) != "item":
                continue
            txt = _text_of(item)
            if txt:
                self.blocks.append(Block("item", txt, lead=lead))

    def walk_mixed(self, el):
        self.add_text(el.text)
        for child in el:
            tag = _local(child.tag)
            if tag in LIST_TAGS:
                self.add_list(child)
            elif tag == "req":
                self.flush()
                self.blocks.append(_req_block(child))
            elif tag == "text_body":
                self.walk_mixed(child)
            elif tag in SKIP_TAGS or tag == "p":
                pass
            else:  # crossref e similares: mantém o texto inline
                self.add_text(" ".join(child.itertext()))
            self.add_text(child.tail)


def _req_block(el):
    modifier = el.find(NS + "modifier")
    parts = []
    for child in el:
        tag = _local(child.tag)
        if tag == "modifier":
            continue
        parts.append(_text_of(child))
    text = normalize_ws(" ".join([el.text or ""] + parts))
    return Block(
        "req",
        text,
        req_id=(el.get("id") or "").strip() or None,
        modifier=_text_of(modifier) if modifier is not None else None,
    )


def _walk_section(el, path, out):
    title = _title_of(el)
    sec = Section(sid=(el.get("id") or "").strip(), title=title, path=path + [title], order=len(out))
    out.append(sec)
    col = _Collector(sec.blocks)
    for child in el:
        tag = _local(child.tag)
        if tag == "p":
            col.flush()
            _walk_section(child, sec.path, out)
        elif tag == "text_body":
            col.walk_mixed(child)
            col.flush()
        elif tag == "req":
            col.flush()
            sec.blocks.append(_req_block(child))
        elif tag in LIST_TAGS:
            col.add_list(child)
    col.flush()


def load_document(path):
    path = Path(path)
    root = ET.parse(path).getroot()
    title = normalize_ws(_text_of(root.find(NS + "title"))) if root.find(NS + "title") is not None else path.stem
    sections = []
    for child in root:
        if _local(child.tag) == "p":
            _walk_section(child, [], sections)
    return Document(doc_id=slugify(path.name), source_file=path.name, title=title, sections=sections)
