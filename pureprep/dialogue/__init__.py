"""Modo ``meetings``: reuniões de elicitação com bagunça e fenômenos de
requisitos (conflito, ambiguidade, inconsistência, incompletude).

Arquitetura em duas fases para permitir variantes comparáveis:

    requisitos ──► plan.build_plan  (estrutura + fenômenos; depende só da
                                     semente e do perfil)
               ──► realizador       (superfície do texto: ``rules`` = A;
                                     ``llm`` = B, a implementar)
               ──► gold.build_gold  (gabarito schema 2.0 a partir do log)

Com a mesma semente e o mesmo perfil, realizadores diferentes recebem o
mesmo plano — logo o mesmo gabarito de requisitos, fenômenos e desfechos.
"""

import random

from . import realize_rules
from .gold import build_gold, meeting_file
from .plan import build_plan
from .profiles import PROFILES, get_profile

REALIZERS = {"rules": realize_rules.realize}


def variant_name(realizer, profile):
    return f"{realizer}-{profile}"


def build_meetings(doc, ext, reqs, *, profile, realizer, seed):
    """Retorna (plano, [(meeting, texto, segmentos)], gabarito)."""
    if realizer not in REALIZERS:
        raise ValueError(f"realizador desconhecido: {realizer} (opções: {', '.join(REALIZERS)})")
    plan = build_plan(doc, ext, reqs, profile, random.Random(f"{seed}:{doc.doc_id}:meetings:{profile}"))
    realized = REALIZERS[realizer](plan, random.Random(f"{seed}:{doc.doc_id}:meetings:{profile}:{realizer}"))
    params = {"seed": seed, **get_profile(profile)}
    gold = build_gold(doc, plan, realized, reqs, variant=variant_name(realizer, profile), realizer=realizer, params=params)
    return plan, realized, gold


__all__ = ["PROFILES", "REALIZERS", "build_meetings", "build_plan", "meeting_file", "variant_name"]
