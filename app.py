import os
import re
import csv
import json
import time
import random
from io import StringIO
from typing import List, Dict, Tuple, Optional

import requests

GRAPH_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = "state.json"

REQUIRED_COLS_MIN = {"name", "url"}  # image handled flexibly

# ---------- Utilities ----------

def env_required(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise SystemExit(f"ERROR: Missing env: {name}")
    return v

def load_state() -> Dict:
    if not os.path.exists(STATE_FILE):
        return {"posted_keys": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted_keys": []}

def save_state(state: Dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def is_direct_image_url(url: str) -> bool:
    # Must look like an image file URL (simple heuristic)
    if not url:
        return False
    u = url.strip()
    if not (u.startswith("http://") or u.startswith("https://")):
        return False
    return bool(re.search(r"\.(jpg|jpeg|png|webp|gif)(\?.*)?$", u, re.IGNORECASE))

def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def make_key(row: Dict) -> str:
    # stable key for "already posted"
    # prefer URL as unique, fallback name
    return normalize_text(row.get("url", "")) or normalize_text(row.get("name", ""))

# ---------- CSV Fetch & Parse ----------

def fetch_csv_text(url: str, timeout: int = 30) -> str:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    # Some CSV are served as bytes; requests will guess encoding. Keep as text.
    return r.text

def parse_rows(csv_text: str) -> Tuple[List[Dict], List[str]]:
    """
    Returns (usable_rows, issues)
    Supports:
      - image as "img1|img2|img3"
      - or image1,image2,image3 columns
      - or image column with single image
    """
    issues = []
    sio = StringIO(csv_text)
    reader = csv.DictReader(sio)
    if not reader.fieldnames:
        return [], ["CSV has no header row (no columns found)."]

    fieldnames = [fn.strip() for fn in reader.fieldnames if fn]
    missing_min = [c for c in REQUIRED_COLS_MIN if c not in fieldnames]
    if missing_min:
        issues.append(f"CSV missing required columns: {missing_min}. Found: {fieldnames}")

    usable = []
    preview = []

    for i, row in enumerate(reader, start=1):
        # Keep a small preview for debugging
        if len(preview) < 5:
            preview.append({k: (row.get(k) or "").strip() for k in fieldnames})

        name = (row.get("name") or "").strip()
        url = (row.get("url") or "").strip()

        # collect images
        images: List[str] = []

        # prefer image1,image2,image3 if present
        for col in ["image1", "image2", "image3"]:
            if col in fieldnames:
                v = (row.get(col) or "").strip()
                if v:
                    images.append(v)

        if not images:
            img = (row.get("image") or "").strip()
            if img:
                if "|" in img:
                    images.extend([p.strip() for p in img.split("|") if p.strip()])
                else:
                    images.append(img)

        # validate
        if not name or not url:
            continue

        # Keep only direct image urls
        images = [u for u in images if is_direct_image_url(u)]
        # Require at least 1 image; we will use up to 3
        if len(images) < 1:
            continue

        usable.append({
            "name": name,
            "url": url,
            "images": images[:3],  # up to 3
        })

    if not usable:
        issues.append("CSV has no usable rows. Need columns: name,url and at least 1 direct image URL (jpg/png/webp...).")
        if preview:
            issues.append(f"Preview first rows (first 5): {preview}")

    return usable, issues

# ---------- Caption / Reach ----------

CAPTION_TEMPLATES = [
    """🔧 {name}

✅ ของแท้ใช้งานจริง เหมาะงานซ่อมบ้าน/DIY
📌 ดูรายละเอียด + ราคา:
{url}

#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง""",
    """⚡ {name}

งานช่างในบ้านมีติดไว้คุ้มมาก ✅
🛒 กดสั่งซื้อได้ที่ลิงก์:
{url}

ถามได้เลยครับ ต้องการให้แนะนำรุ่น/การใช้งาน 👇
#BENHomeElectrical #เครื่องมือช่าง #งานช่าง #บ้านและสวน""",
    """🧰 {name}

จุดเด่น:
• แข็งแรง ทน ใช้งานง่าย
• เหมาะกับงานบ้านและงานช่างทั่วไป

👉 ลิงก์สินค้า:
{url}

#BENHomeElectrical #อุปกรณ์ไฟฟ้า #ของใช้ในบ้าน #ช่าง""",
    """🔥 แนะนำวันนี้: {name}

ใครกำลังหาของใช้ซ่อมบ้าน/งานช่าง ตัวนี้น่าโดน ✅
📦 ดูรายละเอียด/สั่งซื้อ:
{url}

คอมเมนต์ “สนใจ” เดี๋ยวส่งลิงก์ให้ก็ได้ครับ 🙂
#BENHomeElectrical #เครื่องมือ #DIY #ของดีบอกต่อ"""
]

def build_caption(name: str, url: str) -> str:
    tpl = random.choice(CAPTION_TEMPLATES)
    return tpl.format(name=name.strip(), url=url.strip())

# ---------- Facebook Posting (3 photos) ----------

def fb_post_unpublished_photo(page_id: str, token: str, image_url: str) -> str:
    """
    Upload a photo as unpublished to use in multi-photo feed post.
    Returns photo id.
    """
    endpoint = f"{GRAPH_BASE}/{page_id}/photos"
    data = {
        "url": image_url,
        "published": "false",
        "access_token": token,
    }
    r = requests.post(endpoint, data=data, timeout=60)
    try:
        js = r.json()
    except Exception:
        js = {"error": {"message": r.text}}
    if r.status_code >= 400 or "error" in js:
        raise RuntimeError(f"Upload photo failed: {js}")
    return js["id"]

def fb_create_feed_post_with_media(page_id: str, token: str, message: str, media_ids: List[str]) -> Dict:
    endpoint = f"{GRAPH_BASE}/{page_id}/feed"
    data = {
        "message": message,
        "access_token": token,
    }
    # attached_media[0].. format
    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid}, ensure_ascii=False)
    r = requests.post(endpoint, data=data, timeout=60)
    js = r.json()
    if r.status_code >= 400 or "error" in js:
        raise RuntimeError(f"Create feed post failed: {js}")
    return js

# ---------- Main ----------

def main():
    random.seed()

    page_id = env_required("PAGE_ID")
    token = env_required("PAGE_ACCESS_TOKEN")
    csv_url = env_required("SHOPEE_CSV_URL")

    print("INFO: Fetching CSV...")
    csv_text = fetch_csv_text(csv_url)

    rows, issues = parse_rows(csv_text)
    if issues:
        print("INFO: CSV checks:")
        for it in issues:
            print(" -", it)

    if not rows:
        raise SystemExit("ERROR: No usable rows in CSV. Fix CSV then re-run.")

    state = load_state()
    posted_keys = set(state.get("posted_keys", []))

    # Filter not yet posted
    candidates = [r for r in rows if make_key(r) not in posted_keys]

    # If all posted, reset (optional behavior)
    if not candidates:
        print("INFO: All items already posted. Resetting posted_keys to start over.")
        posted_keys = set()
        candidates = rows[:]

    # Pick random product
    picked = random.choice(candidates)
    name = picked["name"]
    url = picked["url"]
    images = picked["images"][:3]

    caption = build_caption(name, url)

    print("INFO: Picked product:", name)
    print("INFO: Images:", images)
    print("INFO: Posting 3-photo feed post...")

    # Upload up to 3 photos unpublished
    media_ids = []
    for u in images:
        mid = fb_post_unpublished_photo(page_id, token, u)
        media_ids.append(mid)
        # small delay to avoid rate quirks
        time.sleep(1.0)

    result = fb_create_feed_post_with_media(page_id, token, caption, media_ids)
    post_id = result.get("id") or result.get("post_id")

    print("SUCCESS: Posted:", post_id)

    # Save state
    posted_keys.add(make_key(picked))
    state["posted_keys"] = list(posted_keys)
    save_state(state)

if __name__ == "__main__":
    main()
