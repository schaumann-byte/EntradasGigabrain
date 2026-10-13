"""Realizador por LLM (variante B): reescreve as falas do **mesmo plano** da
variante A com um modelo de linguagem.

Fluxo:

1. o plano de cada reunião é fatiado em janelas de ~``window`` turnos;
   cada janela vira uma requisição independente (permite paralelismo);
2. a resposta (JSON ``{"turns": [{"id", "text"}]}``) fica em cache em disco,
   chaveada pelo hash do prompt + modelo — uma segunda execução reproduz a
   variante sem chamar o LLM (``offline=True`` exige cache completo);
3. cada fala é **verificada** contra o plano (números preservados, nenhum
   valor inventado, detalhe removido não reaparece, conteúdo mínimo
   preservado, tamanho do ato); se falhar, o turno volta para o texto do
   realizador por regras e o motivo entra nas estatísticas;
4. o ruído lexical é aplicado depois, igual ao da variante A
   (:func:`realize_rules.assemble`), para que A e B difiram só na paráfrase.
"""

import hashlib
import json
import os
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..textsim import containment, normalize_ws, token_set
from .llm_providers import LLMUnavailable
from .model import VALID_ROLES
from .realize_rules import assemble, render_turn

PROMPT_VERSION = "b1"

SYSTEM = """You rewrite the turns of a requirements-elicitation meeting so they sound like real, spontaneous spoken English between colleagues on a video call.

You receive the turns as JSON. Each turn has an id, a speaker, a dialogue act with a short guide and, sometimes, `content`: the information the turn must convey. Write the spoken text of every turn and return {"turns": [{"id": "...", "text": "..."}]} with exactly the same ids, in the same order.

For turns with content:
1. Convey all of the content's information: every number with its unit, every actor or role, every condition, list item and technical term (product names, acronyms, standards). Write numbers as digits, exactly as given. Rephrase freely in casual speech; do not copy the sentence as written.
2. Add nothing: no new requirements, values, examples, reasons or details that are not in the content.
3. Never make the content more precise than it is. If it is vague ("a few seconds", "someone", "it"), stay vague. If information is missing, keep it missing.
4. Follow the turn's notes (for example: sound unsure, trail off, say you don't remember the number).
5. A turn whose content role is "part2" continues the same speaker's previous turn: it is the next piece of the same idea, not a new topic.

For every turn:
- Write only what the speaker says: no speaker labels, quotes, stage directions or markdown.
- Do not add filler words such as "uh", "um", "you know" or "like"; they are added later.
- Keep short acts short: acknowledgments 1-3 words, reactions up to 6 words.
- Speakers: Analyst runs the meeting, asks and confirms; Client is the business owner; TechLead covers technical constraints and quality attributes; EndUser is a day-to-day user. Keep each voice consistent across turns."""

SCHEMA = {
    "type": "object",
    "properties": {
        "turns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["turns"],
    "additionalProperties": False,
}

GUIDES = {
    "open": "Analyst opens the meeting about {title} (meeting {index} of {total}, {kind}).",
    "context": "Client gives the project background below, in their own words.",
    "recap": "Analyst briefly recaps the previous meeting's topics: {topics}.{open_note}",
    "smalltalk": "A short piece of small talk before getting started.",
    "offtopic": "A brief off-topic remark typical of video calls (audio, screen sharing, schedule).",
    "ask_topic": "Analyst moves the discussion to the topic '{topic}' and asks about it.{revisit_note}",
    "state": "The speaker states the content in their own words.",
    "continue": "The speaker goes on with their previous turn: next piece of the same idea.",
    "resume": "After being interrupted, the speaker picks up where they left off and finishes the idea.",
    "interrupt": "A short interruption of the previous speaker (a quick question or apology).",
    "echo": "Analyst paraphrases the content back as a question, to confirm understanding.",
    "confirm": "Short confirmation that the paraphrase is right.",
    "backchannel": "Short acknowledgment while listening (1-3 words).",
    "react": "Short agreeing reaction from another participant (up to 6 words).",
    "counter": "The speaker disagrees with the previous turn and proposes the content instead.",
    "defend": "The speaker insists on their own value: {value}. Do not mention any other value.",
    "resolve": "Analyst settles the disagreement on {value} and restates the content as decided.",
    "park": "Suggest leaving this disagreement open for now and deciding later.",
    "object_scope": "The speaker questions whether the previous requirement is needed at all.",
    "defend_scope": "The speaker argues the requirement is needed.",
    "resolve_keep": "Analyst decides to keep the requirement.",
    "drop": "Analyst decides to drop the requirement from the scope.",
    "resolve_later": "Analyst says the point about '{topic}' left open last time has been settled, and states the content as decided.",
    "drop_later": "Analyst says the open point about '{topic}' from last time was dropped from the scope.",
    "followup": "The speaker brings information that was missing last time about '{topic}', stating the content.",
    "restate": "The speaker mentions the content again as if it were what everyone already agreed. Do not signal any change.",
    "clarify_question": "Analyst asks for something more specific about what was just said.",
    "evade": "The speaker answers vaguely, without adding any concrete detail.",
    "anything_else": "Analyst asks whether there is anything else on '{topic}'.",
    "nothing_else": "Short answer: nothing else on this topic.",
    "crosstalk_a": "The speaker starts to say something and gets cut off (end with an em dash).",
    "crosstalk_b": "The speaker yields after talking over someone (very short).",
    "close": "Analyst closes the meeting.{final_note}",
}

NOTES = {
    "hedge": "Sound unsure whether this is really mandatory (for example 'maybe', 'it'd be nice if').",
    "false_start": "Begin with a false start and correct yourself.",
    "truncated": "Leave the idea unfinished: trail off at the end.",
    "missing_value": "Say you don't remember the exact number and will check.",
    "missing_condition": "",
    "remark": "Mention there are some exceptions you can't recall right now.",
    "interrupted": "You get cut off before finishing: end with an em dash.",
    "chunked": "Your thought continues in your next turn: do not wrap it up here.",
    "self_intro": "Bring up the topic '{topic}' yourself, without being asked.",
}

_SHORT_ACTS = {"backchannel", "confirm", "react", "crosstalk_b", "nothing_else"}
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _guide(turn):
    info = turn.info
    fmt = {
        "title": info.get("title", ""), "index": info.get("index", ""), "total": info.get("total", ""),
        "kind": info.get("kind", ""), "topics": ", ".join(info.get("topics", [])), "topic": info.get("topic", ""),
        "value": info.get("value", ""),
        "open_note": " Mention that some points were left open." if info.get("n_open") else "",
        "revisit_note": " It was already discussed earlier; say you want to go back to it." if info.get("revisit") else "",
        "final_note": " This is the last meeting: say you will consolidate everything." if info.get("final") else
                      " There will be another meeting: say you will continue next time.",
    }
    return GUIDES[turn.act].format(**fmt)


def _turn_payload(turn, tid):
    item = {"id": tid, "speaker": turn.speaker, "act": turn.act, "guide": _guide(turn)}
    if turn.act == "context":
        item["content"] = [{"text": turn.info["text"], "role": "background"}]
    elif turn.utts:
        item["content"] = [{"text": u.text, "role": u.role} for u in turn.utts]
    notes = []
    for u in turn.utts:
        for k in ("hedge", "false_start", "remark"):
            if u.flags.get(k):
                notes.append(NOTES[k])
        if u.flags.get("incomplete") and NOTES[u.flags["incomplete"]]:
            notes.append(NOTES[u.flags["incomplete"]])
    for k in ("interrupted", "chunked"):
        if turn.info.get(k):
            notes.append(NOTES[k])
    if turn.info.get("self_intro"):
        notes.append(NOTES["self_intro"].format(topic=turn.info["self_intro"]))
    if notes:
        item["notes"] = notes
    return item


def build_windows(plan, window=20, context=3):
    """[(seg_ids, prompt_user)] — janelas independentes de turnos por reunião."""
    jobs = []
    for m in plan.meetings:
        ids = [f"{m.mid}:T{i}" for i in range(1, len(m.turns) + 1)]
        for s in range(0, len(m.turns), window):
            turns = m.turns[s : s + window]
            prev = [{"speaker": t.speaker, "act": t.act, **({"content": [u.text for u in t.utts]} if t.utts else {})}
                    for t in m.turns[max(0, s - context) : s]]
            payload = {
                "project": plan.title,
                "meeting": f"{m.index} of {m.total} ({m.kind})",
                "participants": m.participants,
                "previous_turns_for_context_only": prev,
                "turns": [_turn_payload(t, tid) for t, tid in zip(turns, ids[s : s + window])],
            }
            jobs.append((ids[s : s + window], json.dumps(payload, ensure_ascii=False, indent=1)))
    return jobs


# ---------------------------------------------------------------------------
# verificação
# ---------------------------------------------------------------------------

def clean_text(text, speaker):
    t = normalize_ws(str(text))
    t = re.sub(rf"^\**{re.escape(speaker)}\**\s*:\s*", "", t)
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1].strip()
    return t


def verify(turn, text, phen, min_content=0.5):
    """``None`` se a fala serve; senão o motivo da recusa."""
    if not text:
        return "empty"
    words = len(text.split())
    sources = [u.text for u in turn.utts] + ([turn.info["text"]] if turn.act == "context" else [])
    allowed = set(_NUM.findall(" ".join(sources + [str(v) for v in turn.info.values() if isinstance(v, (str, int))])))
    for topic in turn.info.get("topics", []):
        allowed |= set(_NUM.findall(topic))
    if not sources:
        limit = 6 if turn.act in _SHORT_ACTS else 45
        if words > limit:
            return "too_long"
    else:
        expected = sum(len(s.split()) for s in sources)
        if words > 2.5 * expected + 25:
            return "too_long"
    nums = set(_NUM.findall(text))
    if nums - allowed:
        return "invented_number"
    for s in sources:
        if set(_NUM.findall(s)) - nums:
            return "lost_number"
        if containment(token_set(s), token_set(text)) < min_content:
            return "lost_content"
    out_tokens = token_set(text)
    for u in turn.utts:
        p = phen.get(u.pid)
        if p is None:
            continue
        if p.type in ("ambiguity", "incompleteness") and u.role not in ("followup", "resolution"):
            removed = p.details.get("removed") or p.details.get("missing")
            if removed:
                leak = (token_set(removed) - token_set(u.text)) & out_tokens
                tolerance = 1 if p.kind in ("missing_condition", "truncated") else 0
                if len(leak) > tolerance:
                    return "leaked_detail"
        if u.role in ("distractor", "restatement"):
            new_v = p.details.get("proposed_value") or p.details.get("conflicting_value") or ""
            old_v = p.details.get("original_value") or ""
            if not token_set(new_v) <= out_tokens:
                return "lost_variant_value"
            if (token_set(old_v) - token_set(new_v) - token_set(u.text)) & out_tokens:
                return "mixed_values"
    return None


# ---------------------------------------------------------------------------
# cache + execução
# ---------------------------------------------------------------------------

def _key(provider_params, user):
    blob = json.dumps({"v": PROMPT_VERSION, "p": provider_params, "s": SYSTEM, "u": user}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_path(cache_dir, provider_params, key):
    slug = re.sub(r"[^\w.-]+", "_", f"{provider_params['provider']}-{provider_params['model']}")
    return Path(cache_dir) / slug / key[:2] / f"{key}.json"


_LOCK = threading.Lock()


def _count(stats, key):
    with _LOCK:
        stats[key] += 1


def _fetch(provider, cache_dir, offline, user, stats):
    params = provider.params()
    key = _key(params, user)
    path = _cache_path(cache_dir, params, key) if cache_dir else None
    if path and path.exists():
        _count(stats, "cache_hits")
        return json.loads(path.read_text(encoding="utf-8"))["response"]
    if offline:
        raise RuntimeError(f"modo offline: resposta ausente no cache ({key[:12]}…)")
    try:
        text = provider.complete(SYSTEM, user, SCHEMA)
    except LLMUnavailable as e:
        _count(stats, f"request_failed:{e}")
        return None
    _count(stats, "requests")
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"prompt_version": PROMPT_VERSION, "provider": params, "request": user, "response": text},
                                  ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    return text


def _parse(text):
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)  # alguns servidores compatíveis embrulham o JSON
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    turns = data.get("turns", []) if isinstance(data, dict) else []
    return {t["id"]: t["text"] for t in turns if isinstance(t, dict) and isinstance(t.get("id"), str) and isinstance(t.get("text"), str)}


def realize(plan, rng, *, provider, cache_dir=None, offline=False, workers=8, window=20, min_content=0.5):
    """Mesmo contrato de :func:`realize_rules.realize`; devolve também as
    estatísticas do realizador (falas aceitas, fallbacks por motivo, cache)."""
    stats = Counter()
    jobs = build_windows(plan, window=window)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        texts = list(ex.map(lambda job: _fetch(provider, cache_dir, offline, job[1], stats), jobs))
    llm = {}
    for (ids, _), text in zip(jobs, texts):
        got = _parse(text)
        for tid in ids:
            if tid in got:
                llm[tid] = got[tid]
    phen = {p.pid: p for p in plan.phenomena}

    def render(turn, seg_id):
        stats["turns"] += 1
        raw = llm.get(seg_id)
        if raw is None:
            stats["fallback:no_response"] += 1
            return render_turn(turn, rng)
        text = clean_text(raw, turn.speaker)
        reason = verify(turn, text, phen, min_content)
        if reason:
            stats[f"fallback:{reason}"] += 1
            return render_turn(turn, rng)
        stats["llm_accepted"] += 1
        if any(u.role in VALID_ROLES for u in turn.utts):
            stats["llm_accepted_content"] += 1
        return text

    realized = assemble(plan, rng, render)
    stats["windows"] = len(jobs)
    return realized, dict(sorted(stats.items()))


__all__ = ["PROMPT_VERSION", "SCHEMA", "SYSTEM", "build_windows", "clean_text", "realize", "verify"]
