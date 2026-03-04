import os
import re
import io
import json
import time
import random
import datetime as dt
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import requests
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -----------------------
# Config (ENV)
# -----------------------
STATE_FILE = os.getenv("STATE_FILE", "state.json")

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ = os.getenv("TZ", "Asia/Bangkok")

POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "2"))   # Auto Pro: โพสต์มากกว่าเดิม
TOP_POOL = int(os.getenv("TOP_POOL", "200"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

BRAND = os.getenv("BRAND", "BEN Home & Electrical")
CAPTION_STYLE = os.getenv("CAPTION_STYLE", "full").strip().lower()

HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeAndElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #ดีลดี #Shopee #ลดราคา #ของมันต้องมี"
)

# โฟกัสหมวด/คีย์เวิร์ดให้ตรงเพจ (ปรับได้ใน ENV)
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟ|ปลั๊ก|สายไฟ|พาวเวอร์|ปลั๊กพ่วง|หลอดไฟ|โคม|สวิตช์|เบรกเกอร์|อะแดปเตอร์|ชาร์จ|เครื่องมือ|คีม|ไขควง|สว่าน|เทปพันสาย|กล่อง|ราง|ตู้|แม่เหล็ก|กาว|ซิลิโคน|อุปกรณ์บ้าน|ครัว|ห้องน้ำ)"
).strip()

BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(อาหาร|เสื้อผ้า|เครื่องสำอาง|สกินแคร์|เกม|บัตรเติม|18\+)"
).strip()

# ต้องมีสื่อเท่านั้น (รูปหรือวิดีโอ)
REQUIRE_MEDIA = os.getenv("REQUIRE_MEDIA", "1").strip() != "0"

# เงื่อนไข Auto Pro (ถ้า CSV มีคอลัมน์พวกนี้จะใช้)
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))          # เน้นเรตติ้ง
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))# เน้นลดราคา %
MIN_SOLD = int(os.getenv("MIN_SOLD", "50"))                 # เน้นขายดี
REQUIRE_COUPON = os.getenv("REQUIRE_COUPON", "0").strip() == "1"  # บังคับมีคูปอง/โค้ดไหม

# เวลาหน่วงระหว่างโพสต์ (กันยิงถี่)
SLEEP_BETWEEN_POSTS_SEC = int(os.getenv("SLEEP_BETWEEN_POSTS_SEC", "8"))


def now_th() -> dt.datetime:
    return dt.datetime.now(ZoneInfo(TZ))


def die(msg: str, code: int = 1):
    print("FATAL:", msg)
    raise SystemExit(code)


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted_ids": {}, "last_run_iso": ""}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted_ids": {}, "last_run_iso": ""}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


SESSION = make_session()


def normalize_text(x) -> str:
    if x is None:
        return ""
    s = str(x)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def to_float(x) -> float | None:
    s = normalize_text(x)
    if not s:
        return None
    # ดึงตัวเลข 4.8 / 4,8 / "4.8/5"
    s = s.replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def to_int(x) -> int | None:
    s = normalize_text(x)
    if not s:
        return None
    # "1.2k" "3,400" "1200"
    s = s.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k|m)?", s)
    if not m:
        return None
    num = float(m.group(1))
    suf = m.group(2)
    if suf == "k":
        num *= 1000
    elif suf == "m":
        num *= 1_000_000
    return int(num)


def compile_pat(expr: str):
    if not expr:
        return None
    return re.compile(expr, flags=re.IGNORECASE)


ALLOW_PAT = compile_pat(ALLOW_KEYWORDS)
BLOCK_PAT = compile_pat(BLOCK_KEYWORDS)


def is_allowed(title: str, category: str) -> bool:
    text = f"{title} {category}".strip()
    if BLOCK_PAT and BLOCK_PAT.search(text):
        return False
    if ALLOW_PAT:
        return bool(ALLOW_PAT.search(text))
    return True


def pick_columns(df: pd.DataFrame) -> dict:
    """
    รองรับคอลัมน์หลายชื่อ (CSV จากหลายแหล่ง)
    """
    cols = {c.lower().strip(): c for c in df.columns}

    def find(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    return {
        # หลัก
        "title": find("title", "name", "product_name"),
        "url": find("url", "product_url", "link", "product_link"),
        # media
        "media": find("media", "media_url", "video", "video_url", "image", "image_url", "image_link", "img", "thumbnail", "images"),
        "image": find("image", "image_url", "image_link", "img", "thumbnail", "images"),
        "video": find("video", "video_url"),
        # category
        "category": find("category", "cat", "category_name"),
        # pricing / discount
        "price": find("price", "sale_price", "discount_price", "current_price"),
        "original_price": find("original_price", "list_price", "normal_price", "price_before"),
        "discount_pct": find("discount_pct", "discount_percent", "discount", "off_percent"),
        # rating / sold
        "rating": find("rating", "rate", "stars", "score"),
        "sold": find("sold", "sales", "sold_count", "total_sold", "orders", "order_count"),
        # coupon / promo
        "coupon": find("coupon", "voucher", "promo", "promo_code", "discount_code", "code"),
    }


def extract_first_url(field: str) -> str:
    s = normalize_text(field)
    if not s:
        return ""
    parts = re.split(r"[;,|]\s*", s)
    for p in parts:
        p = p.strip()
        if p.startswith("http"):
            return p
    return ""


def guess_media_url(row, col) -> str:
    # priority: video -> image -> media
    for key in ("video", "image", "media"):
        c = col.get(key)
        if c:
            u = extract_first_url(row[c])
            if u:
                return u
    return ""


def is_video_url(url: str) -> bool:
    u = url.lower()
    # เงื่อนไขเบื้องต้น (แล้วแต่ CSV)
    return any(u.endswith(ext) for ext in (".mp4", ".mov", ".m4v", ".webm"))


def fetch_csv(url: str) -> pd.DataFrame:
    print("Fetching CSV...")
    r = SESSION.get(url, timeout=25)
    print("CSV status:", r.status_code)
    if r.status_code >= 400:
        die(f"CSV download failed status={r.status_code} (check SHOPEE_CSV_URL)")
    content = r.content
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    df = pd.read_csv(io.StringIO(text))
    if df.empty:
        die("CSV is empty")
    return df


def calc_discount_pct(price_now: float | None, price_old: float | None, discount_pct_field: float | None) -> float | None:
    # ถ้า CSV มี % อยู่แล้ว ใช้อันนั้นก่อน
    if discount_pct_field is not None:
        # ถ้าเป็น "20%" จะถูก to_float ดึง 20
        return float(discount_pct_field)

    if price_now is None or price_old is None:
        return None
    if price_old <= 0:
        return None
    return max(0.0, (price_old - price_now) * 100.0 / price_old)


def build_caption(title: str, price: str, url: str, rating: float | None, sold: int | None, discount_pct: float | None, coupon: str) -> str:
    title = normalize_text(title)
    price = normalize_text(price)
    url = normalize_text(url)
    coupon = normalize_text(coupon)

    lines = []
    # Hook + Brand
    lines.append(f"🏠⚡ {BRAND}")
    lines.append(f"📌 {title}")

    # ไฮไลต์ดีล
    if discount_pct is not None and discount_pct > 0:
        lines.append(f"🔥 ลด {discount_pct:.0f}%")

    if price:
        lines.append(f"💰 ราคา: {price}")

    if rating is not None:
        lines.append(f"⭐ เรตติ้ง: {rating:.1f}/5")

    if sold is not None:
        lines.append(f"📈 ขายแล้ว: {sold:,}")

    if coupon:
        lines.append(f"🎟 โค้ด/คูปอง: {coupon}")

    if url:
        lines.append(f"🔗 สั่งซื้อ: {url}")

    lines.append(HASHTAGS)

    return "\n".join([x for x in lines if x])


def fb_post_photo(page_id: str, access_token: str, image_url: str, caption: str) -> dict:
    endpoint = f"https://graph.facebook.com/v19.0/{page_id}/photos"
    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": access_token,
        "published": "true",
    }
    r = SESSION.post(endpoint, data=payload,
