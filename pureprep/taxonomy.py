"""Classificação das seções de um SRS pelo título.

Cada seção recebe um papel:

- ``meta``     : metadocumento (referências, glossário, convenções...) — descartada.
- ``context``  : texto discursivo (propósito, escopo, perspectiva do produto,
                 usuários, visão...) — alimenta a entrada bruta simulada.
- ``scenario`` : narrativas de uso (estímulo/resposta, descrição e prioridade) —
                 também alimenta a entrada bruta.
- ``fr``       : requisitos funcionais — gabarito.
- ``nfr``      : requisitos não funcionais (com subtipo) — gabarito.

Títulos sem correspondência herdam o papel do ancestral mais próximo. As
regras seguem os templates encontrados no PURE: IEEE 830, Wiegers/Volere,
RUP/FURPS+, MIL-STD-498 e especificações ferroviárias (EIRENE/ERTMS).
"""

import re

# Subtipos de RNF. ``promise`` mapeia para as 11 classes do PROMISE NFR
# (usadas pelo ReqFromSRS/REQINONE) quando a correspondência é natural.
NFR_SUBTYPES = {
    "PE": ("Performance", "PE"),
    "SE": ("Security", "SE"),
    "US": ("Usability", "US"),
    "LF": ("Look & Feel", "LF"),
    "A": ("Availability", "A"),
    "FT": ("Fault Tolerance", "FT"),
    "MN": ("Maintainability/Supportability", "MN"),
    "PO": ("Portability", "PO"),
    "SC": ("Scalability", "SC"),
    "L": ("Legal/Standards", "L"),
    "O": ("Operational/Environment", "O"),
    "RL": ("Reliability/RAMS", None),
    "SA": ("Safety", None),
    "IF": ("External Interface", None),
    "DC": ("Design/Implementation Constraint", None),
    "EN": ("Environmental/Physical", None),
    "OT": ("Other NFR", None),
}

# (regex, papel, subtipo). A ordem importa: a primeira regra que casa vence.
_RULES = [
    # --- metadocumento -----------------------------------------------------
    (r"\b(references?|applicable documents?|government documents?|bibliograph)", "meta", None),
    (r"\b(definitions?|acronyms?|abbreviations?|glossary|terminology)\b", "meta", None),
    (r"\b(document conventions?|conventions|intended audience|reading suggestions?)\b", "meta", None),
    (r"\b(document overview|srs document overview|structure of the specification|overview of (this|the) document)\b", "meta", None),
    (r"\b(change log|revision history|table of contents|appendix|index|issues list|notes)\b", "meta", None),
    (r"\b(traceability matrix|requirements traceability|qualification provisions|precedence and criticality)\b", "meta", None),
    (r"^(deleted|identification|identification of functional area|conclusions?|next steps.*|preface)$", "meta", None),
    (r"\b(version \d+ suggestions?|future (work|releases?)|swot)\b", "meta", None),
    # --- cenários (discursivos, dentro de features) -----------------------
    (r"\bstimulus\s*/?\s*response", "scenario", None),
    (r"\bdescription and priority\b", "scenario", None),
    # Obs.: títulos "Use Case: ..." NÃO são cenário — no blitdraft (RUP/FURPS)
    # eles agrupam declarações "shall" formais; herdam o papel do ancestral.
    # --- RNF específicos (antes dos contêineres genéricos) ----------------
    (r"\bperformance\b|\bresponse time|\bcapacity\b|set-up time|\btiming\b", "nfr", "PE"),
    (r"\bsecurity\b|\baccess (module|control|modes?)\b|\bprivileges?\b|\bprotections?\b|\bauthenticat|\baudit\b", "nfr", "SE"),
    (r"\bsafety\b", "nfr", "SA"),
    (r"\brams\b|\breliability\b", "nfr", "RL"),
    (r"\bavailability\b", "nfr", "A"),
    (r"\bfault|\bfall-?back|\bcontingenc|\bredundanc|\bfailures?\b", "nfr", "FT"),
    (r"\bmaintainability\b|\bsupportability\b", "nfr", "MN"),
    (r"\bportability\b", "nfr", "PO"),
    (r"\bscalability\b", "nfr", "SC"),
    (r"\blegal\b|\blicen[cs]|\bregulat|\bapplicable standards?\b|\bcompliance\b", "nfr", "L"),
    (r"\busability\b|\bease of use\b|\bhelp\b|\bman-machine interface\b|\bdriver-machine interface\b|\bonline user documentation\b", "nfr", "US"),
    (r"\blook (and|&) feel\b|\buser interfaces?\b", "nfr", "LF"),
    (r"\b(hardware|software|communications?|external|internal) interfaces?\b|\binterface (requirements|identification)\b|^interfaces?$", "nfr", "IF"),
    (r"\benvironmental\b|\bphysical requirements\b|\benvironment requirements\b", "nfr", "EN"),
    (r"\bdesign constraints?\b|\bmemory constraints?\b|\bsite adaptation\b|\badaptation requirements\b|\bpackaging\b|\bhardware constraints?\b|\bsoftware constraints?\b|\buser constraints?\b", "nfr", "DC"),
    (r"^(training|personnel|logistics)\b|\btest and checkout\b|\bquality attributes?\b|\b(software system )?attributes$", "nfr", "OT"),
    (r"\bhuman (engineering|factors)\b", "nfr", "US"),
    (r"\btestab", "nfr", "MN"),
    (r"\bquality factors\b", "nfr", "OT"),
    (r"\bnon-?\s?functional\b", "nfr", "OT"),
    # --- contexto discursivo (IEEE 830 §1–2, Wiegers §1–2) ----------------
    (r"\b(general|design and implementation) constraints?\b|\bconstraints\b", "context", None),
    (r"\bassumptions?\b|\bdependencies\b", "context", None),
    (r"\boperating environment\b|\buser documentation\b", "context", None),
    (r"\bpurpose\b|\bscope\b|\bintroduction\b|\bmotivation\b|\bbackground\b|\bvision\b|\bobjectives?\b", "context", None),
    (r"\b(product|system|general|functional|functional area) (perspective|overview|description)\b", "context", None),
    (r"\boverall description\b|\bgeneral description\b|\bsystem overview\b|^overview$|^general$", "context", None),
    (r"\bproduc[te] (features|functions)\b", "context", None),
    (r"\buser (classes|characteristics|needs)\b|\bsystem users\b|\busers of the system\b|\blocations of users\b", "context", None),
    (r"\bneed for\b|\bstatus quo\b|\boutline of\b|\bextent of specification\b|\bapplicability\b|\bappliccability\b", "context", None),
    # --- RF ---------------------------------------------------------------
    (r"\bfunctional requirements?\b|\bfunctionality\b|\bsystem features\b|\bfunctions?\b|\bcapabilit", "fr", None),
    (r"\bmodules?\b|\bservices\b|\bdata requirements\b|\bstates and modes\b|\boperational states\b", "fr", None),
    (r"\brequirements?\b", "fr", None),
]
_COMPILED = [(re.compile(p, re.I), role, sub) for p, role, sub in _RULES]
_GENERIC_CONTEXT = re.compile(r"^(introduction|general|overview|purpose|background)$")


def normalize_title(title):
    t = (title or "").strip()
    t = re.sub(r"^(\d+(\.\d+)*\.?|[A-Z]\.|>?figure\s+\S+)\s*", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" .:").lower()
    return "" if t in ("?", "none") else t


def classify_title(title):
    """Classifica um título isolado. Retorna (papel, subtipo) ou None."""
    t = normalize_title(title)
    if not t:
        return None
    for rx, role, sub in _COMPILED:
        if rx.search(t):
            return role, sub
    return None


def resolve_role(path_titles):
    """Papel efetivo de uma seção dado o caminho de títulos (raiz → folha).

    Usa o título mais específico que casa com alguma regra. Títulos de RNF
    específicos dentro de um contêiner de RF (ex.: "Performance" em
    "Specific Requirements") prevalecem por serem mais profundos.

    Exceção: tudo sob "Product/System Perspective" (IEEE 830 §2.1) é
    descritivo, mesmo subseções chamadas "User Interfaces" ou "Memory
    Constraints".
    """
    if any(re.search(r"\bperspective\b", normalize_title(t)) for t in path_titles[:-1]):
        return "context", None
    hits = [classify_title(t) for t in path_titles]
    for depth in range(len(hits) - 1, -1, -1):
        hit = hits[depth]
        if hit is None:
            continue
        # Títulos genéricos ("Introduction", "General", "Purpose") aninhados
        # num capítulo de requisitos herdam o papel do capítulo (ex.: THEMAS
        # 3.1.x > Introduction contém frases "shall").
        if hit[0] == "context" and _GENERIC_CONTEXT.search(normalize_title(path_titles[depth])):
            for anc in reversed(hits[:depth]):
                if anc is not None and anc[0] in ("fr", "nfr"):
                    return anc
        return hit
    return ("context", None) if not path_titles else ("unknown", None)
