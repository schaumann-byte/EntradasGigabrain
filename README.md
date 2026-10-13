# pure_ingestao — banco de testes do módulo de ingestão (PURE)

Transforma os SRS do dataset PURE em pares de teste para o módulo de
entrada do sistema multiagente de Engenharia de Requisitos:

- **entrada**: texto bruto simulando a entrada (contexto discursivo, notas de necessidades, transcrição de reunião ou várias reuniões);
- **gabarito**: requisitos RF/RNF de referência, com rastreabilidade até a seção do SRS de origem **e** até o trecho da entrada que os sustenta.

Somente biblioteca padrão do Python (≥ 3.10). Diagnóstico completo em
[RELATORIO_DIAGNOSTICO.md](RELATORIO_DIAGNOSTICO.md).

## Execução

```bash
bash scripts/run_all.sh          # baixa dados, gera pares, roda baselines, validações e testes
# ou passo a passo:
python scripts/download_data.py                   # PURE (Zenodo, com MD5) + ReqFromSRS
python -m pureprep.cli --out output               # gera os pares (v1 + meetings)
python -m pureprep.evaluate --pairs output/pairs/context --pred <pasta_predições> --out relatorio.json
python -m pytest -q
python scripts/export_entradas.py                 # publica as variantes meetings em ../Entradas
```

Parâmetros de `pureprep.cli`: `--seed` (padrão 42), `--support-threshold` (0,6),
`--dialogue-cap` (60 requisitos por reunião), `--noise` (0,08),
`--profiles` (`clean,realistic,hard`; vazio desativa o modo meetings),
`--realizer` (`rules`).

## Modos

| modo | entrada | gabarito | estado |
|---|---|---|---|
| `context` | texto real das seções discursivas do SRS | schema 1.0 | congelado (v1) |
| `notes` | lista informal de necessidades | schema 1.0 | congelado (v1) |
| `dialogue` | uma reunião, ruído lexical | schema 1.0 | **congelado**: reproduz byte a byte o dataset `Entradas` v1.0 (`tests/test_regression_v1.py`) |
| `meetings` | várias reuniões, bagunça e fenômenos de requisitos | schema 2.0 | ativo |

### Modo `meetings`: plano + realizador

```
requisitos ─► plan.build_plan ─► realizador ─► gold.build_gold
              (estrutura e         (superfície    (gabarito 2.0 a
               fenômenos)           do texto)      partir do log)
```

- **Plano** (`pureprep/dialogue/plan.py`): divide em reuniões, escolhe participantes, embaralha
  tópicos, decide interrupções e quais requisitos sofrem cada fenômeno e com qual desfecho.
  Depende só de `seed` e do perfil; **não** depende do realizador.
- **Realizador** (`pureprep/dialogue/realize_*.py`): escreve as falas. `rules` (variante A) usa
  modelos e léxico casual (`resources/casual_en.json`). Um realizador `llm` (variante B) deve
  consumir o **mesmo plano** — assim A e B têm o mesmo gabarito e a comparação isola o efeito
  da superfície do texto.
- **Variante** = `<realizador>-<perfil>`, ex.: `rules-realistic`. Todas usam a mesma amostra de
  requisitos do `dialogue` v1.

Fenômenos (no máximo um por requisito) e o que viram no gabarito:

| fenômeno | como aparece na conversa | `status` | extra no gabarito |
|---|---|---|---|
| reuniões separadas | 1–4 arquivos `reuniao_NN.txt`, recapitulação, participantes variam | — | segmentos `M2:T14` |
| bagunça | ordem fora do documento, tópico retomado, interrupção no meio da fala, falso começo, *crosstalk*, *smalltalk* | — | `stats.messiness` |
| conflito de valor/ator | um propõe variante (número ou papel trocado), outro contesta | `conflict_resolved` ou `conflict_open` | `distractors` (proposta rejeitada) |
| conflito de escopo | "do we really need that?" | `conflict_resolved`, `rejected` ou `conflict_open` | — |
| conflito adiado | "let's park it" → decidido numa reunião seguinte | `conflict_resolved` / `rejected` | desfecho `resolved_later` |
| ambiguidade | número vago, ator vago, referência vaga ("it"), obrigatoriedade hesitante | `ambiguous` | `issues` (`ask_clarification`) |
| inconsistência | reafirmado depois com valor divergente; ninguém percebe | `inconsistent` | `issues` |
| incompletude | valor faltante, condição omitida, fala cortada; às vezes completada depois | `incomplete` ou `clear` | `issues`; desfecho `completed_later` |
| omissão | requisito nunca discutido | `omitted` | `expected_in_output: false` |

Perfis (`pureprep/dialogue/profiles.py`): `clean` (1 reunião, sem fenômenos; só a superfície
casual), `realistic` (2–3 reuniões, ~30% dos requisitos com fenômeno), `hard` (3–4 reuniões,
~50%).

### Como adicionar o realizador B (LLM)

1. Criar `pureprep/dialogue/realize_llm.py` com `realize(plan, rng) -> [(meeting, texto, segmentos)]`,
   mesma assinatura de `realize_rules.realize`. Cada `Turn` do plano traz `speaker`, `act`,
   `utts` (conteúdo do requisito a expressar, já transformado pelo plano, com `flags`) e `info`.
2. Verificar cada fala gerada (cobertura de tokens do `Utt.text`, números preservados) e cair
   para `realize_rules.render_turn` quando a verificação falhar.
3. Guardar as respostas do LLM em cache versionado (chave = hash de prompt + modelo + turno),
   pois o LLM não é determinístico.
4. Registrar em `REALIZERS` (`pureprep/dialogue/__init__.py`) e gerar com `--realizer llm`.

## Saída

```
output/
  pairs/{context,notes,dialogue}/<doc_id>/input_raw.txt
  pairs/{context,notes,dialogue}/<doc_id>/ground_truth_requirements.json
  pairs/meetings/<variante>/<doc_id>/reuniao_NN.txt
  pairs/meetings/<variante>/<doc_id>/ground_truth_requirements.json   # schema 2.0
  audit/section_roles/<doc_id>.json     # papel atribuído a cada seção (auditoria dos rótulos)
  audit/plans/<perfil>/<doc_id>.json    # plano das reuniões (turnos, fenômenos, desfechos)
  manifest.json, summary.csv            # estatísticas e tiers de adequação por documento
  baselines/                            # predições e avaliação oracle/naive
  crosscheck_reqfromsrs.json            # validação contra anotação humana (REQINONE)
  originals_scan.csv                    # triagem dos 79 originais (PDF/DOC/HTML/RTF)
```

## Formato da predição esperada pelo avaliador

Um arquivo `<doc_id>.json` por documento:

```json
{"requirements": [
  {"text": "The system shall ...", "class": "FR", "subtype": null,
   "source_text": "trecho literal da entrada que justifica o requisito"}
 ],
 "issues": [
  {"type": "ambiguity", "requirement_text": "...", "source_text": "...", "question": "..."}
 ]}
```

`issues` só é avaliado no schema 2.0 (`type` ∈ `conflict`, `ambiguity`, `inconsistency`,
`incompleteness`; sinônimos comuns são aceitos). Métricas do schema 2.0
(`pureprep/evaluate_meetings.py`): P/R/F1 sobre `expected_in_output`, revocação por status e
por desfecho, acertos em distratores/rejeitados/omitidos, taxa de alucinação de detalhe
(o número que ninguém disse) e P/R/F1 de issues.

## Módulos

| módulo | função |
|---|---|
| `pureprep/parse.py` | leitura do XML `req_document.xsd` → seções e blocos (parágrafo, item, `<req>`) |
| `pureprep/taxonomy.py` | papel de cada seção pelo título (meta, context, scenario, fr, nfr + subtipo) |
| `pureprep/extract.py` | gabarito (primário/secundário), classe FR/NFR, limpeza de IDs, padrão IPO |
| `pureprep/synth.py` | modos de entrada `context`, `notes`, `dialogue` (v1); rastreabilidade (`support`) |
| `pureprep/dialogue/` | modo `meetings`: `transforms`, `profiles`, `plan`, `realize_rules`, `gold` |
| `pureprep/evaluate.py` | P/R/F1 de extração, classificação, Trace-to-Source, taxa sem suporte |
| `pureprep/evaluate_meetings.py` | métricas do schema 2.0 (distratores, issues, recall por status) |
| `pureprep/baseline.py` | baselines `oracle` e `naive` (v1 e meetings) |
| `pureprep/crosscheck.py` | concordância com o ReqFromSRS |
| `pureprep/scan_originals.py` | triagem dos 79 documentos originais |
| `scripts/export_entradas.py` | publica variantes em `Entradas/variantes/` e regenera o índice |
