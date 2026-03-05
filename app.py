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


# =========================
# CONFIG
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = os.getenv("STATE_FILE", "state.json")
MAX_STATE_ITEMS = int(os.getenv("MAX_STATE_ITEMS", "9000"))

# Page + CSV
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

# Shopee Affiliate
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()

# Schedule (Bangkok)
TZ_BKK = timezone(timedelta(hours=7))
SLOTS_BKK = os.getenv("SLOTS_BKK", "09:00,12:00,18:30,21:00").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))  # ต่อ 1 run โพสต์ได้กี่โพสต์
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

# Selection filters
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

# Caption
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ShopeeAffiliate"
).strip()

# Category/Keyword targeting for your page (BEN Home & Electrical)
# ใช้เป็น “ตัวกรอง” ให้ใกล้หมวดเพจ
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|สายไฟ|เบรกเกอร์|หลอดไฟ|โคม|สวิตช์|มิเตอร์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|ชาร์จ|เครื่องมือ|สว่าน|ค้อน|ประแจ|คีม|ไขควง|งานช่าง|บ้าน|ซ่อม|DIY)"
).strip()
BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(เสื้อผ้า|เครื่องสำอาง|ของเล่นเด็ก|อาหารเสริม|บุหรี่|แอลกอฮอล์)"
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
    base = {"used_urls": [], "posted_slots": {}, "posted_at": {}, "first_run_done": False}
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
    key = now.strftime("%Y-%m-%d")
    posted = set(state.get("posted_slots", {}).get(key, []))
    due = []
    for hhmm in SLOTS_BKK:
        t = parse_slot_today_bkk(now, hhmm)
        # ถ้าเลยเวลาแล้ว และยังไม่โพสต์ slot นี้ -> ถือว่า due (catch-up)
        if now >= t and hhmm not in posted:
            due.append(hhmm)
    return due


# =========================
# TEXT / FILTER
# =========================
ALLOW_PAT = re.compile(ALLOW_KEYWORDS, re.IGNORECASE) if ALLOW_KEYWORDS else None
BLOCK_PAT = re.compile(BLOCK_KEYWORDS, re.IGNORECASE) if BLOCK_KEYWORDS else None


def normalize_text(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def is_allowed_text(text: str) -> bool:
    t = normalize_text(text)
    if not t:
        return False
    if BLOCK_PAT and BLOCK_PAT.search(t):
        return False
    if ALLOW_PAT:
        return bool(ALLOW_PAT.search(t))
    return True


# =========================
# AFFILIATE LINK BUILDER
# =========================
def add_affiliate_params(url: str) -> str:
    """
    ทำให้ลิงก์เป็น “ลิงก์นายหน้า” เสมอ:
    - เติม affiliate_id=...
    - เติม utm_source=facebook
    - เติม afftag=... (ใช้ช่วย track)
    * ถ้าลิงก์มีอยู่แล้ว จะไม่ลบของเดิม แต่จะ overwrite key เดียวกัน
    """
    url = normalize_text(url)
    if not url:
        return ""

    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))

    q["affiliate_id"] = AFFILIATE_ID
    q["utm_source"] = AFF_UTM_SOURCE
    q["afftag"] = AFF_TAG

    new_query = urlencode(q, doseq=True)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))


# =========================
# HTTP / GRAPH
# =========================
def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=headers, stream=stream)
    r.raise_for_status()
    return r


def graph_post(path: str, data=None, files=None, params=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    p = {"access_token": PAGE_ACCESS_TOKEN}
    if params:
        p.update(params)

    r = requests.post(url, params=p, data=data, files=files, timeout=(20, 120))
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise

    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR {r.status_code}: {js}")
    return js


def graph_get(path: str, params=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    p = {"access_token": PAGE_ACCESS_TOKEN}
    if params:
        p.update(params)
    r = requests.get(url, params=p, timeout=(20, 80))
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR {r.status_code}: {js}")
    return js


# =========================
# PRODUCT MODEL
# =========================
@dataclass
class Product:
    name: str
    url: str
    images: List[str]
    video_url: Optional[str]
    price: Optional[float]
    sale_price: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    sold: Optional[int]
    voucher: Optional[str]
    category: Optional[str]
    raw: Dict


def fnum(x) -> Optional[float]:
    try:
        if x is None:
            return None
        s = str(x).strip().replace(",", "")
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def fint(x) -> Optional[int]:
    try:
        if x is None:
            return None
        s = str(x).strip().replace(",", "")
        if not s:
            return None
        return int(float(s))
    except Exception:
        return None


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def extract_images(row: Dict) -> List[str]:
    """
    รองรับ: image_link_1..10, image_link, image, images (คั่น ; , |)
    """
    imgs = []
    for i in range(1, 11):
        v = normalize_text(row.get(f"image_link_{i}", ""))
        if v.startswith("http"):
            imgs.append(v)

    v0 = normalize_text(row.get("image_link", "")) or normalize_text(row.get("image", ""))
    if v0.startswith("http"):
        imgs.append(v0)

    v_multi = normalize_text(row.get("images", ""))
    if v_multi:
        parts = re.split(r"[;,|]\s*", v_multi)
        for p in parts:
            p = p.strip()
            if p.startswith("http"):
                imgs.append(p)

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
        v = normalize_text(row.get(k, ""))
        if v.startswith("http"):
            return v
    return None


def normalize_row(row: Dict) -> Product:
    name = normalize_text(row.get("name") or row.get("title") or row.get("product_name"))
    url = normalize_text(row.get("affiliate_link") or row.get("deeplink") or row.get("url") or row.get("product_link") or row.get("link"))
    url = add_affiliate_params(url) if url else ""

    images = extract_images(row)
    video_url = extract_video(row)

    price = fnum(row.get("price") or row.get("original_price") or row.get("list_price"))
    sale_price = fnum(row.get("sale_price") or row.get("discount_price") or row.get("final_price"))

    dp = fnum(row.get("discount_percentage") or row.get("discount_pct"))
    if dp is None and price and sale_price and price > 0 and sale_price < price:
        dp = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating") or row.get("rating") or row.get("avg_rating"))
    sold = fint(row.get("item_sold") or row.get("historical_sold") or row.get("sold") or row.get("sold_count"))

    voucher = normalize_text(row.get("voucher") or row.get("voucher_code") or row.get("promo_code") or row.get("discount_code"))
    category = normalize_text(row.get("category") or row.get("category_name") or row.get("cat"))

    return Product(
        name=name,
        url=url,
        images=images,
        video_url=video_url,
        price=price,
        sale_price=sale_price,
        discount_pct=dp,
        rating=rating,
        sold=sold,
        voucher=voucher if voucher else None,
        category=category if category else None,
        raw=row
    )


def effective_price(p: Product) -> Optional[float]:
    return p.sale_price if p.sale_price is not None else p.price


def product_pass(p: Product) -> bool:
    if not p.name or not p.url:
        return False

    # ต้องมีรูป/วิดีโอ
    if len(p.images) < 1 and not p.video_url:
        return False

    # ให้ตรงหมวดเพจ
    blob = f"{p.name} {p.category or ''}"
    if not is_allowed_text(blob):
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
    """
    ให้คะแนน:
    - เรตติ้ง (หนักสุด)
    - ส่วนลด
    - ขายแล้ว
    - มีวิดีโอ + นิดหน่อย
    """
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    s = p.sold if p.sold is not None else 0
    ep = effective_price(p) or 999.0

    r_score = clamp((r - 4.0) / 1.0, 0, 1)          # 4.0..5.0
    d_score = clamp(d / 70.0, 0, 1)                 # 0..70%
    s_score = clamp((s ** 0.5) / 80.0, 0, 1)        # sqrt scale

    # ราคาไม่ให้หลุดกรอบมาก
    price_score = 1.0 - clamp((ep - PRICE_MIN) / max(1.0, (PRICE_MAX - PRICE_MIN)), 0, 1) * 0.12

    base = (0.52 * r_score) + (0.28 * d_score) + (0.20 * s_score)
    base *= price_score

    if p.video_url:
        base *= 1.06

    # random เล็กน้อยกันซ้ำ pattern
    base *= random.uniform(0.985, 1.025)
    return base


# =========================
# CSV STREAMING
# =========================
def stream_top_products(csv_url: str, now: datetime) -> List[Tuple[float, Product]]:
    print("INFO: Streaming Shopee CSV ...")
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"}
    r = http_get(csv_url, timeout=(25, 180), headers=headers, stream=True)
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
        die("No usable products found. ลองลด MIN_* หรือขยาย PRICE_*")
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
    used_urls = set(state.get("used_urls", []))

    # กัน repost ภายใน REPOST_AFTER_DAYS โดยใช้ posted_at
    posted_at: Dict[str, str] = state.get("posted_at", {})
    cutoff = now - timedelta(days=REPOST_AFTER_DAYS)

    def not_recent(url: str) -> bool:
        iso = posted_at.get(url)
        if not iso:
            return True
        try:
            t = datetime.fromisoformat(iso)
            if t.tzinfo is None:
                t = t.replace(tzinfo=TZ_BKK)
            return t < cutoff
        except Exception:
            return True

    fresh = [(sc, p) for sc, p in top_items if (p.url not in used_urls) and not_recent(p.url)]
    pool = fresh if fresh else top_items

    chosen = weighted_choice(pool)
    state.setdefault("used_urls", []).append(chosen.url)
    return chosen


# =========================
# CAPTION (AI-ish templates)
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

    voucher_line = f"🎫 โค้ด/โปร: {p.voucher}" if p.voucher else ""

    parts = [
        f"🏠⚡ {BRAND}",
        hook,
        "",
        f"🛒 {p.name}",
        "",
        price_line,
        rating_line,
        sold_line,
        voucher_line,
        "",
        f"✅ จุดเด่น: {benefit}",
        "✅ ดูรูป/รีวิวจริงก่อนซื้อได้",
        "",
        f"👉 {p.url}",
        "",
        cta,
        "",
        HASHTAGS,
    ]
    out = []
    for s in parts:
        s = s.strip()
        if s == "" and (not out or out[-1] == ""):
            continue
        out.append(s)
    return "\n".join(out).strip()


# =========================
# FACEBOOK POSTING
# =========================
def download_bytes(url: str, timeout=(20, 100)) -> bytes:
    r = http_get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
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


def post_images_multi(p: Product, caption: str) -> str:
    imgs = p.images[:max(1, POST_IMAGES_COUNT)]
    media_ids = []
    for u in imgs:
        img_bytes = download_bytes(u, timeout=(20, 80))
        mid = upload_unpublished_photo(PAGE_ID, img_bytes)
        media_ids.append(mid)
        time.sleep(1.0)

    post_id = create_feed_post_with_media(PAGE_ID, caption, media_ids)
    return post_id


def head_size_mb(url: str) -> Optional[float]:
    try:
        r = requests.head(url, timeout=(15, 20), allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
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


def verify_post_visibility(post_id: str) -> None:
    """
    เช็คเบื้องต้นว่าโพสต์ publish แล้ว + ได้ permalink
    """
    try:
        js = graph_get(f"/{post_id}", params={"fields": "id,is_published,permalink_url,created_time"})
        print("VERIFY:", js)
    except Exception as e:
        print("VERIFY WARN:", str(e))


# =========================
# MAIN
# =========================
def main():
    now = now_bkk()
    print("==== V30 ULTRA AI ====")
    print("INFO: Now(BKK) =", now.isoformat())
    print("INFO: Graph =", GRAPH_VERSION)
    print("INFO: Slots(BKK) =", SLOTS_BKK)
    print("INFO: Posts/Run =", POSTS_MAX_PER_RUN, "| PREFER_VIDEO =", PREFER_VIDEO)
    print("INFO: Filters: rating>=", MIN_RATING, "discount>=", MIN_DISCOUNT_PCT, "sold>=", MIN_SOLD, "price=[", PRICE_MIN, "..", PRICE_MAX, "]")
    print("INFO: Affiliate =", AFFILIATE_ID)

    state = load_state()

    # เงื่อนไข “รันครั้งแรกโพสต์ 1 โพสต์ทันที”
    first_run = not state.get("first_run_done", False)
    if first_run and FIRST_RUN_POST_1:
        print("INFO: First run detected -> force 1 post now")
        due = ["FIRST_RUN"]
    else:
        due = due_slots_today(state, now)

    if not due and not FORCE_POST:
        print("INFO: No due slot (already posted). Exit. (Set FORCE_POST=1 to test)")
        return

    if FORCE_POST and not due:
        due = ["MANUAL"]

    print("INFO: Due slots =", due)

    top_items = stream_top_products(SHOPEE_CSV_URL, now)

    posts_done = 0
    for slot_used in due:
        if posts_done >= POSTS_MAX_PER_RUN:
            break

        p = pick_product(top_items, state, now)
        caption = build_caption(p, now)

        print("\nINFO: Picked:", (p.name or "")[:110], "| video?", bool(p.video_url), "| images:", len(p.images))
        print("INFO: URL (affiliate) =", p.url)

        # โพสต์ (วิดีโอ/รูป)
        try:
            if PREFER_VIDEO and p.video_url:
                vid_id = post_video_by_url(caption, p.video_url)
                print("OK: Posted VIDEO id =", vid_id)
                # video ไม่มี post_id แบบ feed เสมอ เลยไม่ verify แบบเดียวกัน
            else:
                post_id = post_images_multi(p, caption)
                print("OK: Posted FEED post id =", post_id)
                verify_post_visibility(post_id)

        except Exception as e:
            # fallback: ถ้าวิดีโอพัง -> รูป
            if p.video_url:
                print("WARN: Video post failed -> fallback to images. Reason:", str(e))
                post_id = post_images_multi(p, caption)
                print("OK: Posted FEED fallback id =", post_id)
                verify_post_visibility(post_id)
            else:
                raise

        # mark slot posted (ยกเว้น manual/first_run ก็ mark ได้แต่คนละชื่อ)
        if slot_used not in ("MANUAL",):
            if slot_used in SLOTS_BKK:
                mark_slot_posted(state, now, slot_used)
            else:
                # FIRST_RUN -> mark ว่าโพสต์แล้วสำหรับ slot ที่ “ใกล้ที่สุด” ที่เลยเวลา (ถ้ามี)
                # ถ้าไม่มี ให้ไม่ mark slot
                today_due = due_slots_today(state, now)
                if today_due:
                    mark_slot_posted(state, now, today_due[0])

        # remember posted time by url
        state.setdefault("posted_at", {})[p.url] = now.isoformat()

        posts_done += 1
        time.sleep(4)

    state["first_run_done"] = True
    save_state(state)
    print("\nINFO: Done. posts_done =", posts_done)


if __name__ == "__main__":
    main()
