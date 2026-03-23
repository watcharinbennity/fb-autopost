import csv
import json
import re
import requests
from datetime import datetime, timezone, timedelta

THAI_TZ = timezone(timedelta(hours=7))


def log(message):
    now = datetime.now(THAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def to_float(value):
    try:
        text = str(value).strip().replace(",", "")
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


def _stream_csv_lines(response):
    first = True
    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue

        line = raw_line
        if first:
            line = line.lstrip("\ufeff")
            first = False

        if line == "":
            continue

        yield line


def iter_csv_rows(csv_url, max_rows=100000):
    log("Streaming CSV from URL...")

    with requests.get(csv_url, stream=True, timeout=(20, 120)) as r:
        r.raise_for_status()

        lines = (
            line.decode("utf-8-sig", errors="ignore")
            for line in r.iter_lines()
            if line  # กัน None / blank
        )

        reader = csv.DictReader(lines)

        for i, row in enumerate(reader, start=1):
            if i % 5000 == 0:
                log(f"streamed_rows={i}")

            if i > max_rows:
                log(f"Reached max_rows={max_rows}")
                break

            yield row
