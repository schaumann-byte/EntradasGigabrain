"""Utilitários de texto: normalização, segmentação em frases, detecção de
modais de requisito e similaridade lexical.

Tudo em biblioteca padrão para manter o pipeline reprodutível sem modelos.
A similaridade é lexical (conjunto de tokens de conteúdo com stemming
simples); para avaliação semântica ver a seção de recomendações do relatório.
"""

import re
import unicodedata

STOPWORDS = frozenset(
    """a an the and or but if then else of to in on at by for with from as is are was
    were be been being this that these those it its into onto over under than such
    which who whom whose what when where while there their them they he she his her
    we our us you your i me my shall must should will would may might can could
    has have had do does did not no nor all any each some other also only same so
    very just about within without upon via per etc able""".split()
)

# Modais fortes: indicam requisito vinculante (IEEE 830 / INCOSE GtWR).
STRONG_MODAL = re.compile(
    r"\b(shall|must|is required to|are required to|has to|have to|needs to|need to)\b",
    re.I,
)
# Modais fracos: comuns em SRS acadêmicos/Wiegers ("The system will ...").
WEAK_MODAL = re.compile(r"\b(should|will|is able to|are able to|may not|can not|cannot)\b", re.I)

# Frases de metadocumento que contêm modais mas não são requisitos.
META_SENTENCE = re.compile(
    r"^\s*(this|the following|these)\s+(document|section|chapter|srs|specification|subsections?|paragraphs?)\b"
    r"|\b(this document|this section|this srs|this specification)\s+(will|shall|is|describes|provides|contains)\b",
    re.I,
)

_ABBREV = ("e.g.", "i.e.", "etc.", "vs.", "fig.", "no.", "approx.", "min.", "max.", "sec.", "ref.")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")


def normalize_ws(text):
    """Normaliza Unicode (NFKC desfaz ligaturas "ﬁ" vindas de PDF), colapsa
    espaços/quebras e remove caracteres de controle."""
    text = unicodedata.normalize("NFKC", text or "")
    for curly, plain in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u00a0", " "), ("\ufeff", "")):
        text = text.replace(curly, plain)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text):
    """Segmentação de frases por regex, protegendo abreviações comuns."""
    text = normalize_ws(text)
    if not text:
        return []
    protected = text
    for i, ab in enumerate(_ABBREV):
        protected = re.sub(re.escape(ab), f"\x00{i}\x00", protected, flags=re.I)
    parts = _SENT_SPLIT.split(protected)
    out = []
    for p in parts:
        for i, ab in enumerate(_ABBREV):
            p = p.replace(f"\x00{i}\x00", ab)
        p = p.strip()
        if p:
            out.append(p)
    return out


def modal_strength(sentence):
    """Retorna 'strong', 'weak' ou None conforme o modal presente."""
    if META_SENTENCE.search(sentence):
        return None
    if STRONG_MODAL.search(sentence):
        return "strong"
    if WEAK_MODAL.search(sentence):
        return "weak"
    return None


def _stem(tok):
    for suf in ("ations", "ation", "ings", "ing", "ies", "ied", "es", "ed", "ly", "s"):
        if len(tok) > len(suf) + 3 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def content_tokens(text):
    """Tokens de conteúdo (minúsculos, sem stopwords, com stemming simples)."""
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(t) for t in toks if t not in STOPWORDS and len(t) > 1]


def token_set(text):
    return frozenset(content_tokens(text))


def overlap_f1(a, b):
    """F1 de sobreposição de tokens de conteúdo (≈ ROUGE-1 F sobre conjuntos)."""
    sa, sb = (a if isinstance(a, frozenset) else token_set(a)), (b if isinstance(b, frozenset) else token_set(b))
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    if not inter:
        return 0.0
    p, r = inter / len(sb), inter / len(sa)
    return 2 * p * r / (p + r)


def containment(needle, haystack):
    """Fração dos tokens de ``needle`` presentes em ``haystack``."""
    sn = needle if isinstance(needle, frozenset) else token_set(needle)
    sh = haystack if isinstance(haystack, frozenset) else token_set(haystack)
    if not sn:
        return 0.0
    return len(sn & sh) / len(sn)
