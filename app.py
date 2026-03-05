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
from urllib.parse import quote, urlparse, parse_qsl, urlencode, urlunparse

import requests

# ============================================================
# V30 ULTRA FIX (BKK schedule + catch-up + first-run 1 post)
# - Graph v25.0
# - Stream Shopee CSV
# - Build affiliate "shopee.ee/an_redir" links (affiliate_id, utm_source, afftag)
# - Page-target keywords (BEN Home & Electrical)
# - Caption: REMOVE "sold/ขายแล้ว" line
# - Robust state + repost after days
# ============================================================

# -------------------------
# CONFIG / ENV
# -------------------------
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = os.getenv("STATE_FILE", "state.json")
MAX_STATE_ITEMS = int(os.getenv("MAX_STATE_ITEMS", "9000"))

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

# Shopee Affiliate (หน้านาย)
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()

# Bangkok timezone
TZ_BKK = timezone(timedelta(hours=7))

# Posting schedule in BKK (แก้ได้ใน ENV: SLOTS_BKK="09:00,12:00,18:30,21:00")
SLOTS_BKK = os.getenv("SLOTS_BKK", "09:00,12:00,18:30,21:00").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))  # ต่อ 1 run โพสต์กี่โพสต์
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

# Filters (ปรับได้)
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))
MIN_SOLD = int(os.getenv("MIN_SOLD", "0"))  # ใช้เป็นตัวคัดสินค้าได้ แต่ "ไม่แสดง" ในแคปชั่น
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

# CSV streaming
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "220"))

# Media
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
PREFER_VIDEO = os.getenv("PREFER_VIDEO", "1").strip().lower() in ("1", "true", "yes")
VIDEO_MAX_MB = int(os.getenv("VIDEO_MAX_MB", "80"))

# Caption
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ShopeeAffiliate"
).strip()

# เน้นหมวดให้ตรงเพจ (กรองด้วยคีย์เวิร์ด)
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|สายไฟ|เบรกเกอร์|หลอดไฟ|โคม|สวิตช์|มิเตอร์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|ชาร์จ|พาวเวอร์แบงค์|อะแดปเตอร์|หัวชาร์จ|ปลั๊กพ่วง|เครื่องมือ|สว่าน|ค้อน|ประแจ|คีม|ไขควง|ตลับเมตร|เครื่องมือช่าง|งานช่าง|ซ่อม|DIY|บ้าน|กาว|เทปพันสายไฟ|มัลติมิเตอร์|ปืนกาว|บัดกรี|หัวแร้ง)"
).strip()

BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(เครื่องสำอาง|อาหารเสริม|บุหรี่|แอลกอฮอล์|ชุดชั้นใน|ย้อมผม|วิกผม|ครีม|น้ำหอม|เสื้อผ้า|กระโปรง|กางเกง|เดรส|รองเท้าแฟชั่น|ของเล่นเด็ก|เบาะ|ผ้าปู|หมอน)"
).strip()

# Timeouts
CSV_CONNECT_TIMEOUT = 25
CSV_READ_TIMEOUT = 180
IMG_CONNECT_TIMEOUT = 20
IMG_READ_TIMEOUT = 80
VID_CONNECT_TIMEOUT = 20
VID_READ_TIMEOUT = 120
GRAPH_CONNECT_TIMEOUT = 20
GRAPH_READ_TIMEOUT = 80

# -------------------------
# Helpers
# -------------------------
def die(msg: str, code: int = 1):
    print("FATAL:", msg)
    raise SystemExit(code)

if not PAGE_ID:
    die("Missing env: PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    die("Missing env: PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    die("Missing env: SHOPEE_CSV_URL")

ALLOW_PAT = re.compile(ALLOW_KEYWORDS, flags=re.IGNORECASE) if ALLOW_KEYWORDS else None
BLOCK_PAT = re.compile(BLOCK_KEYWORDS, flags=re.IGNORECASE) if BLOCK_KEYWORDS else None

def now_bkk() -> datetime:
    return datetime.now(TZ_BKK)

def parse_slot_today_bkk(now: datetime, hhmm: str) -> datetime:
    hh, mm = hhmm.split(":")
    return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)

def load_state() -> dict:
    base = {
        "used_urls": [],
        "posted_slots": {},     # {"YYYY-MM-DD": ["12:00", ...]}
        "posted_at": {},        # {"url": "ISO"}
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
        s.setdefault("first_run_done", True)  # ถ้ามี state แล้วถือว่ารันมาแล้ว
        if not isinstance(s["used_urls"], list):
            s["used_urls"] = []
        if not isinstance(s["posted_slots"], dict):
            s["posted_slots"] = {}
        if not isinstance(s["posted_at"], dict):
            s["posted_at"] = {}
        if not isinstance(s["first_run_done"], bool):
            s["first_run_done"] = True
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
    """ถ้าเลยเวลา slot แล้วแต่ยังไม่โพสต์ -> ถือว่า due"""
    key = now.strftime("%Y-%m-%d")
    posted = set(state.get("posted_slots", {}).get(key, []))
    due = []
    for hhmm in SLOTS_BKK:
        t = parse_slot_today_bkk(now, hhmm)
        if now >= t and hhmm not in posted:
            due.append(hhmm)
    return due

# -------------------------
# HTTP / GRAPH
# -------------------------
def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=headers, stream=stream, allow_redirects=True)
    r.raise_for_status()
    return r

def graph_post(path: str, data=None, files=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    r = requests.post(
        url, params=params, data=data, files=files,
        timeout=(GRAPH_CONNECT_TIMEOUT, GRAPH_READ_TIMEOUT)
    )
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: {js}")
    return js

# -------------------------
# Product model
# -------------------------
@dataclass
class Product:
    title: str
    origin_url: str          # original product url (shopee.co.th/product/.. or others)
    affiliate_url: str       # final affiliate url (shopee.ee/an_redir...)
    images: List[str]
    video_url: Optional[str]
    price: Optional[float]
    sale_price: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    sold: Optional[int]      # used in scoring/filter only
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

def fint(x) -> Optional[int]:
    try:
        if x is None:
            return None
        s = str(x).strip().replace(",", "")
        if s == "":
            return None
        return int(float(s))
    except Exception:
        return None

def effective_price(p: Product) -> Optional[float]:
    return p.sale_price if p.sale_price is not None else p.price

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def text_ok_for_page(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    t = f"{title} {cat1} {cat2} {cat3}".strip()
    if BLOCK_PAT and BLOCK_PAT.search(t):
        return False
    if ALLOW_PAT:
        return bool(ALLOW_PAT.search(t))
    return True

# -------------------------
# Shopee link handling (Affiliate)
# -------------------------
def build_affiliate_url(origin: str) -> str:
    """
    Always output:
    https://shopee.ee/an_redir?origin_link=<urlencoded(origin)>&affiliate_id=...&utm_source=...&afftag=...
    If origin already is shopee.ee/an_redir -> replace params.
    """
    origin = (origin or "").strip()
    if not origin:
        return ""

    # If already an_redir -> keep its origin_link as base
    try:
        u = urlparse(origin)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        if "shopee.ee" in (u.netloc or "") and u.path.startswith("/an_redir"):
            base_origin = q.get("origin_link", "")
            if base_origin:
                origin_link = base_origin
            else:
                # fallback: use the whole origin
                origin_link = origin
        else:
            origin_link = origin
    except Exception:
        origin_link = origin

    params = {
        "origin_link": origin_link,
        "affiliate_id": AFFILIATE_ID,
        "utm_source": AFF_UTM_SOURCE,
        "afftag": AFF_TAG,
    }

    # build final
    return "https://shopee.ee/an_redir?" + urlencode(params, doseq=False, safe=":/%?=&")

# -------------------------
# Extract images/video from your CSV columns
# (your real headers: image_link, image_link_3..10 etc)
# -------------------------
def extract_images(row: Dict) -> List[str]:
    imgs = []
    for i in range(1, 11):
        v = str(row.get(f"image_link_{i}", "")).strip()
        if v:
            imgs.append(v)
    v0 = str(row.get("image_link", "")).strip()
    if v0:
        imgs.append(v0)

    # additional_image_link sometimes contains more
    addi = str(row.get("additional_image_link", "")).strip()
    if addi.startswith("http"):
        imgs.append(addi)

    # unique keep order
    seen = set()
    out = []
    for u in imgs:
        u = u.strip()
        if u and u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_video(row: Dict) -> Optional[str]:
    for k in ["video_url", "video_link", "video", "reel_video", "reels_video", "short_video"]:
        v = str(row.get(k, "")).strip()
        if v.startswith("http"):
            return v
    return None

def normalize_row(row: Dict) -> Optional[Product]:
    title = (row.get("title") or row.get("name") or "").strip()
    product_link = (row.get("product_link") or row.get("url") or row.get("link") or "").strip()
    short_link = (row.get("product_short link") or row.get("product_short_link") or "").strip()

    origin_url = product_link or short_link
    if not title or not origin_url:
        return None

    images = extract_images(row)
    video_url = extract_video(row)

    # price fields from your example:
    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))
    discount_pct = fnum(row.get("discount_percentage"))

    # derive discount if missing
    if discount_pct is None and price and sale_price and price > 0 and sale_price <= price:
        discount_pct = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))
    sold = fint(row.get("item_sold")) or fint(row.get("historical_sold")) or fint(row.get("sold"))

    cat1 = str(row.get("global_category1", "")).strip()
    cat2 = str(row.get("global_category2", "")).strip()
    cat3 = str(row.get("global_category3", "")).strip()

    # page targeting
    if not text_ok_for_page(title, cat1, cat2, cat3):
        return None

    aff = build_affiliate_url(origin_url)

    return Product(
        title=title,
        origin_url=origin_url,
        affiliate_url=aff,
        images=images,
        video_url=video_url,
        price=price,
        sale_price=sale_price,
        discount_pct=discount_pct,
        rating=rating,
        sold=sold,
        raw=row
    )

def product_pass(p: Product) -> bool:
    if not p.title or not p.origin_url or not p.affiliate_url:
        return False

    # ต้องมีสื่ออย่างน้อย 1 (รูปหรือวิดีโอ)
    if len(p.images) < 1 and not p.video_url:
        return False

    ep = effective_price(p)
    if ep is None:
        return False
    if not (PRICE_MIN <= ep <= PRICE_MAX):
        return False

    if p.rating is not None and p.rating < MIN_RATING:
        return False
    if p.discount_pct is not None and p.discount_pct < MIN_DISCOUNT_PCT:
        return False
    if p.sold is not None and p.sold < MIN_SOLD:
        return False

    return True

def score_product(p: Product, now: datetime) -> float:
    """
    เน้น: เรตติ้ง + ส่วนลด + (sold ใช้ช่วยเลือก แต่ไม่โชว์)
    """
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    s = p.sold if p.sold is not None else 0
    ep = effective_price(p) or 999.0

    r_score = clamp((r - 4.0) / 1.0, 0, 1)
    d_score = clamp(d / 70.0, 0, 1)
    s_score = clamp((s ** 0.5) / 70.0, 0, 1)
    price_score = 1.0 - clamp((ep - PRICE_MIN) / max(1.0, (PRICE_MAX - PRICE_MIN)), 0, 1) * 0.15

    base = (0.50 * r_score) + (0.35 * d_score) + (0.15 * s_score)
    base *= price_score

    if p.video_url:
        base *= 1.06

    base *= random.uniform(0.97, 1.03)
    return base

# -------------------------
# Stream CSV (safe)
# -------------------------
def stream_top_products(csv_url: str, now: datetime) -> List[Tuple[float, Product]]:
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
        if not p:
            continue
        if not product_pass(p):
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
        raise SystemExit("ERROR: No usable products found. ปรับ MIN_* / PRICE_* / keywords ได้")
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

def pick_product(top_items: List[Tuple[float, Product]], state: dict, now: datetime) -> Product:
    used = set(state.get("used_urls", []))

    # repost policy
    posted_at: Dict[str, str] = state.get("posted_at", {})
    cutoff = now - timedelta(days=REPOST_AFTER_DAYS)

    fresh = []
    for sc, p in top_items:
        if p.origin_url in used:
            continue

        last_iso = posted_at.get(p.origin_url) or posted_at.get(p.affiliate_url)
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=TZ_BKK)
                if last_dt > cutoff:
                    continue
            except Exception:
                pass

        fresh.append((sc, p))

    pool = fresh if fresh else top_items
    chosen = weighted_choice(pool)

    state.setdefault("used_urls", []).append(chosen.origin_url)
    return chosen

# -------------------------
# Caption (NO SOLD LINE)
# -------------------------
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
    "เหมาะกับใช้ในบ้าน/งานช่างทั่วไป",
    "รีวิวดี น่าลองมาก",
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

    tags = HASHTAGS

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
        f"👉 {p.affiliate_url}",
        "",
        cta,
        "",
        tags,
    ]

    out = []
    for s in parts:
        if s == "" and (not out or out[-1] == ""):
            continue
        out.append(s)
    return "\n".join(out).strip()

# -------------------------
# Facebook posting
# -------------------------
def download_image_bytes(url: str) -> bytes:
    r = http_get(url, timeout=(IMG_CONNECT_TIMEOUT, IMG_READ_TIMEOUT),
                 stream=True, headers={"User-Agent": "Mozilla/5.0"})
    return r.content

def upload_unpublished_photo(page_id: str, image_bytes: bytes) -> str:
    files = {"source": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"published": "false"}
    js = graph_post(f"/{page_id}/photos", data=data, files=files)
    return js["id"]

def create_feed_post_with_media(page_id: str, message: str, media_fbids: List[str]) -> str:
    data = {"message": message}
    for i, mid in enumerate(media_fbids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    js = graph_post(f"/{page_id}/feed", data=data)
    return js["id"]

def post_images(p: Product, caption: str) -> str:
    imgs = p.images[:POST_IMAGES_COUNT]
    if not imgs:
        raise RuntimeError("No images to post")

    media_ids = []
    for u in imgs:
        img_bytes = download_image_bytes(u)
        mid = upload_unpublished_photo(PAGE_ID, img_bytes)
        media_ids.append(mid)
        time.sleep(1.1)

    post_id = create_feed_post_with_media(PAGE_ID, caption, media_ids)
    return post_id

def head_size_mb(url: str) -> Optional[float]:
    try:
        r = requests.head(url, timeout=(VID_CONNECT_TIMEOUT, 20), allow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code >= 400:
            return None
        cl = r.headers.get("content-length")
        if not cl:
            return None
        return int(cl) / (1024 * 1024)
    except Exception:
        return None

def post_video_by_url(caption: str, video_url: str) -> str:
    mb = head_size_mb(video_url)
    if mb is not None and mb > VIDEO_MAX_MB:
        raise RuntimeError(f"Video too large: {mb:.1f}MB > {VIDEO_MAX_MB}MB")

    data = {"description": caption, "file_url": video_url}
    js = graph_post(f"/{PAGE_ID}/videos", data=data)
    return js.get("id", "unknown_video_id")

# -------------------------
# MAIN
# -------------------------
def main():
    now = now_bkk()
    print("==== V30 ULTRA FIX ====")
    print("INFO: Now(BKK) =", now.isoformat())
    print("INFO: Graph =", GRAPH_VERSION)
    print("INFO: Slots(BKK) =", ",".join(SLOTS_BKK))
    print("INFO: FirstRunPost1 =", FIRST_RUN_POST_1, "| ForcePost =", FORCE_POST)
    print("INFO: PreferVideo =", PREFER_VIDEO, "| ImagesCount =", POST_IMAGES_COUNT)
    print("INFO: Filters rating>=", MIN_RATING, "discount>=", MIN_DISCOUNT_PCT,
          "sold>=", MIN_SOLD, "price=[", PRICE_MIN, "..", PRICE_MAX, "]")
    print("INFO: REPOST_AFTER_DAYS =", REPOST_AFTER_DAYS)

    state = load_state()

    # Decide posting reason
    due = due_slots_today(state, now)

    # First run guarantee: post 1 even if not due
    if (not state.get("first_run_done", False)) and FIRST_RUN_POST_1:
        slot_used = "FIRST_RUN"
        print("INFO: First run detected -> will post 1 immediately.")
    elif due:
        slot_used = due[0]
        print("INFO: Due slots today (catch-up) =", due)
        print("INFO: Will post for slot =", slot_used)
    elif FORCE_POST:
        slot_used = "MANUAL"
        print("INFO: FORCE_POST enabled -> manual post")
    else:
        print("INFO: No due slot (already posted for past times). Exit. (Set FORCE_POST=1 to test)")
        return

    top_items = stream_top_products(SHOPEE_CSV_URL, now)

    posts_done = 0
    for i in range(POSTS_MAX_PER_RUN):
        p = pick_product(top_items, state, now)
        caption = build_caption(p, now)

        print("INFO: Picked:", p.title[:90], "| video?", bool(p.video_url), "| images:", len(p.images))

        try:
            if PREFER_VIDEO and p.video_url:
                vid_id = post_video_by_url(caption, p.video_url)
                print("OK: Posted VIDEO id =", vid_id)
                posted_key = p.origin_url
            else:
                post_id = post_images(p, caption)
                print("OK: Posted IMAGES feed id =", post_id)
                posted_key = p.origin_url
        except Exception as e:
            # fallback: if video fails -> try images
            if p.video_url:
                print("WARN: Video post failed -> fallback to images. Reason:", str(e))
                post_id = post_images(p, caption)
                print("OK: Posted IMAGES(feed) fallback id =", post_id)
                posted_key = p.origin_url
            else:
                raise

        # mark slot & record posted time
        if slot_used not in ("MANUAL",):
            mark_slot_posted(state, now, slot_used)

        state.setdefault("posted_at", {})
        state["posted_at"][posted_key] = now.isoformat()
        state["posted_at"][p.affiliate_url] = now.isoformat()

        posts_done += 1
        time.sleep(4)

    # mark first run done
    if not state.get("first_run_done", False):
        state["first_run_done"] = True

    save_state(state)
    print("INFO: Done. posts_done =", posts_done)

if __name__ == "__main__":
    main()
