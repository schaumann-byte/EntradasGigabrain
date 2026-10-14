# Dataset de Entradas: Reuniões de Elicitação e Gabarito de Requisitos

Conjunto de dados para experimentos de **Engenharia de Requisitos** e **Melhoria de Processos de Software**: reuniões de elicitação simuladas e o gabarito (*ground truth*) dos requisitos que elas contêm. A base é o dataset público **PURE** (*Public Requirements Engineering Dataset*, [Zenodo 10.5281/zenodo.1414117](https://doi.org/10.5281/zenodo.1414117)).

Os dados são gerados pelo `pureprep` (pasta [`gerador_reunioes/`](gerador_reunioes/), antigo repositório `pure_ingestao`) com transformações **determinísticas, sem IA generativa**. Cada variante traz no `manifest.json` o commit do gerador, a semente e os parâmetros usados, o que a torna reproduzível.

---

## 1. Variantes

Requisitos raramente surgem limpos. Eles aparecem espalhados por várias reuniões, no meio de discussões, conflitos, falas vagas e informações que faltam. Para medir o quanto isso atrapalha um extrator de requisitos, o dataset tem **variantes com níveis crescentes de ruído**. Todas usam o **mesmo conjunto de requisitos** por documento.

| variante | reuniões/doc | o que tem | gabarito |
|---|:---:|---|:---:|
| `v1-original` | 1 | Dataset original (tag `v1.0`): uma reunião, ruído só lexical ("uh", gagueira, `[crosstalk]`), todo requisito dito com clareza | schema 1.0 |
| `rules-clean` | 1 | Mesma estrutura, com fala mais casual: contrações, léxico coloquial, 1ª pessoa, marcadores de discurso | schema 2.0 |
| `rules-realistic` | 2–3 | Várias reuniões, conversa bagunçada e ~25% dos requisitos com algum fenômeno (conflito, ambiguidade, inconsistência, incompletude) | schema 2.0 |
| `rules-hard` | 3–4 | Bagunça intensa e ~45% dos requisitos com fenômeno | schema 2.0 |
| `llm-clean` · `llm-realistic` · `llm-hard` | 1 · 2–3 · 3–4 | Variante B: **mesmo plano e mesmo gabarito** das `rules-*` correspondentes, com as falas reescritas por LLM (Claude Opus 5.5, ver seção 3) | schema 2.0 |

O prefixo indica o **realizador**, isto é, quem escreve as falas: `rules` são regras (variante A) e `llm` é um modelo de linguagem (variante B). O sufixo indica o **perfil de ruído**. Variantes com o mesmo perfil e realizadores diferentes compartilham o mesmo plano de reuniões, os mesmos fenômenos e o mesmo gabarito. A comparação A × B isola o efeito da linguagem.

### Números agregados (18 documentos, 820 requisitos)

| variante | palavras | esperados na saída | clear | conflito resolvido | conflito aberto | rejeitado | ambíguo | inconsistente | incompleto | omitido | issues | distratores |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `v1-original` | 35.398 | 820 | 820 | – | – | – | – | – | – | – | – | – |
| `rules-clean` | 37.628 | 820 | 820 | – | – | – | – | – | – | – | – | – |
| `rules-realistic` | 46.304 | 781 | 614 | 22 | 18 | 15 | 64 | 21 | 42 | 24 | 145 | 6 |
| `rules-hard` | 48.924 | 761 | 438 | 46 | 43 | 16 | 110 | 52 | 72 | 43 | 277 | 3 |
| `llm-clean` | 36.804 | 820 | 820 | – | – | – | – | – | – | – | – | – |
| `llm-realistic` | 50.849 | 781 | 614 | 22 | 18 | 15 | 64 | 21 | 42 | 24 | 145 | 6 |
| `llm-hard` | 55.133 | 761 | 438 | 46 | 43 | 16 | 110 | 52 | 72 | 43 | 277 | 3 |

O detalhamento por documento está em [`indice_documentos.csv`](indice_documentos.csv), com uma linha por (variante, documento).

---

## 2. Estrutura de diretórios

```text
Entradas/
├── README.md
├── indice_documentos.csv              # uma linha por (variante, documento)
├── gerador_reunioes/                 # código do gerador (pureprep), testes e cache LLM
├── originais/<doc_id>.pdf             # documento de requisitos original (compartilhado)
└── variantes/
    ├── v1-original/<doc_id>/
    │   ├── transcricao_reuniao.txt
    │   └── gabarito_requisitos.json   # schema 1.0
    └── rules-realistic/               # (idem rules-clean, rules-hard)
        ├── manifest.json              # commit do gerador, semente, parâmetros, estatísticas
        └── <doc_id>/
            ├── reuniao_01.txt
            ├── reuniao_02.txt
            └── gabarito_requisitos.json   # schema 2.0
```

Projetos: `0000-cctns`, `0000-gamma-j`, `1995-gemini`, `1998-themas`, `1999-dii`, `1999-tcs`, `2003-qheadache`, `2005-microcare` (sem requisitos normativos, tier C), `2005-phin`, `2006-eirene-sys-15`, `2007-eirene-fun-7-2`, `2007-ertms`, `2007-get-real-0-2`, `2008-keepass`, `2008-peering`, `2009-peppol-approved`, `2009-video-search`, `2010-blitdraft`.

---

## 3. As reuniões (`reuniao_NN.txt`)

```text
Meeting 2 of 3 (follow-up)
Participants: Analyst, Client, TechLead

Analyst: Hi everyone, thanks for making time again. Let's pick up where we left off on KeePass Password Safe.
Analyst: Quick recap from last time: we went over new database, open database and search database. We also left a few things open.
Client: Oh, about master password from last time, I checked: ...
```

- **Participantes**: `Analyst` (conduz), `Client` (negócio), `TechLead` (restrições técnicas e RNF), `EndUser` (uso). A composição muda de reunião para reunião.
- **Bagunça**: tópicos fora da ordem do documento, tópico retomado mais tarde ("going back to search…"), stakeholder que puxa o tópico sem o analista perguntar, interrupção no meio de uma fala que é retomada depois, falso começo ("We need the— actually, …"), *crosstalk*, conversa de abertura e comentários fora do tópico.
- **Turnos curtos** (`realistic`/`hard`): falas longas são fatiadas em pedaços do mesmo falante, cortados só em fronteiras naturais (fim de frase, vírgula, oração), com *backchannel* ("Mm-hmm.", "Okay.") e reações curtas de outros participantes ("Yeah, agreed.") entre eles. A mediana cai de 16 palavras por turno (v1) para 9–10, e os turnos de até duas palavras sobem de 17% para 22–29%. O `clean` mantém a estrutura de turnos do v1.
- **Ruído lexical**: hesitações, muletas, gagueira e marcas `[laughter]`, `[crosstalk]`, `[pause]`, como no v1.

### Variante B: como as falas foram escritas

Nas `llm-*`, cada fala foi reescrita pelo **Claude Opus 5.5** (`claude-opus-5-5`, esforço `low`, prompt `b2`), a partir do mesmo plano da `rules-*` correspondente. O LLM recebeu só o conteúdo que cada fala deve expressar; o detalhe removido de propósito (ambiguidade, incompletude) nunca chegou a ele. Cada fala gerada foi verificada, e as reprovadas voltaram para o texto da variante A:

| variante | falas | aceitas do LLM | voltaram para a A |
|---|---:|---:|---:|
| `llm-clean` | 1.611 | 1.583 (98,3%) | 28 |
| `llm-realistic` | 3.335 | 3.284 (98,5%) | 51 |
| `llm-hard` | 3.226 | 3.195 (99,0%) | 31 |

As hesitações e marcas (`uh`, `[crosstalk]`…) são aplicadas depois, iguais às da variante A, então A e B diferem só na paráfrase. O motivo de cada fallback está em `generator.realizer_stats` de cada gabarito. Exemplo do mesmo turno nas duas variantes (2008-keepass, `realistic`):

> **A:** Well, when the database is found, the master password is wanted so that erm the database will be unlocked, that's uhm the the main thing.
>
> **B:** Once the database is found, it asks for the master password so um the database can be unlocked.

O DeepSeek, usado pelo Gigabrain, é de outra família, o que evita que o sistema avaliado "reconheça" o próprio estilo de escrita.

### Fenômenos de requisitos

Cada requisito recebe no máximo um fenômeno.

| fenômeno | como aparece | `status` final |
|---|---|---|
| **Conflito de valor/ator** | Um stakeholder propõe uma variante (número ou papel trocado, ex.: "5 sec" × "15 sec", "the driver" × "the operator") e outro contesta. O analista decide na hora ou adia ("let's park it"). O que foi adiado pode ser decidido numa reunião seguinte. | `conflict_resolved` (vence a versão original; a proposta perdedora vira **distrator**) ou `conflict_open` |
| **Conflito de escopo** | "Do we really need that?" seguido de defesa. Desfecho: mantém, retira ou adia. | `conflict_resolved`, `rejected` (retirado; **não** deve ser extraído) ou `conflict_open` |
| **Ambiguidade** | Número vago ("a few seconds"), ator vago ("someone"), referência vaga ("it should…") ou obrigatoriedade hesitante ("it'd be nice if…"). Às vezes o analista pede detalhes e recebe uma evasiva. | `ambiguous` |
| **Inconsistência** | O requisito é reafirmado mais tarde, em geral em outra reunião, com valor, ator ou polaridade divergente ("shall" × "shall not"), e ninguém percebe. | `inconsistent` |
| **Incompletude** | Valor faltante ("I'd have to check the exact number"), condição omitida ou fala cortada. Às vezes alguém traz a informação numa reunião seguinte. | `incomplete` ou `clear` (completado depois) |
| **Omissão** | O requisito existe no SRS, mas nunca é discutido. | `omitted` (**não** deve ser extraído) |

---

## 4. O gabarito schema 2.0 (`gabarito_requisitos.json`)

```jsonc
// exemplo ilustrativo (valores abreviados)
{
  "schema_version": "2.0",
  "doc_id": "2008-keepass",
  "variant": "rules-realistic",
  "generator": {"tool": "pureprep", "realizer": "rules", "profile": "realistic", "params": {"seed": 42, ...}},
  "input": {
    "n_meetings": 2,
    "meetings": [{"id": "M1", "file": "reuniao_01.txt", "kind": "kickoff", "participants": [...], "topics": [...],
                  "segments": [{"id": "M1:T7", "start": 812, "end": 960, "speaker": "Client", "act": "state",
                                "gt_ids": ["2008-keepass:R0009"],
                                "refs": [{"rid": "2008-keepass:R0009", "role": "statement", "pid": "P3"}]}]}]
  },
  "stats": {"by_status": {...}, "phenomena": {"conflict:resolved_later": 1, ...}, "messiness": {...}, ...},
  "requirements": [{
    "id": "2008-keepass:R0009", "text": "<texto canônico do SRS>", "class": "FR", "subtype": null,
    "status": "conflict_resolved", "expected_in_output": true,
    "phenomena": [{"pid": "P3", "type": "conflict", "kind": "value", "outcome": "resolved_later",
                   "details": {"original_value": "100 characters", "proposed_value": "50 characters", ...},
                   "segments": ["M1:T7", "M1:T8", "M1:T9", "M1:T10", "M2:T12"]}],
    "trace": {"input_segments": [...], "related_segments": [...], "support_score": 0.97, "reachable": true}
  }],
  "distractors": [{"id": "...:D001", "text": "<proposta rejeitada>", "requirement": "...", "segments": [...]}],
  "issues": [{"id": "...:I001", "type": "ambiguity", "kind": "vague_quantity", "requirement": "...",
              "expected_action": "ask_clarification", "segments": [...], "details": {...}}]
}
```

- **`start`/`end`** são posições de caractere (Unicode) no arquivo da reunião, com quebras de linha LF. `text[start:end]` é exatamente a fala, sem o prefixo `Falante: `.
- **`refs[].role`** indica o papel da fala em relação ao requisito: `statement`, `part1`/`part2` (fala interrompida), `echo`, `resolution`, `followup`, `restatement` (versão inconsistente), `distractor` (proposta rejeitada), `conflict`, `clarification`.
- **`trace.input_segments`** são as falas que carregam a versão válida do requisito. **`related_segments`** inclui também objeções, adiamentos e versões divergentes.
- **`expected_in_output`** é `false` para `rejected` e `omitted`. Um bom extrator **não** deve devolver esses requisitos, nem os `distractors`.
- **`issues`** lista o que um bom sistema deveria **apontar** em vez de silenciar: conflitos em aberto, ambiguidades, inconsistências e lacunas. Cada issue tem a ação esperada (`ask_clarification`, `resolve_with_stakeholders`, `flag_inconsistency`, `request_missing_information`).
- O texto canônico em `requirements[].text` é sempre o do SRS original. Num requisito ambíguo ou incompleto, isso inclui o detalhe que **ninguém disse** na reunião (veja a métrica de alucinação abaixo).

O schema 1.0 (`v1-original`) é o formato anterior: um arquivo `transcricao_reuniao.txt`, segmentos `T1…Tn` em `input.segments`, sem status, distratores ou issues.

---

## 5. Avaliação

O avaliador está em `pureprep.evaluate` e despacha automaticamente pelo `schema_version`. A predição é um JSON por documento:

```json
{"requirements": [{"text": "The system shall ...", "class": "FR", "subtype": null, "source_text": "trecho citado"}],
 "issues": [{"type": "ambiguity", "requirement_text": "...", "source_text": "...", "question": "..."}]}
```

```bash
python -m pureprep.evaluate --pairs output/pairs/meetings/rules-realistic --pred minhas_predicoes/rules-realistic --out relatorio.json
```

Métricas do schema 2.0:

| métrica | o que mede |
|---|---|
| `extraction.{precision, recall_expected, f1_expected}` | Extração contra os requisitos `expected_in_output` |
| `recall_by_status`, `recall_by_phenomenon` | Onde o sistema perde: requisitos ambíguos? completados em outra reunião? |
| `false_positives.{distractor_hits, rejected_hits, omitted_hits}` | Extraiu a proposta derrotada, o requisito retirado ou algo nunca discutido |
| `detail_hallucination_rate` | Em requisitos ambíguos ou incompletos, fração em que a predição traz o detalhe removido (ex.: o número exato), que não aparece em lugar nenhum da entrada |
| `issues.{precision, recall, f1, recall_untyped, recall_by_type}` | Detecção de problemas. A issue casa com a do gabarito pelo texto do requisito ou pelo trecho citado |
| `classification_on_matched`, `trace_to_source`, `unsupported_rate` | Como no v1 |

### Baselines de referência

O `naive` transforma em requisito toda frase com modal ou expressão de necessidade e não detecta issues. O `oracle` devolve o gabarito.

| variante | P | R (esperados) | F1 | distratores extraídos | rejeitados extraídos |
|---|---:|---:|---:|---:|---:|
| `v1-original` | 0,673 | 0,782 | 0,723 | – | – |
| `rules-clean` | 0,709 | 0,842 | 0,770 | 0 | 0 |
| `rules-realistic` | 0,540 | 0,721 | 0,617 | 6 | 14 |
| `rules-hard` | 0,504 | 0,677 | 0,578 | 3 | 15 |
| `llm-clean` | 0,608 | 0,607 | 0,608 | 0 | 0 |
| `llm-realistic` | 0,393 | 0,560 | 0,462 | 5 | 11 |
| `llm-hard` | 0,361 | 0,551 | 0,436 | 2 | 9 |

O `oracle` tem F1 = 1,0 em extração e issues, mas `detail_hallucination_rate` ≈ 0,55–0,63. Isso é esperado: ele copia o texto canônico do SRS, que contém detalhes que ninguém disse na reunião.

---

## 6. Limitações conhecidas

- **Distratores são raros** (3–6 por variante): só conflitos de valor ou de ator geram uma proposta perdedora distinguível lexicalmente, e poucos requisitos do PURE têm número ou ator explícito. Inversões de polaridade ("shall" × "shall not") entram apenas como inconsistência, porque "not" é stopword no casamento lexical.
- **Nas `rules-*`, as falas ainda carregam o texto do SRS.** O realizador `rules` muda a forma (modal, contrações, léxico, discurso), mas mantém as palavras de conteúdo, e requisitos longos continuam soando como documento. Nas `llm-*`, a paráfrase é real: a fração das palavras de conteúdo do requisito que aparece nas falas cai de 0,98 para 0,80–0,84.
- **A verificação das falas da variante B é por regras, não semântica.** Ela confere números, valores, detalhes removidos e uma cobertura mínima de palavras, mas não garante equivalência de significado. Falas reprovadas (1–1,7% por variante) voltam para o texto da `rules-*`. Uma revisão humana por amostragem é recomendada antes de conclusões fortes.
- **As falas curtas da variante B são um pouco mais longas** ("Yes, that's right." em vez de "Yep."): a mediana de palavras por turno sobe de 9–14 para 11–16, e os turnos de até duas palavras caem de 15–29% para 14–24%.
- **`v1-original` está congelado** como foi publicado. Os arquivos usam CRLF, e os offsets só batem quando o texto é lido com tradução de quebras de linha (Python em modo texto). O campo `input.file` do gabarito diz `input_raw.txt`, embora o arquivo se chame `transcricao_reuniao.txt`. As variantes 2.0 não têm esses problemas.

## 7. Como regenerar

Na pasta `gerador_reunioes/`:

```bash
python scripts/download_data.py
python -m pureprep.cli --out output                      # v1 + rules-clean/realistic/hard
python scripts/export_entradas.py                        # copia variantes para a pasta pai e regenera o índice
```

O `export_entradas.py` se recusa a exportar quando há alterações não commitadas no gerador, para que o `manifest.json` sempre aponte um commit reproduzível.
