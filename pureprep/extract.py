"""Extração do gabarito (ground truth) e do texto de contexto de um SRS.

Regras de decisão (documentadas também no relatório):

1. ``<req id>`` explícito → requisito ``primary`` em qualquer seção não-meta.
2. Em seções ``fr``/``nfr``/``unknown``: toda frase com modal de requisito
   (shall/must/should/will/needs to...) → ``primary``. Itens de lista
   introduzidos por uma frase-requisito terminada em ":" são anexados a ela
   (até ``MAX_MERGED_ITEMS``); itens com modal próprio viram requisitos.
3. Em seções ``context``/``scenario``: o texto vai para a entrada bruta;
   frases com modal FORTE (shall/must...) também entram no gabarito como
   ``secondary`` — são requisitos legítimos que o sistema pode extrair e não
   devem contar como falso positivo.
4. Classe: seção ``nfr`` → RNF com subtipo da seção; seção ``fr`` → RF;
   ``unknown``/``context`` → pistas lexicais (``keyword_hint``) ou RF.
"""

import re
from dataclasses import dataclass, field

from .taxonomy import NFR_SUBTYPES, resolve_role
from .textsim import content_tokens, modal_strength, normalize_ws, split_sentences, token_set

MAX_MERGED_ITEMS = 8
MIN_CONTENT_TOKENS = 4

# Pistas lexicais de RNF (usadas como dica; só decidem a classe fora de seções RF/RNF).
KEYWORD_HINTS = [
    ("PE", r"\b\d+(\.\d+)?\s*(ms|milliseconds?|seconds?|secs?|minutes?)\b|\bresponse time\b|\bthroughput\b|\blatency\b|\bper second\b|\bconcurrent(ly)? users\b"),
    ("SE", r"\bpasswords?\b|\bencrypt|\bauthenticat|\bunauthori[sz]ed\b|\baccess rights\b|\bsecur(e|ity)\b|\bprivileges?\b"),
    ("A", r"\bavailab(le|ility) (24|99)|\b24\s*/\s*7\b|\buptime\b|\bdowntime\b|\b24 hours a day\b"),
    ("US", r"\buser[- ]friendly\b|\beasy to (use|learn|understand)\b|\bintuitive\b|\busability\b"),
    ("LF", r"\blook and feel\b|\bcolou?rs?\b|\bfonts?\b|\bappearance\b"),
    ("PO", r"\bportab|\b(windows|linux|unix|mac ?os)\b|\bbrowsers?\b"),
    ("MN", r"\bmaintainab|\bcoding standards?\b|\bmodular(ity)?\b"),
    ("SC", r"\bscalab|\bscale (up|out)\b"),
    ("L", r"\blaws?\b|\blegal\b|\bregulations?\b|\bcomply\b|\bcompliance\b|\blicen[cs]es?\b|\bcopyright\b"),
    ("FT", r"\bfault\b|\bfailures?\b|\brecover(y|s)?\b|\bbackups?\b|\bredundan"),
    ("SA", r"\bsafety\b|\bhazard"),
]
_KW = [(sub, re.compile(rx, re.I)) for sub, rx in KEYWORD_HINTS]

# Dicas de subtipo para <req> explícitos em seções descritivas do IEEE 830 §2.
_CONTEXT_REQ_HINTS = [
    (re.compile(r"operating environment", re.I), "O"),
    (re.compile(r"constraints?", re.I), "DC"),
    (re.compile(r"user documentation", re.I), "US"),
]

_ID_PREFIX = re.compile(
    r"^\s*(\[[A-Z]{2,6}\d+\]|REQ[- ]?\d+[a-z]?\s*[:.)-]?|[A-Z]{1,6}[- ]\d+(\.\d+)*[a-z]?\s*[:.)]|\d+(\.\d+)+[a-z]?\.?)\s+"
)
_ASSUMPTION = re.compile(r"\bassumptions?\b|\bdependenc", re.I)
_MANDATORY_MARK = re.compile(r"\s*\((M|O|I)\)\s*")


@dataclass
class Requirement:
    rid: str
    text: str
    cls: str
    subtype: str
    tier: str
    label_source: str
    confidence: float
    section_id: str
    section_path: list
    element: str
    original_req_id: str = None
    modifier: str = None
    keyword_hint: str = None
    modal: str = None
    tokens: frozenset = field(default=None, repr=False)

    def to_json(self):
        name, promise = NFR_SUBTYPES.get(self.subtype, (None, None)) if self.subtype else (None, None)
        return {
            "id": self.rid,
            "text": self.text,
            "class": self.cls,
            "subtype": self.subtype,
            "subtype_name": name,
            "promise_subtype": promise if self.cls == "NFR" else None,
            "tier": self.tier,
            "label_source": self.label_source,
            "confidence": self.confidence,
            "keyword_hint": self.keyword_hint,
            "source": {
                "section_id": self.section_id,
                "section_path": self.section_path,
                "xml_element": self.element,
                "original_req_id": self.original_req_id,
                "modifier": self.modifier,
                "modal": self.modal,
            },
        }


@dataclass
class ContextUnit:
    """Frase (ou item) de seção discursiva, candidata à entrada bruta."""

    text: str
    section_id: str
    section_path: list
    role: str
    is_item: bool
    modal: str = None


@dataclass
class Extraction:
    requirements: list
    context: list
    duplicates_removed: int
    section_roles: list


def clean_req_text(text):
    """Remove prefixos de ID ("REQ-1:", "OE-1:", "2.1.1") e marcas (M)/(O)."""
    modifier = None
    m = _MANDATORY_MARK.search(text)
    if m:
        modifier = m.group(1)
    text = _MANDATORY_MARK.sub(" ", text)
    prev = None
    while prev != text:
        prev = text
        text = _ID_PREFIX.sub("", text, count=1)
    return normalize_ws(text), modifier


def keyword_hint(text):
    for sub, rx in _KW:
        if rx.search(text):
            return sub
    return None


def _label(role, subtype, text, section_title, element):
    """Retorna (classe, subtipo, label_source, confiança, keyword_hint)."""
    hint = keyword_hint(text)
    if role == "nfr":
        # Seção RNF genérica ("Quality Attributes", "Non-functional"): o
        # subtipo vem das pistas lexicais quando houver.
        if subtype == "OT" and hint:
            return "NFR", hint, "section+keyword", 0.85, hint
        return "NFR", subtype, "section", 0.9, hint
    if role == "fr":
        return "FR", None, "section", 0.85, hint
    if role in ("context", "scenario") and element == "req":
        for rx, sub in _CONTEXT_REQ_HINTS:
            if rx.search(section_title):
                return "NFR", sub, "section", 0.75, hint
    if hint:
        return "NFR", hint, "keyword", 0.6, hint
    return "FR", None, "default", 0.5, hint


class _Builder:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        self.reqs = []
        self.seen = {}
        self.duplicates = 0

    def add(self, text, sec, role, subtype, tier, element, modal, original_req_id=None, modifier=None):
        text, mark = clean_req_text(text)
        modifier = modifier or mark
        if len(content_tokens(text)) < MIN_CONTENT_TOKENS:
            return None
        key = " ".join(content_tokens(text))
        if key in self.seen:
            self.duplicates += 1
            return self.seen[key]
        cls, sub, source, conf, hint = _label(role, subtype, text, " / ".join(sec.path), element)
        if modal == "weak":
            conf = round(conf - 0.1, 2)
        req = Requirement(
            rid=f"{self.doc_id}:R{len(self.reqs) + 1:04d}",
            text=text,
            cls=cls,
            subtype=sub,
            tier=tier,
            label_source=source,
            confidence=conf,
            section_id=sec.sid,
            section_path=[normalize_ws(t) for t in sec.path if normalize_ws(t)],
            element=element,
            original_req_id=original_req_id,
            modifier=modifier,
            keyword_hint=hint,
            modal=modal,
            tokens=token_set(text),
        )
        self.reqs.append(req)
        self.seen[key] = req
        return req


_IPO_TITLES = {"input": "Input", "inputs": "Input", "processing": "Processing", "output": "Output", "outputs": "Output"}


def _ipo_groups(doc):
    """Padrão IEEE 830 (A.x) "Description/Input/Processing/Output" por função.

    Retorna {índice da seção-pai: {"Input": txt, ...}} e o conjunto de índices
    das subseções I/P/O consumidas.
    """
    by_path = {tuple(s.path): i for i, s in enumerate(doc.sections)}
    groups, consumed = {}, set()
    for i, sec in enumerate(doc.sections):
        key = _IPO_TITLES.get(normalize_ws(sec.title).strip(" .:").lower())
        parent = by_path.get(tuple(sec.path[:-1]))
        if key is None or parent is None:
            continue
        text = normalize_ws(" ".join(b.text for b in sec.blocks))
        if text and text.lower().strip(" .") not in ("none", "n/a", "-"):
            groups.setdefault(parent, {})[key] = (i, text)
    # Só sintetiza quando não há modais: se "Processing" já traz frases
    # "shall" (ex.: THEMAS), elas são extraídas individualmente.
    out = {}
    for parent, g in groups.items():
        if "Processing" in g and not any(modal_strength(s) for _, t in g.values() for s in split_sentences(t)):
            out[parent] = {k: t for k, (_, t) in g.items()}
            consumed.update(i for i, _ in g.values())
    return out, consumed


def extract(doc):
    b = _Builder(doc.doc_id)
    context = []
    roles = []
    ipo, ipo_consumed = _ipo_groups(doc)
    for idx, sec in enumerate(doc.sections):
        role, subtype = resolve_role(sec.path)
        roles.append({"section_id": sec.sid, "path": sec.path, "role": role, "subtype": subtype})
        if role == "meta" or idx in ipo_consumed:
            continue
        req_section = role in ("fr", "nfr", "unknown")
        if req_section and idx in ipo:
            g = ipo[idx]
            parts = [f"{normalize_ws(sec.title).rstrip('. ')}."] + [f"{k}: {g[k]}" for k in ("Input", "Processing", "Output") if k in g]
            r = b.add(" ".join(parts), sec, role, subtype, "primary", "ipo", None)
            if r is not None:
                r.label_source, r.confidence = "ipo-structure", 0.6
        # Frase-requisito terminada em ":" aguardando os itens da lista. Só é
        # registrada quando os itens chegam (ou a lista termina), pois sozinha
        # ("The cart shall show the following:") costuma ser curta demais.
        lead = None
        assumption = role == "context" and _ASSUMPTION.search(sec.path[-1] if sec.path else "")
        for blk in sec.blocks:
            if blk.kind == "req" and assumption:
                # Premissas marcadas com <req> (ex.: gamma j AS-x) não são
                # requisitos (IEEE 830 §2.5): vão para a entrada como contexto.
                context.append(ContextUnit(clean_req_text(blk.text)[0], sec.sid, sec.path, role, False, None))
                continue
            if blk.kind == "req":
                lead = _close_lead(b, lead)
                txt = blk.text
                b.add(txt, sec, role, subtype, "primary", "req", modal_strength(txt), blk.req_id, blk.modifier)
                continue
            if blk.kind == "para":
                for sent in split_sentences(blk.text):
                    lead = _close_lead(b, lead)
                    modal = modal_strength(sent)
                    if req_section:
                        if modal and sent.rstrip().endswith(":"):
                            lead = {"base": sent, "items": [], "req": None, "args": (sec, role, subtype), "modal": modal}
                        elif modal:
                            b.add(sent, sec, role, subtype, "primary", "text_body", modal)
                    else:
                        context.append(ContextUnit(sent, sec.sid, sec.path, role, False, modal))
                        if modal == "strong":
                            b.add(sent, sec, role, subtype, "secondary", "text_body", modal)
                continue
            # item de lista
            modal = modal_strength(blk.text)
            if req_section:
                if lead is not None and blk.lead and len(lead["items"]) < MAX_MERGED_ITEMS:
                    lead["items"].append(blk.text.rstrip(";.,"))
                    merged = f"{lead['base']} " + "; ".join(lead["items"]) + "."
                    if lead["req"] is None:
                        lead["req"] = b.add(merged, *lead["args"], "primary", "text_body+items", lead["modal"])
                    else:
                        lead["req"].text = clean_req_text(merged)[0]
                        lead["req"].tokens = token_set(lead["req"].text)
                elif modal:
                    b.add(blk.text, sec, role, subtype, "primary", "item", modal)
            else:
                context.append(ContextUnit(blk.text, sec.sid, sec.path, role, True, modal))
                if modal == "strong":
                    b.add(blk.text, sec, role, subtype, "secondary", "item", modal)
        _close_lead(b, lead)
    return Extraction(b.reqs, context, b.duplicates, roles)


def _close_lead(b, lead):
    """Registra uma frase-guia que não recebeu itens como requisito comum."""
    if lead is not None and lead["req"] is None and not lead["items"]:
        b.add(lead["base"], *lead["args"], "primary", "text_body", lead["modal"])
    return None
