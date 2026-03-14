import csv
import json
import os
import hashlib
import requests
from datetime import datetime, timedelta, timezone

TZ_TH = timezone(timedelta(hours=7))
POSTED_FILE = "posted.json"


def log(msg: str):
    print(f"[{datetime.now(TZ_TH).strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def iter_csv_rows(url: str, max_rows: int):
    if not url:
        raise ValueError("Missing SHOPEE_CSV_URL")

    log(f"Streaming CSV from URL... max_rows={max_rows}")

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()

        lines = (
            line.decode("utf-8-sig", errors="ignore")
            for line in r.iter_lines()
            if line
        )

        reader = csv.DictReader(lines)

        for i, row in enumerate(reader, start=1):
            yield row
            if i >= max_rows:
                break


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return {"ids": [], "image_keys": []}

    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"ids": [], "image_keys": []}
            data.setdefault("ids", [])
            data.setdefault("image_keys", [])
            return data
    except Exception:
        return {"ids": [], "image_keys": []}


def save_posted(data):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def image_key_from_url(url: str) -> str:
    return hashlib.md5(str(url).strip().lower().encode("utf-8")).hexdigest()
