"""Planejador de reuniões: decide a estrutura e os fenômenos, sem escrever
texto final.

Etapas (todas determinísticas dada a semente):

1. **Atribuição de fenômenos** a cada requisito (no máximo um): omissão,
   conflito, ambiguidade, inconsistência ou incompletude, conforme o perfil.
2. **Ordem dos tópicos** com bagunça: embaralhamento local e retomada de
   tópicos já discutidos.
3. **Divisão em reuniões** (blocos contíguos de tópicos, balanceados pelo
   número de requisitos) e escolha dos participantes de cada reunião.
4. **Turnos** de cada reunião, incluindo efeitos entre reuniões (conflito
   adiado e resolvido depois, informação que faltava trazida depois,
   requisito reafirmado com valor divergente).
"""

import re
from collections import Counter, defaultdict

from ..synth import _groups, _intro_sentences, short_title
from . import transforms as T
from .model import STAKEHOLDERS, Meeting, Phenomenon, Plan, Turn, Utt
from .profiles import get_profile

FR_SPEAKERS = ("Client", "EndUser")
NFR_SPEAKERS = ("TechLead", "Client")

_ORDER = (
    ("omission", "p_omit"),
    ("conflict", "p_conflict"),
    ("ambiguity", "p_ambiguity"),
    ("inconsistency", "p_inconsistency"),
    ("incompleteness", "p_incomplete"),
)


def _is_nfr(grp):
    return sum(r.cls == "NFR" for r in grp) > len(grp) / 2


_TOPIC_ID = re.compile(r"^\s*(?:[a-z]{1,5}[-_ ]?\d+(?:\.\d+)*|\d+(?:\.\d+)+)\s*[:.)\-–]?\s+", re.I)


def spoken_topic(topic):
    """Tópico como alguém falaria: sem ID de seção ("si-1: weborder ui" → "weborder ui")."""
    t = _TOPIC_ID.sub("", topic).strip(" :-")
    return t or topic


def spoken_title(title, limit=48):
    """Título curto para a fala de abertura (corta em fronteira de palavra)."""
    t = title.rstrip(". ")
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-")


class _Planner:
    def __init__(self, doc, ext, reqs, profile, rng):
        self.doc, self.ext, self.reqs = doc, ext, list(reqs)
        self.profile = profile
        self.P = get_profile(profile)
        self.mess = self.P["mess"]
        self.rng = rng
        self.status = {r.rid: "clear" for r in self.reqs}
        self.phen = []
        self.assign = {}
        self.counts = Counter()
        self.pending = defaultdict(list)  # índice da reunião -> blocos vindos de reuniões anteriores
        self.pending_same = defaultdict(list)  # índice da reunião -> [(bloco de origem, bloco)]

    # ------------------------------------------------------------------ 1
    def _new_phen(self, typ, rid, kind, **details):
        p = Phenomenon(f"P{len(self.phen) + 1}", typ, rid, kind, details=details)
        self.phen.append(p)
        return p

    def assign_phenomena(self):
        rng, P = self.rng, self.P
        for r in self.reqs:
            u, acc, chosen = rng.random(), 0.0, None
            for typ, key in _ORDER:
                acc += P[key]
                if u < acc:
                    chosen = typ
                    break
            if chosen is None:
                continue
            if chosen == "omission":
                p = self._new_phen("omission", r.rid, "not_discussed")
                p.outcome = "not_discussed"
                self.status[r.rid] = "omitted"
                self.assign[r.rid] = p
            elif chosen == "conflict":
                m = T.mutate(r.text, rng)
                if m and rng.random() < 0.9:
                    self.assign[r.rid] = self._new_phen("conflict", r.rid, m["kind"], original_value=m["original_value"],
                                                        proposed_value=m["proposed_value"], proposed_text=m["text"])
                else:
                    self.assign[r.rid] = self._new_phen("conflict", r.rid, "scope")
            elif chosen == "ambiguity":
                a = T.ambiguity(r.text, rng)
                self.assign[r.rid] = self._new_phen("ambiguity", r.rid, a["kind"], removed=a["removed"],
                                                    replacement=a["replacement"], stated_text=a["text"])
            elif chosen == "inconsistency":
                m = T.mutate_for_inconsistency(r.text, rng)
                if m:
                    self.assign[r.rid] = self._new_phen("inconsistency", r.rid, m["kind"], original_value=m["original_value"],
                                                        conflicting_value=m["proposed_value"], conflicting_text=m["text"])
            elif chosen == "incompleteness":
                m = T.incompleteness(r.text, rng)
                if m:
                    self.assign[r.rid] = self._new_phen("incompleteness", r.rid, m["kind"], missing=m["missing"], stated_text=m["text"])

    # ------------------------------------------------------------------ 2
    def order_topics(self):
        rng, mess = self.rng, self.mess
        items = []
        for i, (tp, grp) in enumerate(_groups(self.reqs)):
            tp, grp = spoken_topic(tp), list(grp)
            if mess and len(grp) > 1 and rng.random() < 0.5 * mess:
                rng.shuffle(grp)
            jitter = rng.uniform(0, 4 * mess) if mess else 0.0
            if mess and len(grp) >= 3 and rng.random() < 0.3 * mess:
                k = rng.randint(1, len(grp) // 2)
                items.append((i + jitter, tp, grp[:-k], False))
                items.append((i + rng.uniform(2, 2 + 6 * mess), tp, grp[-k:], True))
                self.counts["topic_revisits"] += 1
            else:
                items.append((i + jitter, tp, grp, False))
        original = list(items)
        items.sort(key=lambda x: x[0])
        if mess:
            self.counts["topics_out_of_document_order"] = sum(1 for a, b in zip(items, original) if a is not b)
        return [(tp, grp, rev) for _, tp, grp, rev in items]

    # ------------------------------------------------------------------ 3
    def partition(self, items):
        lo, hi = self.P["meetings"]
        n = max(1, min(self.rng.randint(lo, hi), len(items)))
        total = sum(len(g) for _, g, _ in items)
        chunks, acc, idx = [[] for _ in range(n)], 0, 0
        for it in items:
            if idx < n - 1 and chunks[idx] and acc >= total * (idx + 1) / n:
                idx += 1
            chunks[idx].append(it)
            acc += len(it[1])
        return [c for c in chunks if c] or [[]]

    def participants(self, chunk):
        if not self.mess:
            return ["Analyst", *STAKEHOLDERS]
        has_nfr = any(_is_nfr(g) for _, g, _ in chunk)
        has_fr = any(not _is_nfr(g) for _, g, _ in chunk)
        st = {"Client"}
        if has_nfr or self.rng.random() < 0.4:
            st.add("TechLead")
        if (has_fr and self.rng.random() < 0.85) or len(st) < 2:
            st.add("EndUser")
        return ["Analyst"] + [s for s in STAKEHOLDERS if s in st]

    # ------------------------------------------------------------------ 4
    def _later(self, k):
        return self.rng.randint(k + 1, self.n - 1) if k < self.n - 1 else None

    def _speaker_in(self, k, preferred):
        present = self.meetings[k].participants
        return preferred if preferred in present else self.rng.choice([p for p in present if p != "Analyst"])

    def _other(self, present, spk, stakeholders_only=True):
        pool = [p for p in present if p != spk and (p != "Analyst" or not stakeholders_only)]
        return self.rng.choice(pool)

    def _put(self, k, tgt, blk):
        """Agenda um bloco na reunião ``tgt``; se ``tgt == k``, mais adiante
        na própria reunião (depois do bloco atual)."""
        if tgt != k:
            self.pending[tgt].append(blk)
        else:
            self.pending_same[k].append((self._cur_block, blk))

    def _clear(self, chunk, spk, intro, present):
        rng, mess = self.rng, self.mess
        if len(chunk) == 1 and mess and rng.random() < 0.3 * mess:
            parts = T.split_for_interruption(chunk[0].text)
            if parts:
                self.counts["interruptions"] += 1
                rid = chunk[0].rid
                return [
                    Turn(spk, "state", [Utt(rid, parts[0], "part1")], info={**intro, "interrupted": True}),
                    Turn(self._other(present, spk, stakeholders_only=False), "interrupt", info={"key": rng.randrange(1000)}),
                    Turn(spk, "resume", [Utt(rid, parts[1], "part2")]),
                ]
        flags = {}
        if mess and rng.random() < 0.15 * mess:
            flags["false_start"] = True
            self.counts["false_starts"] += 1
        if self.P["p_chunk"]:
            # um requisito por vez, fatiado em turnos curtos
            out = []
            for j, r in enumerate(chunk):
                if j and rng.random() < self.P["p_mid_backchannel"]:
                    out.append(Turn(self._listener(spk, present), "backchannel"))
                out += self._say(spk, r.rid, r.text, flags=flags if j == 0 else {}, intro=intro if j == 0 else {}, present=present)
        else:
            utts = [Utt(r.rid, r.text, "statement", flags=dict(flags) if j == 0 else {}) for j, r in enumerate(chunk)]
            out = [Turn(spk, "state", utts, info=intro)]
        if rng.random() < 0.12:
            out.append(Turn("Analyst", "echo", [Utt(chunk[-1].rid, chunk[-1].text, "echo")]))
            out.append(Turn(spk, "confirm"))
        elif rng.random() < self.P["p_backchannel"]:
            out.append(Turn("Analyst", "backchannel"))
        out += self._react(spk, present)
        return out

    def _listener(self, spk, present):
        """Quem solta o *backchannel* no meio da fala: em geral o analista."""
        if self.rng.random() < 0.75 or len(present) < 3:
            return "Analyst" if spk != "Analyst" else self._other(present, spk)
        return self._other(present, spk)

    def _react(self, spk, present):
        """Reação curta de outro stakeholder ("Yeah, agreed.")."""
        if self.P["p_react"] and self.rng.random() < self.P["p_react"]:
            self.counts["reactions"] += 1
            return [Turn(self._other(present, spk), "react", info={"key": self.rng.randrange(1000)})]
        return []

    def _say(self, spk, rid, text, pid=None, flags=None, intro=None, present=None):
        """Afirmação de um requisito; se longa, vira vários turnos curtos do
        mesmo falante com *backchannel* entre eles (calibração com o AMI).
        Marcas de início (hesitação, falso começo) vão na primeira parte;
        marcas de fim (fala cortada, valor faltante) na última."""
        flags, intro, P = flags or {}, intro or {}, self.P
        if P["p_chunk"] and len(text.split()) > P["chunk_target"] * 1.5 and self.rng.random() < P["p_chunk"]:
            parts = T.chunk_text(text, P["chunk_target"])
            if len(parts) > 1:
                self.counts["chunked_statements"] += 1
                head = {k: v for k, v in flags.items() if k in ("hedge", "false_start")}
                tail = {k: v for k, v in flags.items() if k in ("incomplete", "remark")}
                turns = [Turn(spk, "state", [Utt(rid, parts[0], "part1", pid, head)], info={**intro, "chunked": True})]
                for j, part in enumerate(parts[1:], 1):
                    if self.rng.random() < P["p_mid_backchannel"]:
                        turns.append(Turn(self._listener(spk, present), "backchannel"))
                    turns.append(Turn(spk, "continue", [Utt(rid, part, "part2", pid, tail if j == len(parts) - 1 else {})]))
                return turns
        return [Turn(spk, "state", [Utt(rid, text, "statement", pid, flags)], info=intro)]

    def _conflict(self, r, p, spk, intro, present, k, topic):
        rng = self.rng
        other = self._other(present, spk)
        p.details.update(raised_by=other, meeting=self.meetings[k].mid)
        ref = [(r.rid, "conflict", p.pid)]
        if p.kind in ("value", "actor"):
            orig_v, prop_v = p.details["original_value"], p.details["proposed_value"]
            if rng.random() < 0.5:
                turns = [
                    Turn(spk, "state", [Utt(r.rid, r.text, "statement", p.pid)], info=intro),
                    Turn(other, "counter", [Utt(r.rid, p.details["proposed_text"], "distractor", p.pid)]),
                    Turn(spk, "defend", info={"value": orig_v}, refs=ref),
                ]
                p.details["proposer"] = other
            else:
                turns = [
                    Turn(spk, "state", [Utt(r.rid, p.details["proposed_text"], "distractor", p.pid)], info=intro),
                    Turn(other, "counter", [Utt(r.rid, r.text, "statement", p.pid)]),
                    Turn(spk, "defend", info={"value": prop_v}, refs=ref),
                ]
                p.details["proposer"] = spk
            if rng.random() < self.P["p_conflict_open"]:
                turns.append(Turn(rng.choice([x for x in ("Analyst", "Client") if x in present]), "park", info={"topic": topic}, refs=ref))
                tgt = self._later(k)
                if tgt is not None and rng.random() < self.P["p_resolve_later"]:
                    self._put(k, tgt, [Turn("Analyst", "resolve_later", [Utt(r.rid, r.text, "resolution", p.pid)],
                                            info={"topic": topic, "value": orig_v})])
                    p.outcome, self.status[r.rid] = "resolved_later", "conflict_resolved"
                    p.details["resolved_in"] = self.meetings[tgt].mid
                else:
                    p.outcome, self.status[r.rid] = "open", "conflict_open"
            else:
                turns.append(Turn("Analyst", "resolve", [Utt(r.rid, r.text, "resolution", p.pid)], info={"value": orig_v}))
                p.outcome, self.status[r.rid] = "resolved", "conflict_resolved"
            return turns

        # conflito de escopo: precisa ou não do requisito?
        turns = [
            Turn(spk, "state", [Utt(r.rid, r.text, "statement", p.pid)], info=intro),
            Turn(other, "object_scope", info={"key": rng.randrange(1000)}, refs=ref),
            Turn(spk, "defend_scope", info={"key": rng.randrange(1000)}, refs=ref),
        ]
        u, p_open = rng.random(), self.P["p_conflict_open"]
        if u < p_open:
            turns.append(Turn(rng.choice([x for x in ("Analyst", "Client") if x in present]), "park", info={"topic": topic}, refs=ref))
            tgt = self._later(k)
            if tgt is not None and rng.random() < self.P["p_resolve_later"]:
                if rng.random() < 0.65:
                    blk = [Turn("Analyst", "resolve_later", [Utt(r.rid, r.text, "resolution", p.pid)], info={"topic": topic})]
                    p.outcome, self.status[r.rid] = "resolved_later", "conflict_resolved"
                else:
                    blk = [Turn("Analyst", "drop_later", info={"topic": topic}, refs=[(r.rid, "resolution", p.pid)])]
                    p.outcome, self.status[r.rid] = "dropped_later", "rejected"
                self._put(k, tgt, blk)
                p.details["resolved_in"] = self.meetings[tgt].mid
            else:
                p.outcome, self.status[r.rid] = "open", "conflict_open"
        elif u < p_open + (1 - p_open) * 0.3:
            turns.append(Turn("Analyst", "drop", refs=[(r.rid, "resolution", p.pid)]))
            p.outcome, self.status[r.rid] = "dropped", "rejected"
        else:
            turns.append(Turn("Analyst", "resolve_keep", refs=[(r.rid, "resolution", p.pid)]))
            p.outcome, self.status[r.rid] = "resolved", "conflict_resolved"
        return turns

    def _ambiguity(self, r, p, spk, intro, present):
        flags = {"hedge": True} if p.kind == "optionality" else {}
        turns = self._say(spk, r.rid, p.details["stated_text"], p.pid, flags, intro, present)
        if self.rng.random() < 0.3:
            ref = [(r.rid, "clarification", p.pid)]
            turns += [Turn("Analyst", "clarify_question", info={"kind": p.kind}, refs=ref),
                      Turn(spk, "evade", info={"key": self.rng.randrange(1000)}, refs=ref)]
            p.details["clarification_attempted"] = True
        elif self.rng.random() < 0.4:
            turns.append(Turn("Analyst", "backchannel"))
        p.outcome, self.status[r.rid] = "unresolved", "ambiguous"
        return turns

    def _incompleteness(self, r, p, spk, intro, k, topic, present):
        flags = {"incomplete": p.kind}
        if p.kind == "missing_condition" and self.rng.random() < 0.5:
            flags["remark"] = True
        turns = self._say(spk, r.rid, p.details["stated_text"], p.pid, flags, intro, present)
        later = self._later(k)
        if later is not None and self.rng.random() < self.P["p_complete_later"]:
            self._put(k, later, [Turn(self._speaker_in(later, spk), "followup", [Utt(r.rid, r.text, "followup", p.pid)],
                                      info={"topic": topic, "kind": p.kind})])
            p.outcome, self.status[r.rid] = "completed_later", "clear"
            p.details["completed_in"] = self.meetings[later].mid
        else:
            p.outcome, self.status[r.rid] = "open", "incomplete"
        return turns

    def _inconsistency(self, r, p, spk, intro, k, topic, present):
        turns = self._say(spk, r.rid, r.text, p.pid, intro=intro, present=present)
        later = self._later(k) if self.rng.random() < 0.8 else None
        tgt = k if later is None else later
        speaker2 = self._speaker_in(tgt, self.rng.choice([s for s in STAKEHOLDERS if s != spk]))
        self._put(k, tgt, [Turn(speaker2, "restate", [Utt(r.rid, p.details["conflicting_text"], "restatement", p.pid)],
                                info={"topic": topic})])
        p.outcome, self.status[r.rid] = "unnoticed", "inconsistent"
        p.details["restated_in"] = self.meetings[tgt].mid
        return turns

    def topic_block(self, item, k):
        rng, mess = self.rng, self.mess
        topic, grp, revisit = item
        present = self.meetings[k].participants
        stakeholders = [p for p in present if p != "Analyst"]
        nfr = _is_nfr(grp) if grp else False
        speakers = [s for s in (NFR_SPEAKERS if nfr else FR_SPEAKERS) if s in present] or stakeholders
        block = []
        self_intro = bool(mess) and rng.random() < 0.4 * mess
        if self_intro:
            self.counts["self_introduced_topics"] += 1
        else:
            block.append(Turn("Analyst", "ask_topic", info={"topic": topic, "nfr": nfr, "revisit": revisit}))
        first, i = True, 0
        while i < len(grp):
            r = grp[i]
            p = self.assign.get(r.rid)
            if p is not None and p.type == "omission":
                i += 1
                continue
            spk = rng.choice(speakers)
            intro = {"self_intro": topic, "revisit": revisit} if (self_intro and first) else {}
            n = 1
            if p is None:
                if i + 1 < len(grp) and grp[i + 1].rid not in self.assign and rng.random() < 0.35:
                    n = 2
                turns = self._clear(grp[i : i + n], spk, intro, present)
            elif p.type == "conflict":
                turns = self._conflict(r, p, spk, intro, present, k, topic)
            elif p.type == "ambiguity":
                turns = self._ambiguity(r, p, spk, intro, present)
            elif p.type == "incompleteness":
                turns = self._incompleteness(r, p, spk, intro, k, topic, present)
            else:
                turns = self._inconsistency(r, p, spk, intro, k, topic, present)
            block.extend(turns)
            first = False
            i += n
        if grp and rng.random() < 0.15:
            block += [Turn("Analyst", "anything_else", info={"topic": topic}), Turn(rng.choice(speakers), "nothing_else")]
        if rng.random() < 0.06 + 0.15 * mess:
            block.insert(rng.randint(1, max(1, len(block))), Turn(rng.choice(present), "offtopic", info={"key": rng.randrange(1000)}))
            self.counts["offtopic"] += 1
        if mess and len(block) > 2 and rng.random() < 0.15 * mess:
            a = rng.choice(stakeholders)
            pos = rng.randint(1, len(block))
            block[pos:pos] = [Turn(a, "crosstalk_a"), Turn(self._other(present, a, stakeholders_only=False), "crosstalk_b")]
            self.counts["crosstalk"] += 1
        return block

    def build(self):
        self.assign_phenomena()
        chunks = self.partition(self.order_topics())
        self.n = len(chunks)
        title = spoken_title(short_title(self.doc.title))
        self.meetings = []
        for k, chunk in enumerate(chunks):
            kind = "kickoff" if k == 0 else ("review" if k == self.n - 1 and self.n >= 3 else "follow-up")
            topics = list(dict.fromkeys(tp for tp, _, _ in chunk))
            self.meetings.append(Meeting(f"M{k + 1}", k + 1, self.n, kind, self.participants(chunk), topics))
        open_items = 0
        for k, chunk in enumerate(chunks):
            m = self.meetings[k]
            head = [Turn("Analyst", "open", info={"kind": m.kind, "title": title, "index": m.index, "total": m.total})]
            if k == 0:
                intro = _intro_sentences(self.ext)
                if intro:
                    head.append(Turn("Client", "context", info={"text": " ".join(intro)}))
            else:
                head.append(Turn("Analyst", "recap", info={"topics": self.meetings[k - 1].topics[:3], "n_open": open_items}))
            if self.mess and self.rng.random() < 0.3 + 0.5 * self.mess:
                head.insert(1, Turn(self.rng.choice(m.participants), "smalltalk", info={"key": self.rng.randrange(1000)}))
                self.counts["smalltalk"] += 1
            before = sum(1 for p in self.phen if p.outcome in ("open", "resolved_later", "dropped_later"))
            blocks = []
            for item in chunk:
                self._cur_block = len(blocks)
                blocks.append(self.topic_block(item, k))
            for src, blk in sorted(self.pending_same[k], key=lambda x: -x[0]):
                blocks.insert(self.rng.randint(src + 1, len(blocks)), blk)
            for blk in self.pending[k]:
                blocks.insert(self.rng.randint(0, len(blocks)), blk)
            open_items += sum(1 for p in self.phen if p.outcome in ("open", "resolved_later", "dropped_later")) - before
            m.turns = head + [t for b in blocks for t in b] + [Turn("Analyst", "close", info={"final": k == self.n - 1})]
        self.counts["meetings"] = self.n
        return Plan(self.doc.doc_id, self.doc.title, self.profile, self.P, self.meetings, self.status, self.phen, dict(self.counts))


def build_plan(doc, ext, reqs, profile, rng):
    return _Planner(doc, ext, reqs, profile, rng).build()
