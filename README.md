# Dataset de Entradas: Transcrições de Reuniões e Gabarito de Requisitos

Este diretório contém o conjunto de dados processado para experimentos de **Engenharia de Requisitos** e **Melhoria de Processos de Software**. Ele fornece conversas de reuniões simuladas e seus respectivos gabaritos estruturados (*ground truth*), baseados no conceituado dataset público **PURE (*Public Requirements Engineering Dataset*)** ([Zenodo 10.5281/zenodo.1414117](https://doi.org/10.5281/zenodo.1414117)).

---

## 📌 1. Visão Geral e Propósito Científico

Em cenários reais de engenharia de software, requisitos raramente nascem como especificações formais limpas. Eles emergem em **reuniões de brainstorming, entrevistas e alinhamentos entre stakeholders**, repletos de linguagem informal, hesitações, termos coloquiais e confirmações mútuas.

Este repositório fornece **pares controlados de teste** (`Entradas/<projeto>/`):
1. **Entrada Informal (`transcricao_reuniao.txt`)**: A transcrição integral de uma reunião virtual realista de elicitação de requisitos, com múltiplos participantes discutindo o sistema.
2. **Gabarito Estruturado (`gabarito_requisitos.json`)**: O padrão-ouro contendo cada requisito formalmente extraído, classificado (Funcional vs Não-Funcional, com subtipos) e rastreado diretamente aos turnos da conversa.

### Principais Diferenciais:
- **Sem uso de IA generativa no pré-processamento**: As falas foram geradas através de transformações determinísticas aditivas dos requisitos reais do PURE. Isso elimina o risco de contaminação ou viés de LLMs na geração do benchmark.
- **Preservação Semântica Total**: Todas as palavras de conteúdo e regras originais do requisito são preservadas; apenas a sintaxe modal ("*the system shall*") é convertida em fala informal ("*we'd need to be able to*").
- **Rastreabilidade Fina (*Traceability*)**: Cada requisito formal aponta exatamente para quais turnos de fala (`T1`, `T2`, etc.) o originaram.

---

## 📂 2. Estrutura de Diretórios

A pasta `Entradas` está organizada da seguinte forma:

```text
Entradas/
├── README.md                      # Este guia completo de documentação
├── indice_documentos.csv          # Tabela com métricas rápidas de todos os 18 projetos
│
├── 0000-cctns/                    # Projeto: Crime & Criminal Tracking Network
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 1995-gemini/                    # Projeto: Gemini 8m Telescopes
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 1998-themas/                    # Projeto: THEMAS - Energy Management System
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 1999-dii/                    # Projeto: Defense Information Infrastructure XML Services
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 1999-tcs/                    # Projeto: Tactical Control System (TCS)
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2003-qheadache/                    # Projeto: QHeadache Diagnostic System
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2005-microcare/                    # Projeto: Voucher Management System (MicroCare)
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2005-phin/                    # Projeto: Public Health Info Network Outbreak Mgmt
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2006-eirene-sys-15/                    # Projeto: EIRENE Railway System Requirements
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2007-eirene-fun-7-2/                    # Projeto: EIRENE Railway Functional Requirements
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2007-ertms/                    # Projeto: ERTMS/ETCS European Rail Traffic System
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2007-get-real-0-2/                    # Projeto: Get Real 0.2
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2008-keepass/                    # Projeto: KeePass Password Safe
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2008-peering/                    # Projeto: Internetworking of CDNs through Peering
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2009-peppol-approved/                    # Projeto: Pan-European Public Procurement (PEPPOL)
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
├── 2009-video-search/                    # Projeto: Video Search Engine
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
    │
└── 2010-blitdraft/                    # Projeto: BlitDraft Specification
    │   ├── transcricao_reuniao.txt    # Conversa da reunião (texto livre)
    │   ├── gabarito_requisitos.json   # Gabarito com requisitos e rastreabilidade
    │   └── requisitos_originais.pdf   # Cópia do documento original de requisitos
```

---

## 🗣️ 3. Anatomia da Conversa (`transcricao_reuniao.txt`)

Cada transcrição simula uma sessão de trabalho de aproximadamente **45 minutos a 1 hora** entre stakeholders e analistas.

### Formato dos Turnos
As falas seguem o padrão padronizado:
```text
Falante: Texto da fala
```

### Personas Envolvidas
A reunião conta com até 4 participantes com papéis definidos:
- **`Analyst`**: Moderador da reunião. Introduz tópicos, faz perguntas estruturadas ("*So, let's talk about search database. What do you need there?*"), checa o entendimento e resume pontos.
- **`Client`**: Stakeholder de negócios. Descreve objetivos do sistema, regras de negócio e necessidades funcionais gerais.
- **`TechLead`**: Líder técnico e arquiteto. Foca principalmente em requisitos não-funcionais (segurança, disponibilidade, desempenho, restrições arquiteturais).
- **`EndUser`**: Usuário final. Destaca fluxos práticos de uso, interface, acessibilidade e preferências de usabilidade.

### Padrões Naturais de Fala Presentes
Para reproduzir a dinâmica de uma reunião humana real, foram incorporados fenômenos de fala espontânea:
1. **Hesitações e Marcadores Conversacionais**: Palavras como `"uh"`, `"erm"`, `"you know"`, `"i mean"`, `"sort of"`, `"well"`.
2. **Gagueira e Repetição de Palavras**: Repetições acidentais de artigos e conectivos curtos (ex: `"the the"`, `"of of"`).
3. **Ruídos de Fala e Ambiente**: Marcadores de evento sonoro, como `[crosstalk]` (falas sobrepostas) e `[laughter]`.
4. **Ecos de Confirmação**: O analista parafraseia o requisito para validar se entendeu corretamente:
   > **EndUser**: *Databases would have to have different names or else the previews one will be replace if selected.*  
   > **Analyst**: *Just to confirm, databases would have to have you know different names or else the previews one will be replace if selected?*  
   > **EndUser**: *Mm-hmm, yes.*
5. **Comentários Fora do Tópico (*Off-topic*)**: Pequenos imprevistos típicos de conferências online:
   > **TechLead**: *Sorry, I was on mute.*  
   > **Client**: *Sorry, can everyone hear me? My connection is a bit unstable today.*

---

## 📋 4. Anatomia do Gabarito (`gabarito_requisitos.json`)

O arquivo de gabarito contém o conjunto formal de requisitos que a reunião gerou, além dos metadados completos de rastreabilidade.

### Estrutura Geral do JSON

```json
{
  "schema_version": "1.0",
  "doc_id": "2008-keepass",
  "doc_title": "Software Requirements Specification for KeePass Password Safe",
  "mode": "dialogue",
  "generator": { ... },
  "input": {
    "file": "transcricao_reuniao.txt",
    "n_chars": 9260,
    "n_words": 1613,
    "segments": [ ... ]
  },
  "stats": { ... },
  "requirements": [ ... ]
}
```

### Detalhamento dos Campos:

#### 1. Mapeamento de Segmentos (`input.segments`)
Divide a transcrição em blocos contínuos de fala (`T1`, `T2`, etc.):
- `id`: Identificador do segmento de fala (ex: `"T6"`).
- `start` / `end`: Posição exata em caracteres dentro de `transcricao_reuniao.txt`.
- `speaker`: Quem pronunciou a frase.
- `gt_ids`: Lista de IDs de requisitos presentes nesta fala específica.

#### 2. Resumo de Métricas (`stats`)
- `n_requirements`: Total de requisitos no gabarito.
- `n_primary_fr`: Quantidade de Requisitos Funcionais.
- `n_primary_nfr`: Quantidade de Requisitos Não-Funcionais.
- `n_reachable`: Requisitos que de fato foram cobertos e discutidos na conversa.
- `reachable_ratio_primary`: Taxa de cobertura (geralmente 1.0 = 100%).

#### 3. Especificação de Cada Requisito (`requirements`)
Cada objeto dentro do array `"requirements"` possui:

| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `id` | `string` | Identificador único no dataset (ex: `"2008-keepass:R0006"`). |
| `text` | `string` | Texto formal e canônico do requisito (padrão-ouro). |
| `class` | `string` | Classe do requisito: `"FR"` (Funcional) ou `"NFR"` (Não-Funcional). |
| `subtype` | `string` | Código do subtipo para NFR (veja tabela de taxonomia abaixo). |
| `subtype_name`| `string` | Nome por extenso do subtipo (ex: `"Performance"`, `"Security"`). |
| `tier` | `string` | `"primary"` (normativo formal) ou `"secondary"` (modal de apoio). |
| `source` | `object` | Origem no documento XML original (seção, elemento, força do modal `shall`/`must`). |
| `trace` | `object` | Rastreabilidade direta com os segmentos de fala (`input_segments`, `support_score`). |

### Taxonomia de Subtipos Não-Funcionais (NFR)
Os requisitos não-funcionais seguem as normas internacionais de qualidade de software (ISO/IEC 25010 e IEEE 830):

| Código | Subtipo | Exemplo de Foco |
| :---: | :--- | :--- |
| **`PE`** | Performance / Efficiency | Tempo de resposta, throughput, latência. |
| **`SE`** | Security | Autenticação, permissões, criptografia, senhas. |
| **`US`** | Usability | Intuitividade, facilidade de aprendizado, documentação. |
| **`LF`** | Look & Feel | Interface gráfica, cores, fontes, layout. |
| **`A`** | Availability | Uptime, disponibilidade 24/7, tolerância a falhas. |
| **`SA`** | Safety | Prevenção de perda de dados e acidentes operacionais. |
| **`PO`** | Portability | Suporte a múltiplos navegadores, SOs ou dispositivos. |
| **`MN`** | Maintainability | Modularidade, facilidade de manutenção e código limpo. |
| **`SC`** | Scalability | Capacidade de expansão de carga e usuários. |
| **`L`** | Legal / Compliance | Leis, regulamentações, termos de licença (GPL, LGPD). |
| **`FT`** | Fault Tolerance | Recuperação de desastres, backups e contingência. |
| **`OT`** | Other NFR | Outros atributos de qualidade genéricos. |

---

## 🧪 5. Como Utilizar este Dataset como Benchmark no Mestrado

Este conjunto de dados permite desenhar experimentos reprodutíveis para avaliar LLMs, agentes autônomos ou técnicas tradicionais de PLN:

### Fluxo de Teste Recomendado:

```
[ transcricao_reuniao.txt ] 
            │
            ▼
┌───────────────────────────────┐
│     Sistema / LLM sob Teste   │  (Prompt com instruções de extração)
└───────────────────────────────┘
            │
            ▼
[ Predições: requisitos_extraidos.json ]
            │
            ▼
┌───────────────────────────────┐
│     Avaliador Automático      │  (pureprep.evaluate)
└───────────────────────────────┘
            ▲
            │
[ gabarito_requisitos.json ] (Ground Truth)
```

### Métricas Científicas que Você Pode Coletar:

1. **Extração de Requisitos (Extração Pura)**:
   - **Precisão (Precision)**: Dos requisitos que o seu modelo extraiu, quantos realmente existem no gabarito?
   - **Revocação (Recall)**: De todos os requisitos do gabarito, quantos o seu modelo foi capaz de recuperar?
   - **F1-Score**: Média harmônica entre Precisão e Revocação.

2. **Classificação Funcional vs Não-Funcional (FR / NFR)**:
   - Mede se o modelo classificou adequadamente o requisito como funcional ou de qualidade.
   - Matriz de confusão e Macro-F1 por classe.

3. **Precisão de Rastreabilidade (*Trace to Source*)**:
   - O modelo consegue citar o trecho da reunião que justifica o requisito?
   - Verifica se o trecho citado pelo modelo coincide com `trace.input_segments`.

4. **Taxa de Alucinação (*Unsupported Rate*)**:
   - Quantas sentenças geradas pelo modelo afirmam ser requisitos mas não têm qualquer respaldo na conversa da reunião?

---

## 📊 6. Tabela Índice dos 18 Projetos

A tabela abaixo resume todos os projetos disponíveis na pasta `Entradas`. Os dados completos também estão disponíveis em formato de planilha no arquivo `indice_documentos.csv`:

| ID | Nome do Projeto | Requisitos no Diálogo | Palavras na Reunião | Qualidade |
| :--- | :--- | :---: | :---: | :---: |
| **`0000-cctns`** | Crime & Criminal Tracking Network and Systems | 60 | 2.972 | Tier A |
| **`0000-gamma-j`** | Gamma-J Web Store (Connecting Retailers) | 60 | 1.633 | Tier A |
| **`1995-gemini`** | Gemini 8m Telescopes System | 60 | 3.302 | Tier A |
| **`1998-themas`** | THEMAS - Energy Management System | 60 | 2.226 | Tier B |
| **`1999-dii`** | Defense Information Infrastructure XML Services | 19 | 1.779 | Tier B |
| **`1999-tcs`** | Tactical Control System (TCS) | 60 | 2.758 | Tier A |
| **`2003-qheadache`** | QHeadache Diagnostic System | 23 | 1.516 | Tier B |
| **`2005-microcare`**| Voucher Management System (MicroCare) | 0 | 114 | Tier C |
| **`2005-phin`** | Public Health Info Network Outbreak Mgmt | 60 | 2.430 | Tier B |
| **`2006-eirene-sys`**| EIRENE Railway System Requirements | 60 | 2.775 | Tier B |
| **`2007-eirene-fun`**| EIRENE Railway Functional Requirements | 60 | 2.949 | Tier A |
| **`2007-ertms`** | ERTMS/ETCS European Rail Traffic System | 60 | 2.089 | Tier A |
| **`2007-get-real`** | Get Real 0.2 | 10 | 553 | Tier B |
| **`2008-keepass`** | KeePass Password Safe | 54 | 1.613 | Tier A |
| **`2008-peering`** | Internetworking of CDNs through Peering | 27 | 809 | Tier B |
| **`2009-peppol`** | Pan-European Public Procurement (PEPPOL) | 60 | 3.096 | Tier A |
| **`2009-video`** | Video Search Engine | 30 | 865 | Tier A |
| **`2010-blitdraft`**| BlitDraft Specification | 57 | 1.919 | Tier A |

> **Nota sobre os Tiers de Qualidade:**
> - **Tier A**: Documentos com alto volume de requisitos, excelente equilíbrio entre funcionais/não-funcionais e cobertura profunda na transcrição. Ideais para testes primários.
> - **Tier B**: Documentos médios ou altamente especializados (ex: foco exclusivo em RF ou RNF).
> - **Tier C**: Documentos com seções predominantemente discursivas/narrativas e poucos requisitos normativos explícitos.