import os
import re
import io
import json
import time
import random
import datetime as dt
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple

import requests
import pandas as pd


# ---------------------------
# Config
# ---------------------------
STATE_FILE = os.getenv("STATE_FILE", "state.json")

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ = os.getenv("TZ", "Asia/Bangkok")
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))
TOP_POOL = int(os.getenv("TOP_POOL", "120"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

BRAND_NAME = os.getenv("BRAND_NAME", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv("HASHTAGS", "#BENHomeAndElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า").strip()
CAPTION_STYLE = os.getenv("CAPTION_STYLE", "short").strip().lower()

KEYWORDS_ALLOW = os.getenv("KEYWORDS_ALLOW", "").strip()
KEYWORDS_BLOCK = os.getenv("KEYWORDS_BLOCK", "").strip()

GRAPH = "https://graph.facebook.com/v19.0"

# Timeouts (กันค้างจน Action โดน cancel)
CSV_TIMEOUT = (10, 25)      # connect, read
IMG_TIMEOUT = (10, 25)
API_TIMEOUT = (10, 25)

USER_AGENT = "fb-autopost/1.0 (+github actions)"


# ---------------------------
# Helpers
# ---------------------------
def die(msg: str) -> None:
    raise SystemExit(msg)


def now_th() -> dt.datetime:
    return dt.datetime.now(tz=ZoneInfo(TZ))


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"used": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def prune_state(state: Dict[str, Any]) -> None:
    """ลบของเก่าเกิน REPOST_AFTER_DAYS เพื่อให้วนโพสได้หลังครบกำหนด"""
    cutoff = now_th() - dt.timedelta(days=REPOST_AFTER_DAYS)
    used_new = []
    for item in state.get("used", []):
        ts = item.get("ts")
        if not ts:
            continue
        try:
            t = dt.datetime.fromisoformat(ts)
        except Exception:
            continue
        if t >= cutoff:
            used_new.append(item)
    state["used"] = used_new


def normalize_text(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip()


def compile_kw(pattern: str) -> Optional[re.Pattern]:
    if not pattern:
        return None
    return re.compile(pattern, re.IGNORECASE)


ALLOW_RE = compile_kw(KEYWORDS_ALLOW)
BLOCK_RE = compile_kw(KEYWORDS_BLOCK)


def match_keywords(title: str) -> bool:
    """คัดหมวดแบบง่าย: ต้องผ่าน allow (ถ้ามี) และห้ามเจอ block"""
    t = title or ""
    if BLOCK_RE and BLOCK_RE.search(t):
        return False
    if ALLOW_RE:
        return bool(ALLOW_RE.search(t))
    return True


def pick_first_existing(row: Dict[str, Any], keys: List[str]) -> str:
    for k in keys:
        v = normalize_text(row.get(k))
        if v:
            return v
    return ""


def detect_fields(df: pd.DataFrame) -> Tuple[str, str, str, str]:
    """
    พยายามเดา column ของ:
    - title
    - link
    - image_url
    - price
    """
    cols = {c.lower(): c for c in df.columns}

    def find(candidates: List[str]) -> str:
        for cand in candidates:
            if cand in cols:
                return cols[cand]
        # หาแบบ contains
        for cand in candidates:
            for k_lower, k_orig in cols.items():
                if cand in k_lower:
                    return k_orig
        return ""

    title_col = find(["title", "name", "product_name", "item_name"])
    link_col = find(["link", "url", "product_url", "product link", "product_link"])
    img_col = find(["image", "image_url", "img", "thumbnail", "thumb", "image link", "image_link"])
    price_col = find(["price", "sale_price", "final_price", "discount_price"])

    return title_col, link_col, img_col, price_col


def get_csv_df(url: str) -> pd.DataFrame:
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=CSV_TIMEOUT)
    r.raise_for_status()

    # รองรับ csv ปกติ + utf-8-sig
    content = r.content
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    bio = io.StringIO(text)
    df = pd.read_csv(bio)
    return df


def already_used(state: Dict[str, Any], key: str) -> bool:
    for item in state.get("used", []):
        if item.get("key") == key:
            return True
    return False


def add_used(state: Dict[str, Any], key: str, title: str) -> None:
    state.setdefault("used", []).append({
        "key": key,
        "title": title,
        "ts": now_th().isoformat()
    })


def http_post(url: str, data=None, files=None) -> Dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    r = requests.post(url, data=data, files=files, headers=headers, timeout=API_TIMEOUT)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    if r.status_code >= 400 or ("error" in j):
        raise RuntimeError(f"HTTP {r.status_code} error: {j}")
    return j


def http_get(url: str, params=None) -> Dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text}
    if r.status_code >= 400 or ("error" in j):
        raise RuntimeError(f"HTTP {r.status_code} error: {j}")
    return j


def download_image_bytes(img_url: str) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(img_url, headers=headers, timeout=IMG_TIMEOUT, stream=True)
    r.raise_for_status()
    # จำกัดขนาดกันไฟล์ใหญ่ผิดปกติ (10MB)
    max_bytes = 10 * 1024 * 1024
    chunks = []
    total = 0
    for ch in r.iter_content(chunk_size=65536):
        if not ch:
            continue
        chunks.append(ch)
        total += len(ch)
        if total > max_bytes:
            raise RuntimeError("Image too large (>10MB)")
    return b"".join(chunks)


def build_caption(title: str, price: str, link: str) -> str:
    title = title.strip()
    price = price.strip()
    link = link.strip()

    if CAPTION_STYLE == "full":
        parts = [
            f"🏠⚡ {BRAND_NAME}",
            f"✅ {title}",
        ]
        if price:
            parts.append(f"💸 ราคา: {price}")
        if link:
            parts.append(f"🔗 ดูรายละเอียด: {link}")
        parts.append(HASHTAGS)
        return "\n".join(parts)

    # short
    line1 = f"✅ {title}"
    line2 = f"🔗 {link}" if link else ""
    return "\n".join([x for x in [line1, line2, HASHTAGS] if x])


def upload_photo_unpublished(image_bytes: bytes, caption: str) -> str:
    """
    อัปโหลดรูปเข้าเพจแบบ unpublished เพื่อเอา media_fbid ไปแนบโพส
    """
    url = f"{GRAPH}/{PAGE_ID}/photos"
    files = {
        "source": ("image.jpg", image_bytes, "image/jpeg")
    }
    data = {
        "published": "false",
        "caption": caption,
        "access_token": PAGE_ACCESS_TOKEN
    }
    j = http_post(url, data=data, files=files)
    media_id = j.get("id")
    if not media_id:
        raise RuntimeError(f"Upload photo failed: {j}")
    return media_id


def create_feed_post_with_media(message: str, media_id: str) -> str:
    """
    สร้างโพสบนหน้าเพจ โดยแนบรูปที่อัปโหลดไว้
    """
    url = f"{GRAPH}/{PAGE_ID}/feed"
    data = {
        "message": message,
        "attached_media[0]": json.dumps({"media_fbid": media_id}),
        "access_token": PAGE_ACCESS_TOKEN
    }
    j = http_post(url, data=data)
    post_id = j.get("id")
    if not post_id:
        raise RuntimeError(f"Create post failed: {j}")
    return post_id


def main() -> None:
    if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
        die("Missing env: PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL")

    print("== fb-autopost ==")
    print("time(th):", now_th().strftime("%Y-%m-%d %H:%M:%S %Z"))
    print("page_id:", PAGE_ID[:4] + "****")
    print("tz:", TZ)
    print("posts_per_run:", POSTS_PER_RUN)
    print("top_pool:", TOP_POOL)
    print("repost_after_days:", REPOST_AFTER_DAYS)
    print("caption_style:", CAPTION_STYLE)
    print("brand:", BRAND_NAME)
    print("hashtags:", HASHTAGS)
    print("allow:", KEYWORDS_ALLOW)
    print("block:", KEYWORDS_BLOCK)

    state = load_state()
    prune_state(state)

    # 1) load CSV
    df = get_csv_df(SHOPEE_CSV_URL)
    if df.empty:
        die("CSV is empty")

    title_col, link_col, img_col, price_col = detect_fields(df)
    if not title_col:
        die("Cannot detect title column in CSV")
    if not img_col:
        die("Cannot detect image column in CSV (ต้องมีรูปเท่านั้น)")

    # 2) build candidates
    rows = df.to_dict(orient="records")
    random.shuffle(rows)

    candidates = []
    for r in rows:
        title = normalize_text(r.get(title_col))
        if not title:
            continue
        if not match_keywords(title):
            continue

        img = normalize_text(r.get(img_col))
        if not img or not img.lower().startswith(("http://", "https://")):
            continue  # ต้องมีรูปเท่านั้น

        link = normalize_text(r.get(link_col)) if link_col else ""
        price = normalize_text(r.get(price_col)) if price_col else ""

        # key ใช้กันโพสซ้ำ
        key = link or (title + "|" + img)
        if already_used(state, key):
            continue

        candidates.append((title, price, link, img, key))
        if len(candidates) >= TOP_POOL:
            break

    if not candidates:
        die("No candidates found (อาจโดนคัดหมวด/หรือไม่มีรูป/หรือโพสไปแล้ว)")

    # 3) post N items
    posted = 0
    for title, price, link, img, key in candidates:
        if posted >= POSTS_PER_RUN:
            break

        caption = build_caption(title=title, price=price, link=link)
        print("\n---")
        print("pick:", title)
        print("img:", img)
        print("link:", link)

        # download image
        image_bytes = download_image_bytes(img)

        # upload photo unpublished -> create feed post with attached media
        media_id = upload_photo_unpublished(image_bytes, caption)
        post_id = create_feed_post_with_media(caption, media_id)

        print("posted:", post_id)
        add_used(state, key, title)
        posted += 1

        # หน่วงนิดกันโดน rate limit
        time.sleep(2)

    save_state(state)
    print("\nDone. posted:", posted)


if __name__ == "__main__":
    main()
