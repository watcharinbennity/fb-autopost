import csv
import io
import json
import os
import requests
from datetime import datetime, timedelta, timezone

TZ_TH = timezone(timedelta(hours=7))
POSTED_FILE = "posted.json"


def log(msg: str):
    print(f"[{datetime.now(TZ_TH).strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def load_csv(url: str, max_rows: int):
    if not url:
        raise ValueError("Missing SHOPEE_CSV_URL")

    log(f"Downloading CSV from: {url}")
    r = requests.get(url, timeout=120)
    r.raise_for_status()

    text = r.content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    rows = []
    for i, row in enumerate(reader, start=1):
        rows.append(row)
        if i >= max_rows:
            break

    log(f"Loaded rows: {len(rows)}")
    return rows


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return []

    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_posted(data):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0
