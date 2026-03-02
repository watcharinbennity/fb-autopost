# app.py
# Facebook Page autopost (Shopee CSV) for BEN Home & Electrical
# Required ENV (GitHub Secrets):
#   PAGE_ID
#   PAGE_ACCESS_TOKEN
#   SHOPEE_CSV_URL
#
# Optional ENV:
#   TZ=Asia/Bangkok
#   POSTS_PER_RUN=1
#   TOP_POOL=120
#   REPOST_AFTER_DAYS=14
#   STATE_FILE=state.json
#   CAPTION_STYLE=short|full
#   BRAND=BEN Home & Electrical
#   HASHTAGS=...
#   ALLOW_KEYWORDS=... (regex with |)
#   BLOCK_KEYWORDS=... (regex with |)

import os
import io
import re
import json
import time
import random
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# -----------------------------
# HTTP session with retry/timeout
# -----------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


SESSION = make_session()


# -----------------------------
# Config
# -----------------------------
STATE_FILE = os.getenv("STATE_FILE", "state.json").strip()
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ = os.getenv("TZ", "Asia/Bangkok").strip()
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))
TOP_POOL = int(os.getenv("TOP_POOL", "120"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

CAPTION_STYLE = os.getenv("CAPTION_STYLE", "short").strip().lower()
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeAndElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #ดีลดี #Shopee",
).strip()

ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    "ปลั๊ก|ปลั๊กพ่วง|ปลั๊กไฟ|สายไฟ|หลอดไฟ|โคมไฟ|พัดลม|สวิตช์|เบรกเกอร์|ตู้ไฟ|อะแดปเตอร์|ชาร์จ|USB|เครื่องมือ|สว่าน|ไขควง|คีม|เทปพันสาย|รางปลั๊ก|ไฟฉาย|แบต|ถ่าน|ของใช้ในบ้าน|ครัว|จัดเก็บ|ทำความสะอาด",
).strip()

BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    "แชมพู|ครีม|อาหารเสริม|บุหรี่ไฟฟ้า|ยา|การพนัน|เซ็กซ์|18\\+",
).strip()

ALLOW_RE = re.compile(ALLOW_KEYWORDS, re.IGNORECASE)
BLOCK_RE = re.compile(BLOCK_KEYWORDS, re.IGNORECASE)


def die(msg: str) -> None:
    raise SystemExit(msg)


def now_th() -> dt.datetime:
    return dt.datetime.now(ZoneInfo(TZ))


# -----------------------------
# State
# -----------------------------
def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted": {}}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def posted_recently(state: dict, key: str, days: int) -> bool:
    posted = state.get("posted", {}).get(key)
    if not posted:
        return False
    try:
        t = dt.datetime.fromisoformat(posted)
        if t.tzinfo is None:
            t = t.replace(tzinfo=ZoneInfo(TZ))
    except Exception:
        return False
    return (now_th() - t) < dt.timedelta(days=days)


def mark_posted(state: dict, key: str) -> None:
    state.setdefault("posted", {})[key] = now_th().isoformat()


# -----------------------------
# CSV loader
# -----------------------------
def fetch_csv(url: str) -> pd.DataFrame:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    # รองรับ csv ที่เป็น utf-8 / หรือมี BOM
    content = r.content
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def pick_columns(df: pd.DataFrame) -> dict:
    """
    พยายาม map คอลัมน์จาก CSV ให้ยืดหยุ่น:
    - title/name/product -> title
    - url/link -> link
    - image/image_url/img -> image
    - price/discount -> price
    """
    cols = set(df.columns)

    def first_match(candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    return {
        "title": first_match(["title", "name", "product", "product_name"]),
        "link": first_match(["url", "link", "product_url", "shopee_url"]),
        "image": first_match(["image", "image_url", "img", "img_url", "thumbnail", "thumb"]),
        "price": first_match(["price", "sale_price", "discount_price"]),
    }


def normalize_row(row: dict, cmap: dict) -> dict:
    def get(key):
        col = cmap.get(key)
        v = row.get(col) if col else None
        if pd.isna(v):
            return ""
        return str(v).strip()

    title = get("title")
    link = get("link")
    image = get("image")
    price = get("price")

    return {"title": title, "link": link, "image": image, "price": price}


# -----------------------------
# Filters
# -----------------------------
def allowed_item(item: dict) -> bool:
    text = f"{item.get('title','')} {item.get('link','')}"
    if not item.get("image"):
        return False  # ต้องมีรูปเท่านั้น
    if BLOCK_RE.search(text):
        return False
    if not ALLOW_RE.search(text):
        return False
    return True


def build_caption(item: dict) -> str:
    title = item.get("title", "").strip()
    link = item.get("link", "").strip()
    price = item.get("price", "").strip()

    # ไม่ใส่คำว่า "เพจนายหน้า" ตามที่สั่ง
    # ใช้สไตล์ขายดีลบ้าน/ไฟฟ้า + ชวนสอบถาม
    if CAPTION_STYLE == "full":
        lines = [
            f"🏠⚡ {BRAND}",
            f"✨ ดีลแนะนำ: {title}" if title else "✨ ดีลแนะนำวันนี้",
            f"💬 สนใจทักแชทสอบถามรายละเอียด/วิธีสั่งซื้อได้เลย",
        ]
        if price:
            lines.append(f"💸 ราคา/โปร: {price}")
        if link:
            lines.append(f"🔗 ลิงก์สินค้า: {link}")
        lines.append(HASHTAGS)
        return "\n".join(lines)

    # short (กระชับ)
    parts = []
    if title:
        parts.append(f"✨ {title}")
    if price:
        parts.append(f"💸 {price}")
    parts.append("💬 สนใจทักแชทสอบถามได้เลย")
    if link:
        parts.append(link)
    parts.append(HASHTAGS)
    return "\n".join(parts)


# -----------------------------
# Facebook Graph API: Photo post
# -----------------------------
def fb_post_photo(image_url: str, caption: str) -> dict:
    """
    โพสต์แบบ 'รูป' (ไม่ใช่ feed text) เพื่อให้แน่ใจว่ามีรูปจริง
    ใช้ endpoint: /{page_id}/photos
    """
    endpoint = f"https://graph.facebook.com/v20.0/{PAGE_ID}/photos"
    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": PAGE_ACCESS_TOKEN,
        "published": "true",
    }
    r = SESSION.post(endpoint, data=payload, timeout=30)
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(f"FB error {r.status_code}: {data}")
    return data


# -----------------------------
# Main
# -----------------------------
def main():
    print("== fb-autopost ==")
    print("time(th):", now_th().strftime("%Y-%m-%d %H:%M:%S %z"))
    print("page_id:", PAGE_ID[:4] + "****" if PAGE_ID else "")
    print("tz:", TZ)
    print("posts_per_run:", POSTS_PER_RUN)
    print("top_pool:", TOP_POOL)
    print("repost_after_days:", REPOST_AFTER_DAYS)
    print("caption_style:", CAPTION_STYLE)
    print("brand:", BRAND)
    print("hashtags:", HASHTAGS)
    print("allow:", ALLOW_KEYWORDS)
    print("block:", BLOCK_KEYWORDS)

    if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
        die("Missing env: PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL")

    state = load_state()

    df = fetch_csv(SHOPEE_CSV_URL)
    if df.empty:
        die("CSV is empty")

    cmap = pick_columns(df)
    if not cmap["image"]:
        die("CSV must have an image column (image/image_url/img/thumbnail)")

    # สุ่มจาก top_pool แรก (กันวนซ้ำมาก)
    df2 = df.head(TOP_POOL).copy()
    rows = df2.to_dict(orient="records")
    random.shuffle(rows)

    posted_count = 0

    for row in rows:
        item = normalize_row(row, cmap)
        if not allowed_item(item):
            continue

        # key กันโพสต์ซ้ำ: ใช้ link ถ้ามี ไม่งั้นใช้ title+image
        key = item["link"] or (item["title"] + "|" + item["image"])
        key = key.strip()
        if not key:
            continue

        if posted_recently(state, key, REPOST_AFTER_DAYS):
            continue

        caption = build_caption(item)

        print("\n--- posting ---")
        print("title:", item.get("title", "")[:120])
        print("image:", item.get("image", "")[:120])
        print("link:", item.get("link", "")[:120])

        # โพสต์รูป
        fb_post_photo(item["image"], caption)

        mark_posted(state, key)
        save_state(state)

        posted_count += 1
        if posted_count >= POSTS_PER_RUN:
            break

        # เว้นนิดนึงกันยิงถี่
        time.sleep(3)

    if posted_count == 0:
        print("No eligible item found (need image + match allow keywords + not blocked).")
    else:
        print(f"Done. posted={posted_count}")


if __name__ == "__main__":
    main()
