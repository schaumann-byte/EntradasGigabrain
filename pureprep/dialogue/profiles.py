"""Perfis de ruído. Probabilidades por requisito (mutuamente exclusivas: cada
requisito recebe no máximo um fenômeno semântico) e intensidade da bagunça
estrutural (``mess`` ∈ [0, 1]).

- ``clean``     : 1 reunião, ordem do documento, sem fenômenos semânticos.
                  Só a superfície casual do realizador + ruído lexical.
- ``realistic`` : 2–3 reuniões, bagunça moderada, ~25% dos requisitos com
                  algum fenômeno.
- ``hard``      : 3–4 reuniões, bagunça alta, ~45% com fenômeno.
"""

PROFILES = {
    "clean": {
        "meetings": (1, 1),
        "mess": 0.0,
        "p_omit": 0.0,
        "p_conflict": 0.0,
        "p_ambiguity": 0.0,
        "p_inconsistency": 0.0,
        "p_incomplete": 0.0,
        "p_conflict_open": 0.0,
        "p_resolve_later": 0.0,
        "p_complete_later": 0.0,
        "noise": 0.08,
    },
    "realistic": {
        "meetings": (2, 3),
        "mess": 0.4,
        "p_omit": 0.03,
        "p_conflict": 0.07,
        "p_ambiguity": 0.08,
        "p_inconsistency": 0.05,
        "p_incomplete": 0.08,
        "p_conflict_open": 0.4,
        "p_resolve_later": 0.5,
        "p_complete_later": 0.5,
        "noise": 0.10,
    },
    "hard": {
        "meetings": (3, 4),
        "mess": 0.75,
        "p_omit": 0.05,
        "p_conflict": 0.12,
        "p_ambiguity": 0.14,
        "p_inconsistency": 0.08,
        "p_incomplete": 0.12,
        "p_conflict_open": 0.55,
        "p_resolve_later": 0.35,
        "p_complete_later": 0.35,
        "noise": 0.14,
    },
}


def get_profile(name):
    if name not in PROFILES:
        raise ValueError(f"perfil desconhecido: {name} (opções: {', '.join(PROFILES)})")
    return dict(PROFILES[name])
