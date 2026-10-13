"""Realizador por regras (variante A): transforma o plano em texto de
reunião casual, sem modelos generativos.

Camadas aplicadas a cada conteúdo de requisito:

1. **desformalização** do cabeçalho "<sujeito> shall ..." em fala de
   stakeholder (modelos variados, 1ª pessoa para o usuário final);
2. **léxico casual** ("in order to" → "to", "prior to" → "before"...),
   remoção de referências ao documento ("see section 3.2") e contrações;
3. **quebra de frases longas** e marcadores de discurso ("So, basically,");
4. **marcas do plano** (hesitação de obrigatoriedade, falso começo, fala
   cortada, observação sobre valor faltante);
5. **ruído lexical** (hesitações, gagueira, [crosstalk]) de ``synth``.

O realizador nunca decide conteúdo: tudo o que é semântico vem do plano.
"""

import json
import re
from pathlib import Path

from ..synth import _HEAD, _HUMAN, _lower_first, add_disfluency
from ..textsim import modal_strength, normalize_ws
from .model import VALID_ROLES

_LEX = json.loads((Path(__file__).resolve().parents[1] / "resources" / "casual_en.json").read_text(encoding="utf-8"))
_PHRASES = [(re.compile(r"\b" + re.escape(k) + r"\b", re.I), v) for k, v in _LEX["phrases"].items()]
_CONTRACTIONS = [(re.compile(r"\b" + re.escape(k) + r"\b", re.I), v) for k, v in _LEX["contractions"].items()]
_DOC_REFS = [re.compile(p, re.I) for p in _LEX["doc_refs"]]

_USER_SUBJ = re.compile(r"^(?:the|a|an|each|every|all|any)?\s*(?:end\s+)?users?$", re.I)


def _cap(s):
    s = s.strip()
    return s[:1].upper() + s[1:] if s else s


def _match_case(src, rep):
    return rep[:1].upper() + rep[1:] if src[:1].isupper() else rep


def casual_lexicon(text, rng, p=0.75):
    """Troca expressões formais por coloquiais e remove referências ao
    documento. Cada ocorrência é trocada com probabilidade ``p``."""
    for rx in _DOC_REFS:
        text = rx.sub("", text)
    for rx, rep in _PHRASES:
        text = rx.sub(lambda m, rep=rep: _match_case(m.group(0), rep) if rng.random() < p else m.group(0), text)
    return normalize_ws(text)


def contract(text, rng, p=0.8):
    for rx, rep in _CONTRACTIONS:
        text = rx.sub(lambda m, rep=rep: _match_case(m.group(0), rep) if rng.random() < p else m.group(0), text)
    return text


def split_long(text, max_words=26):
    """Quebra frases longas em ``;`` ou ``, and`` (só palavras funcionais mudam)."""
    if len(text.split()) <= max_words:
        return text
    text = re.sub(r";\s+", ". Also, ", text, count=2)
    m = re.search(r",\s+and\s+", text)
    if m and len(text[: m.start()].split()) >= 12 and len(text[m.end() :].split()) >= 8:
        text = text[: m.start()] + ". And " + text[m.end() :]
    return text


_HEDGE_NEG = ["maybe {s} shouldn't {r}", "I guess we'd rather {s} didn't {r}", "probably {s} shouldn't {r}, not sure"]
_HEDGE_HUMAN = ["maybe {s} could {r}", "it'd be nice if {s} could {r}", "I guess {s} could {r}, if it's not too hard",
                "possibly {s} should be able to {r}, we'll see"]
_HEDGE_THING = ["maybe {s} could {r}", "it'd be nice if {s} could {r}", "{s} might {r}, if possible",
                "ideally {s} would {r}, but I'm not sure it's a must"]
_NEG = ["{s} should never {r}", "we don't want {s} to {r}", "{s} mustn't {r}", "{s} really shouldn't {r}"]
_HUMAN_T = ["{s} should be able to {r}", "{s} would need to be able to {r}", "it's important that {s} can {r}",
            "we want {s} to be able to {r}", "what we really want is for {s} to be able to {r}",
            "for us it's key that {s} can {r}", "{s} must be able to {r}"]
_USER_T = ["as a user, I'd want to be able to {r}", "we, as users, need to be able to {r}",
           "for us users it's important to be able to {r}", "us users should be able to {r}"]
_THING_T = ["we need {s} to {r}", "{s} should {r}", "I'd like {s} to {r}", "{s} would have to {r}",
            "{s} ought to {r}", "we'd want {s} to {r}", "the idea is that {s} will {r}", "{s} has to {r}"]


_MAIN_MODAL = re.compile(r"\b(shall|must)\b", re.I)
_OTHER_MODAL = re.compile(r"\b(has to|have to|needs to|need to|is required to|are required to|should|will)\b", re.I)


def _fill(tpl, x, **kw):
    """Preenche ``{x}`` ajustando a caixa: minúscula se o modelo continua a
    frase ("I'd say {x}"), maiúscula depois de ponto ("Wait. {x}")."""
    before = tpl[: tpl.index("{x}")].rstrip()
    x = _lower_first(x) if before and before[-1] not in ".?!" else _cap(x)
    return tpl.format(x=x, **kw)


def _strip_able(rest):
    return re.sub(r"^be able to\s+", "", rest, flags=re.I)


def deformalize_casual(text, rng, speaker=None, hedge=False):
    """Versão mais variada de ``synth.deformalize`` (que fica congelada no v1)."""
    t = normalize_ws(text).rstrip(" .;")
    m = _HEAD.match(t)
    if m:
        subj = _lower_first(m.group("subj"))
        rest = m.group("rest")
        able = bool(m.group("able"))
        human = bool(_HUMAN.search(subj))
        if m.group("neg"):
            tpl = rng.choice(_HEDGE_NEG if hedge else _NEG)
            r = ("be able to " if able else "") + rest
        elif human or able:
            if hedge:
                tpl, r = rng.choice(_HEDGE_HUMAN if human else _HEDGE_THING), rest
            elif speaker == "EndUser" and _USER_SUBJ.match(subj):
                tpl, r = rng.choice(_USER_T), rest
            else:
                tpl, r = rng.choice(_HUMAN_T), rest
            if "be able to {r}" in tpl or "can {r}" in tpl or "could {r}" in tpl:
                r = _strip_able(r)
        else:
            tpl, r = rng.choice(_HEDGE_THING if hedge else _THING_T), rest
            if "{s} has to" in tpl and subj.split()[-1].endswith("s") and not subj.split()[-1].endswith("ss"):
                tpl = "{s} have to {r}"
        return tpl.format(s=subj, r=r)
    if modal_strength(t):
        if hedge:
            # a hesitação precisa cair no modal principal: shall/must primeiro
            repl = rng.choice(["could maybe", "might"])
            for rx in (_MAIN_MODAL, _OTHER_MODAL):
                if rx.search(t):
                    return _lower_first(rx.sub(repl, t, count=1))
        repl = rng.choice(["should", "will need to", "ought to", "would have to"])
        return _lower_first(_MAIN_MODAL.sub(repl, t, count=1))
    lead = rng.choice(["maybe ", "possibly ", "I think "]) if hedge else rng.choice(["", "also, ", "one thing is, ", "and ", "so "])
    return lead + _lower_first(t)


_PREFIX = ["So, ", "Basically, ", "Well, ", "The thing is, ", "For us, ", "Honestly, ", "Okay so ", "Yeah, so ", "I mean, "]
_SUFFIX = [", you know?", ", if that makes sense.", ", that's the main thing.", ", that's pretty important for us.", ", right?"]


def casual_need(text, rng, speaker=None, flags=None, discourse=True):
    """Fala completa de um requisito (com cabeçalho)."""
    flags = flags or {}
    s = deformalize_casual(text, rng, speaker, hedge=flags.get("hedge", False))
    s = split_long(contract(casual_lexicon(s, rng), rng))
    if discourse and rng.random() < 0.35:
        s = rng.choice(_PREFIX) + _lower_first(s)
    s = _cap(s).rstrip(" .;,")
    if flags.get("incomplete") == "truncated":
        s += rng.choice(["... well, anyway, we can come back to that.", "— sorry, I lost my train of thought.",
                         "... hmm, I'd need to think about the rest."])
    elif flags.get("incomplete") == "missing_value":
        s += ". " + rng.choice(["I'd have to check the exact number though.", "Don't quote me on the number, I'll confirm it.",
                                "I don't remember the exact figure right now."])
    elif flags.get("remark"):
        s += ". " + rng.choice(["There are some exceptions, but I can't remember them right now.",
                                "Well, mostly, there are a few special cases."])
    elif discourse and rng.random() < 0.2:
        s += rng.choice(_SUFFIX)
    else:
        s += "."
    if flags.get("false_start"):
        s = rng.choice(["We need the— actually, ", "So the— sorry, let me rephrase. ", "It should— well, "]) + _lower_first(s)
    return s


def casual_fragment(text, rng):
    """Continuação de fala interrompida (sem cabeçalho)."""
    s = contract(casual_lexicon(normalize_ws(text), rng), rng).rstrip(" .;,")
    return rng.choice(["Anyway, as I was saying, ", "Yeah, so, ", "Right, so, ", "Where was I... yes, "]) + _lower_first(s) + "."


# ---------------------------------------------------------------------------
# modelos dos atos sem conteúdo de requisito
# ---------------------------------------------------------------------------

_OPEN = {
    "kickoff": ["Okay, let's get started. Thanks for joining. Today I'd like to understand what you need for {title}.",
                "Hi everyone, thanks for coming. The idea today is to understand what you need for {title}."],
    "follow-up": ["Hi everyone, thanks for making time again. Let's pick up where we left off on {title}.",
                  "Okay, welcome back. Let's continue with {title}."],
    "review": ["Okay, this should be our last session on {title}, let's go through the remaining points.",
               "Hi all. Let's try to close the remaining points on {title} today."],
}
_RECAP = ["Quick recap from last time: we went over {topics}.", "So, last time we talked about {topics}.",
          "Just to recap, in the last meeting we covered {topics}."]
_RECAP_OPEN = [" We also left a few things open.", " And a couple of points were still open.", ""]
_SMALLTALK = ["How was everyone's weekend?", "Busy week, sorry if I'm a bit slow today.", "Give me a sec, my headset is acting up.",
              "Can everyone see my screen?", "Sorry, I'm a couple of minutes late, the previous call ran over.",
              "Is it just me or is it really cold in here today?"]
_OFFTOPIC = ["Sorry, can everyone hear me? My connection is a bit unstable today.", "Hold on, let me share my screen again.",
             "By the way, are we still meeting on Thursday?", "Sorry, I was on mute.",
             "Let's try to finish on time, I have another call after this.", "Sorry, someone just knocked on my door, go ahead.",
             "Wait, did anyone else lose the audio for a second?", "Can we take a two-minute break after this topic?"]
_ASK = ["So, let's talk about {t}. What do you need there?", "Okay, next topic: {t}. How should that work?",
        "Can you walk me through {t}?", "What are your expectations regarding {t}?", "Right. And {t}? Anything specific?",
        "Okay, what about {t}?", "Let's move on to {t}. What do you have in mind?", "And {t}, how do you see that working?",
        "Alright, {t}. Thoughts?"]
_ASK_NFR = ["What about {t}? Any constraints we should know about?", "Let's cover {t} now. What level do you expect?",
            "What about {t}? Any hard limits there?", "And {t}, how strict do we need to be?"]
_ASK_REVISIT = ["Going back to {t} for a sec, anything else there?", "Sorry, one more thing on {t}.",
                "Can we go back to {t}? I think we missed something."]
_SELF_INTRO = ["Oh, and about {t}, ", "Something on {t}: ", "Can I jump in on {t}? ", "Before I forget, on {t}, "]
_INTERRUPT = ["Sorry, quick question, is that for everyone?", "Wait, sorry— [crosstalk]", "Sorry, go on.",
              "Hold on, does that apply to mobile too?", "Can you repeat that? You cut out a bit.", "Sorry, sorry, go ahead."]
_CONFIRM = ["Yeah, exactly.", "Yes, that's it.", "Right, correct.", "Mm-hmm, yes.", "Yep.", "Exactly, yeah."]
_BACKCHANNEL = ["Mm-hmm.", "Okay.", "Right.", "Got it.", "Okay, noted.", "Yeah.", "Makes sense."]
_ECHO = ["Just to confirm, {x}?", "So if I got it right, {x}?", "Let me check I got this: {x}?"]
_COUNTER = ["Hmm, I'm not sure about that. I'd say {x}", "Wait, I don't think that's right. {x}", "Really? I had in mind that {x}",
            "I disagree a bit here. {x}"]
_DEFEND = ["No, it really has to be {v}, otherwise it doesn't work for us.", "I'd still go with {v}, honestly.",
           "Hmm, I don't know, I'm pretty sure it was {v}."]
_RESOLVE = ["Okay, so we'll go with {v}. Let me write it down: {x}", "Fine, let's settle on {v} then. So, {x}",
            "Alright, {v} it is. Just so it's clear: {x}"]
_PARK = ["Okay, we're not going to solve this today. Let's park it and come back to it.",
         "Let's leave that open for now, I need to check with my team.", "Let's take this offline and decide later."]
_OBJECT_SCOPE = ["Do we really need that? I'd leave it out, at least for the first version.",
                 "I'm not convinced that's necessary, honestly.", "That sounds like a lot of work for little value."]
_DEFEND_SCOPE = ["We do need it, it's important for our people.", "I'd really like to keep it.",
                 "Without it the whole thing doesn't make much sense for us."]
_RESOLVE_KEEP = ["Okay, we'll keep it in then.", "Alright, it stays.", "Okay, noted, we keep it."]
_DROP = ["Fine, let's drop it for now.", "Okay, we take it out of the scope.", "Alright, let's leave that one out."]
_RESOLVE_LATER = ["About {t} we parked last time: we checked, and it's settled. {x}",
                  "On the open point about {t}: we decided. {x}", "Coming back to {t} from last time, it's decided: {x}"]
_DROP_LATER = ["About the open point on {t}: we decided to drop it.", "On {t}, the thing we left open, we're taking it out."]
_FOLLOWUP = ["Oh, about {t} from last time, I checked: {x}", "I have the missing info on {t}: {x}",
             "Quick follow-up on {t}: {x}"]
_RESTATE = ["Just as a reminder, {x}", "And like we said, {x}", "On {t}, {x}", "{x}"]
_CLARIFY = ["Can you be more specific?", "What exactly do you mean by that?", "Do you have a concrete number or example?"]
_EVADE = ["Hmm, hard to say right now. We'll see.", "I don't know, something reasonable.", "We'll figure that out later, I guess."]
_ANYTHING = ["Anything else on {t}?", "Is that all for {t}?"]
_NOTHING = ["No, I think that's it.", "That's all for now.", "Nothing else, I think."]
_CROSS_A = ["Yeah, and also—", "But what if—", "Sorry, I just wanted to—"]
_CROSS_B = ["—sorry, go ahead.", "—no, you go.", "[crosstalk] sorry."]
_CLOSE = ["Okay, we're out of time. I'll send a summary and we'll pick up the rest next time.",
          "Let's stop here for today. I'll write this up and we continue next time."]
_CLOSE_FINAL = ["Great, I think that covers it for today. I'll write this up and send it around.",
                "Okay, I think we have everything. I'll consolidate and send it around."]


def _join(topics):
    topics = list(topics)
    if not topics:
        return "the first topics"
    return topics[0] if len(topics) == 1 else ", ".join(topics[:-1]) + " and " + topics[-1]


def _q(s):
    """Fala transformada em pergunta de eco."""
    return _lower_first(s.rstrip(" .?!"))


def render_turn(turn, rng):
    act, info, spk = turn.act, turn.info, turn.speaker
    ch = rng.choice
    if act == "state":
        parts = [casual_need(u.text, rng, spk, u.flags, discourse=j == 0) for j, u in enumerate(turn.utts)]
        s = " ".join(parts if len(parts) == 1 else [parts[0]] + ["And " + _lower_first(p) for p in parts[1:]])
        if info.get("interrupted"):
            s = s.rstrip(" .,!?") + "—"
        if info.get("self_intro"):
            s = _fill(ch(_SELF_INTRO) + "{x}", s, t=info["self_intro"])
        return s
    if act == "resume":
        return casual_fragment(turn.utts[0].text, rng)
    if act == "echo":
        return _fill(ch(_ECHO), _q(casual_need(turn.utts[0].text, rng, discourse=False)))
    if act in ("counter", "resolve", "resolve_later", "followup", "restate"):
        x = casual_need(turn.utts[0].text, rng, spk, discourse=False)
        tpl = {"counter": _COUNTER, "resolve": _RESOLVE, "resolve_later": _RESOLVE_LATER,
               "followup": _FOLLOWUP, "restate": _RESTATE}[act]
        return _fill(ch(tpl), x, v=info.get("value", ""), t=info.get("topic", "that"))
    if act == "context":
        return contract(casual_lexicon(info["text"], rng), rng)
    simple = {
        "open": lambda: ch(_OPEN[info["kind"]]).format(title=info["title"]),
        "recap": lambda: ch(_RECAP).format(topics=_join(info["topics"])) + (ch(_RECAP_OPEN) if info.get("n_open") else ""),
        "smalltalk": lambda: _SMALLTALK[info["key"] % len(_SMALLTALK)],
        "offtopic": lambda: _OFFTOPIC[info["key"] % len(_OFFTOPIC)],
        "ask_topic": lambda: ch(_ASK_REVISIT if info.get("revisit") else (_ASK_NFR if info.get("nfr") else _ASK)).format(t=info["topic"]),
        "interrupt": lambda: _INTERRUPT[info["key"] % len(_INTERRUPT)],
        "confirm": lambda: ch(_CONFIRM),
        "backchannel": lambda: ch(_BACKCHANNEL),
        "defend": lambda: ch(_DEFEND).format(v=info["value"]),
        "park": lambda: ch(_PARK),
        "object_scope": lambda: _OBJECT_SCOPE[info["key"] % len(_OBJECT_SCOPE)],
        "defend_scope": lambda: _DEFEND_SCOPE[info["key"] % len(_DEFEND_SCOPE)],
        "resolve_keep": lambda: ch(_RESOLVE_KEEP),
        "drop": lambda: ch(_DROP),
        "drop_later": lambda: ch(_DROP_LATER).format(t=info["topic"]),
        "clarify_question": lambda: ch(_CLARIFY),
        "evade": lambda: _EVADE[info["key"] % len(_EVADE)],
        "anything_else": lambda: ch(_ANYTHING).format(t=info["topic"]),
        "nothing_else": lambda: ch(_NOTHING),
        "crosstalk_a": lambda: ch(_CROSS_A),
        "crosstalk_b": lambda: ch(_CROSS_B),
        "close": lambda: ch(_CLOSE_FINAL if info.get("final") else _CLOSE),
    }
    if act not in simple:
        raise ValueError(f"ato sem modelo: {act}")
    return simple[act]()


# atos curtos não recebem ruído lexical (soariam artificiais)
_NO_NOISE = {"confirm", "backchannel", "crosstalk_a", "crosstalk_b", "nothing_else"}


def realize(plan, rng, noise=None):
    """Retorna [(meeting, texto, segmentos)] — um texto por reunião.

    Cada turno vira um segmento ``{id: "M1:T5", start, end, speaker, act,
    gt_ids, refs}`` com offsets relativos ao arquivo da reunião.
    """
    noise = plan.params["noise"] if noise is None else noise
    out = []
    for m in plan.meetings:
        header = f"Meeting {m.index} of {m.total} ({m.kind})\nParticipants: {', '.join(m.participants)}\n\n"
        parts, pos, segs = [header], len(header), []
        for i, t in enumerate(m.turns, 1):
            text = render_turn(t, rng)
            if t.act not in _NO_NOISE:
                text = add_disfluency(text, rng, noise)
            prefix = f"{t.speaker}: "
            start = pos + len(prefix)
            refs = t.all_refs()
            seg = {"id": f"{m.mid}:T{i}", "start": start, "end": start + len(text), "speaker": t.speaker, "act": t.act}
            gt = list(dict.fromkeys(rid for rid, role, _ in refs if role in VALID_ROLES))
            if gt:
                seg["gt_ids"] = gt
            if refs:
                seg["refs"] = [{"rid": rid, "role": role, **({"pid": pid} if pid else {})} for rid, role, pid in refs]
            segs.append(seg)
            line = prefix + text + "\n"
            parts.append(line)
            pos += len(line)
        out.append((m, "".join(parts), segs))
    return out
