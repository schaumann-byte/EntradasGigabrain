# Relatório de diagnóstico — PURE como banco de testes do módulo de ingestão

**Projeto:** sistema multiagente de Engenharia de Requisitos (sumarização → extração no padrão INCOSE/IEEE → classificação RF/RNF)
**Data:** 23/09/2026 · **Artefatos:** `EntradasGigabrain/gerador_reunioes/` (código, saídas e testes reproduzíveis com `bash scripts/run_all.sh`)

---

## 0. Resumo executivo

1. **O PURE não estava no workspace.** Foi baixado do Zenodo (DOI 10.5281/zenodo.1414117, checksum MD5 verificado): 79 SRS originais (62 PDF, 13 DOC, 3 HTML, 1 RTF), dos quais **apenas 18 têm versão XML estruturada** [R6].
2. Dos 18 XMLs extraímos um gabarito de **2.926 requisitos primários (1.788 RF / 1.138 RNF)** e 199 secundários, com rastreabilidade até a seção de origem. O gabarito foi validado contra a anotação humana do ReqFromSRS (REQINONE [R2]): **cobertura de 89 %, concordância RF/RNF de 96 % e de subtipo RNF de 95 %**.
3. **Achado central:** o texto discursivo dos próprios SRS (Escopo, Perspectiva do Produto etc.) sustenta apenas **12,3 %** dos requisitos formais (359/2.926). Usar essas seções como "entrada bruta" e medir revocação contra todo o gabarito penalizaria o sistema por não "adivinhar" requisitos ausentes da entrada. Por isso o avaliador reporta `recall_reachable` e uma taxa de conteúdo sem suporte (proxy de alucinação).
4. Foram gerados **três modos de entrada** para cada documento: `context` (texto real, difícil), `notes` (lista informal de necessidades) e `dialogue` (reunião sintética com ruído de fala). Um baseline ingênuo sem LLM atinge F1 = 0,14 / 0,89 / 0,72 respectivamente, o que mostra que os modos discriminam níveis diferentes de dificuldade.
5. **Documentos recomendados:** 4 são ideais para entrada real (keepass, video-search, peering, peppol) e 10 para entrada sintetizada. Há ainda **25 documentos Tier A sem XML** que podem ampliar o benchmark se convertidos.
6. **O PURE não tem diálogos.** Recomendação: (a) síntese de diálogo em três níveis, com verificação de preservação semântica, e (b) complementar com o AMI Meeting Corpus, já presente localmente, para **calibrar e testar robustez de formato**, não como gabarito de requisitos.
7. **Atualização de 13/10/2026 (seção 5.3):** o nível N2 foi implementado por regras no novo modo `meetings`, com várias reuniões, conversa bagunçada, conflitos, ambiguidade, inconsistência e incompletude, e gabarito schema 2.0 com status, distratores e *issues*. O baseline ingênuo cai de F1 0,77 (`rules-clean`) para 0,62 (`rules-realistic`) e 0,58 (`rules-hard`). Nos requisitos ambíguos, a revocação fica em 0,25–0,35. A estrutura de turnos foi calibrada contra o AMI: a mediana cai de 16 para 9–10 palavras por turno, e o *backchannel* sobe de 17% para 22–29% (no AMI, 3 palavras e 45%).

---

## 1. Auditoria dos arquivos

### 1.1 Workspace
| Local | Conteúdo | Relevância |
|---|---|---|
| `Artigos/` | MARE [R1], REQINONE [R2], Elicitron [R3] + análise MARE (.pptx) | MARE e REQINONE usam PURE; Elicitron simula entrevistas |
| raiz | Survey LLM4SE [R4], roteiro da disciplina [R5], apresentação "O Impacto dos LLMs…" (imagem, sem camada de texto) | contexto; a apresentação destaca escassez de dados rotulados de RNF e risco de *data leakage* |
| `Sanitização de Texto/` | sanitizador de transcrições + **AMI Meeting Corpus** (98 reuniões em texto, com `gold.json` de decisões/ações) [R12] | reuso: léxicos de ruído e dados de diálogo real |
| `gerador_reunioes/` (novo) | PURE baixado, pipeline, saídas e testes | este trabalho |

### 1.2 Formato dos XMLs do PURE (`req_document.xsd`)
```
<req_document> <title/> <version/> <issue_date/>
  <p id="1"> <title>Introduction</title>
     <text_body> texto … <itemize|enum|description><item/></…> <crossref/> </text_body>
     <req id="REQ-1" part="Y" part_id="0"> <text_body/> <modifier>M</modifier> </req>
     <p id="1.1"> … </p>            ← seções aninhadas
```
Contagem de tags nos 18 XMLs: 2.698 `<p>`, 2.983 `<text_body>`, 3.126 `<item>`, **1.004 `<req>`** (em apenas 6 documentos: cctns, gamma-j, eirene-fun, ertms, keepass, peering), 199 `<modifier>` (M/O = obrigatório/opcional), 170 entradas de glossário.

**Conclusão:** a tag `<req>` não é confiável como gabarito isolado, porque 12 dos 18 documentos não a usam. Os requisitos estão em texto corrido, identificáveis por modais (*shall/must/should/will*) e pela seção onde aparecem.

### 1.3 Como os SRS estão fatiados
Os 18 documentos seguem cinco famílias de template, e cada uma exigiu regras próprias:

| Template | Documentos | Seções de entrada (discursivas) | Seções de gabarito |
|---|---|---|---|
| IEEE 830 [R8] | themas, qheadache, gemini | 1 Introduction/Purpose/Scope; 2 Product Perspective, Product Functions, User Characteristics | 3 Specific/Functional Requirements; Performance; Attributes |
| Wiegers/IEEE 830 web | gamma-j, keepass, peering, get-real, video-search | 1.4 Project Scope; 2.1–2.7 Overall Description; 3.x.1 *Description and Priority*; 3.x.2 *Stimulus/Response* | 3.x.3 Functional Requirements; 4 External Interfaces; 5 Other Nonfunctional |
| RUP/FURPS+ | blitdraft | 1 Purpose/Scope | 2.1 Functionality … 2.9 Applicable Standards |
| MIL-STD-498 (SSS/SRS) | tcs, dii | 1 Scope/System Overview | 3/4 Requirements (states & modes, capability, interfaces, quality factors) |
| Especificação ferroviária | eirene-sys-15, eirene-fun-7-2, ertms | 1 Introduction/Scope | capítulos técnicos com `<req>` e marca (M)/(O) |
| Relatório/visão | peppol, microcare, phin, cctns | Vision/Scope, System Perspective (discursivo longo) | seções de requisitos dispersas ou ausentes |

A taxonomia implementada em [taxonomy.py](pureprep/taxonomy.py) atribui a cada seção um papel: `meta` (descartado), `context`/`scenario` (entrada), `fr`/`nfr` + subtipo (gabarito). Regras relevantes: herança do ancestral mais próximo; RNF específico prevalece sobre contêiner RF; "Introduction" dentro de capítulo RF herda RF (caso THEMAS); tudo sob "Product Perspective" é descritivo. A auditoria seção a seção fica em `output/audit/section_roles/`.

---

## 2. Viabilidade como entrada de teste

### 2.1 Seções que simulam a "entrada bruta"
- **Mais adequadas:** *Project Scope*, *Product Perspective*, *Product Features/Functions*, *User Classes and Characteristics*, *Operating Environment*, *Assumptions and Dependencies* e, sobretudo, ***Stimulus/Response Sequences*** e ***Description and Priority*** do template Wiegers. Estas descrevem uso em linguagem narrativa, próxima do que um stakeholder diria.
- **Linguagem mais informal:** keepass, get-real, video-search, peering (projetos acadêmicos) e peppol/microcare (relatórios de visão, longos e discursivos).
- **Pouco útil como entrada:** cctns, ertms, dii, blitdraft, qheadache e tcs, com menos de 260 palavras discursivas (cctns: 114) ou contexto sem relação com os requisitos.

### 2.2 Seções formais como *Ground Truth*
Regras de extração ([extract.py](pureprep/extract.py)):
1. `<req id>` explícito → requisito **primário**, com o ID original preservado (`source.original_req_id`) e o modificador M/O.
2. Em seções RF/RNF: toda frase com modal → primário. Frase-guia terminada em ":" absorve até 8 itens de lista. Padrão IEEE 830 *Input/Processing/Output* sem modais → um requisito sintetizado (qheadache).
3. Em seções discursivas: frases com modal forte (*shall/must*) → **secundário**. São requisitos legítimos presentes na entrada; o avaliador não os conta como falso positivo, mas também não os exige na revocação.
4. Premissas marcadas com `<req>` (gamma-j AS-x) vão para a entrada, não para o gabarito (IEEE 830 §2.5).
5. Classe: seção RNF → RNF com subtipo (16 subtipos, mapeados para as 11 classes PROMISE quando possível [R7]). Seção RF → RF. Seções sem título reconhecível → pistas lexicais (`keyword_hint`) ou RF por padrão.

Cada item carrega `label_source` e `confidence`: 85,5 % dos rótulos vêm da seção, 11,6 % são *default* (sobretudo EIRENE, com capítulos sem título padronizado).

**Completude, consistência e rastreabilidade:**
- *Rastreabilidade para a fonte (SRS):* `source.section_id`, `section_path`, `xml_element`, `original_req_id`.
- *Rastreabilidade para a entrada:* `trace.input_segments` (IDs de trechos com offsets de caractere em `input.segments`), `support_score` (fração dos tokens de conteúdo do requisito cobertos por até 3 segmentos consecutivos) e `reachable` (≥ 0,6). É isto que viabiliza medir o *Trace to Source* do REQINONE [R2] de forma automática.
- *Completude:* `recall_reachable` mede quanto do que **estava na entrada** foi extraído.
- *Consistência/alucinação:* `unsupported_rate` mede a fração das predições sem suporte na entrada, independentemente do gabarito.

### 2.3 Validação do gabarito contra anotação humana
O ReqFromSRS [R2] (200 requisitos rotulados à mão a partir de 22 SRS do PURE) não informa o documento de origem. Localizamos cada item por cobertura lexical:

| Métrica | Valor |
|---|---|
| itens do ReqFromSRS localizados nos 18 XMLs | 56 / 200 (gamma-j 28, cctns 18, video-search 8, keepass 1, eirene-fun 1) |
| desses, presentes no nosso gabarito | **50 (89,3 %)** |
| concordância RF/RNF | **96 %** (48/50) |
| concordância de subtipo RNF (PROMISE) | **95 %** (38/40) |
| rótulos por seção / por *default* | 97,6 % / 0 % de concordância (1 item) |

Os 6 ausentes são parágrafos descritivos de módulos do CCTNS **sem modal**, que os anotadores humanos consideraram RF. É uma limitação conhecida da heurística de modais. A validação também revelou um bug (seção "Quality Attribute Requirements" rotulada RF), já corrigido: a concordância subiu de 78 % para 96 %.

---

## 3. Pipeline de preparação

```
PURE XML ─parse─▶ seções+blocos ─taxonomy─▶ papéis ─extract─▶ gabarito (primário/secundário)
                                                  └──────────▶ unidades de contexto
     ┌──────────── synth ────────────┐
     │ context  : texto real das seções discursivas            (cobertura parcial, medida)
     │ notes    : requisitos "desformalizados" em bullets       (cobertura total)
     │ dialogue : reunião Analista×Client×EndUser×TechLead      (cobertura total, ruído aditivo)
     └──────────────┬────────────────┘
                    ▼
   output/pairs/<modo>/<doc>/input_raw.txt + ground_truth_requirements.json
                    ▼
   evaluate: P/R/F1 extração · RF/RNF · subtipo · Trace-to-Source · unsupported_rate
```

- **Desformalização** (`notes`, `dialogue`): troca somente palavras funcionais ("The system shall X" → "we need the system to X"). Os tokens de conteúdo são preservados (teste automático exige ≥ 90 % de cobertura).
- **Ruído de diálogo:** hesitações, muletas, gagueira e marcas [laughter]/[crosstalk], com **os mesmos léxicos do sanitizador** do projeto *Sanitização de Texto*. O ruído é só aditivo (testado), o que permite medir o encadeamento *sanitizador → extração*. Há também eco de confirmação do analista (testa deduplicação) e conversa fora do tópico (testa filtragem).
- **Determinismo:** semente fixa por documento e modo (testado). **29 testes** automatizados passando.
- **Casamento predição↔gabarito:** F1 lexical de tokens de conteúdo ≥ 0,5, pareamento 1-1 guloso. Oracle → F1 = 1,000 nos três modos (sanidade do avaliador).

---

## 4. Diagnóstico quantitativo

### 4.1 Por documento (18 XMLs)

| Documento | RF | RNF | Tags `<req>` | Palavras contexto | Cobertura contexto | Tier *context* | Tier sintético |
|---|---:|---:|---:|---:|---:|:-:|:-:|
| 2008-keepass | 49 | 5 | 31 | 2.842 | **0,56** | **A** | A |
| 2008-peering | 24 | 3 | 20 | 2.948 | **0,52** | **A** | B |
| 2009-video-search | 12 | 18 | 0 | 1.005 | **0,50** | **A** | A |
| 2009-peppol-approved | 140 | 293 | 0 | 15.502 | 0,33 | **A** | A |
| 1998-themas | 84 | 0 | 0 | 1.141 | 0,29 | B | B |
| 1995-gemini | 135 | 161 | 0 | 3.896 | 0,14 | B | A |
| 0000-gamma-j | 24 | 43 | 46 | 901 | 0,13 | B | A |
| 2005-phin | 134 | 2 | 0 | 251 | 0,13 | B | B |
| 2007-get-real-0-2 | 4 | 6 | 0 | 961 | 0,10 | B | B |
| 1999-tcs | 254 | 241 | 0 | 1.556 | 0,08 | C | A |
| 2006-eirene-sys-15 | 253 | 91 | 0 | 2.408 | 0,05 | C | B |
| 2007-eirene-fun-7-2 | 430 | 107 | 537 | 729 | 0,02 | C | A |
| 0000-cctns | 27 | 90 | 114 | 114 | 0,00 | C | A |
| 2007-ertms | 162 | 35 | 197 | 134 | 0,00 | C | A |
| 2010-blitdraft | 23 | 34 | 0 | 251 | 0,00 | C | A |
| 2003-qheadache | 19 | 4 | 0 | 174 | 0,00 | C | B |
| 1999-dii | 14 | 5 | 0 | 57 | 0,00 | C | B |
| 2005-microcare | 0 | 0 | 0 | 5.642 | — | C | C |
| **Total** | **1.788** | **1.138** | **945** | **40.512** | **0,12** | 4A·5B·9C | 10A·7B·1C |

Critérios: *context* A = ≥ 20 primários, ≥ 3 RF e ≥ 3 RNF, ≥ 300 palavras de contexto e cobertura ≥ 0,25; B = ≥ 10 primários, ≥ 150 palavras e cobertura ≥ 0,10. Sintético A = ≥ 20 primários, ≥ 5 RF, ≥ 5 RNF e ≥ 70 % dos rótulos vindos da seção.
Distribuição de subtipos RNF: OT 210, US 158, L 133, IF 130, SE 113, EN 113, PE 64, DC 64, MN 38, FT 37, SA 30, LF 14, RL 13, PO 10, A 7, O 4.

### 4.2 Dificuldade por modo (baselines sem LLM, micro-média)

| Modo | Entrada (palavras) | Requisitos | Baseline ingênuo P | R (alcançável) | F1 | Macro-F1 RF/RNF | Oracle `unsupported` |
|---|---:|---:|---:|---:|---:|---:|---:|
| context | 40.512 | 3.125 (359 alcançáveis) | 0,36 | 0,08 | **0,14** | 0,88* | **0,70** |
| notes | 84.769 | 2.926 | 0,92 | 0,87 | **0,89** | 0,57 | 0,00 |
| dialogue | 35.398 | 820 (≤ 60/doc) | 0,67 | 0,78 | **0,72** | 0,57 | 0,00 |

\* calculado sobre poucos pares casados (majoritariamente secundários).
Leitura: **`context` é o teste real de descoberta e sumarização** (difícil, com cobertura parcial). **`notes` é lexicalmente fácil** e testa sobretudo classificação e reescrita INCOSE/IEEE. **`dialogue` testa robustez a formato e ruído.** O `unsupported` de 0,70 do oracle no modo `context` quantifica o quanto um gabarito "completo" seria injusto: 70 % dele não está na entrada.

### 4.3 Onde estão os melhores casos de teste
- **Suíte 1, núcleo ouro (com rótulo humano parcial):** gamma-j, cctns, video-search, keepass. Concentram 55 dos 56 itens do ReqFromSRS e permitem comparar diretamente com os resultados do REQINONE.
- **Suíte 2, entrada real (modo `context`):** keepass, peering, video-search (curtos, cobertura ≥ 0,5) e peppol (15,5 mil palavras: estresse de contexto longo e sumarização). Complementares B: themas, gemini, gamma-j.
- **Suíte 3, escala e rastreabilidade por ID:** ertms (197 `<req>` com M/O), eirene-fun-7-2 (537 `<req>`), tcs (495 requisitos, MIL-STD).
- **Excluir ou usar só como controle:** microcare (sem gabarito), dii e get-real (≤ 19 requisitos).
- **Expansão:** triagem dos 79 originais (`output/originals_scan.csv`) indica **25 documentos Tier A e 16 Tier B sem XML** (ex.: pontis, clarus low/high, rlcs, grid bgc, evla back/corr, inventory 2.0, home 1.3, viper, virtual ed). Convertê-los para o schema XML mais que dobraria o benchmark.

### 4.4 Ameaças à validade
1. **Contaminação de dados:** o PURE é público desde 2017 e muito provavelmente está no pré-treino dos LLMs (risco apontado pela apresentação da disciplina e pelo survey [R4]). Mitigações: os modos `notes`/`dialogue` mudam a superfície do texto; medir memorização (dado o início de um requisito, o modelo completa o restante literalmente?); manter um conjunto pequeno inédito e privado como teste final.
2. **Gabarito heurístico:** os 11,6 % de rótulos *default* concentram-se em EIRENE; a revisão humana deve priorizar `label_source = default` e `confidence < 0,6`.
3. **Casamento lexical:** subestima acertos parafraseados no modo `context`. Recomenda-se complementar com similaridade semântica (ex.: embeddings de sentença ou BERTScore [R16]) e adjudicação humana de uma amostra.
4. **Requisitos descritivos sem modal** (6 dos 56 itens humanos) ficam de fora do gabarito.

---

## 5. Lacuna de diálogo: estratégia recomendada

**Diagnóstico:** o PURE não contém transcrições. O único corpus conversacional disponível localmente é o AMI [R12], e ele não tem gabarito de requisitos: suas anotações são decisões e ações de reuniões de design de um controle remoto. Comparando o AMI com os diálogos gerados:

| | AMI (98 reuniões) | Diálogo sintético PURE |
|---|---:|---:|
| hesitações/muletas por 100 palavras | 4,84 | 5,88 |
| mediana de palavras por turno | 3 | 16 |
| turnos de *backchannel* (≤ 2 palavras) | 45 % | 17 % |

A densidade de ruído está calibrada. A **estrutura de turnos não**: os turnos sintéticos são longos e monológicos. Recomenda-se `--noise 0.065`, fatiar respostas em vários turnos curtos e elevar a taxa de *backchannel* e interrupções.

### 5.1 Protocolo de síntese em três níveis
| Nível | Como | Garantia semântica | Status |
|---|---|---|---|
| **N0 — template** | regras determinísticas + ruído aditivo (este pipeline) | por construção (nenhuma palavra de conteúdo removida) | implementado |
| **N1 — paráfrase por LLM** | LLM reescreve blocos de 3–8 requisitos como diálogo entre papéis (persona do stakeholder a partir de *User Classes*), marcando internamente os IDs de requisito em cada turno | verificação dupla: (i) cada requisito do gabarito é **implicado** pelos turnos marcados (NLI ou LLM-juiz); (ii) verificação reversa: nenhum requisito novo é introduzido; (iii) sobreposição lexical com o gabarito abaixo de um teto (ex.: ROUGE-1 < 0,5), para forçar paráfrase real; (iv) revisão humana de 10 % | **implementado e gerado** (variantes `llm-*`, seção 5.4); verificação por regras no lugar do NLI/LLM-juiz; revisão humana pendente |
| **N2 — fenômenos realistas** | mudança de ideia ("aliás, 5 s em vez de 2 s"; o gabarito guarda o estado final), requisitos implícitos, contradições, interrupções; ruído de ASR via TTS → Whisper | gabarito atualizado pelo roteiro do fenômeno; mede consistência | **implementado por regras** (modo `meetings`, seção 5.3); ruído de ASR pendente |

Para N1, usar um LLM de família diferente da do sistema avaliado, para evitar viés de autopreferência. Essa abordagem é análoga à simulação de entrevistas do Elicitron [R3] e à entrada conversacional prevista no REQINONE [R2].

### 5.2 Complementar com corpora conversacionais?
**Sim, com papéis bem definidos:**
- **AMI Meeting Corpus [R12]** (já local): (a) calibrar o gerador (estatísticas acima); (b) testar a robustez do sanitizador e do agente de sumarização com fala real; (c) criar um pequeno conjunto **AMI-RE**, rotulando como RF/RNF as decisões já anotadas em `data/ami/text/*.gold.json`. Exemplos: "production costs cannot exceed 12.50 Euro" → RNF/restrição; "The remote will be sold on an international scale" → contexto. As reuniões de cenário (ES/IS/TS) são projetos de produto, portanto há requisitos reais em diálogo real.
- **ICSI Meeting Corpus [R13]** e **QMSum [R14]:** úteis para robustez e sumarização orientada a consulta, sem valor como gabarito de requisitos.
- **Entrevistas de elicitação de Ferrari et al. [R9]:** 70 gravações de entrevistas com stakeholders simulados, usadas pelo LLMREI [R10]. São o recurso conversacional mais próximo do domínio, mas a disponibilidade pública não foi confirmada (contatar os autores). O pacote aberto no Zenodo [R11] traz o briefing do produto ("Happy Camping") e as *user stories* produzidas por 30 analistas, **sem transcrições**. Serve como gabarito para uma entrevista simulada no estilo Elicitron.
- Trabalho relacionado direto: **RECOVER** [R15] (geração de requisitos a partir de conversas de stakeholders). Não identificamos publicação de dataset aberto.

**Recomendação final:** manter o PURE como fonte do **conteúdo semântico e do gabarito**. Gerar diálogo nos níveis N0 a N2 e usar o AMI para **calibrar o formato e testar robustez**. Um pequeno AMI-RE rotulado à mão fornece validação externa com diálogo 100 % real.

### 5.3 Implementação do N2: modo `meetings` (13/10/2026)

**Motivação.** As transcrições do modo `dialogue` (N0) eram formais demais. Cada requisito era dito uma única vez, com clareza, na ordem do documento, e ninguém discordava. Esse cenário não exercita as dificuldades reais da elicitação: informação espalhada por várias reuniões, conflitos entre stakeholders, falas vagas e lacunas.

**Arquitetura.** O gerador foi dividido em duas fases (`pureprep/dialogue/`):

```
requisitos ─► plano (determinístico) ─► realizador ─► gabarito schema 2.0
              reuniões, participantes,   superfície     construído a partir
              ordem, fenômenos e         do texto       do log do plano
              desfechos
```

O plano depende só da semente e do perfil. O realizador `rules` (variante A) usa modelos de frase e léxico coloquial. O realizador `llm` (variante B, futuro N1) vai consumir **o mesmo plano**, de modo que A e B tenham gabaritos idênticos e a comparação isole o efeito da linguagem. A rastreabilidade passa a vir do log do plano, e não da similaridade lexical, porque a ambiguidade e a incompletude removem de propósito palavras do requisito. O modo `dialogue` ficou congelado, com teste de regressão byte a byte contra o dataset v1 publicado.

**Fenômenos** (no máximo um por requisito):

| fenômeno | realização | status no gabarito |
|---|---|---|
| reuniões separadas | 1–4 reuniões com recapitulação; participantes variam | segmentos `M<n>:T<k>` |
| bagunça | ordem fora do documento, tópico retomado, interrupção no meio da fala, falso começo, *crosstalk*, conversa fora do tópico | `stats.messiness` |
| conflito de valor/ator | variante com número ou papel trocado, contestada; decidida na hora, adiada ou decidida em reunião posterior | `conflict_resolved` (a proposta perdedora vira **distrator**) ou `conflict_open` |
| conflito de escopo | "do we really need that?" | `conflict_resolved`, `rejected` ou `conflict_open` |
| ambiguidade | quantidade vaga, ator vago, referência vaga, obrigatoriedade hesitante | `ambiguous` |
| inconsistência | reafirmado depois com valor, ator ou polaridade divergente, sem que ninguém perceba | `inconsistent` |
| incompletude | valor faltante, condição omitida, fala cortada; às vezes completada em reunião posterior | `incomplete` ou `clear` |
| omissão | requisito nunca discutido | `omitted` |

**Variantes geradas** (18 documentos, mesma amostra de 820 requisitos do v1, seed 42):

| variante | reuniões/doc | palavras | esperados | ambíguos | inconsistentes | incompletos | conflitos (resolvidos/abertos/rejeitados) | omitidos | *issues* | distratores |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| `rules-clean` | 1,0 | 37.628 | 820 | – | – | – | – | – | – | – |
| `rules-realistic` | 2,4 | 46.304 | 781 | 64 | 21 | 42 | 22 / 18 / 15 | 24 | 145 | 6 |
| `rules-hard` | 3,3 | 48.924 | 761 | 110 | 52 | 72 | 46 / 43 / 16 | 43 | 277 | 3 |

**Dificuldade (baseline ingênuo, micro-média sobre os requisitos esperados).** O oracle obtém F1 = 1,0 em extração e em *issues* em todas as variantes.

| variante | P | R | F1 | R ambíguos | R incompletos | R conflito aberto | distratores extraídos | rejeitados extraídos |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `dialogue` v1 | 0,67 | 0,78 | 0,72 | – | – | – | – | – |
| `rules-clean` | 0,71 | 0,84 | 0,77 | – | – | – | 0 | 0 |
| `rules-realistic` | 0,54 | 0,72 | 0,62 | 0,25 | 0,43 | 0,94 | 6 | 14 |
| `rules-hard` | 0,50 | 0,68 | 0,58 | 0,35 | 0,40 | 0,91 | 3 | 15 |

Leitura:
- **A queda de F1 é monotônica** com o perfil, e os fenômenos derrubam a revocação exatamente onde se esperava: requisitos ambíguos e incompletos.
- **O baseline extrai propostas rejeitadas e requisitos retirados do escopo.** É o erro que as métricas novas (`false_positives`) tornam visível.
- **`rules-clean` fica um pouco mais fácil que o v1.** A superfície casual quebra menos frases no meio do requisito.
- **Os turnos curtos também pesam.** Depois da calibração de turnos (abaixo), o F1 de `realistic` caiu de 0,67 para 0,62 e o de `hard` de 0,62 para 0,58: um requisito fatiado em vários turnos não é recuperado por quem extrai frase a frase.
- **O detalhe que ninguém disse fica registrado.** A métrica `detail_hallucination_rate` mede se a predição traz o valor removido. O próprio oracle marca ≈ 0,55–0,63, porque copia o texto canônico do SRS.

**Calibração com o AMI** (mesma métrica da tabela da seção 5). A contagem de hesitações abaixo usa o léxico de `resources/noise_en.json` sobre todos os turnos, que é mais amplo que a contagem original: o v1 dá 8,05 por esse critério, contra 5,88 na tabela anterior. Compare só as variantes entre si.

| | `dialogue` v1 | `rules-clean` | `realistic` 1ª versão | `realistic` calibrado | `hard` 1ª versão | `hard` calibrado | AMI |
|---|---:|---:|---:|---:|---:|---:|---:|
| hesitações/muletas por 100 palavras (critério amplo) | 8,05 | 8,01 | 9,76 | **7,25** | 13,17 | **8,06** | — |
| mediana de palavras por turno | 16 | 14 | 14 | **9** | 15 | **10** | 3 |
| 3º quartil de palavras por turno | 31 | 29 | — | **16** | — | **18** | — |
| turnos de *backchannel* (≤ 2 palavras) | 17 % | 15 % | 10 % | **29 %** | 7 % | **22 %** | 45 % |

A primeira versão do modo `meetings` **não corrigia** a lacuna de estrutura de turnos apontada acima, e chegava a piorá-la: objeções, adiamentos e retomadas acrescentavam turnos de tamanho médio, o *backchannel* aparecia só depois de afirmações claras e as hesitações do `hard` passavam bastante das do v1.

**Calibração aplicada** (parâmetros em `pureprep/dialogue/profiles.py`, decididos no plano para que a variante B herde a mesma estrutura):
- **Fatiamento de falas longas** (`p_chunk` = 0,9; `chunk_target` = 7 palavras): a fala vira vários turnos curtos do mesmo falante, cortados só em fim de frase, vírgula ou início de oração (*and*, *which*, *when*, *if*…). Sem fronteira natural, a fala fica inteira: cortar no meio da oração soava artificial.
- ***Backchannel*** entre os pedaços (`p_mid_backchannel` = 0,9) e depois da afirmação (`p_backchannel` = 0,75). Em geral vem do analista, às vezes de outro stakeholder.
- **Reações curtas** de outro stakeholder ("Yeah, agreed.", "Same for us."; `p_react` = 0,35).
- **Ruído lexical reduzido**: `noise` 0,07 em `realistic` e 0,075 em `hard`, o que devolve as hesitações ao nível do v1.
- **`rules-clean` mantém a estrutura de turnos do v1**, de propósito: continua sendo a ablação que isola só a superfície do texto.

Uma varredura de parâmetros mostrou retorno decrescente abaixo de ~7 palavras por pedaço (mediana 8, *backchannel* 33%). Chegar aos 45% do AMI exigiria *backchannel* também depois de perguntas e objeções, o que deixava o diálogo repetitivo. A distância que resta para o AMI (mediana 3) vem principalmente de as falas carregarem o texto do SRS. É uma limitação da variante A que a variante B pode atacar.

**Limitações.**
- **Distratores são raros** (3–6 por variante): só conflitos de valor ou de ator geram uma proposta perdedora distinguível lexicalmente, e apenas 31/820 requisitos têm grandeza numérica e 138/820 têm ator explícito.
- **A inversão de polaridade só entra como inconsistência.** "not" é stopword no casamento lexical, então ela não pode virar distrator.
- **As falas preservam as palavras de conteúdo do SRS**, e requisitos longos continuam soando como documento. É o efeito que a variante B (N1) deve medir.
- **O casamento continua lexical.** As ressalvas da seção 4.4 valem aqui também.

**Onde estão os dados.** O repositório `Entradas` foi reorganizado em `variantes/{v1-original, rules-clean, rules-realistic, rules-hard}`, com `manifest.json` (commit do gerador, semente e parâmetros) por variante, PDFs em `originais/` e índice com uma linha por (variante, documento). A exportação é feita por `scripts/export_entradas.py`.


### 5.4 Variante B: realizador por LLM (13/10/2026)

O nível N1 foi implementado como um segundo realizador do modo `meetings` (`pureprep/dialogue/realize_llm.py`), que consome **o mesmo plano** da variante A. Com a mesma semente e o mesmo perfil, requisitos, status, *issues* e distratores são idênticos entre A e B (teste `test_same_plan_and_gold_as_variant_a`); só a superfície das falas muda. Assim a comparação A × B mede o efeito da paráfrase, isolado da estrutura e dos fenômenos.

Desenho:
- **Unidade de geração:** janelas de ~20 turnos por reunião, cada uma uma requisição independente (paralelizável), com os 3 turnos anteriores do plano como contexto. O prompt leva só o conteúdo do plano, então o detalhe removido por ambiguidade ou incompletude nunca chega ao LLM.
- **Verificação por regras** de cada fala, no lugar do NLI/LLM-juiz previsto na tabela 5.1. São verificados: números preservados, nenhum número inventado, detalhe removido não reaparece, ≥ 50% dos tokens de conteúdo preservados, valor da variante preservado em distratores e reafirmações, e tamanho compatível com o ato. Fala reprovada volta para o texto da variante A, e os motivos ficam no gabarito (`generator.realizer_stats`). A verificação é mais fraca que um NLI: confere preservação lexical e numérica, não a equivalência semântica completa. Uma revisão humana por amostragem continua recomendada.
- **Ruído lexical idêntico ao da A**, aplicado depois do LLM com a mesma semente. Um B sem nenhuma fala aceita reproduz a A byte a byte (teste `test_dry_run_falls_back_to_rules_everywhere`).
- **Reprodutibilidade:** as respostas ficam em cache versionado (hash de versão do prompt, provedor, modelo e prompt), e `--llm-offline` regenera a variante sem chamar o LLM.
- **Provedor configurável:** Anthropic (padrão `claude-opus-5-5`, esforço `low`) ou qualquer API compatível com OpenAI. Como a família do LLM do sistema avaliado ainda não está definida, a escolha fica para a geração; recomenda-se uma família diferente da do sistema.

**Escala** (dry-run, 18 documentos, perfis `clean`, `realistic` e `hard`): 470 requisições, ~0,8 M tokens de entrada e ~0,35 M de saída, sem contar o raciocínio do modelo.

**Geração (13/10/2026).** Com `claude-opus-5-5`, esforço `low` e prompt `b2`: 470 requisições em 13,5 min, sem falhas. O cache (4,8 MB) está versionado em `llm_cache/`, e a reprodução offline sai idêntica byte a byte.

O prompt `b1` foi descartado depois do teste com o KeePass. Nos turnos de discussão (objeção e defesa de escopo), o LLM inventava justificativas sobre o domínio ("people offline would get stuck"), que um extrator poderia ler como requisito. No `b2`, as razões ficam genéricas (importância, esforço, prioridade).

| perfil | falas aceitas | fallbacks (principais motivos) | cobertura de tokens A → B | F1 naive A → B | mediana palavras/turno A → B | *backchannel* A → B |
|---|---:|---|---:|---:|---:|---:|
| `clean` | 98,3 % | conteúdo 17, número perdido 10 | 0,98 → 0,80 | 0,77 → **0,61** | 14 → 16 | 15 % → 14 % |
| `realistic` | 98,5 % | conteúdo 36, número inventado 7, detalhe vazado 2 | 0,98 → 0,84 | 0,62 → **0,46** | 9 → 11 | 29 % → 24 % |
| `hard` | 99,0 % | conteúdo 16, número perdido 8, número inventado 5 | 0,98 → 0,84 | 0,58 → **0,44** | 10 → 13 | 22 % → 18 % |

Leitura:
- **O efeito da paráfrase é grande e consistente.** Com plano, fenômenos e gabarito idênticos, o F1 do baseline lexical cai 14–16 pontos da A para a B. Parte do que as variantes `rules-*` medem é casamento de superfície com o texto do SRS, e a B remove essa vantagem.
- **A verificação barrou o que devia.** Houve números inventados (12), detalhes removidos que reapareceram (3) e uma mistura de valores num distrator; essas falas voltaram para a A.
- **A estrutura de turnos piora um pouco.** As concordâncias do LLM são mais longas ("Yes, that's right."), o que desfaz parte da calibração contra o AMI. Uma versão futura do prompt pode restringir os atos curtos a 1–2 palavras.
- **A verificação continua lexical.** Uma revisão humana por amostragem (ex.: 50 falas por perfil, priorizando turnos com fenômeno) deve preceder conclusões fortes sobre a equivalência semântica.
---

## 6. Próximos passos sugeridos
1. Rodar o sistema multiagente nas Suítes 1 e 2 e avaliar com `python -m pureprep.evaluate`.
2. Revisão humana de uma amostra estratificada do gabarito (prioridade: `label_source = default`), com medida de concordância (kappa de Cohen).
3. Revisar por amostragem as falas da variante B (seção 5.4) e implementar o casamento semântico no avaliador, que deve reduzir a distância entre A e B atribuível só ao casamento lexical.
3a. Avaliar o sistema multiagente nas variantes `rules-*`, incluindo a detecção de *issues*. A estrutura de turnos já foi calibrada contra o AMI (seção 5.3).
4. Converter 5–10 documentos Tier A sem XML (começando por pontis, clarus, rlcs e inventory 2.0).
5. Montar o AMI-RE (~10 reuniões ES).

---

## Referências

### A. Artigos analisados (workspace)
- **[R1]** JIN, D.; JIN, Z.; CHEN, X.; WANG, C. *MARE: Multi-Agents Collaboration Framework for Requirements Engineering*. arXiv:2405.03256, 2024. — usa o PURE (GoalModelDataset, via [R17]); material em github.com/publicsubmission/MARE-support-material (indisponível em 23/09/2026).
- **[R2]** ZHU, T.; CORDEIRO, L. C.; SUN, Y. *ReqInOne: A Large Language Model-Based Agent for Software Requirements Specification Generation*. In: IEEE 33rd International Requirements Engineering Conference (RE), 2025. arXiv:2508.09648. Código e dados (ReqFromSRS: 100 RF + 100 RNF de 22 SRS do PURE): https://github.com/TaohongZ/ReqInOne
- **[R3]** ATAEI, M.; CHEONG, H.; GRANDI, D.; WANG, Y.; MORRIS, N.; TESSIER, A. *Elicitron: An LLM Agent-Based Simulation Framework for Design Requirements Elicitation*. In: ASME IDETC-CIE 2024 (50th Design Automation Conference). arXiv:2404.16045.
- **[R4]** ZHANG, Q.; FANG, C.; XIE, Y.; ZHANG, Y.; YU, S.; SUN, W.; YANG, Y.; CHEN, Z. *A survey on large language models for software engineering*. Science China Information Sciences, v. 69, n. 4, 141102, 2026. DOI: 10.1007/s11432-025-4670-0.
- **[R5]** FONTOURA, L. M. *Roteiro de leitura — Uso de IA no apoio às atividades de desenvolvimento de software*. ELC 922 Melhoria de Processos de Software, UFSM, 2026 (material da disciplina), e a apresentação "O Impacto dos LLMs na Engenharia de Software" (fundamentação teórica).

### B. Datasets e repositórios
- **[R6]** FERRARI, A.; SPAGNOLO, G. O.; GNESI, S. *PURE: A Dataset of Public Requirements Documents*. In: IEEE 25th International Requirements Engineering Conference (RE), 2017, p. 502–505. Dados: Zenodo, DOI 10.5281/zenodo.1414117 (`requirements-xml.zip`, `requirements.zip`).
- **[R7]** CLELAND-HUANG, J.; MAZROUEE, S.; HUANG, L.; PORT, D. *PROMISE NFR Dataset*. Zenodo, record 268542, 2007 (conforme citado em [R2]).
- **[R9]** FERRARI, A.; SPOLETINI, P.; BANO, M.; ZOWGHI, D. *Learning requirements elicitation interviews with role-playing, self-assessment and peer-review*. In: IEEE 27th International Requirements Engineering Conference (RE), 2019, p. 28–39 (conforme citado em [R10]).
- **[R11]** FERRARI, A.; SPOLETINI, P.; DEBNATH, S. *Replication Package — How Do Requirements Evolve During Elicitation? An Empirical Study Combining Interviews and App Store Analysis*. Zenodo, DOI 10.5281/zenodo.6475039, 2022 (CC-BY-4.0).
- **[R12]** CARLETTA, J. et al. *The AMI Meeting Corpus: A Pre-announcement*. In: Machine Learning for Multimodal Interaction (MLMI 2005), LNCS 3869, Springer, 2006, p. 28–39. (Cópia local em `Sanitização de Texto/data/ami`.)
- **[R13]** JANIN, A. et al. *The ICSI Meeting Corpus*. In: IEEE ICASSP, 2003.
- **[R14]** ZHONG, M. et al. *QMSum: A New Benchmark for Query-based Multi-domain Meeting Summarization*. In: NAACL-HLT, 2021.

### C. Normas e guias
- **[R8]** IEEE. *IEEE Std 830-1998 — Recommended Practice for Software Requirements Specifications*, 1998; e ISO/IEC/IEEE 29148:2018 (substituta).
- **[R18]** INCOSE Requirements Working Group. *Guide to Writing Requirements* (GtWR), v4, 2023 (conforme citado em [R2]).

### D. Trabalhos relacionados
- **[R10]** KORN, A.; GORSCH, S.; VOGELSANG, A. *LLMREI: Automating Requirements Elicitation Interviews with LLMs*. arXiv:2507.02564, 2025.
- **[R15]** VORIA, G.; CASILLO, F.; GRAVINO, C.; CATOLINO, G.; PALOMBA, F. *RECOVER: Toward Requirements Generation from Stakeholders' Conversations*. arXiv:2411.19552, 2024/2025.
- **[R16]** ZHANG, T. et al. *BERTScore: Evaluating Text Generation with BERT*. ICLR, 2020.
- **[R17]** ZHOU, Q.; LI, T.; WANG, Y. *Assisting in requirements goal modeling: a hybrid approach based on machine learning and logical reasoning*. In: MODELS 2022, p. 199–209 (conforme citado em [R1]).
- **[R19]** HEY, T.; KEIM, J.; KOZIOLEK, A.; TICHY, W. F. *NoRBERT: Transfer Learning for Requirements Classification*. In: IEEE RE, 2020, p. 169–179.
