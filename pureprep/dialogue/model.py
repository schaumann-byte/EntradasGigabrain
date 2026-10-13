"""Estruturas do *plano* de reuniões.

O plano é independente do realizador: diz quem fala, que ato de diálogo
executa e qual conteúdo de requisito (canônico ou transformado) a fala deve
expressar. O realizador (regras ou LLM) só decide a superfície do texto.
"""

from dataclasses import asdict, dataclass, field

STAKEHOLDERS = ("Client", "EndUser", "TechLead")

# papéis de uma referência a requisito numa fala
CONTENT_ROLES = ("statement", "part1", "part2", "echo", "resolution", "followup", "restatement", "distractor")
# papéis que carregam a versão válida do requisito (alimentam gt_ids e support)
VALID_ROLES = ("statement", "part1", "part2", "echo", "resolution", "followup")

# status final de cada requisito no gabarito
STATUSES = ("clear", "conflict_resolved", "conflict_open", "rejected", "ambiguous", "inconsistent", "incomplete", "omitted")
EXPECTED_IN_OUTPUT = {"clear", "conflict_resolved", "conflict_open", "ambiguous", "inconsistent", "incomplete"}


@dataclass
class Utt:
    """Conteúdo de requisito expresso numa fala."""

    rid: str
    text: str
    role: str
    pid: str = None
    flags: dict = field(default_factory=dict)


@dataclass
class Turn:
    speaker: str
    act: str
    utts: list = field(default_factory=list)
    info: dict = field(default_factory=dict)
    refs: list = field(default_factory=list)  # [(rid, role, pid)] sem conteúdo (objeção, adiamento...)

    def all_refs(self):
        return [(u.rid, u.role, u.pid) for u in self.utts] + [tuple(r) for r in self.refs]


@dataclass
class Meeting:
    mid: str
    index: int
    total: int
    kind: str
    participants: list
    topics: list
    turns: list = field(default_factory=list)


@dataclass
class Phenomenon:
    pid: str
    type: str  # conflict | ambiguity | inconsistency | incompleteness | omission
    rid: str
    kind: str  # value/actor/scope, vague_quantity, missing_value, ...
    outcome: str = None  # resolved, open, dropped, resolved_later, dropped_later, completed_later, unnoticed...
    details: dict = field(default_factory=dict)


@dataclass
class Plan:
    doc_id: str
    title: str
    profile: str
    params: dict
    meetings: list
    status: dict  # rid -> status
    phenomena: list
    messiness: dict = field(default_factory=dict)  # contagem dos efeitos estruturais

    def to_json(self):
        return asdict(self)
