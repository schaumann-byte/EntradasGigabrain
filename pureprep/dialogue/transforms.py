"""Transformações semânticas determinísticas sobre o texto canônico de um
requisito. Usadas pelo *plano* (não pelo realizador): o resultado de cada
transformação é o conteúdo que a fala deve expressar, e os detalhes
retornados alimentam o gabarito (o que foi trocado, removido ou vago).

Cada função devolve ``None`` quando não se aplica ao requisito.
"""

import re

from ..textsim import normalize_ws

# número "de grandeza": não pega seções (3.2.1), IDs (R12, FR-3), anos ou versões
_NUM = re.compile(r"(?<![\w./\-])(\d{1,7}(?:\.\d+)?)(?![\w/\-]|\.\d)(\s*%|\s+percent\b)?(?:\s+([A-Za-z]+))?")

_UNITS = {
    "ms", "millisecond", "milliseconds", "second", "seconds", "sec", "secs", "minute", "minutes", "min", "mins",
    "hour", "hours", "hr", "hrs", "day", "days", "week", "weeks", "month", "months", "year", "years",
    "character", "characters", "char", "chars", "digit", "digits", "byte", "bytes", "kb", "mb", "gb", "tb",
    "kbps", "mbps", "item", "items", "entry", "entries", "record", "records", "user", "users", "time", "times",
    "attempt", "attempts", "line", "lines", "page", "pages", "transaction", "transactions", "request", "requests",
    "meter", "meters", "metre", "metres", "km", "kilometers", "m", "cm", "mm", "hz", "khz", "mhz", "degrees",
    "level", "levels", "file", "files", "message", "messages", "session", "sessions", "km/h", "kph", "mph",
}
_TIME_UNITS = {"ms", "millisecond", "milliseconds", "second", "seconds", "sec", "secs", "minute", "minutes", "min",
               "mins", "hour", "hours", "hr", "hrs", "day", "days", "week", "weeks", "month", "months", "year", "years"}


def _fmt(x, like):
    if "." in like:
        decimals = len(like.split(".")[1])
        return f"{x:.{decimals}f}"
    return str(int(round(x)))


def _plural(unit):
    u = unit.lower()
    if u.endswith("s") or u in {"ms", "kb", "mb", "gb", "tb", "kbps", "mbps", "km", "m", "cm", "mm", "hz", "khz", "mhz", "mph", "kph"}:
        return unit
    if u.endswith("y") and not u.endswith(("ay", "ey", "oy")):
        return unit[:-1] + "ies"
    return unit + "s"


_QTY_CUE = re.compile(r"\b(at least|at most|up to|more than|less than|fewer than|no more than|maximum( of)?|minimum( of)?|max\.?|min\.?|within|every|over|under|exceeds?|limit( of)?)\s+$", re.I)


def find_quantities(text):
    """Quantidades candidatas (número + unidade opcional), ignorando anos."""
    out = []
    for m in _NUM.finditer(text):
        num, pct, unit = m.group(1), m.group(2), m.group(3)
        val = float(num)
        if not pct and "." not in num and 1900 <= val <= 2100:
            continue  # ano
        start = m.start(1)
        if pct:
            end, kind = m.end(2), "percent"
        elif unit and unit.lower() in _UNITS:
            end, kind = m.end(3), ("time" if unit.lower() in _TIME_UNITS else "count")
        elif _QTY_CUE.search(text[max(0, start - 20) : start]):
            end, kind = m.end(1), "number"
        else:
            continue  # número solto ("stage 2"): não é grandeza
        out.append({"start": start, "end": end, "num": num, "unit": (unit if kind in ("time", "count") else None),
                    "kind": kind, "span": text[start:end]})
    return out


def _mutate_value(num, kind, rng):
    v = float(num)
    if kind == "percent":
        if v >= 99:
            cands = [95, 90, 98]
        elif v >= 50:
            cands = [max(1, v - 10), min(99, v + 5), max(1, v - 20)]
        else:
            cands = [v * 2, max(1, v / 2)]
    elif v == 0:
        cands = [1, 5]
    elif v < 1:
        cands = [v * 2, v * 5]
    elif v <= 3:
        cands = [v + 1, v * 3, v * 5]
    else:
        cands = [v * 2, v / 2, v * 3, v * 1.5]
    cands = [c for c in cands if _fmt(c, num) != _fmt(v, num) and c > 0]
    return _fmt(rng.choice(cands), num)


def mutate_quantity(text, rng):
    """Troca o valor de uma quantidade (conflito/inconsistência de valor)."""
    qs = find_quantities(text)
    if not qs:
        return None
    q = rng.choice(qs)
    new_num = _mutate_value(q["num"], q["kind"], rng)
    tail = text[q["start"] + len(q["num"]) : q["end"]]
    if q["unit"] and float(q["num"]) == 1 and float(new_num) != 1:
        tail = tail[: len(tail) - len(q["unit"])] + _plural(q["unit"])
    new_span = new_num + tail
    return {
        "text": text[: q["start"]] + new_span + text[q["end"] :],
        "kind": "value",
        "original_value": q["span"],
        "proposed_value": new_span,
    }


_ROLES = ["administrator", "manager", "operator", "supervisor", "any user", "registered user", "guest user"]
_ACTOR = re.compile(
    r"\b(?:the|a|an|each|every|any|all)\s+((?:system |registered |authorized |authorised |end |guest )?"
    r"(?:users?|administrators?|admins?|operators?|managers?|supervisors?|customers?|clients?|staff|drivers?|controllers?))\b"
    # não troca o papel quando ele é modificador de substantivo composto ("user interface", "driver's")
    r"(?!['’]s\b|-|\s+(?:interfaces?|stations?|names?|accounts?|data|manuals?|groups?|ids?|inputs?|profiles?|guides?|"
    r"documentation|types?|levels?|friendly|desks?|cabs?|machine|consoles?|panels?|screens?|sessions?|roles?|rights|"
    r"privileges|permissions|requests?|community|base|experience|preferences?|settings?|training)\b)",
    re.I,
)


def mutate_actor(text, rng):
    """Troca o papel de quem executa/acessa (inconsistência de ator)."""
    m = _ACTOR.search(text)
    if not m:
        return None
    old = m.group(0).strip()
    head = m.group(1).lower()
    cands = [r for r in _ROLES if r.split()[-1] not in head]
    new = "the " + rng.choice(cands) if not old.lower().startswith(("any", "all", "every", "each")) else rng.choice(cands)
    if old[0].isupper():
        new = new[0].upper() + new[1:]
    return {"text": text[: m.start()] + new + text[m.end() :], "kind": "actor", "original_value": old, "proposed_value": new}


_POLAR = re.compile(r"\b(shall|must|should|will)(\s+not)?\b", re.I)
_COND_BEFORE = re.compile(r"\b(if|when|unless|whenever)\b", re.I)  # modal dentro de condição: inverter mudaria a condição


def mutate_polarity(text, rng):
    """Inverte a polaridade do modal principal ("shall" <-> "shall not").

    Só serve para inconsistência: "not" é stopword, então a variante é
    lexicalmente indistinguível do original e não pode virar distrator."""
    m = _POLAR.search(text)
    if not m or _COND_BEFORE.search(text[: m.start()]):
        return None
    modal, neg = m.group(1), m.group(2)
    new = modal if neg else f"{modal} not"
    return {"text": text[: m.start()] + new + text[m.end() :], "kind": "polarity",
            "original_value": m.group(0), "proposed_value": new}


def mutate(text, rng):
    """Variante conflitante: valor numérico se houver, senão o ator."""
    return mutate_quantity(text, rng) or mutate_actor(text, rng)


def mutate_for_inconsistency(text, rng):
    return mutate_quantity(text, rng) or mutate_actor(text, rng) or mutate_polarity(text, rng)


# ---------------------------------------------------------------------------
# ambiguidade
# ---------------------------------------------------------------------------

def _vague_for(q, rng):
    kind, v = q["kind"], float(q["num"])
    if kind == "percent":
        return "most" if v >= 50 else "some"
    if v <= 5:
        quant = rng.choice(["a couple of", "a few"])
    elif v <= 60:
        quant = rng.choice(["a few", "several", "some"])
    else:
        quant = rng.choice(["lots of", "many", "a large number of"])
    if q["unit"]:
        return f"{quant} {_plural(q['unit'])}"
    return rng.choice(["some", "a reasonable number of"]) if kind == "number" else quant


def vague_quantity(text, rng):
    qs = find_quantities(text)
    if not qs:
        return None
    q = rng.choice(qs)
    rep = _vague_for(q, rng)
    after = text[q["end"] :]
    if q["kind"] == "percent" and not re.match(r"\s+of\b", after):
        rep = "high" if float(q["num"]) >= 50 else "some"
    return {"text": text[: q["start"]] + rep + after, "kind": "vague_quantity", "removed": q["span"], "replacement": rep}


_HUMAN_SUBJ = re.compile(
    r"^(?P<subj>(?:the|a|an|each|every|any|all)\s+(?:[\w\-]+\s+){0,2}"
    r"(?:users?|administrators?|admins?|operators?|managers?|supervisors?|customers?|clients?|staff|drivers?|controllers?|personnel))"
    r"(?=\s+(?:shall|must|should|will|can|may|would|needs? to|has to|have to)\b)",  # o ator é o sujeito da frase
    re.I,
)
_THING_SUBJ = re.compile(r"^(?P<subj>(?:the|this|each|every|all)\s+(?:[\w\-]+\s+){0,2}[\w\-]+)\s+(?=shall|must|should|will|needs to|has to)\b", re.I)


def vague_actor(text, rng):
    m = _HUMAN_SUBJ.match(text)
    if not m:
        return None
    rep = rng.choice(["Someone", "They", "People"])
    return {"text": rep + " " + text[m.end() :].lstrip(), "kind": "vague_actor", "removed": m.group("subj"), "replacement": rep.lower()}


def vague_reference(text, rng):
    m = _THING_SUBJ.match(text)
    if not m or m.group("subj").lower().split()[-1] in {"system", "software", "application", "product", "tool"}:
        return None
    rep = rng.choice(["It", "That", "That thing"])
    return {"text": rep + " " + text[m.end() :].lstrip(), "kind": "vague_reference", "removed": m.group("subj"), "replacement": rep.lower()}


def ambiguity(text, rng):
    """Aplica um tipo de ambiguidade. Quantidade e ator têm prioridade (são
    os mais informativos); ``optionality`` (modal hesitante) sempre se aplica
    e é realizado pelo realizador via ``flags['hedge']``."""
    options = [f for f in (vague_quantity, vague_actor, vague_reference)]
    rng.shuffle(options)
    options.sort(key=lambda f: f is not vague_quantity)  # quantidade primeiro, se houver
    for f in options:
        r = f(text, rng)
        if r:
            return r
    return {"text": text, "kind": "optionality", "removed": None, "replacement": None}


# ---------------------------------------------------------------------------
# incompletude
# ---------------------------------------------------------------------------

_TRAIL_COND = re.compile(
    r",?\s+(?=\b(?:when|whenever|if|unless|after|before|once|in case|except|so that|in order to|provided that|until|while|within|without)\b)",
    re.I,
)
_LEAD_COND = re.compile(r"^(?P<clause>(?:if|when|whenever|once|after|before|in case|unless)\b[^,]{6,}?),\s*", re.I)


def missing_value(text, rng):
    qs = find_quantities(text)
    if not qs:
        return None
    q = rng.choice(qs)
    unit = f" {_plural(q['unit'])}" if q["unit"] else ""
    rep = (rng.choice(["a certain number of", "some number of"]) + unit) if unit else rng.choice(["a certain value", "some value"])
    if q["kind"] == "percent":
        rep = "a certain percentage"
    return {"text": text[: q["start"]] + rep + text[q["end"] :], "kind": "missing_value", "missing": q["span"]}


def missing_condition(text, rng):
    # a última oração condicional que deixe uma frase principal razoável
    for m in reversed(list(_TRAIL_COND.finditer(text))):
        head, clause = text[: m.start()], text[m.end() :]
        if len(head.split()) >= 5 and len(clause.split()) >= 3:
            return {"text": head.rstrip(" ,;"), "kind": "missing_condition", "missing": clause.rstrip(" .;")}
    m = _LEAD_COND.match(text)
    if m and len(text[m.end() :].split()) >= 5:
        rest = text[m.end() :]
        return {"text": rest[0].upper() + rest[1:], "kind": "missing_condition", "missing": m.group("clause")}
    return None


def truncated(text, rng):
    words = text.split()
    if len(words) < 9:
        return None
    cut = max(5, int(len(words) * rng.uniform(0.5, 0.7)))
    return {"text": " ".join(words[:cut]).rstrip(" ,;:"), "kind": "truncated", "missing": " ".join(words[cut:])}


def incompleteness(text, rng):
    options = [missing_value, missing_condition, truncated]
    rng.shuffle(options)
    for f in options:
        r = f(text, rng)
        if r:
            return r
    return None


# ---------------------------------------------------------------------------
# bagunça: quebrar uma fala em duas partes (interrupção)
# ---------------------------------------------------------------------------

_BREAK = re.compile(r",\s+|;\s+|\s+(?=(?:and|or|which|so that|when|if|including|such as|but)\b)")


def split_for_interruption(text):
    """Divide o requisito num ponto de oração próximo do meio (ou na metade
    das palavras). Retorna (parte1, parte2) ou None se for curto demais."""
    text = normalize_ws(text)
    words = text.split()
    if len(words) < 10:
        return None
    mid = len(text) / 2
    best = None
    for m in _BREAK.finditer(text):
        left, right = text[: m.start()], text[m.end() :]
        if len(left.split()) >= 4 and len(right.split()) >= 4:
            d = abs(m.start() - mid)
            if best is None or d < best[0]:
                best = (d, left, right)
    if best:
        return best[1].rstrip(" ,;"), best[2]
    k = len(words) // 2
    return " ".join(words[:k]), " ".join(words[k:])
