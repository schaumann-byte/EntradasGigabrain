"""Baixa o PURE (Zenodo) e o ReqFromSRS (GitHub do REQINONE), com checagem MD5.

Uso: python scripts/download_data.py
"""

import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
EXT = ROOT / "data" / "external" / "reqinone"
ZENODO_RECORD = "https://zenodo.org/api/records/1414117"
REQINONE = "https://raw.githubusercontent.com/TaohongZ/ReqInOne/HEAD/ReqInOne_data"


def fetch(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        print("baixando", url)
        urllib.request.urlretrieve(url, dest)
    return dest


def main():
    record = json.loads(urllib.request.urlopen(ZENODO_RECORD).read())
    for f in record["files"]:
        dest = fetch(f["links"]["self"], RAW / f["key"])
        algo, expected = f["checksum"].split(":")
        got = hashlib.new(algo, dest.read_bytes()).hexdigest()
        assert got == expected, f"checksum inválido para {dest.name}"
        with zipfile.ZipFile(dest) as z:
            z.extractall(RAW / dest.stem, members=[m for m in z.namelist() if not m.startswith("__MACOSX")])
        print(f"ok {dest.name} ({algo} {got})")
    fetch(f"{REQINONE}/Dataset/reqFromSRS.csv", EXT / "reqFromSRS.csv")
    fetch(f"{REQINONE}/Generated%20SRS/Source_natural_language_text.pdf", EXT / "Source_natural_language_text.pdf")


if __name__ == "__main__":
    main()
