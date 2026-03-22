import csv
import io
import json
import re
import requests
from datetime import datetime


def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def to_float(value):
    try:
        text = str(value).strip()
        text = text.replace(",", "")
        match = re.findall(r"-?\d+\.?\d*", text)
        if not match:
            return 0.0
        return float(match[0])
    except Exception:
        return 0.0


def image_key_from_url(url):
    if not url:
        return ""
    return re.sub(r"[\W_]+", "", str(url).strip().lower())[:180]


def load_json_file(path, default=None):
    default = default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def iter_csv_rows(csv_url, max_rows=200000):
    r = requests.get(csv_url, timeout=180)
    r.raise_for_status()

    content = r.content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(content))

    for i, row in enumerate(reader, start=1):
        if i > max_rows:
            break
        yield row
