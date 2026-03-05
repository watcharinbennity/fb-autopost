# app.py — V38 ULTRA (BEN Home & Electrical)
# - Facebook Graph API v25.0
# - Shopee CSV streaming (affiliate feed)
# - Focus category for BEN Home & Electrical (keyword allow/block)
# - Images only (no video) by default
# - Remove "sold" line from caption
# - Catch-up schedule: if past slot not posted yet -> post it
# - First run auto-post 1 post

import os
import io
import csv
import json
import time
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, quote

import requests


# =========================
# CONFIG
# =========================
APP_VERSION = "V38 ULTRA"
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = os.getenv("STATE_FILE", "state.json")
MAX_STATE_ITEMS = int(os.getenv("MAX_STATE_ITEMS", "9000"))

# Page + CSV
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

# Shopee Affiliate (ของคุณ)
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()

# Schedule (Bangkok)
TZ_BKK = timezone(timedelta(hours=7))
SLOTS_BKK = os.getenv("SLOTS_BKK", "09:00,12:00,15:30,18:30,21:00").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))  # ต่อ 1 run โพสต์ได้กี่โพสต์
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

# Selection filters (ปรับได้)
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

# Media (รูปเท่านั้นตามเงื่อนไขเพจ)
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
PREFER_VIDEO = os.getenv("PREFER_VIDEO", "0").strip().lower() in ("1", "true", "yes")  # default OFF
VIDEO_MAX_MB = int(os.getenv("VIDEO_MAX_MB", "80"))  # เผื่ออนาคต

# CSV streaming
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "220"))

# Timeouts
CSV_CONNECT_TIMEOUT = 25
CSV_READ_TIMEOUT = 180
IMG_CONNECT_TIMEOUT = 20
IMG_READ_TIMEOUT = 80
GRAPH_CONNECT_TIMEOUT = 20
GRAPH_READ_TIMEOUT = 120

# Caption
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #DIY #ShopeeAffiliate"
).strip()

# เพจ BEN Home & Electrical: เน้นหมวด/คีย์เวิร์ดแนวบ้าน-ช่าง-ไฟฟ้า
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|สายไฟ|เบรกเกอร์|หลอดไฟ|โคม|สวิตช์|เต้ารับ|พาวเวอร์ปลั๊ก|รางปลั๊ก|ปลั๊กพ่วง|หม้อแปลง|อะแดปเตอร์|หัวชาร์จ|สายชาร์จ|USB|Type-?C|PD|QC|ชาร์จเร็ว|อินเวอร์เตอร์|โซล่า|solar|แบตเตอรี่|LiFePO4|UPS|มิเตอร์|วัดไฟ|เทสเตอร์|มัลติมิเตอร์|เครื่องมือ|สว่าน|ไขควง|ค้อน|ประแจ|คีม|เลื่อย|บล็อก|หัวบล็อก|ชุดเครื่องมือ|กาวซิลิโคน|เทปพันสายไฟ|เทปกาว|เคเบิลไทร์|ไฟฉาย|โคมไฟ|สปอร์ตไลท์|พัดลม|สวิตช์อัจฉริยะ|ปลั๊กอัจฉริยะ|smart)"
).strip()

# บล็อคของที่ไม่ตรงเพจ
BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(เสื้อผ้า|แฟชั่น|ชุดนอน|ผ้าห่ม|หมอน|ตุ๊กตา|ของเล่น|อาหาร|ขนม|เครื่องสำอาง|ครีม|ย้อมผม|สีย้อมผม|สกินแคร์|บุหรี่|แอลกอฮอล์|ไวน์|เบียร์|กัญชา|CBD|ยา|อาหารเสริม)"
).strip()

# เพิ่มตัวกัน “หมวดหลุด” แบบแรง ๆ (ถ้า category มีคำพวกนี้ให้ตัดทิ้ง)
BLOCK_CATEGORIES = os.getenv(
    "BLOCK_CATEGORIES",
    r"(Beauty|Fashion|Toys|Groceries|Health|Women|Men|Baby|Mom|Food|Beverage|Pets|Stationery)"
).strip()


def die(msg: str, code: int = 1):
    print("FATAL:", msg)
    raise SystemExit(code)


if not PAGE_ID:
    die("Missing env: PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    die("Missing env: PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    die("Missing env: SHOPEE_CSV_URL")


# =========================
# TIME / STATE
# =========================
def now_bkk() -> datetime:
    return datetime.now(TZ_BKK)


def parse_slot_today_bkk(now: datetime, hhmm: str) -> datetime:
    hh, mm = hhmm.split(":")
    return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)


def load_state() -> dict:
    base = {
        "used_urls": [],
        "posted_slots": {},      # {"YYYY-MM-DD": ["09:00", ...]}
        "posted_at": {},         # {"product_url": "ISO_DATETIME"}
        "first_run_done": False
    }
    if not os.path.exists(STATE_FILE):
        return base
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
        if not isinstance(s, dict):
            return base
        s.setdefault("used_urls", [])
        s.setdefault("posted_slots", {})
        s.setdefault("posted_at", {})
        s.setdefault("first_run_done", True)  # ถ้ามีไฟล์แล้วถือว่าเคยรัน
        if not isinstance(s["used_urls"], list):
            s["used_urls"] = []
        if not isinstance(s["posted_slots"], dict):
            s["posted_slots"] = {}
        if not isinstance(s["posted_at"], dict):
            s["posted_at"] = {}
        return s
    except Exception:
        return base


def save_state(state: dict) -> None:
    used = state.get("used_urls", [])
    if len(used) > MAX_STATE_ITEMS:
        state["used_urls"] = used[-MAX_STATE_ITEMS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def mark_slot_posted(state: dict, now: datetime, slot_hhmm: str) -> None:
    key = now.strftime("%Y-%m-%d")
    state.setdefault("posted_slots", {})
    state["posted_slots"].setdefault(key, [])
    if slot_hhmm not in state["posted_slots"][key]:
        state["posted_slots"][key].append(slot_hhmm)


def due_slots_today(state: dict, now: datetime) -> List[str]:
    """ถ้าเลยเวลา slot แล้ว แต่ยังไม่ได้โพส -> ถือว่า due"""
    key = now.strftime("%Y-%m-%d")
    posted = set(state.get("posted_slots", {}).get(key, []))
    due = []
    for hhmm in SLOTS_BKK:
        t = parse_slot_today_bkk(now, hhmm)
        if now >= t and hhmm not in posted:
            due.append(hhmm)
    return due


# =========================
# HTTP / GRAPH
# =========================
def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=headers, stream=stream, allow_redirects=True)
    r.raise_for_status()
    return r


def graph_post(path: str, data=None, files=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    r = requests.post(
        url,
        params=params,
        data=data,
        files=files,
        timeout=(GRAPH_CONNECT_TIMEOUT, GRAPH_READ_TIMEOUT),
    )
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise

    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: {js}")
    return js


# =========================
# PRODUCT
# =========================
@dataclass
class Product:
    title: str
    product_link: str
    product_short_link: Optional[str]
    images: List[str]
    price: Optional[float]
    sale_price: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    category_text: str
    raw: Dict


def fnum(x) -> Optional[float]:
    try:
        if x is None:
            return None
        s = str(x).strip().replace(",", "")
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def safe_str(x) -> str:
    return ("" if x is None else str(x)).strip()


def extract_images(row: Dict) -> List[str]:
    # รองรับทั้ง image_link และ image_link_1..10 และ additional_image_link
    imgs = []
    for i in range(1, 11):
        v = safe_str(row.get(f"image_link_{i}", ""))
        if v:
            imgs.append(v)

    v0 = safe_str(row.get("image_link", ""))
    if v0:
        imgs.append(v0)

    v_add = safe_str(row.get("additional_image_link", ""))
    if v_add:
        # บางไฟล์จะเป็น URL เดียว / หรือคั่นด้วย , หรือ |
        parts = re.split(r"[,\|]\s*", v_add)
        for p in parts:
            p = p.strip()
            if p:
                imgs.append(p)

    # unique keep order
    seen = set()
    out = []
    for u in imgs:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def get_row_link(row: Dict) -> Tuple[str, Optional[str]]:
    """
    ฟีด Shopee มักมี:
    - product_link
    - product_short link  (มีช่องว่างในชื่อคอลัมน์จริง)
    - url / product_url (เผื่อบางไฟล์)
    """
    product_link = (
        safe_str(row.get("product_link"))
        or safe_str(row.get("product url"))
        or safe_str(row.get("product_url"))
        or safe_str(row.get("url"))
        or safe_str(row.get("link"))
    )

    # คอลัมน์นี้ในตัวอย่างคุณชื่อ "product_short link" (มีช่องว่าง)
    product_short_link = safe_str(row.get("product_short link")) or safe_str(row.get("product_short_link"))
    if product_short_link == "":
        product_short_link = None

    return product_link, product_short_link


def normalize_row(row: Dict) -> Product:
    title = safe_str(row.get("title")) or safe_str(row.get("name")) or safe_str(row.get("item_name"))
    product_link, product_short_link = get_row_link(row)
    images = extract_images(row)

    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))
    discount_pct = fnum(row.get("discount_percentage"))

    if discount_pct is None and price and sale_price and price > 0 and sale_price < price:
        discount_pct = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))

    cat1 = safe_str(row.get("global_category1"))
    cat2 = safe_str(row.get("global_category2"))
    cat3 = safe_str(row.get("global_category3"))
    category_text = " | ".join([c for c in [cat1, cat2, cat3] if c])

    return Product(
        title=title,
        product_link=product_link,
        product_short_link=product_short_link,
        images=images,
        price=price,
        sale_price=sale_price,
        discount_pct=discount_pct,
        rating=rating,
        category_text=category_text,
        raw=row
    )


def effective_price(p: Product) -> Optional[float]:
    return p.sale_price if p.sale_price is not None else p.price


def is_repost_allowed(state: dict, p: Product, now: datetime) -> bool:
    """
    ป้องกันโพสซ้ำเร็วเกินไป: URL เดิมให้เว้น REPOST_AFTER_DAYS วัน
    """
    key = p.product_link or p.product_short_link or ""
    posted_at = state.get("posted_at", {}).get(key)
    if not posted_at:
        return True
    try:
        dt = datetime.fromisoformat(posted_at)
        return (now - dt) >= timedelta(days=REPOST_AFTER_DAYS)
    except Exception:
        return True


def keyword_ok(p: Product) -> bool:
    text = f"{p.title} {p.category_text}".lower()

    # บล็อกหมวดหลุดก่อน
    if BLOCK_CATEGORIES:
        if re.search(BLOCK_CATEGORIES, p.category_text, flags=re.IGNORECASE):
            return False

    # บล็อกคำต้องห้าม
    if BLOCK_KEYWORDS:
        if re.search(BLOCK_KEYWORDS, text, flags=re.IGNORECASE):
            return False

    # ต้องมีคำที่เข้ากลุ่มเพจ
    if ALLOW_KEYWORDS:
        if not re.search(ALLOW_KEYWORDS, text, flags=re.IGNORECASE):
            return False

    return True


def product_pass(p: Product, state: dict, now: datetime) -> bool:
    if not p.title:
        return False
    if not (p.product_link or p.product_short_link):
        return False
    if len(p.images) < 1:
        return False  # เพจนี้ต้องมีรูปเท่านั้น

    ep = effective_price(p)
    if ep is None:
        return False
    if not (PRICE_MIN <= ep <= PRICE_MAX):
        return False

    if p.rating is not None and p.rating < MIN_RATING:
        return False
    if p.discount_pct is not None and p.discount_pct < MIN_DISCOUNT_PCT:
        return False

    if not keyword_ok(p):
        return False

    if not is_repost_allowed(state, p, now):
        return False

    return True


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def score_product(p: Product, now: datetime) -> float:
    """
    ให้คะแนนเน้น:
    - rating (หลัก)
    - discount
    - ความเป็นหมวดช่าง/ไฟฟ้า: มีคำหลักหลายคำ -> boost
    """
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    ep = effective_price(p) or 9999.0

    r_score = clamp((r - 4.0) / 1.0, 0, 1)
    d_score = clamp(d / 70.0, 0, 1)

    # ยิ่งราคาใกล้ช่วงกลางๆจะดี (ไม่ถูกเกิน/แพงเกิน)
    mid = (PRICE_MIN + PRICE_MAX) / 2.0
    dist = abs(ep - mid) / max(1.0, (PRICE_MAX - PRICE_MIN))
    price_score = 1.0 - clamp(dist, 0, 1) * 0.12

    # keyword boost: ถ้ามีคำช่าง/ไฟฟ้าหนักๆหลายคำ -> boost
    boost_words = ["ไฟฟ้า", "ปลั๊ก", "สายไฟ", "เบรกเกอร์", "หลอดไฟ", "สวิตช์", "เต้ารับ",
                   "สว่าน", "ไขควง", "ประแจ", "คีม", "มัลติมิเตอร์", "เทสเตอร์", "โซล่า", "อินเวอร์เตอร์"]
    text = f"{p.title} {p.category_text}"
    hits = sum(1 for w in boost_words if re.search(re.escape(w), text, flags=re.IGNORECASE))
    kw_boost = 1.0 + min(0.18, hits * 0.03)

    base = (0.58 * r_score) + (0.42 * d_score)
    base *= price_score
    base *= kw_boost
    base *= random.uniform(0.97, 1.03)
    return base


# =========================
# AFFILIATE LINK (ชัวร์)
# =========================
def build_affiliate_link(p: Product) -> str:
    """
    ทำให้เป็นลิงก์นายหน้าเสมอ:
    - ถ้ามี product_short_link (shope.ee/an_redir?origin_link=...) ก็ใช้เป็นฐานได้
    - ไม่ว่าจะฐานอะไร สุดท้ายเราจะ wrap เป็น shopee.ee/an_redir พร้อมพารามิเตอร์นายหน้า
    """
    base = p.product_link or ""
    # ถ้า short link มี origin_link อยู่แล้ว ให้ใช้ short link เป็น base ได้
    if p.product_short_link:
        base = p.product_short_link

    # ถ้า base เป็น shope.ee/an_redir และมี origin_link อยู่แล้ว เราจะคง origin_link เดิม
    parsed = urlparse(base)
    qs = dict(parse_qsl(parsed.query, keep_blank_values=True))

    origin = qs.get("origin_link")
    if origin:
        origin_link = origin
    else:
        # ถ้าเป็น shopee.co.th/product/... ก็ใช้ตัวนั้นเป็น origin_link
        origin_link = base

    # สร้าง an_redir ใหม่แบบมาตรฐานของเรา
    redir_base = "https://shopee.ee/an_redir"
    params = {
        "origin_link": origin_link,
        "affiliate_id": AFFILIATE_ID,
        "utm_source": AFF_UTM_SOURCE,
        "afftag": AFF_TAG,
    }
    return f"{redir_base}?{urlencode(params, doseq=True)}"


# =========================
# CSV STREAMING
# =========================
def stream_top_products(csv_url: str, state: dict, now: datetime) -> List[Tuple[float, Product]]:
    print("INFO: Streaming Shopee CSV ...")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,application/octet-stream,*/*",
        "Connection": "keep-alive",
    }
    r = http_get(csv_url, timeout=(CSV_CONNECT_TIMEOUT, CSV_READ_TIMEOUT), headers=headers, stream=True)
    r.raw.decode_content = True

    text_stream = io.TextIOWrapper(r.raw, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.DictReader(text_stream)

    top: List[Tuple[float, Product]] = []
    rows_seen = 0
    kept = 0

    for row in reader:
        rows_seen += 1
        if rows_seen > STREAM_MAX_ROWS:
            print(f"INFO: Stop at STREAM_MAX_ROWS={STREAM_MAX_ROWS}")
            break

        p = normalize_row(row)
        if not product_pass(p, state, now):
            continue

        sc = score_product(p, now)
        kept += 1

        if len(top) < TOPK_POOL:
            top.append((sc, p))
        else:
            worst_i = min(range(len(top)), key=lambda i: top[i][0])
            if sc > top[worst_i][0]:
                top[worst_i] = (sc, p)

        if rows_seen % 50000 == 0:
            print(f"INFO: rows={rows_seen} kept={kept} top_pool={len(top)}")

    print(f"INFO: Done rows={rows_seen} kept={kept} top_pool={len(top)}")
    if not top:
        die("No usable products found for BEN Home & Electrical. (ลองปรับ ALLOW_KEYWORDS/MIN_RATING/MIN_DISCOUNT_PCT)")
    return top


def weighted_choice(items: List[Tuple[float, Product]]) -> Product:
    total = sum(max(0.001, sc) for sc, _ in items)
    pick = random.uniform(0, total)
    upto = 0.0
    for sc, p in items:
        upto += max(0.001, sc)
        if upto >= pick:
            return p
    return items[-1][1]


def pick_product(top_items: List[Tuple[float, Product]], state: dict) -> Product:
    used = set(state.get("used_urls", []))
    # ใช้ key เป็น affiliate link เพื่อไม่วนซ้ำ
    fresh = [(sc, p) for sc, p in top_items if build_affiliate_link(p) not in used]
    pool = fresh if fresh else top_items
    chosen = weighted_choice(pool)

    state.setdefault("used_urls", []).append(build_affiliate_link(chosen))
    # trim
    if len(state["used_urls"]) > MAX_STATE_ITEMS:
        state["used_urls"] = state["used_urls"][-MAX_STATE_ITEMS:]
    return chosen


# =========================
# CAPTION (ตัด “ขายแล้ว” ออก)
# =========================
HOOKS = [
    "🔥 ของมันต้องมีติดบ้าน!",
    "⚡ สายช่างต้องมี ช่วยให้งานไวขึ้นจริง",
    "✅ คัดตัวฮิตรีวิวดี ราคาโดน",
    "🏡 ของใช้ในบ้านที่ทำให้ชีวิตง่ายขึ้น",
    "🎯 เลือกให้แล้ว “คุ้มสุด” สำหรับงบนี้",
]

BENEFITS = [
    "ใช้งานง่าย มือใหม่ก็ทำเองได้",
    "ประหยัดเวลา งานเสร็จไวขึ้น",
    "คุ้มราคา คุณภาพเกินตัว",
    "เหมาะกับงานบ้าน/งานช่างทั่วไป",
    "รีวิวดี คุ้มค่าตัวจริง",
]

CTA = [
    "กดลิงก์ดูโปร/โค้ดส่วนลดตอนนี้เลย 👇",
    "ดูรีวิวจริง + ราคาล่าสุดในลิงก์ได้เลย ✅",
    "สนใจทักแชทได้ครับ เดี๋ยวช่วยเลือกให้ 💬",
]


def fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{x:,.0f}"


def fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{x:.0f}%"


def build_caption(p: Product, now: datetime) -> str:
    hook = random.choice(HOOKS)
    benefit = random.choice(BENEFITS)
    cta = random.choice(CTA)

    ep = effective_price(p)
    if p.sale_price is not None and p.price is not None and p.sale_price < p.price:
        price_line = f"💸 โปรวันนี้: {fmt_money(p.sale_price)} บาท (ปกติ {fmt_money(p.price)} | ลด {fmt_pct(p.discount_pct)})"
    else:
        price_line = f"💸 ราคา: {fmt_money(ep)} บาท | ลด {fmt_pct(p.discount_pct)}"

    rating_line = f"⭐ เรตติ้ง: {p.rating:.1f}/5" if p.rating is not None else "⭐ เรตติ้ง: -"

    aff_link = build_affiliate_link(p)

    parts = [
        f"🏠⚡ {BRAND}",
        hook,
        "",
        f"🛒 {p.title}",
        "",
        price_line,
        rating_line,
        "",
        f"✅ จุดเด่น: {benefit}",
        "✅ ดูรูป/รีวิวจริงก่อนซื้อได้",
        "",
        "👉 ลิงก์นายหน้า:",
        aff_link,
        "",
        cta,
        "",
        HASHTAGS,
    ]

    out = []
    for s in parts:
        if s == "" and (not out or out[-1] == ""):
            continue
        out.append(s)
    return "\n".join(out).strip()


# =========================
# FACEBOOK: IMAGE POST (Multi image)
# =========================
def download_image_bytes(url: str) -> bytes:
    r = http_get(url, timeout=(IMG_CONNECT_TIMEOUT, IMG_READ_TIMEOUT), stream=True,
                 headers={"User-Agent": "Mozilla/5.0"})
    return r.content


def upload_unpublished_photo(page_id: str, image_bytes: bytes) -> str:
    files = {"source": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"published": "false"}
    js = graph_post(f"/{page_id}/photos", data=data, files=files)
    return js["id"]


def create_feed_post_with_media(page_id: str, message: str, media_fbids: List[str]) -> str:
    data = {"message": message}
    for i, mid in en
