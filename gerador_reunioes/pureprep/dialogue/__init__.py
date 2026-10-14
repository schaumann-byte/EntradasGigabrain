"""Modo ``meetings``: reuniões de elicitação com bagunça e fenômenos de
requisitos (conflito, ambiguidade, inconsistência, incompletude).

Arquitetura em duas fases para permitir variantes comparáveis:

    requisitos ──► plan.build_plan  (estrutura + fenômenos; depende só da
                                     semente e do perfil)
               ──► realizador       (superfície do texto: ``rules`` = A;
                                     ``llm`` = B)
               ──► gold.build_gold  (gabarito schema 2.0 a partir do log)

Com a mesma semente e o mesmo perfil, realizadores diferentes recebem o
mesmo plano — logo o mesmo gabarito de requisitos, fenômenos e desfechos.
"""

import random

from . import realize_llm, realize_rules
from .gold import build_gold, meeting_file
from .plan import build_plan
from .profiles import PROFILES, get_profile

REALIZERS = {"rules": realize_rules.realize, "llm": realize_llm.realize}


def variant_name(realizer, profile):
    return f"{realizer}-{profile}"


def build_meetings(doc, ext, reqs, *, profile, realizer, seed, realizer_options=None):
    """Retorna (plano, [(meeting, texto, segmentos)], gabarito).

    ``realizer_options`` vai para o realizador (ex.: ``provider``,
    ``cache_dir``, ``offline`` no ``llm``)."""
    if realizer not in REALIZERS:
        raise ValueError(f"realizador desconhecido: {realizer} (opções: {', '.join(REALIZERS)})")
    plan = build_plan(doc, ext, reqs, profile, random.Random(f"{seed}:{doc.doc_id}:meetings:{profile}"))
    # mesma semente de superfície para todo realizador (o sufixo "rules" é o da
    # variante A): ruído lexical e fallbacks são sorteados igual, e um B sem
    # nenhuma fala aceita reproduz A byte a byte
    surface_rng = random.Random(f"{seed}:{doc.doc_id}:meetings:{profile}:rules")
    out = REALIZERS[realizer](plan, surface_rng, **(realizer_options or {}))
    realized, rstats = out if isinstance(out, tuple) else (out, None)
    params = {"seed": seed, **get_profile(profile)}
    opts = realizer_options or {}
    if "provider" in opts:
        params["llm"] = {**opts["provider"].params(), "prompt_version": realize_llm.PROMPT_VERSION}
    gold = build_gold(doc, plan, realized, reqs, variant=variant_name(realizer, profile), realizer=realizer, params=params)
    if rstats is not None:
        # no gabarito só o que descreve o conteúdo; requisições, acertos de cache
        # e falhas de rede dependem da execução (vão em "_run_stats", fora do JSON)
        run_keys = ("requests", "cache_hits", "request_failed:")
        gold["generator"]["realizer_stats"] = {k: v for k, v in rstats.items() if not k.startswith(run_keys)}
        gold["_run_stats"] = rstats
    return plan, realized, gold


__all__ = ["PROFILES", "REALIZERS", "build_meetings", "build_plan", "meeting_file", "variant_name"]
