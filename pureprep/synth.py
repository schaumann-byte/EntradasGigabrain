"""Construção da entrada bruta (``input_raw.txt``) em três modos.

- ``context``  : texto real das seções discursivas do SRS (propósito, escopo,
                 perspectiva, usuários, cenários). Nenhum texto é inventado; a
                 cobertura do gabarito é PARCIAL e medida por ``support``.
- ``notes``    : lista informal de necessidades (como o texto-fonte usado no
                 REQINONE), obtida "desformalizando" cada requisito do
                 gabarito com regras determinísticas. Cobertura total.
- ``dialogue`` : transcrição de reunião sintética (Analista × stakeholders),
                 com turnos, perguntas, eco de confirmação, conversa fora do
                 tópico e ruído de fala (hesitações, muletas, gagueira,
                 marcas [laughter]) usando os mesmos léxicos do projeto
                 "Sanitização de Texto". O ruído é ADITIVO: nenhuma palavra do
                 requisito é removida, logo o conteúdo semântico é preservado.

Todas as transformações são determinísticas dada a semente.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .taxonomy import normalize_title
from .textsim import containment, modal_strength, normalize_ws, token_set

_RES = json.loads((Path(__file__).parent / "resources" / "noise_en.json").read_text(encoding="utf-8"))


@dataclass
class Segment:
    sid: str
    start: int
    end: int
    meta: dict = field(default_factory=dict)

    def to_json(self):
        return {"id": self.sid, "start": self.start, "end": self.end, **self.meta}


class _Writer:
    """Acumula texto registrando os offsets de cada segmento rastreável."""

    def __init__(self, prefix):
        self.parts = []
        self.pos = 0
        self.segments = []
        self.prefix = prefix

    def raw(self, text):
        self.parts.append(text)
        self.pos += len(text)

    def seg(self, text, **meta):
        start = self.pos
        self.raw(text)
        s = Segment(f"{self.prefix}{len(self.segments) + 1}", start, self.pos, meta)
        self.segments.append(s)
        return s

    def text(self):
        return "".join(self.parts)


# ---------------------------------------------------------------------------
# rastreabilidade: qual trecho da entrada sustenta cada requisito
# ---------------------------------------------------------------------------

def support(reqs, text, segments, window=3):
    """Para cada requisito, maior cobertura (containment) dos seus tokens por
    uma janela de até ``window`` segmentos consecutivos da entrada.

    Retorna {rid: (score, [segment ids])}.
    """
    seg_tokens = [token_set(text[s.start : s.end]) for s in segments]
    out = {}
    for r in reqs:
        best, best_ids = 0.0, []
        for i in range(len(segments)):
            acc = frozenset()
            for w in range(window):
                if i + w >= len(segments):
                    break
                acc = acc | seg_tokens[i + w]
                sc = containment(r.tokens, acc)
                if sc > best + 1e-9:
                    best, best_ids = sc, [s.sid for s in segments[i : i + w + 1]]
            if best >= 0.999:
                break
        out[r.rid] = (round(best, 3), best_ids)
    return out


# ---------------------------------------------------------------------------
# modo context
# ---------------------------------------------------------------------------

def build_context(doc, ext):
    w = _Writer("S")
    w.raw(f"Project: {short_title(doc.title)}\n\n")
    prev_section, prev_item = None, None
    for u in ext.context:
        if prev_section is not None and (u.section_id, tuple(u.section_path)) != prev_section:
            w.raw("\n\n")
        elif prev_item is not None and (u.is_item or prev_item):
            w.raw("\n")
        elif prev_section is not None:
            w.raw(" ")
        if u.is_item:
            w.raw("- ")
        w.seg(u.text, section_id=u.section_id, section_path=[t for t in u.section_path if t])
        prev_section, prev_item = (u.section_id, tuple(u.section_path)), u.is_item
    return w.text().rstrip() + "\n", w.segments


# ---------------------------------------------------------------------------
# desformalização (requisito → fala/nota de stakeholder)
# ---------------------------------------------------------------------------

_HEAD = re.compile(
    r"^(?P<subj>(?:(?:the|a|an|each|every|all|any)\s+)?[\w/&'\-]+(?:\s+[\w/&'\-]+){0,3}?)\s+"
    r"(?P<modal>shall|must|should|will|needs to|has to)\s+(?P<neg>not\s+)?(?P<able>be able to\s+)?(?P<rest>.+)$",
    re.I,
)
_HUMAN = re.compile(r"\b(users?|operators?|drivers?|admin(istrator)?s?|customers?|clients?|players?|staff|personnel|controllers?|students?|police)\b", re.I)


def _lower_first(s):
    if len(s) > 1 and s[0].isupper() and not s[1].isupper():
        return s[0].lower() + s[1:]
    return s


def deformalize(text, rng):
    """Reescreve um requisito formal como necessidade informal.

    Só troca palavras funcionais (modal, sujeito genérico); as palavras de
    conteúdo são mantidas para preservar a semântica e a rastreabilidade.
    """
    t = normalize_ws(text).rstrip(" .;")
    m = _HEAD.match(t)
    if m:
        subj = _lower_first(m.group("subj"))
        rest = m.group("rest")
        able = bool(m.group("able"))
        if m.group("neg"):
            tpl = rng.choice(["{s} should never {r}", "we don't want {s} to {r}", "{s} must not {r}"])
            r = ("be able to " if able else "") + rest
        elif _HUMAN.search(subj) or able:
            tpl = rng.choice([
                "{s} would need to be able to {r}",
                "it's important that {s} can {r}",
                "{s} should be able to {r}",
                "we want {s} to be able to {r}",
            ])
            r = rest
        else:
            tpl = rng.choice([
                "we need {s} to {r}",
                "{s} should {r}",
                "I'd like {s} to {r}",
                "{s} would have to {r}",
                "{s} ought to {r}",
            ])
            r = rest
        return tpl.format(s=subj, r=r)
    if modal_strength(t):
        repl = rng.choice(["should", "will need to", "ought to"])
        return _lower_first(re.sub(r"\b(shall|must)\b", repl, t, count=1, flags=re.I))
    return rng.choice(["", "also, ", "one thing: ", "and "]) + _lower_first(t)


_GENERIC_TOPIC = re.compile(
    r"^(functional requirements?|requirements?|specific requirements|engineering requirements|description|"
    r"stimulus.*|processing|input|output|introduction|general|system features|functions?|functionality|"
    r"other nonfunctional requirements|non-?functional requirements|use case.*|action.*|module.*|)$"
)


def topic_of(req):
    for title in reversed(req.section_path):
        t = normalize_title(title)
        t = re.sub(r"\(srs\s*-?\s*\d+\)", "", t).strip()
        if not _GENERIC_TOPIC.match(t) and len(t) < 60:
            return t
    return "general needs"


def _groups(reqs):
    groups = []
    for r in reqs:
        tp = topic_of(r)
        if groups and groups[-1][0] == tp:
            groups[-1][1].append(r)
        else:
            groups.append((tp, [r]))
    return groups


_TITLE_NOISE = re.compile(
    r"\b((software|system) )?requirements? specifications?\b|\(srs\)|\bsrs\b|\bdocument\b|\bversion\s*[\d.]+|^\s*for\b",
    re.I,
)
_META_INTRO = re.compile(r"\b(this|the present) (document|srs|specification|section)\b|requirements? specification|\bsrs\b", re.I)


def short_title(title):
    t = normalize_ws(_TITLE_NOISE.sub(" ", normalize_ws(title)))
    t = normalize_ws(_TITLE_NOISE.sub(" ", t)).strip(" -:,")
    return (t[:70] + "...") if len(t) > 70 else (t or normalize_ws(title)[:70])


def _intro_sentences(ext, k=3):
    """Primeiras frases discursivas SEM modal (não vazam requisitos)."""
    out = []
    for u in ext.context:
        if not u.is_item and not u.modal and not _META_INTRO.search(u.text) and 6 <= len(u.text.split()) <= 60:
            out.append(u.text)
        if len(out) >= k:
            break
    return out


# ---------------------------------------------------------------------------
# modo notes
# ---------------------------------------------------------------------------

def build_notes(doc, ext, reqs, rng, merge_prob=0.15, header_prob=0.8):
    w = _Writer("N")
    w.raw(f"Stakeholder needs - {short_title(doc.title)}\n")
    intro = _intro_sentences(ext)
    if intro:
        w.raw("\nContext: ")
        w.seg(" ".join(intro), kind="context")
        w.raw("\n")
    for topic, grp in _groups(reqs):
        grp = grp[:]
        rng.shuffle(grp)
        w.raw("\n")
        if rng.random() < header_prob:
            w.raw(f"{topic}:\n")
        i = 0
        while i < len(grp):
            if i + 1 < len(grp) and rng.random() < merge_prob:
                pair = grp[i : i + 2]
                w.raw("- ")
                w.seg(f"{deformalize(pair[0].text, rng)}; also {deformalize(pair[1].text, rng)}", gt_ids=[r.rid for r in pair])
                i += 2
            else:
                w.raw("- ")
                w.seg(deformalize(grp[i].text, rng), gt_ids=[grp[i].rid])
                i += 1
            w.raw("\n")
    return w.text(), w.segments


# ---------------------------------------------------------------------------
# modo dialogue
# ---------------------------------------------------------------------------

_QUESTIONS = [
    "So, let's talk about {t}. What do you need there?",
    "Okay, next topic: {t}. How should that work?",
    "Can you walk me through {t}?",
    "What are your expectations regarding {t}?",
    "Right. And {t}? Anything specific?",
]
_NFR_QUESTIONS = [
    "What about {t}? Any constraints we should know about?",
    "Let's cover {t} now. What level do you expect?",
]
_BACKCHANNEL = ["Mm-hmm.", "Okay.", "Right.", "Got it.", "Okay, noted.", "Yeah."]
_OFFTOPIC = [
    ("Client", "Sorry, can everyone hear me? My connection is a bit unstable today."),
    ("Analyst", "Hold on, let me share my screen again."),
    ("EndUser", "By the way, are we still meeting on Thursday?"),
    ("TechLead", "Sorry, I was on mute."),
    ("Client", "Let's try to finish on time, I have another call after this."),
]
_CONFIRM = ["Yeah, exactly.", "Yes, that's it.", "Right, correct.", "Mm-hmm, yes."]


def add_disfluency(text, rng, rate):
    """Insere hesitações, muletas, gagueira e marcas de ruído (só adições)."""
    if rate <= 0:
        return text
    words = text.split()
    out = []
    if rng.random() < rate * 3:
        out.append(rng.choice(_RES["hesitation"]).capitalize() + ",")
    for i, wd in enumerate(words):
        if i and rng.random() < rate:
            out.append(rng.choice(_RES["filler"] + _RES["hesitation"]))
        if len(wd) <= 4 and wd.isalpha() and rng.random() < rate / 3:
            out.append(wd)  # gagueira: "the the"
        out.append(wd)
    if rng.random() < rate / 2:
        out.insert(rng.randrange(1, len(out) + 1), f"[{rng.choice(_RES['noise_tags'])}]")
    return " ".join(out)


def sample_reqs(reqs, cap, rng):
    """Amostra estratificada por classe preservando a ordem do documento."""
    if cap is None or len(reqs) <= cap:
        return list(reqs)
    fr = [r for r in reqs if r.cls == "FR"]
    nfr = [r for r in reqs if r.cls == "NFR"]
    k_nfr = min(len(nfr), max(round(cap * len(nfr) / len(reqs)), min(len(nfr), cap // 4)))
    keep = set(r.rid for r in rng.sample(nfr, k_nfr)) | set(r.rid for r in rng.sample(fr, min(len(fr), cap - k_nfr)))
    return [r for r in reqs if r.rid in keep]


def build_dialogue(doc, ext, reqs, rng, noise=0.08, confirm_prob=0.12, offtopic_prob=0.06):
    w = _Writer("T")

    def turn(spk, text, **meta):
        w.raw(f"{spk}: ")
        w.seg(text, speaker=spk, **meta)
        w.raw("\n")

    turn("Analyst", add_disfluency(f"Okay, let's get started. Thanks for joining. Today I'd like to understand what you need for {short_title(doc.title)}.", rng, noise))
    intro = _intro_sentences(ext)
    if intro:
        turn("Client", add_disfluency(" ".join(intro), rng, noise), kind="context")
    for topic, grp in _groups(reqs):
        is_nfr = sum(r.cls == "NFR" for r in grp) > len(grp) / 2
        q = rng.choice(_NFR_QUESTIONS if is_nfr else _QUESTIONS).format(t=topic)
        turn("Analyst", add_disfluency(q, rng, noise))
        speakers = ["TechLead", "Client"] if is_nfr else ["Client", "EndUser"]
        i = 0
        while i < len(grp):
            n = 2 if (i + 1 < len(grp) and rng.random() < 0.35) else 1
            chunk = grp[i : i + n]
            spk = rng.choice(speakers)
            said = ". ".join(deformalize(r.text, rng) for r in chunk)
            said = said[0].upper() + said[1:] + "."
            turn(spk, add_disfluency(said, rng, noise), gt_ids=[r.rid for r in chunk])
            if rng.random() < confirm_prob:
                echo = deformalize(chunk[-1].text, rng)
                turn("Analyst", add_disfluency(f"Just to confirm, {echo}?", rng, noise), gt_ids=[chunk[-1].rid], kind="echo")
                turn(spk, rng.choice(_CONFIRM))
            elif rng.random() < 0.3:
                turn("Analyst", rng.choice(_BACKCHANNEL))
            i += n
        if rng.random() < offtopic_prob:
            spk, txt = rng.choice(_OFFTOPIC)
            turn(spk, add_disfluency(txt, rng, noise), kind="offtopic")
    turn("Analyst", add_disfluency("Great, I think that covers it for today. I'll write this up and send it around.", rng, noise))
    return w.text(), w.segments
