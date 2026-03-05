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
from urllib.parse import urlparse, parse_qsl, urlencode, quote

import requests


# =========================
# CONFIG (V30 ULTRA)
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = os.getenv("STATE_FILE", "state.json")
MAX_STATE_ITEMS = int(os.getenv("MAX_STATE_ITEMS", "9000"))

# Page + CSV (required)
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

# Shopee Affiliate (default: your "หน้านาย")
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("SHOPEE_AFF_TAG", "BENHomeElectrical").strip()

# Schedule (Bangkok)
TZ_BKK = timezone(timedelta(hours=7))
SLOTS_BKK = os.getenv("SLOTS_BKK", "09:00,12:00,18:30,21:00").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))  # ต่อ 1 run โพสต์กี่โพสต์ (default 1)
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

# Selection filters
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))
MIN_SOLD = int(os.getenv("MIN_SOLD", "30"))  # ใช้คัดกรอง/ให้คะแนน แต่ "ไม่โชว์" ในแคปชั่น
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

# Media
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
PREFER_VIDEO = os.getenv("PREFER_VIDEO", "1").strip().lower() in ("1", "true", "yes")
VIDEO_MAX_MB = int(os.getenv("VIDEO_MAX_MB", "80"))

# CSV streaming
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "220"))

# Brand / Caption
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate"
).strip()

# Category/Keyword targeting for BEN Home & Electrical
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|พ่วง|ปลั๊กพ่วง|สายไฟ|เบรกเกอร์|RCBO|RCD|ตู้ไฟ|คอนซูมเมอร์|หลอดไฟ|โคม|สวิตช์|เต้ารับ|พัดลม|มิเตอร์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|Solar|ชาร์จ|Adapter|อะแดปเตอร์|หัวชาร์จ|Power|สายชาร์จ|USB|Type\-C|ปลั๊กแปลง|รีเลย์|ฟิวส์|คาปาซิเตอร์|เทปพันสาย|ท่อหด|ขั้วต่อ|คอนเนคเตอร์|ปลอกหุ้มสาย|เครื่องมือ|สว่าน|ไขควง|คีม|ประแจ|ค้อน|ตลับเมตร|เลื่อย|บัดกรี|หัวแร้ง|DIY|ซ่อม|บ้าน|ช่าง)"
).strip()

BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(เสื้อผ้า|กางเกง|ชุด|เดรส|กระโปรง|รองเท้า|กระเป๋า|เครื่องสำอาง|ครีม|สกินแคร์|อาหารเสริม|บุหรี่|แอลกอฮอล์|ของเล่น|ตุ๊กตา|Plush|Kawaii|ย้อมผม|ครีมย้อม|ปิดผมขาว|วิก|แฟลชกล้อง|Godox|Camera|เลนส์|ฟิล์ม|ผ้าปู|ผ้านวม|ปลอกหมอน)"
).strip()

# HTTP timeouts
CSV_CONNECT_TIMEOUT = 25
CSV_READ_TIMEOUT = 180
IMG_CONNECT_TIMEOUT = 20
IMG_READ_TIMEOUT = 80
VID_CONNECT_TIMEOUT = 20
VID_READ_TIMEOUT = 120
GRAPH_CONNECT_TIMEOUT = 20
GRAPH_READ_TIMEOUT = 80


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
        "posted_slots": {},      # {"YYYY-MM-DD": ["12:00","18:30"]}
        "posted_at": {},         # {"url": "iso_time"}
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
        s.setdefault("first_run_done", True)
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
    """ถ้าเลยเวลา slot แล้ว และวันนี้ slot นั้นยังไม่เคยโพสต์ -> ถือว่า 'due'"""
    key = now.strftime("%Y-%m-%d")
    posted = set(state.get("posted_slots", {}).get(key, []))
    due = []
    for hhmm in SLOTS_BKK:
        t = parse_slot_today_bkk(now, hhmm)
        if now >= t and hhmm not in posted:
            due.append(hhmm)
    return due


def recently_posted(state: dict, url: str, now: datetime) -> bool:
    """กันรีโพสต์ลิงก์เดิมใน N วัน"""
    posted_at = state.get("posted_at", {}).get(url)
    if not posted_at:
        return False
    try:
        ts = datetime.fromisoformat(posted_at)
    except Exception:
        return False
    return (now - ts) < timedelta(days=REPOST_AFTER_DAYS)


def mark_posted_url(state: dict, url: str, now: datetime) -> None:
    state.setdefault("posted_at", {})
    state["posted_at"][url] = now.isoformat()
    state.setdefault("used_urls", [])
    state["used_urls"].append(url)


# =========================
# HTTP / GRAPH
# =========================
def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=headers, stream=stream)
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
    origin_link: str
    affiliate_link: str
    images: List[str]
    video_url: Optional[str]
    price: Optional[float]
    sale_price: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    sold: Optional[int]
    categories_text: str
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


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def extract_images(row: Dict) -> List[str]:
    imgs = []
    for i in range(1, 11):
        v = str(row.get(f"image_link_{i}", "")).strip()
        if v:
            imgs.append(v)
    v0 = str(row.get("image_link", "")).strip()
    if v0:
        imgs.append(v0)

    # unique keep order
    seen = set()
    out = []
    for u in imgs:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def extract_video(row: Dict) -> Optional[str]:
    for k in ["video_url", "video_link", "video", "reel_video", "reels_video", "short_video"]:
        v = str(row.get(k, "")).strip()
        if v:
            return v
    return None


def categories_text(row: Dict) -> str:
    parts = [
        str(row.get("global_category1", "")).strip(),
        str(row.get("global_category2", "")).strip(),
        str(row.get("global_category3", "")).strip(),
        str(row.get("global_brand", "")).strip(),
        str(row.get("shop_name", "")).strip(),
    ]
    return " | ".join([p for p in parts if p])


def make_affiliate_link(origin: str) -> str:
    """
    สร้างลิงก์นายหน้าแบบที่ Facebook โชว์ได้ชัด (shopee.ee/an_redir)
    """
    origin = (origin or "").strip()
    if not origin:
        return origin

    # บางไฟล์มี product_short link เป็น shopee.ee/an_redir?origin_link=...
    # ถ้าเป็น an_redir อยู่แล้ว ให้ merge params ให้ครบ
    if "shopee.ee/an_redir" in origin:
        u = urlparse(origin)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        q["affiliate_id"] = AFFILIATE_ID
        q["utm_source"] = AFF_UTM_SOURCE
        q["afftag"] = AFF_TAG
        return u._replace(query=urlencode(q, doseq=True)).geturl()

    # ถ้าเป็น shopee.co.th/product/... -> เอาไปใส่ origin_link
    origin_encoded = quote(origin, safe="")
    return (
        "https://shopee.ee/an_redir"
        f"?origin_link={origin_encoded}"
        f"&affiliate_id={quote(AFFILIATE_ID)}"
        f"&utm_source={quote(AFF_UTM_SOURCE)}"
        f"&afftag={quote(AFF_TAG)}"
    )


def normalize_row(row: Dict) -> Product:
    title = (row.get("title") or row.get("name") or "").strip()

    # ลิงก์สินค้า (ไฟล์คุณมีทั้ง product_link และ product_short link)
    origin = (row.get("product_link") or row.get("url") or row.get("product_link ") or "").strip()
    short_link = (row.get("product_short link") or row.get("product_short_link") or "").strip()
    origin_link = short_link if short_link else origin

    aff_link = make_affiliate_link(origin_link)

    images = extract_images(row)
    video_url = extract_video(row)

    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))
    dp = fnum(row.get("discount_percentage"))
    if dp is None and price and sale_price and price > 0:
        dp = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))
    sold = fint(row.get("item_sold")) or fint(row.get("historical_sold")) or fint(row.get("sold"))

    cat_text = categories_text(row)

    return Product(
        title=title,
        origin_link=origin_link,
        affiliate_link=aff_link,
        images=images,
        video_url=video_url,
        price=price,
        sale_price=sale_price,
        discount_pct=dp,
        rating=rating,
        sold=sold,
        categories_text=cat_text,
        raw=row,
    )


def effective_price(p: Product) -> Optional[float]:
    return p.sale_price if p.sale_price is not None else p.price


_allow_re = re.compile(ALLOW_KEYWORDS, re.IGNORECASE)
_block_re = re.compile(BLOCK_KEYWORDS, re.IGNORECASE)


def matches_page_category(p: Product) -> bool:
    text = f"{p.title} {p.categories_text}"
    if _block_re.search(text):
        return False
    # ต้อง match allow อย่างน้อย 1 คำ
    return bool(_allow_re.search(text))


def product_pass(p: Product) -> bool:
    if not p.title or not p.affiliate_link:
        return False
    if len(p.images) < 1 and not p.video_url:
        return False
    if not matches_page_category(p):
        return False

    ep = effective_price(p)
    if ep is None:
        return False
    if not (PRICE_MIN <= ep <= PRICE_MAX):
        return False
    if p.rating is not None and p.rating < MIN_RATING:
        return False
    if p.sold is not None and p.sold < MIN_SOLD:
        return False
    if p.discount_pct is not None and p.discount_pct < MIN_DISCOUNT_PCT:
        return False
    return True


def score_product(p: Product, now: datetime) -> float:
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

    # random jitter (กันซ้ำ)
    base *= random.uniform(0.98, 1.03)
    return base


# =========================
# CSV STREAMING (SAFE)
# =========================
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
        die("No usable products found. แนะนำ: ลด MIN_* หรือปรับ ALLOW/BLOCK_KEYWORDS ให้ตรงข้อมูล CSV")
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
    pool = []
    for sc, p in top_items:
        if recently_posted(state, p.origin_link, now):
            continue
        pool.append((sc, p))

    if not pool:
        pool = top_items  # ถ้าคัดจนหมด ให้เลือกจากทั้งหมด

    chosen = weighted_choice(pool)
    return chosen


# =========================
# CAPTION (no "sold")
# =========================
HOOKS = [
    "⚡ ของมันต้องมีติดบ้าน!",
    "✅ คัดตัวฮิตรีวิวดี ราคาโดน",
    "🧰 สายช่างต้องมี ช่วยให้งานไวขึ้นจริง",
    "🏡 ของใช้/อุปกรณ์บ้าน ที่ทำให้ชีวิตง่ายขึ้น",
]

BENEFITS = [
    "ใช้งานง่าย มือใหม่ก็ทำเองได้",
    "ประหยัดเวลา งานเสร็จไวขึ้น",
    "คุ้มราคา คุณภาพเกินตัว",
    "เหมาะกับงานช่าง/ไฟฟ้าในบ้าน",
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
        "👉 ลิงก์นายหน้า:",
        p.affiliate_link,
        "",
        cta,
        "",
        tags,
    ]
    # ลบช่องว่างซ้อน
    out = []
    for s in parts:
        if s == "" and (not out or out[-1] == ""):
            continue
        out.append(s)
    return "\n".join(out).strip()


# =========================
# FACEBOOK POSTING
# =========================
def download_image_bytes(url: str) -> bytes:
    r = http_get(
        url,
        timeout=(IMG_CONNECT_TIMEOUT, IMG_READ_TIMEOUT),
        stream=True,
        headers={"User-Agent": "Mozilla/5.0"},
    )
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
        time.sleep(1.0)

    post_id = create_feed_post_with_media(PAGE_ID, caption, media_ids)
    return post_id


def head_size_mb(url: str) -> Optional[float]:
    try:
        r = requests.head(
            url,
            timeout=(VID_CONNECT_TIMEOUT, 20),
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
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


# =========================
# MAIN
# =========================
def main():
    now = now_bkk()
    print("==== V30 ULTRA ====")
    print("INFO: Now(BKK) =", now.isoformat())
    print("INFO: Graph =", GRAPH_VERSION)
    print("INFO: Slots(BKK) =", SLOTS_BKK)
    print("INFO: Filters: rating>=", MIN_RATING, "disc
