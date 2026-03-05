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
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# =========================
# V30 ULTRA TH (BEN Home & Electrical)
# - Graph v25.0
# - First run -> always post 1
# - Catch-up slots: if past slot time and not posted today -> post
# - Affiliate link auto append
# - Prefer video if available else 3 images
# - Strong CSV column compatibility (including "product_short link")
# =========================

# -------------------------
# CONFIG / ENV
# -------------------------
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
# ค่าเริ่มต้นตามที่คุณใช้: 12:00 และ 18:30 (เพิ่ม 21:00 ไว้เป็นโบนัส)
SLOTS_BKK = os.getenv("SLOTS_BKK", "12:00,18:30,21:00").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))  # ต่อ 1 run โพสต์ได้กี่โพสต์ (คุมไม่ให้ยิงถี่)
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

# Selection filters (ปรับได้ใน Secrets/Env)
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))
MIN_SOLD = int(os.getenv("MIN_SOLD", "30"))
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

# Caption / Brand
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate"
).strip()

# Targeting หมวดเพจ BEN Home & Electrical
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|สายไฟ|เบรกเกอร์|หลอดไฟ|โคม|สวิตช์|มิเตอร์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|ชาร์จ|เครื่องมือ|สว่าน|ค้อน|ประแจ|คีม|ไขควง|งานช่าง|บ้าน|ซ่อม|DIY|อะแดปเตอร์|หัวชาร์จ|ปลั๊กพ่วง|สายชาร์จ)"
).strip()
BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(เสื้อผ้า|เครื่องสำอาง|ของเล่นเด็ก|อาหารเสริม|บุหรี่|แอลกอฮอล์)"
).strip()

# Timeouts
CSV_CONNECT_TIMEOUT = 25
CSV_READ_TIMEOUT = 180
IMG_CONNECT_TIMEOUT = 20
IMG_READ_TIMEOUT = 80
VID_CONNECT_TIMEOUT = 20
VID_READ_TIMEOUT = 120
GRAPH_CONNECT_TIMEOUT = 20
GRAPH_READ_TIMEOUT = 90


# -------------------------
# BASIC GUARDS
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


# -------------------------
# HTTP SESSION (RETRY)
# -------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


SESSION = make_session()


def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = SESSION.get(url, timeout=timeout, headers=headers, stream=stream)
    r.raise_for_status()
    return r


def http_head(url: str, timeout=(20, 20), headers=None, allow_redirects=True) -> requests.Response:
    r = SESSION.head(url, timeout=timeout, headers=headers, allow_redirects=allow_redirects)
    return r


def graph_post(path: str, data=None, files=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    r = SESSION.post(
        url, params=params, data=data, files=files,
        timeout=(GRAPH_CONNECT_TIMEOUT, GRAPH_READ_TIMEOUT)
    )
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: status={r.status_code} resp={js}")
    return js


# -------------------------
# TIME / STATE
# -------------------------
def now_bkk() -> datetime:
    return datetime.now(TZ_BKK)


def parse_slot_today_bkk(now: datetime, hhmm: str) -> datetime:
    hh, mm = hhmm.split(":")
    return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)


def load_state() -> dict:
    base = {
        "used_urls": [],          # list[str]
        "posted_slots": {},       # dict[date] -> list[hhmm]
        "posted_at": {},          # dict[url] -> iso
        "first_run_done": False,
        "last_run_iso": "",
    }
    if not os.path.exists(STATE_FILE):
        return base
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
        if not isinstance(s, dict):
            return base
        for k, v in base.items():
            s.setdefault(k, v)
        if not isinstance(s.get("used_urls"), list):
            s["used_urls"] = []
        if not isinstance(s.get("posted_slots"), dict):
            s["posted_slots"] = {}
        if not isinstance(s.get("posted_at"), dict):
            s["posted_at"] = {}
        if not isinstance(s.get("first_run_done"), bool):
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
    key = now.strftime("%Y-%m-%d")
    posted = set(state.get("posted_slots", {}).get(key, []))
    due = []
    for hhmm in SLOTS_BKK:
        t = parse_slot_today_bkk(now, hhmm)
        if now >= t and hhmm not in posted:
            due.append(hhmm)
    return due


# -------------------------
# TEXT / FILTER
# -------------------------
ALLOW_RE = re.compile(ALLOW_KEYWORDS, re.IGNORECASE) if ALLOW_KEYWORDS else None
BLOCK_RE = re.compile(BLOCK_KEYWORDS, re.IGNORECASE) if BLOCK_KEYWORDS else None


def norm(s) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def pass_keywords(title: str, desc: str = "") -> bool:
    text = f"{title} {desc}".strip()
    if BLOCK_RE and BLOCK_RE.search(text):
        return False
    if ALLOW_RE:
        return bool(ALLOW_RE.search(text))
    return True


# -------------------------
# AFFILIATE URL BUILDER
# -------------------------
def append_affiliate_params(url: str) -> str:
    """
    รองรับทั้ง product_link และ product_short link
    - ถ้ามี affiliate_id อยู่แล้ว จะคงไว้
    - เติม affiliate_id + utm_source + afftag
    """
    url = norm(url)
    if not url:
        return ""

    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))

    # เติมค่า ถ้าไม่มี
    q.setdefault("affiliate_id", AFFILIATE_ID)
    q.setdefault("utm_source", AFF_UTM_SOURCE)
    q.setdefault("afftag", AFF_TAG)

    new_query = urlencode(q, doseq=True)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))


# -------------------------
# PRODUCT MODEL
# -------------------------
@dataclass
class Product:
    title: str
    url: str
    short_url: str
    images: List[str]
    video_url: Optional[str]
    price: Optional[float]
    sale_price: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    sold: Optional[int]
    description: str
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


def get_any(row: Dict, keys: List[str]) -> str:
    for k in keys:
        if k in row and str(row.get(k, "")).strip() != "":
            return str(row.get(k, "")).strip()
    return ""


def extract_images(row: Dict) -> List[str]:
    # รองรับ image_link_1..10 + image_link + additional_image_link (ถ้ามี)
    imgs = []
    for i in range(1, 11):
        v = norm(row.get(f"image_link_{i}"))
        if v:
            imgs.append(v)
    v0 = norm(row.get("image_link"))
    if v0:
        imgs.append(v0)
    vadd = norm(row.get("additional_image_link"))
    if vadd and vadd.startswith("http"):
        imgs.append(vadd)

    # unique keep order
    seen = set()
    out = []
    for u in imgs:
        if u and u not in seen and u.startswith("http"):
            seen.add(u)
            out.append(u)
    return out


def extract_video(row: Dict) -> Optional[str]:
    for k in ["video_url", "video_link", "video", "reel_video", "reels_video", "short_video"]:
        v = norm(row.get(k))
        if v and v.startswith("http"):
            return v
    return None


def normalize_row(row: Dict) -> Product:
    # ชื่อคอลัมน์ไฟล์คุณมี "product_short link" (มีเว้นวรรค) ต้องรองรับ
    title = get_any(row, ["title", "name", "product_name"])
    product_link = get_any(row, ["product_link", "url", "product_link "])
    short_link = get_any(row, ["product_short link", "product_short_link", "short_link"])

    images = extract_images(row)
    video_url = extract_video(row)

    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))

    dp = fnum(row.get("discount_percentage"))
    if dp is None and price and sale_price and price > 0:
        dp = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))
    sold = fint(row.get("item_sold")) or fint(row.get("historical_sold")) or fint(row.get("sold"))

    desc = norm(row.get("description"))

    # เลือกลิงก์ที่ดีที่สุด: short link > product_link
    best_link = short_link or product_link
    aff_link = append_affiliate_params(best_link)

    return Product(
        title=title,
        url=aff_link,            # ใช้ลิงก์ที่เติม affiliate แล้ว
        short_url=short_link,
        images=images,
        video_url=video_url,
        price=price,
        sale_price=sale_price,
        discount_pct=dp,
        rating=rating,
        sold=sold,
        description=desc,
        raw=row,
    )


def effective_price(p: Product) -> Optional[float]:
    return p.sale_price if p.sale_price is not None else p.price


def product_pass(p: Product, state: dict, now: datetime) -> bool:
    if not p.title or not p.url:
        return False
    if len(p.images) < 1 and not p.video_url:
        return False

    if not pass_keywords(p.title, p.description):
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

    # กันซ้ำตามวัน
    posted_at = state.get("posted_at", {}).get(p.url)
    if posted_at:
        try:
            last = datetime.fromisoformat(posted_at)
        except Exception:
            last = None
        if last:
            if now - last < timedelta(days=REPOST_AFTER_DAYS):
                return False

    return True


def is_campaign_day(now: datetime) -> bool:
    # 1.1, 2.2, ..., 12.12 + 15/25
    md = f"{now.month}.{now.day}"
    return md in {f"{m}.{m}" for m in range(1, 13)} or now.day in {15, 25}


def is_end_month_boost(now: datetime) -> bool:
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    last_day = next_month - timedelta(days=1)
    return (last_day.day - now.day) <= 2


def score_product(p: Product, now: datetime) -> float:
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    s = p.sold if p.sold is not None else 0
    ep = effective_price(p) or 999.0

    r_score = clamp((r - 4.0) / 1.0, 0, 1)
    d_score = clamp(d / 70.0, 0, 1)
    s_score = clamp((s ** 0.5) / 70.0, 0, 1)

    # ราคาอยู่กลางๆ จะดี (ไม่ถูกเกิน/แพงเกิน)
    mid = (PRICE_MIN + PRICE_MAX) / 2.0
    price_score = 1.0 - (abs(ep - mid) / max(1.0, mid)) * 0.12
    price_score = clamp(price_score, 0.75, 1.05)

    base = (0.46 * r_score) + (0.34 * d_score) + (0.20 * s_score)
    base *= price_score

    if p.video_url:
        base *= 1.08
    if is_campaign_day(now):
        base *= 1.15
    if is_end_month_boost(now):
        base *= 1.08

    base *= random.uniform(0.97, 1.03)
    return base


# -------------------------
# CSV STREAMING
# -------------------------
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
        raise SystemExit("ERROR: No usable products found. ลด MIN_* หรือขยายช่วงราคาได้")
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
    fresh = [(sc, p) for sc, p in top_items if p.url not in used]
    pool = fresh if fresh else top_items
    chosen = weighted_choice(pool)
    state.setdefault("used_urls", []).append(chosen.url)
    return chosen


# -------------------------
# CAPTION (ขายแบบ “มืออาชีพ”)
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
    "รีวิวดี มีคนซื้อเยอะ",
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
    sold_line = f"📦 ขายแล้ว: {p.sold:,} ชิ้น" if p.sold is not None else "📦 ขายแล้ว: -"

    urgency = []
    if is_campaign_day(now):
        urgency.append("🎉 รอบแคมเปญ! โค้ด/โปรเปลี่ยนไว รีบเช็คในลิงก์")
    if is_end_month_boost(now):
        urgency.append("🔥 โค้งสุดท้ายปลายเดือน ของจำเป็นคุ้ม ๆ")

    tags = HASHTAGS

    parts = [
        f"🏠⚡ {BRAND}",
        hook,
        "",
        f"🛒 {p.title}",
        "",
        price_line,
        rating_line,
        sold_line,
        "",
        f"✅ จุดเด่น: {benefit}",
        "✅ ดูรูป/รีวิวจริงก่อนซื้อได้",
        "",
        *urgency,
        "",
        f"👉 {p.url}",
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
# FACEBOOK POSTING
# -------------------------
def download_image_bytes(url: str) -> bytes:
    r = http_get(url, timeout=(IMG_CONNECT_TIMEOUT, IMG_READ_TIMEOUT), stream=True,
                 headers={"User-Agent": "Mozilla/5.0"})
    return r.content


def upload_unpublished_photo(page_id: str, image_bytes: bytes) -> str:
    # Upload as unpublished then attach to feed (public)
    files = {"source": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"published": "false"}
    js = graph_post(f"/{page_id}/photos", data=data, files=files)
    return js["id"]


def create_feed_post_with_media(page_id: str, message: str, media_fbids: List[str]) -> str:
    data = {
        "message": message,
        # บางเคสใส่ published=true ให้ชัดเจน
        "published": "true",
    }
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
        time.sleep(1.2)

    post_id = create_feed_post_with_media(PAGE_ID, caption, media_ids)
    return post_id


def head_size_mb(url: str) -> Optional[float]:
    try:
        r = http_head(url, timeout=(VID_CONNECT_TIMEOUT, 20),
                      headers={"User-Agent": "Mozilla/5.0"},
                      allow_redirects=True)
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

    data = {
        "description": caption,
        "file_url": video_url,
    }
    js = graph_post(f"/{PAGE_ID}/videos", data=data)
    return js.get("id", "unknown_video_id")


# -------------------------
# MAIN
# -------------------------
def main():
    now = now_bkk()
    print("==== V30 ULTRA TH ====")
    print("INFO: Now(BKK) =", now.isoformat())
    print("INFO: Graph =", GRAPH_VERSION)
    print("INFO: Slots(BKK) =", SLOTS_BKK)
    print("INFO: FirstRunPost1 =", FIRST_RUN_POST_1)
    print("INFO: FORCE_POST =", FORCE_POST)
    print("INFO: Filters: rating>=", MIN_RATING, "discount>=", MIN_DISCOUNT_PCT,
          "sold>=", MIN_SOLD, "price=[", PRICE_MIN, "..", PRICE_MAX, "]")
    print("INFO: PreferVideo =", PREFER_VIDEO, "| VIDEO_MAX_MB =", VIDEO_MAX_MB)

    state = load_state()
    state["last_run_iso"] = now.isoformat()

    # 1) First run: โพสต์ 1 แน่นอน
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        print("INFO: First run detected -> will post 1 (guaranteed).")
        slots_to_cover = ["FIRST_RUN"]
    else:
        # 2) ปกติ: ถ้าเลยเวลา slot แล้วยังไม่โพสต์ -> catch-up
        due = due_slots_today(state, now)
        if not due and not FORCE_POST:
            print("INFO: No due slot and FORCE_POST=0 -> Exit.")
            save_state(state)
            return
        slots_to_cover = due if due else ["MANUAL"]

    # จำกัดจำนวนโพสต์ต่อ run
    slots_to_cover = slots_to_cover[:max(1, POSTS_MAX_PER_RUN)]
    print("INFO: slots_to_cover =", slots_to_cover)

    # Load CSV once
    top_items = stream_top_products(SHOPEE_CSV_URL, state, now)

    posts_done = 0
    for slot in slots_to_cover:
        p = pick_product(top_items, state)
        caption = build_caption(p, now)

        print("INFO: Picked:", p.title[:90], "| video?", bool(p.video_url), "| images:", len(p.images))
        print("INFO: Affiliate URL =", p.url)

        # Post
        try:
            if PREFER_VIDEO and p.video_url:
                vid_id = post_video_by_url(caption, p.video_url)
                print("OK: Posted VIDEO id =", vid_id)
                # วิดีโอจะเป็นคนละ object id ไม่ใช่ feed post id เสมอ
            else:
                post_id = post_images(p, caption)
                print("OK: Posted IMAGES feed id =", post_id)
        except Exception as e:
            # fallback: video fail -> images
            if p.video_url:
                print("WARN: Video post failed -> fallback to images. Reason:", str(e))
                post_id = post_images(p, caption)
                print("OK: Posted IMAGES(feed) fallback id =", post_id)
            else:
                raise

        # mark slot posted (ยกเว้น manual/first-run)
        if slot not in ("MANUAL", "FIRST_RUN"):
            mark_slot_posted(state, now, slot)

        # mark posted_at by url
        state.setdefault("posted_at", {})
        state["posted_at"][p.url] = now.isoformat()

        posts_done += 1
        time.sleep(6)

    # close first run flag
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        state["first_run_done"] = True

    save_state(state)
    print("INFO: Done. posts_done =", posts_done)


if __name__ == "__main__":
    main()
