"""Download the cross-schema EVALUATION datasets and convert them for LocalLens. Needs internet; run once.

Both datasets come from the UCI Machine Learning Repository and are licensed CC BY 4.0 (attribution required).
They are used to TEST the model on schemas it has never seen. They are never used for training and never stored in git
(finetune/external/ is ignored). The downloaded files are untrusted data: each goes into its own folder and is only read
by pandas, never executed.

    python -I finetune/fetch_external.py
"""
from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "external"
SOURCES = {
    "uci": ("Online Retail II", "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip",
            "https://archive.ics.uci.edu/dataset/502/online+retail+ii", "CC BY 4.0"),
    "wholesale": ("Wholesale customers", "https://archive.ics.uci.edu/static/public/292/wholesale+customers.zip",
                  "https://archive.ics.uci.edu/dataset/292/wholesale+customers", "CC BY 4.0"),
}


def _download(url: str) -> zipfile.ZipFile:
    with urllib.request.urlopen(url, timeout=300) as r:      # noqa: S310 (fixed https URLs above)
        return zipfile.ZipFile(io.BytesIO(r.read()))


def fetch_online_retail() -> Path:
    folder = OUT / "uci"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "online_retail_ii.parquet"
    if target.exists():
        return target
    z = _download(SOURCES["uci"][1])
    name = next(n for n in z.namelist() if n.lower().endswith(".xlsx"))
    sheets = pd.read_excel(io.BytesIO(z.read(name)), sheet_name=None, engine="openpyxl")   # two sheets, 2009-10 and 2010-11
    pd.concat(sheets.values(), ignore_index=True).to_parquet(target, index=False)
    return target


def fetch_wholesale() -> Path:
    folder = OUT / "wholesale"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "wholesale.csv"
    if target.exists():
        return target
    z = _download(SOURCES["wholesale"][1])
    df = pd.read_csv(io.BytesIO(z.read(next(n for n in z.namelist() if n.lower().endswith(".csv")))))
    # the repository documents these codes: Channel 1 = Horeca (hotels, restaurants, cafes), 2 = Retail; Region 1 = Lisbon, 2 = Oporto, 3 = Other
    df["Channel"] = df["Channel"].map({1: "Horeca", 2: "Retail"})
    df["Region"] = df["Region"].map({1: "Lisbon", 2: "Oporto", 3: "Other"})
    df.to_csv(target, index=False)
    return target


if __name__ == "__main__":
    for key, (title, _, page, lic) in SOURCES.items():
        print(f"{title}: {page} ({lic})")
    print(fetch_online_retail())
    print(fetch_wholesale())
