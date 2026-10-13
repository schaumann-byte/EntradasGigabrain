# pure_ingestao — banco de testes do módulo de ingestão (PURE)

Transforma os SRS do dataset PURE em pares de teste para o módulo de
entrada do sistema multiagente de Engenharia de Requisitos:

- `input_raw.txt`: texto bruto simulando a entrada (contexto discursivo, notas de necessidades ou transcrição de reunião);
- `ground_truth_requirements.json`: requisitos RF/RNF de referência, com rastreabilidade até a seção do SRS de origem **e** até o trecho da entrada que os sustenta.

Somente biblioteca padrão do Python (≥ 3.10). Diagnóstico completo em
[RELATORIO_DIAGNOSTICO.md](RELATORIO_DIAGNOSTICO.md).

## Execução

```bash
bash scripts/run_all.sh          # baixa dados, gera pares, roda baselines, validações e testes
# ou passo a passo:
python scripts/download_data.py                   # PURE (Zenodo, com MD5) + ReqFromSRS
python -m pureprep.cli --out output               # gera os pares
python -m pureprep.evaluate --pairs output/pairs/context --pred <pasta_predições> --out relatorio.json
python -m pytest -q
```

Parâmetros de `pureprep.cli`: `--seed` (padrão 42), `--support-threshold` (0,6),
`--dialogue-cap` (60 requisitos por reunião), `--noise` (0,08).

## Saída

```
output/
  pairs/{context,notes,dialogue}/<doc_id>/input_raw.txt
  pairs/{context,notes,dialogue}/<doc_id>/ground_truth_requirements.json
  audit/section_roles/<doc_id>.json     # papel atribuído a cada seção (auditoria dos rótulos)
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
]}
```

## Módulos

| módulo | função |
|---|---|
| `pureprep/parse.py` | leitura do XML `req_document.xsd` → seções e blocos (parágrafo, item, `<req>`) |
| `pureprep/taxonomy.py` | papel de cada seção pelo título (meta, context, scenario, fr, nfr + subtipo) |
| `pureprep/extract.py` | gabarito (primário/secundário), classe FR/NFR, limpeza de IDs, padrão IPO |
| `pureprep/synth.py` | modos de entrada `context`, `notes`, `dialogue`; rastreabilidade (`support`) |
| `pureprep/evaluate.py` | P/R/F1 de extração, classificação, Trace-to-Source, taxa sem suporte |
| `pureprep/baseline.py` | baselines `oracle` e `naive` |
| `pureprep/crosscheck.py` | concordância com o ReqFromSRS |
| `pureprep/scan_originals.py` | triagem dos 79 documentos originais |
