"""Exporta variantes do modo ``meetings`` para o repositório de dados
``Entradas`` e regenera o índice.

Layout gerado::

    Entradas/
      indice_documentos.csv            # uma linha por (variante, documento)
      originais/<doc_id>.pdf           # documento original (compartilhado)
      variantes/<variante>/manifest.json
      variantes/<variante>/<doc_id>/reuniao_NN.txt
      variantes/<variante>/<doc_id>/gabarito_requisitos.json

O ``manifest.json`` de cada variante registra o commit do gerador, a
semente e os parâmetros do perfil, para que a variante seja reproduzível.

Uso:
    python scripts/export_entradas.py --output output --entradas ../Entradas
    python scripts/export_entradas.py --variants rules-realistic,rules-hard
    python scripts/export_entradas.py --index-only        # só regenera o índice
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pureprep import __version__  # noqa: E402

INDEX_FIELDS = [
    "variante", "id_documento", "nome_projeto", "qualidade_tier", "n_reunioes", "palavras_transcricao",
    "requisitos_dialogo", "requisitos_esperados", "requisitos_fr", "requisitos_nfr", "clear", "conflict_resolved",
    "conflict_open", "rejected", "ambiguous", "inconsistent", "incomplete", "omitted", "issues", "distratores",
    "pasta", "arquivo_gabarito", "arquivo_original",
]


def git_info():
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    commit = run("rev-parse", "HEAD")
    return {"commit": commit or None, "dirty": bool(run("status", "--porcelain", "--untracked-files=no")), "branch": run("rev-parse", "--abbrev-ref", "HEAD") or None}


def export_variant(src, dest, variant_name, git):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    docs, first = [], None
    for d in sorted(p for p in src.iterdir() if p.is_dir()):
        gt_path = d / "ground_truth_requirements.json"
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        out = dest / d.name
        out.mkdir()
        for m in gt["input"]["meetings"]:
            shutil.copyfile(d / m["file"], out / m["file"])
        shutil.copyfile(gt_path, out / "gabarito_requisitos.json")
        first = first or gt
        docs.append({"doc_id": d.name, "n_meetings": gt["input"]["n_meetings"], "n_words": gt["input"]["n_words"], **gt["stats"]})
    manifest = {
        "variant": variant_name,
        "schema_version": first["schema_version"] if first else None,
        "exported_on": date.today().isoformat(),
        "generator": {"tool": "pureprep", "version": __version__, **git, **(first["generator"] if first else {})},
        "source": {"dataset": "PURE", "doi": "10.5281/zenodo.1414117"},
        "documents": docs,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(docs)


def _original(entradas, doc_id):
    hits = sorted((entradas / "originais").glob(f"{doc_id}.*"))
    return hits[0].relative_to(entradas).as_posix() if hits else ""


def build_index(entradas):
    old = {}
    idx = entradas / "indice_documentos.csv"
    if idx.exists():
        with open(idx, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                old.setdefault(row["id_documento"], row)
    rows = []
    for vdir in sorted(p for p in (entradas / "variantes").iterdir() if p.is_dir()):
        for d in sorted(p for p in vdir.iterdir() if p.is_dir()):
            gt = json.loads((d / "gabarito_requisitos.json").read_text(encoding="utf-8"))
            prev = old.get(d.name, {})
            row = {
                "variante": vdir.name,
                "id_documento": d.name,
                "nome_projeto": prev.get("nome_projeto", gt.get("doc_title", "")),
                "qualidade_tier": prev.get("qualidade_tier", ""),
                "pasta": d.relative_to(entradas).as_posix(),
                "arquivo_gabarito": (d / "gabarito_requisitos.json").relative_to(entradas).as_posix(),
                "arquivo_original": _original(entradas, d.name),
            }
            reqs = gt["requirements"]
            row["requisitos_dialogo"] = len(reqs)
            row["requisitos_fr"] = sum(r["class"] == "FR" for r in reqs)
            row["requisitos_nfr"] = sum(r["class"] == "NFR" for r in reqs)
            if str(gt.get("schema_version", "1")).startswith("2"):
                st = gt["stats"]
                row.update(n_reunioes=gt["input"]["n_meetings"], palavras_transcricao=gt["input"]["n_words"],
                           requisitos_esperados=st["n_expected_in_output"], issues=st["n_issues"], distratores=st["n_distractors"])
                for k in INDEX_FIELDS[10:18]:
                    row[k] = st["by_status"].get(k, 0)
            else:
                row.update(n_reunioes=1, palavras_transcricao=gt["input"]["n_words"], requisitos_esperados=len(reqs),
                           issues=0, distratores=0, clear=len(reqs))
                for k in INDEX_FIELDS[11:18]:
                    row[k] = 0
            rows.append(row)
    with open(idx, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
        wr.writeheader()
        wr.writerows(rows)
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default=str(ROOT / "output"), help="saída do pureprep.cli")
    ap.add_argument("--entradas", default=str(ROOT.parent / "Entradas"), help="repositório de dados")
    ap.add_argument("--variants", default="", help="variantes a exportar (padrão: todas as do manifest)")
    ap.add_argument("--index-only", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true", help="exporta mesmo com alterações não commitadas no gerador")
    args = ap.parse_args(argv)
    entradas = Path(args.entradas)
    if not args.index_only:
        out = Path(args.output)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        variants = [v for v in args.variants.split(",") if v] or manifest.get("meetings_variants", [])
        git = git_info()
        if git["dirty"] and not args.allow_dirty:
            sys.exit("O gerador tem alterações não commitadas; faça commit (ou use --allow-dirty) para o manifest apontar um commit reproduzível.")
        for v in variants:
            n = export_variant(out / "pairs" / "meetings" / v, entradas / "variantes" / v, v, git)
            print(f"{v}: {n} documentos -> {entradas / 'variantes' / v}")
    print(f"índice: {build_index(entradas)} linhas -> {entradas / 'indice_documentos.csv'}")


if __name__ == "__main__":
    main()
