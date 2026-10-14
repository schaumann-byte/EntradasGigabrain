# Gerador de reuniões

Gera **reuniões de levantamento de requisitos simuladas** a partir de documentos
de requisitos reais (SRS do dataset [PURE](https://zenodo.org/records/1414117)),
junto com o **gabarito** do que um sistema deveria extrair delas. Serve para
testar o módulo de entrada do sistema multiagente de Engenharia de Requisitos:
você entrega as transcrições ao sistema e compara o que ele extraiu com o gabarito.

```
 SRS do PURE (XML)                         reuniao_01.txt, reuniao_02.txt ...
 ┌──────────────────┐     gerador          (conversa bagunçada, em inglês)
 │ 3.1 The system   │  ───────────────►
 │ shall control... │                      gabarito_requisitos.json
 └──────────────────┘                      (requisitos + conflitos, ambiguidades...)
```

Os dados publicados ficam na pasta pai deste repositório (`EntradasGigabrain`,
ver o [README de lá](../README.md)). Esta pasta contém o código que os gera.
O diagnóstico completo, com decisões e números, está em
[RELATORIO_DIAGNOSTICO.md](RELATORIO_DIAGNOSTICO.md).

**Requisitos:** Python ≥ 3.10, só biblioteca padrão. Os SDKs `anthropic` ou
`openai` só são necessários para gerar a variante B com um LLM novo (ver
[Variante B](#variante-b-falas-reescritas-por-llm)).

---

## Início rápido

Todos os comandos rodam de dentro de `gerador_reunioes/`.

```bash
python scripts/download_data.py      # 1. baixa o PURE e o ReqFromSRS para data/ (uma vez só)
python -m pureprep.cli               # 2. gera tudo em output/
python -m pytest -q                  # 3. confere que nada quebrou
```

Pronto: as reuniões estão em `output/pairs/meetings/<variante>/<documento>/`.
Para o pipeline completo (dados, geração, baselines, validações e testes) use
`bash scripts/run_all.sh`.

---

## Como funciona

A geração passa por quatro etapas. Cada uma é determinística: com a mesma
semente (`--seed`, padrão 42) o resultado sai igual byte a byte.

```
  XML do PURE ──► 1. requisitos ──► 2. plano ──► 3. realizador ──► reuniao_NN.txt
                                        │                                 │
                                        └────────► 4. gabarito ◄──────────┘
                                                  gabarito_requisitos.json
```

1. **Extrair os requisitos** (`parse.py`, `taxonomy.py`, `extract.py`). Lê o XML,
   classifica cada seção pelo título (contexto, funcional, não funcional...) e
   separa os requisitos em FR/NFR, guardando a seção de origem.
2. **Planejar as reuniões** (`dialogue/plan.py`). Decide *o que* acontece, sem
   escrever texto ainda: quantas reuniões, quem participa, em que ordem os
   tópicos aparecem, e quais requisitos vão sofrer algum **fenômeno** (conflito,
   ambiguidade, omissão...) e como ele termina. O plano depende só da semente
   e do **perfil** de dificuldade.
3. **Escrever as falas** (o **realizador**). Transforma cada passo do plano em
   texto de conversa. Há dois realizadores:
   - `rules` (variante A): modelos de frase e um léxico casual (`resources/casual_en.json`);
   - `llm` (variante B): o mesmo plano, com as falas reescritas por um LLM.
4. **Montar o gabarito** (`dialogue/gold.py`). Como o plano registra o que foi
   dito, em qual turno e com qual desfecho, o gabarito sai direto dele, com a
   referência exata de cada turno (`M2:T14` = reunião 2, turno 14).

Como A e B usam o **mesmo plano**, têm o **mesmo gabarito**. Comparar o
desempenho do sistema nas duas isola o efeito do estilo do texto.

### Exemplo

Trecho de `rules-realistic/1998-themas/reuniao_01.txt`:

```text
Meeting 1 of 2 (kickoff)
Participants: Analyst, Client, EndUser, TechLead

Analyst: Okay, what about load h/c um unit definitions?
EndUser: So, we need the THEMAS system to control t he heating.
Analyst: Got it.
EndUser: And cooling units well that are defined as part of the um THEMAS system.
```

Na reunião 2 alguém volta a falar desse requisito dizendo que o sistema *não*
deve controlar essas unidades, e ninguém percebe a contradição. No gabarito,
o requisito aparece assim (resumido):

```json
{
  "id": "1998-themas:R0011",
  "text": "The THEMAS system shall control t he heating and cooling units that are defined as part of the THEMAS system.",
  "class": "FR",
  "status": "inconsistent",
  "expected_in_output": true,
  "phenomena": [{"type": "inconsistency", "kind": "polarity", "outcome": "unnoticed",
                 "segments": ["M1:T4", "M1:T6", "M2:T46"]}],
  "source": {"section_id": "3.1.1.1.1"}
}
```

e a lista `issues` traz o problema que o sistema deveria apontar
(`"expected_action": "flag_inconsistency"`).

---

## Variantes: realizador × perfil

Cada variante tem o nome `<realizador>-<perfil>`, por exemplo `rules-realistic`.
São 3 perfis × 2 realizadores = 6 variantes, todas sobre os mesmos 18 documentos.

| perfil | reuniões | requisitos com fenômeno | estilo dos turnos |
|---|---|---|---|
| `clean` | 1 | nenhum (só linguagem casual) | falas longas, como no v1 |
| `realistic` | 2–3 | ~25% | falas quebradas em turnos curtos, com "uhum", "right" entre eles |
| `hard` | 3–4 | ~45% | idem |

A quebra em turnos curtos foi calibrada contra reuniões reais do AMI Meeting
Corpus (RELATORIO §5.3). Os parâmetros de cada perfil ficam em
`pureprep/dialogue/profiles.py`.

### Fenômenos

Cada requisito sofre no máximo um fenômeno. O campo `status` do gabarito diz
o que o sistema deveria concluir sobre ele:

| fenômeno | como aparece na conversa | `status` no gabarito |
|---|---|---|
| reuniões separadas | 1–4 arquivos, recapitulação no início, participantes variam | — |
| bagunça | ordem fora do documento, tópico retomado, interrupção, falso começo, conversa paralela | — |
| conflito de valor ou ator | alguém propõe outro número ou papel e é contestado | `conflict_resolved` ou `conflict_open` (a proposta derrotada vai para `distractors`) |
| conflito de escopo | "do we really need that?" | `conflict_resolved`, `rejected` ou `conflict_open` |
| conflito adiado | "let's park it" e a decisão sai numa reunião seguinte | `conflict_resolved` ou `rejected` |
| ambiguidade | número vago, ator vago, "it" sem referente, obrigatoriedade hesitante | `ambiguous` |
| inconsistência | reafirmado depois com valor diferente, sem ninguém notar | `inconsistent` |
| incompletude | valor ou condição faltando, fala cortada; às vezes completada depois | `incomplete` ou `clear` |
| omissão | o requisito nunca é discutido | `omitted` (`expected_in_output: false`) |

Ambiguidade, inconsistência, incompletude e conflitos em aberto também geram
uma entrada em `issues`, com a ação esperada do sistema (ex.: `ask_clarification`).

---

## Tarefas comuns

### Gerar só algumas variantes

```bash
python -m pureprep.cli --profiles realistic          # só rules-realistic
python -m pureprep.cli --profiles clean,hard --seed 7
```

### Avaliar o seu sistema

1. Rode o sistema sobre as reuniões de uma variante e salve **um arquivo por documento**,
   `<doc_id>.json`, neste formato:

   ```json
   {"requirements": [
      {"text": "The system shall ...", "class": "FR", "subtype": null,
       "source_text": "trecho literal da reunião que justifica o requisito"}
    ],
    "issues": [
      {"type": "ambiguity", "requirement_text": "...", "source_text": "...", "question": "..."}
    ]}
   ```

   `issues[].type` aceita `conflict`, `ambiguity`, `inconsistency` e `incompleteness`
   (sinônimos comuns também são reconhecidos).

2. Avalie:

   ```bash
   python -m pureprep.evaluate --pairs output/pairs/meetings/rules-realistic \
                               --pred minhas_predicoes/rules-realistic --out relatorio.json
   ```

O relatório traz precisão, revocação e F1 sobre os requisitos esperados,
revocação por `status` e por desfecho, quantos distratores, rejeitados e
omitidos o sistema caiu, taxa de alucinação de detalhe (o número que ninguém
disse) e P/R/F1 das `issues`.

Para ter uma régua de comparação, gere os baselines: `oracle` devolve o próprio
gabarito (F1 = 1, valida o avaliador) e `naive` pega toda frase com "shall",
"must", "need"...

```bash
python -m pureprep.baseline --pairs output/pairs/meetings/rules-realistic --kind naive --out preds/naive
```

### Publicar no EntradasGigabrain

```bash
git commit ...                                   # o exportador exige o gerador commitado
python scripts/export_entradas.py                # todas as variantes
python scripts/export_entradas.py --variants rules-hard,llm-hard
python scripts/export_entradas.py --index-only   # só regenera indice_documentos.csv
```

O script copia `output/pairs/meetings/<variante>/` para `../variantes/<variante>/`,
renomeia o gabarito para `gabarito_requisitos.json`, grava um `manifest.json`
(commit do gerador, semente, parâmetros) e regenera `../indice_documentos.csv`.
Ele se recusa a rodar se houver alterações não commitadas em `gerador_reunioes/`,
para que o manifesto sempre aponte um commit reproduzível. Depois é só commitar
a pasta pai.

### Variante B: falas reescritas por LLM

O realizador `llm` (`pureprep/dialogue/realize_llm.py`) reescreve as falas do
plano em janelas de ~20 turnos. **As respostas já estão em cache** em
`llm_cache/`, então reproduzir a variante B não chama nenhuma API:

```bash
python -m pureprep.cli --realizer llm --llm-offline
```

Para gerar com um LLM novo (outro modelo, prompt alterado):

```bash
# 1. orçar: não chama nada, só conta requisições e tokens
python -m pureprep.cli --realizer llm --llm-provider dry
# 2. gerar (precisa de ANTHROPIC_API_KEY; ou OPENAI_API_KEY com --llm-provider openai --llm-model ...)
python -m pureprep.cli --realizer llm
# 3. versionar o cache para que outros reproduzam sem gastar
git add llm_cache && git commit -m "Cache da variante B"
```

Para as 3 variantes B (18 documentos × perfis `clean`, `realistic`, `hard`), o
dry-run estimou 470 requisições, ~0,8 M tokens de entrada e ~0,35 M de saída.

Garantias do realizador `llm`:

- **O LLM nunca vê o detalhe escondido.** O prompt leva só o que o plano manda
  dizer; o valor removido por uma ambiguidade ou incompletude não chega ao modelo.
- **Cada fala é verificada** e, se falhar, volta para a fala da variante A:
  números preservados, nenhum número inventado, detalhe removido não reaparece,
  ≥ 50% das palavras de conteúdo mantidas, tamanho compatível. Os motivos
  ficam em `generator.realizer_stats` no gabarito.
- **Mesmo ruído da A.** Hesitações ("uh", "um", palavras quebradas) são aplicadas
  depois, com a mesma semente. Um B sem nenhuma fala aceita é idêntico à A.
- **Provedores:** `anthropic` (padrão `claude-opus-5-5`, `--llm-effort low`),
  `openai` (ou qualquer API compatível via `--llm-base-url`, ex.: Ollama em
  `http://localhost:11434/v1`) e `dry`. Prefira um modelo de **família diferente**
  da do sistema avaliado (RELATORIO §5.1).

---

## Referência

### Parâmetros de `python -m pureprep.cli`

| parâmetro | padrão | o que faz |
|---|---|---|
| `--out` | `output` | pasta de saída |
| `--xml-dir` | `data/raw/requirements-xml/XMLZIPFile` | XMLs do PURE |
| `--seed` | `42` | semente de tudo que é aleatório |
| `--profiles` | `clean,realistic,hard` | perfis do modo `meetings` (vazio desativa) |
| `--realizer` | `rules` | `rules` (variante A) ou `llm` (variante B) |
| `--support-threshold` | `0.6` | similaridade mínima para ligar um requisito a um trecho da entrada |
| `--dialogue-cap` | `60` | máximo de requisitos sorteados por documento (≈ 1 h de reunião) |
| `--noise` | `0.08` | taxa de ruído de fala (hesitações, palavras quebradas) |
| `--llm-provider` | `anthropic` | `anthropic`, `openai` ou `dry` |
| `--llm-model` | `claude-opus-5-5` | obrigatório com `openai` |
| `--llm-effort` | `low` | esforço de raciocínio (só `anthropic`) |
| `--llm-base-url` | — | API compatível com OpenAI |
| `--llm-cache` | `llm_cache` | pasta do cache de respostas |
| `--llm-offline` | — | usa só o cache; falha se faltar resposta |
| `--llm-workers` | `8` | requisições em paralelo |
| `--llm-window` | `20` | turnos por requisição |

### O que sai em `output/`

```
output/
  pairs/meetings/<variante>/<doc_id>/reuniao_NN.txt
  pairs/meetings/<variante>/<doc_id>/ground_truth_requirements.json   # gabarito schema 2.0
  pairs/{context,notes,dialogue}/<doc_id>/...                         # modos v1 (abaixo)
  audit/plans/<perfil>/<doc_id>.json      # o plano de cada documento (turnos, fenômenos, desfechos)
  audit/section_roles/<doc_id>.json       # papel atribuído a cada seção do SRS
  manifest.json, summary.csv              # estatísticas e adequação de cada documento
  baselines/                              # predições e avaliações oracle/naive (run_all.sh)
  crosscheck_reqfromsrs.json              # concordância com anotação humana (ReqFromSRS)
  originals_scan.csv                      # triagem dos 79 documentos originais
```

### Modos v1 (congelados)

Além das reuniões (`meetings`, gabarito schema 2.0), o gerador mantém os três
modos da primeira versão, com gabarito schema 1.0. Eles não mudam mais:

| modo | entrada |
|---|---|
| `context` | texto real das seções discursivas do SRS |
| `notes` | lista informal de necessidades |
| `dialogue` | uma reunião com ruído lexical; reproduz byte a byte a variante `v1-original` publicada (garantido por `tests/test_regression_v1.py`) |

### Mapa do código

| arquivo | função |
|---|---|
| `pureprep/cli.py` | ponto de entrada: gera todos os modos e variantes |
| `pureprep/parse.py` | lê o XML do PURE em seções e blocos |
| `pureprep/taxonomy.py` | classifica cada seção pelo título |
| `pureprep/extract.py` | extrai os requisitos e a classe FR/NFR |
| `pureprep/synth.py` | modos v1 (`context`, `notes`, `dialogue`) |
| `pureprep/dialogue/plan.py` | plano das reuniões |
| `pureprep/dialogue/profiles.py` | parâmetros dos perfis `clean`, `realistic`, `hard` |
| `pureprep/dialogue/transforms.py` | como cada fenômeno altera o texto de um requisito |
| `pureprep/dialogue/realize_rules.py` | realizador `rules` (variante A) |
| `pureprep/dialogue/realize_llm.py`, `llm_providers.py` | realizador `llm` (variante B) e provedores |
| `pureprep/dialogue/gold.py` | gabarito schema 2.0 |
| `pureprep/evaluate.py`, `evaluate_meetings.py` | avaliação (schema 1.0 e 2.0) |
| `pureprep/baseline.py` | baselines `oracle` e `naive` |
| `pureprep/crosscheck.py` | comparação com o ReqFromSRS |
| `pureprep/scan_originals.py` | triagem dos documentos originais |
| `scripts/download_data.py` | baixa PURE e ReqFromSRS (com checagem MD5) |
| `scripts/export_entradas.py` | publica as variantes na pasta pai |
| `scripts/run_all.sh` | pipeline completo |
