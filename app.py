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
from urllib.parse import quote, urlparse, urlunparse, parse_qsl, urlencode

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

# Shopee Affiliate (หน้านาย)
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()

# Schedule (Bangkok)
TZ_BKK = timezone(timedelta(hours=7))
SLOTS_BKK = os.getenv("SLOTS_BKK", "09:00,12:00,18:30,21:00").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))  # ต่อ 1 run โพสต์ได้กี่โพสต์ (ปกติ 1)
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

# Anti-repeat
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

# Selection filters
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))

# Media
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
PREFER_VIDEO = os.getenv("PREFER_VIDEO", "0").strip().lower() in ("1", "true", "yes")  # ปิดไว้ก่อนให้ชัวร์
VIDEO_MAX_MB = int(os.getenv("VIDEO_MAX_MB", "80"))

# CSV streaming
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "220"))

# Caption
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate"
).strip()

# Targeting: ให้ตรงแนวเพจ
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|สายไฟ|เบรกเกอร์|หลอดไฟ|โคม|สวิตช์|ปลั๊กพ่วง|รางปลั๊ก|มิเตอร์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|ชาร์จ|อะแดปเตอร์|หัวชาร์จ|สายชาร์จ|เครื่องมือ|สว่าน|ค้อน|ประแจ|คีม|ไขควง|ปืนกาว|เทปพันสายไฟ|งานช่าง|บ้าน|ซ่อม|DIY|ช่าง|ปลั๊กกันไฟกระชาก)"
).strip()

# บล็อกของที่ไม่ตรงเพจ (กันหลุดไปพวกแฟชั่น/บิวตี้/ผ้าห่ม/ยาย้อมผม ฯลฯ)
BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(เสื้อผ้า|แฟชั่น|ชุดนอน|ชุดผ้าปู|ผ้าห่ม|หมอน|ผ้าปู|เครื่องสำอาง|สกินแคร์|ครีม|น้ำหอม|ยาย้อมผม|ย้อมผม|วิกผม|อาหารเสริม|บุหรี่|แอลกอฮอล์|ของเล่นเด็ก|รองเท้า|กระเป๋า|บรา|กางเกงใน)"
).strip()

# =========================
# SAFETY CHECK
# =========================
def die(msg: str, code: int = 1):
    print("FATAL:", msg)
    raise SystemExit(code)

if not PAGE_ID:
    die("Missing env: PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    die("Missing env: PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    die("Missing env: SHOPEE_CSV_URL")

ALLOW_PAT = re.compile(ALLOW_KEYWORDS, re.IGNORECASE) if ALLOW_KEYWORDS else None
BLOCK_PAT = re.compile(BLOCK_KEYWORDS, re.IGNORECASE) if BLOCK_KEYWORDS else None


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
        "posted_slots": {},     # {"YYYY-MM-DD": ["09:00","12:00"...]}
        "posted_at": {},        # {"product_url": "ISO"}
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
    """
    catch-up: ถ้าเลยเวลาแล้วแต่ slot ยังไม่ถูกโพส -> ถือว่า due
    """
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
SESSION = requests.Session()

def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = SESSION.get(url, timeout=timeout, headers=headers, stream=stream, allow_redirects=True)
    r.raise_for_status()
    return r

def graph_post(path: str, data=None, files=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    r = SESSION.post(url, params=params, data=data, files=files, timeout=(20, 80))
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: {js}")
    return js


# =========================
# AFFILIATE LINK
# =========================
def make_affiliate_link(origin_url: str) -> str:
    """
    ให้ได้รูปแบบที่คุณเห็นว่าใช้งานได้:
    https://shope.ee/an_redir?origin_link=...&affiliate_id=...&utm_source=facebook&afftag=BENHomeElectrical
    """
    origin_url = (origin_url or "").strip()
    if not origin_url:
        return ""

    # ถ้าเป็น shope.ee/an_redir อยู่แล้ว -> เติมพารามิเตอร์ให้ครบ
    if "shope.ee/an_redir" in origin_url:
        u = urlparse(origin_url)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        q.setdefault("affiliate_id", AFFILIATE_ID)
        q.setdefault("utm_source", AFF_UTM_SOURCE)
        q.setdefault("afftag", AFF_TAG)
        # ถ้าไม่มี origin_link ก็ปล่อย (แต่ส่วนมากมี)
        return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(q, doseq=True), u.fragment))

    # เอา shopee.co.th/product/... เป็น origin_link
    origin_enc = quote(origin_url, safe="")
    return (
        "https://shope.ee/an_redir"
        f"?origin_link={origin_enc}"
        f"&affiliate_id={quote(AFFILIATE_ID)}"
        f"&utm_source={quote(AFF_UTM_SOURCE)}"
        f"&afftag={quote(AFF_TAG)}"
    )


# =========================
# PRODUCT
# =========================
@dataclass
class Product:
    title: str
    product_link: str           # shopee.co.th/product/...
    short_link: str             # shope.ee/...
    affiliate_link: str         # final
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

def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def extract_images(row: Dict) -> List[str]:
    # รองรับ image_link_1..10 / image_link / image_link_3..4 ที่คุณมี
    imgs = []
    for k in ["image_link"] + [f"image_link_{i}" for i in range(1, 11)] + [f"image_link_{i}" for i in range(2, 11)]:
        v = normalize_spaces(row.get(k, ""))
        if v.startswith("http"):
            imgs.append(v)

    # unique keep order
    seen = set()
    out = []
    for u in imgs:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def pick_best_origin_link(row: Dict) -> str:
    # ในไฟล์คุณมี product_link + product_short link (มีช่องว่างในชื่อ)
    pl = normalize_spaces(row.get("product_link", ""))
    sl = normalize_spaces(row.get("product_short link", ""))  # ตามหัวจริงที่คุณส่ง
    if pl.startswith("http"):
        return pl
    if sl.startswith("http"):
        return sl
    # เผื่อบางไฟล์ใช้ชื่ออื่น
    for k in ["product_short_link", "product_shortlink", "url", "link"]:
        v = normalize_spaces(row.get(k, ""))
        if v.startswith("http"):
            return v
    return ""

def row_category_text(row: Dict) -> str:
    parts = []
    for k in ["global_category1", "global_category2", "global_category3", "global_brand"]:
        v = normalize_spaces(row.get(k, ""))
        if v:
            parts.append(v)
    return " | ".join(parts)

def is_relevant(title: str, cat: str) -> bool:
    txt = f"{title} {cat}".strip()
    if BLOCK_PAT and BLOCK_PAT.search(txt):
        return False
    # ต้อง match allow อย่างน้อย 1 (เพื่อกันหลุดหมวดเพจ)
    if ALLOW_PAT:
        return bool(ALLOW_PAT.search(txt))
    return True

def normalize_product(row: Dict) -> Optional[Product]:
    title = normalize_spaces(row.get("title") or row.get("name") or row.get("product_name") or "")
    if not title:
        return None

    origin = pick_best_origin_link(row)
    if not origin:
        return None

    imgs = extract_images(row)
    if not imgs:
        return None

    cat = row_category_text(row)

    # ราคา / โปร
    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))
    dp = fnum(row.get("discount_percentage"))
    if dp is None and price and sale_price and price > 0 and sale_price < price:
        dp = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))

    # กรองช่วงราคา
    eff = sale_price if sale_price is not None else price
    if eff is None:
        return None
    if not (PRICE_MIN <= eff <= PRICE_MAX):
        return None

    # กรองเรตติ้ง/ส่วนลด
    if rating is not None and rating < MIN_RATING:
        return None
    if dp is not None and dp < MIN_DISCOUNT_PCT:
        return None

    if not is_relevant(title, cat):
        return None

    # ทำลิงก์นายหน้า
    aff = make_affiliate_link(origin)

    # เก็บ product_link/short_link เพื่อ debug
    pl = normalize_spaces(row.get("product_link", ""))
    sl = normalize_spaces(row.get("product_short link", ""))
    return Product(
        title=title,
        product_link=pl,
        short_link=sl,
        affiliate_link=aff,
        images=imgs[:10],
        price=price,
        sale_price=sale_price,
        discount_pct=dp,
        rating=rating,
        category_text=cat,
        raw=row,
    )


# =========================
# SCORE + PICK
# =========================
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def score_product(p: Product) -> float:
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    eff = p.sale_price if p.sale_price is not None else p.price
    eff = eff if eff is not None else 9999.0

    # ให้ความสำคัญ: รีวิวดี + ลดเยอะ + ราคาพอเหมาะ
    r_score = clamp((r - 4.0) / 1.0, 0, 1)       # 4.0-5.0
    d_score = clamp(d / 70.0, 0, 1)              # 0-70%
    price_score = 1.0 - clamp((eff - PRICE_MIN) / max(1.0, (PRICE_MAX - PRICE_MIN)), 0, 1) * 0.12

    base = (0.55 * r_score) + (0.45 * d_score)
    base *= price_score

    # เพิ่มน้ำหนักถ้าหมวดตรงมาก
    if re.search(r"(Electrical|Tools|Home Improvement|Cables|Chargers|Converters)", p.category_text, re.I):
        base *= 1.08

    base *= random.uniform(0.97, 1.03)
    return base

def stream_top_products(csv_url: str) -> List[Tuple[float, Product]]:
    print("INFO: Streaming Shopee CSV ...")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,application/octet-stream,*/*",
        "Connection": "keep-alive",
    }
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

        p = normalize_product(row)
        if not p:
            continue

        sc = score_product(p)
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
        raise SystemExit("ERROR: No usable products found. ลองลด MIN_RATING/MIN_DISCOUNT_PCT หรือปรับ allow/block")
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
    cutoff = now - timedelta(days=REPOST_AFTER_DAYS)
    posted_at = state.get("posted_at", {})

    def ok(p: Product) -> bool:
        if p.affiliate_link and p.affiliate_link not in used:
            # กันโพสซ้ำภายใน REPOST_AFTER_DAYS
            last_iso = posted_at.get(p.affiliate_link)
            if last_iso:
                try:
                    last_dt = datetime.fromisoformat(last_iso)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=TZ_BKK)
                    if last_dt > cutoff:
                        return False
                except Exception:
                    pass
            return True
        return False

    fresh = [(sc, p) for sc, p in top_items if ok(p)]
    pool = fresh if fresh else top_items
    chosen = weighted_choice(pool)

    state.setdefault("used_urls", []).append(chosen.affiliate_link or chosen.product_link or chosen.short_link or chosen.title)
    state.setdefault("posted_at", {})[chosen.affiliate_link or chosen.product_link or chosen.title] = now.isoformat()
    return chosen


# =========================
# CAPTION (เอา "ขายแล้ว" ออก)
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
    "รีวิวดี น่าใช้จริง",
]

CTA = [
    "กดลิงก์ดูโปร/โค้ดส่วนลดตอนนี้เลย 👇",
    "ดูรีวิวจริง + ราคาล่าสุดในลิงก์ได้เลย ✅",
    "ทักแชทได้ครับ เดี๋ยวช่วยเลือกให้ 💬",
]

def fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{x:,.0f}"

def fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{x:.0f}%"

def build_caption(p: Product) -> str:
    hook = random.choice(HOOKS)
    benefit = random.choice(BENEFITS)
    cta = random.choice(CTA)

    # price line
    eff = p.sale_price if p.sale_price is not None else p.price
    if p.sale_price is not None and p.price is not None and p.sale_price < p.price:
        price_line = f"💸 โปรวันนี้: {fmt_money(p.sale_price)} บาท (ปกติ {fmt_money(p.price)} | ลด {fmt_pct(p.discount_pct)})"
    else:
        price_line = f"💸 ราคา: {fmt_money(eff)} บาท | ลด {fmt_pct(p.discount_pct)}"

    rating_line = f"⭐ เรตติ้ง: {p.rating:.1f}/5" if p.rating is not None else "⭐ เรตติ้ง: -"

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
        f"👉 {p.affiliate_link}",
        "",
        cta,
        "",
        HASHTAGS,
    ]
    # clean double blank
    out = []
    for s in parts:
        if s == "" and (not out or out[-1] == ""):
            continue
        out.append(s)
    return "\n".join(out).strip()


# =========================
# FACEBOOK: POST (3 images)
# =========================
def download_image_bytes(url: str) -> bytes:
    r = http_get(url, timeout=(20, 80), stream=True, headers={"User-Agent": "Mozilla/5.0"})
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


# =========================
# MAIN
# =========================
def main():
    now = now_bkk()
    print("==== V30 ULTRA FIX ====")
    print("INFO: Now(BKK) =", now.isoformat())
    print("INFO: Graph =", GRAPH_VERSION)
    print("INFO: Slots =", SLOTS_BKK)
    print("INFO: Filters: rating>=", MIN_RATING, "discount>=", MIN_DISCOUNT_PCT,
          "price=[", PRICE_MIN, "..", PRICE_MAX, "]")
    print("INFO: FIRST_RUN_POST_1 =", FIRST_RUN_POST_1)

    state = load_state()

    # 1) first run -> โพส 1 โพสทันที
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        print("INFO: First run detected -> will post 1 immediately")
        slot_used = "FIRST_RUN"
        do_post = True
    else:
        # 2) catch-up slot
        due = due_slots_today(state, now)
        if due:
            slot_used = due[0]
            print("INFO: Due slot ->", slot_used)
            do_post = True
        elif FORCE_POST:
            slot_used = "MANUAL"
            print("INFO: FORCE_POST enabled -> manual post")
            do_post = True
        else:
            print("INFO: No due slot (alrea
