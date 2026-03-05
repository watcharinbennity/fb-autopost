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


# =========================================================
# V31 ULTRA LOCK (BEN Home & Electrical)
# - Graph API v25.0 (ENV: GRAPH_VERSION)
# - ล็อคสินค้าให้ตรงแนวเพจด้วย keyword + category + blacklist
# - เอา "ขายแล้ว" ออกจากแคปชั่น (ไม่แสดง sold)
# - เช็คเวลาโพสเป็นสล็อต (เลยเวลาแล้วยังไม่โพส -> catch-up)
# - รันครั้งแรกโพส 1 โพส (FIRST_RUN_POST_1=1)
# - โพสแบบหลายรูป: upload unpublished photos -> feed attached_media
# =========================================================


# -------------------------
# REQUIRED ENV
# -------------------------
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

if not PAGE_ID:
    raise SystemExit("ERROR: Missing env PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    raise SystemExit("ERROR: Missing env PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    raise SystemExit("ERROR: Missing env SHOPEE_CSV_URL")


# -------------------------
# GRAPH
# -------------------------
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


# -------------------------
# Affiliate ("หน้านาย")
# -------------------------
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()


# -------------------------
# TIMEZONE / SCHEDULE (BKK)
# -------------------------
TZ_BKK = timezone(timedelta(hours=7))
SLOTS_BKK = os.getenv("SLOTS_BKK", "08:00,12:00,18:30,21:30").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]


# -------------------------
# RUN BEHAVIOR
# -------------------------
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")


# -------------------------
# FILTERS (quality)
# -------------------------
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))


# -------------------------
# CSV STREAMING
# -------------------------
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "220"))


# -------------------------
# MEDIA
# -------------------------
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))


# -------------------------
# CAPTION / BRAND
# -------------------------
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #DIY #ShopeeAffiliate"
).strip()

HOOKS = [
    "⚡ สายช่างต้องมี ช่วยให้งานไวขึ้นจริง",
    "🏠 ของใช้ในบ้านที่ทำให้ชีวิตง่ายขึ้น",
    "✅ คัดของจำเป็นติดบ้าน ราคาโดน",
    "🔥 ของมันต้องมีติดบ้าน!",
    "🛠️ เครื่องมือ/อุปกรณ์ช่าง ใช้จริงคุ้มจริง",
]
BENEFITS = [
    "ใช้งานง่าย มือใหม่ก็ทำเองได้",
    "ประหยัดเวลา งานเสร็จไวขึ้น",
    "คุ้มราคา คุณภาพเกินตัว",
    "เหมาะกับใช้ในบ้าน/งานช่างทั่วไป",
    "ของจำเป็นติดบ้าน ใช้ได้บ่อย",
]
CTA = [
    "กดลิงก์ดูโปร/โค้ดส่วนลดตอนนี้เลย 👇",
    "ดูรีวิวจริง + ราคาล่าสุดในลิงก์ได้เลย ✅",
    "สนใจทักแชทได้ครับ เดี๋ยวช่วยเลือกให้ 💬",
]


# -------------------------
# PAGE LOCK: allow / block / category lock
# (แก้ให้หลุดเพจน้อยลงมาก)
# -------------------------
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|ปลั๊กพ่วง|รางปลั๊ก|สายไฟ|เบรกเกอร์|หลอดไฟ|โคม|สวิตช์|ปลั๊กกันไฟดูด|ตู้ไฟ|มิเตอร์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|โซลาร์|ชาร์จ|หัวชาร์จ|อะแดปเตอร์|รีเลย์|คอนแทค|เทปพันสาย|สายดิน|เครื่องมือ|สว่าน|ค้อน|ประแจ|คีม|ไขควง|เลื่อย|งานช่าง|ซ่อม|DIY|บ้าน|อุปกรณ์บ้าน|กาว|ซิลิโคน|เทปกาว|พัดลม|ไฟฉาย|อุปกรณ์แสงสว่าง)"
).strip()

BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(เสื้อผ้า|แฟชั่น|เครื่องสำอาง|สกินแคร์|น้ำหอม|ตุ๊กตา|ของเล่นเด็ก|ผ้าปู|ปลอกหมอน|ผ้านวม|ย้อมผม|วิกผม|กล้อง|แฟลช|เลนส์|คอนแทคเลนส์|อาหารเสริม|บุหรี่|แอลกอฮอล์)"
).strip()

ALLOW_CATEGORIES = os.getenv(
    "ALLOW_CATEGORIES",
    r"(Home|Tools|Hardware|Electrical|Lighting|DIY|Cables|Chargers|Converters|Power|Solar|Outdoor)"
).strip()

ALLOW_PAT = re.compile(ALLOW_KEYWORDS, flags=re.IGNORECASE) if ALLOW_KEYWORDS else None
BLOCK_PAT = re.compile(BLOCK_KEYWORDS, flags=re.IGNORECASE) if BLOCK_KEYWORDS else None
ALLOW_CAT_PAT = re.compile(ALLOW_CATEGORIES, flags=re.IGNORECASE) if ALLOW_CATEGORIES else None


# -------------------------
# STATE
# -------------------------
STATE_FILE = os.getenv("STATE_FILE", "state.json").strip()
MAX_STATE_ITEMS = int(os.getenv("MAX_STATE_ITEMS", "9000"))


def now_bkk() -> datetime:
    return datetime.now(TZ_BKK)


def parse_slot_today(now: datetime, hhmm: str) -> datetime:
    hh, mm = hhmm.split(":")
    return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)


def load_state() -> dict:
    base = {
        "used_links": [],
        "posted_slots": {},   # {"YYYY-MM-DD": ["08:00", ...]}
        "posted_at": {},      # {affiliate_link: iso}
        "first_run_done": False,
    }
    if not os.path.exists(STATE_FILE):
        return base
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
        if not isinstance(s, dict):
            return base
        s.setdefault("used_links", [])
        s.setdefault("posted_slots", {})
        s.setdefault("posted_at", {})
        s.setdefault("first_run_done", True)
        if not isinstance(s["used_links"], list):
            s["used_links"] = []
        if not isinstance(s["posted_slots"], dict):
            s["posted_slots"] = {}
        if not isinstance(s["posted_at"], dict):
            s["posted_at"] = {}
        return s
    except Exception:
        return base


def save_state(state: dict) -> None:
    used = state.get("used_links", [])
    if len(used) > MAX_STATE_ITEMS:
        state["used_links"] = used[-MAX_STATE_ITEMS:]
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
        if now >= parse_slot_today(now, hhmm) and hhmm not in posted:
            due.append(hhmm)
    return due


# -------------------------
# HTTP / GRAPH
# -------------------------
def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=headers, stream=stream)
    r.raise_for_status()
    return r


def graph_post(path: str, data=None, files=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    r = requests.post(url, params=params, data=data, files=files, timeout=(20, 120))
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: {js}")
    return js


# -------------------------
# Affiliate Link Builder
# -------------------------
def add_query(url: str, extra: Dict[str, str]) -> str:
    try:
        u = urlparse(url)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        q.update({k: v for k, v in extra.items() if v is not None and v != ""})
        return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(q), u.fragment))
    except Exception:
        return url


def build_affiliate_link(product_link: str, product_short: str) -> str:
    base = ""
    if product_short and str(product_short).strip():
        base = str(product_short).strip()
    elif product_link and str(product_link).strip():
        origin = str(product_link).strip()
        base = f"https://shopee.ee/an_redir?origin_link={quote(origin, safe='')}"
    else:
        return ""

    return add_query(base, {
        "affiliate_id": AFFILIATE_ID,
        "utm_source": AFF_UTM_SOURCE,
        "afftag": AFF_TAG,
    })


# -------------------------
# Product model
# -------------------------
@dataclass
class Product:
    title: str
    affiliate_link: str
    images: List[str]
    price: Optional[float]
    sale_price: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    category1: str
    category2: str
    category3: str


def fnum(x) -> Optional[float]:
    try:
        if x is None:
            return None
        s = str(x).strip().replace(",", "")
        return float(s) if s else None
    except Exception:
        return None


def extract_images(row: Dict) -> List[str]:
    imgs: List[str] = []
    for i in range(1, 11):
        v = str(row.get(f"image_link_{i}", "")).strip()
        if v.startswith("http"):
            imgs.append(v)

    v0 = str(row.get("image_link", "")).strip()
    if v0.startswith("http"):
        imgs.append(v0)

    addi = str(row.get("additional_image_link", "")).strip()
    if addi.startswith("http"):
        imgs.append(addi)

    seen = set()
    out = []
    for u in imgs:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def effective_price(p: Product) -> Optional[float]:
    return p.sale_price if p.sale_price is not None else p.price


def normalize_product(row: Dict) -> Product:
    title = str(row.get("title", "")).strip()

    product_link = str(row.get("product_link", "")).strip()
    product_short = str(row.get("product_short link", "")).strip()
    aff = build_affiliate_link(product_link, product_short)

    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))

    dp = fnum(row.get("discount_percentage"))
    if dp is None and price and sale_price and price > 0 and sale_price < price:
        dp = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating"))

    c1 = str(row.get("global_category1", "")).strip()
    c2 = str(row.get("global_category2", "")).strip()
    c3 = str(row.get("global_category3", "")).strip()

    return Product(
        title=title,
        affiliate_link=aff,
        images=extract_images(row),
        price=price,
        sale_price=sale_price,
        discount_pct=dp,
        rating=rating,
        category1=c1, category2=c2, category3=c3,
    )


def pass_page_lock(p: Product) -> bool:
    text = " ".join([p.title, p.category1, p.category2, p.category3]).strip()
    if BLOCK_PAT and BLOCK_PAT.search(text):
        return False
    ok_kw = bool(ALLOW_PAT.search(text)) if ALLOW_PAT else True
    ok_cat = bool(ALLOW_CAT_PAT.search(text)) if ALLOW_CAT_PAT else True
    return ok_kw or ok_cat


def product_pass(p: Product) -> bool:
    if not p.title:
        return False
    if not p.affiliate_link:
        return False
    if len(p.images) < 1:
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

    if not pass_page_lock(p):
        return False

    return True


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def score_product(p: Product) -> float:
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    ep = effective_price(p) or 999.0

    r_score = clamp((r - 4.0) / 1.0, 0, 1)
    d_score = clamp(d / 70.0, 0, 1)

    price_score = 1.0 - clamp((ep - PRICE_MIN) / max(1.0, (PRICE_MAX - PRICE_MIN)), 0, 1) * 0.12
    base = (0.62 * r_score) + (0.38 * d_score)
    base *= price_score
    base *= random.uniform(0.97, 1.03)
    return base


def stream_top_products(csv_url: str) -> List[Tuple[float, Product]]:
    print("INFO: Streaming Shopee CSV ...")
    r = http_get(
        csv_url,
        timeout=(25, 240),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"},
        stream=True
    )
    r.raw.decode_content = True

    text_stream = io.TextIOWrapper(r.raw, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.DictReader(text_stream)

    top: List[Tuple[float, Product]] = []
    rows = 0
    kept = 0

    for row in reader:
        rows += 1
        if rows > STREAM_MAX_ROWS:
            print(f"INFO: Stop at STREAM_MAX_ROWS={STREAM_MAX_ROWS}")
            break

        p = normalize_product(row)
        if not product_pass(p):
            continue

        sc = score_product(p)
        kept += 1

        if len(top) < TOPK_POOL:
            top.append((sc, p))
        else:
            worst_i = min(range(len(top)), key=lambda i: top[i][0])
            if sc > top[worst_i][0]:
                top[worst_i] = (sc, p)

        if rows % 50000 == 0:
            print(f"INFO: rows={rows} kept={kept} top_pool={len(top)}")

    print(f"INFO: Done rows={rows} kept={kept} top_pool={len(top)}")
    if not top:
        raise SystemExit("ERROR: No usable products found. ปรับ ALLOW/BLOCK หรือ MIN_* ได้")
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
    used = set(state.get("used_links", []))
    posted_at = state.get("posted_at", {})
    cutoff = now - timedelta(days=REPOST_AFTER_DAYS)

    def fresh(p: Product) -> bool:
        if p.affiliate_link in used:
            return False
        iso = posted_at.get(p.affiliate_link)
        if not iso:
            return True
        try:
            t = datetime.fromisoformat(iso)
            if t.tzinfo is None:
                t = t.replace(tzinfo=TZ_BKK)
            return t <= cutoff
        except Exception:
            return True

    pool = [(sc, p) for sc, p in top_items if fresh(p)]
    if not pool:
        pool = top_items

    chosen = weighted_choice(pool)
    state.setdefault("used_links", []).append(chosen.affiliate_link)
    state.setdefault("posted_at", {})[chosen.affiliate_link] = now.isoformat()
    return chosen


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

    ep = effective_price(p)
    if p.sale_price is not None and p.price is not None and p.sale_price < p.price:
        price_line = f"💸 โปรวันนี้: {fmt_money(p.sale_price)} บาท (ปกติ {fmt_money(p.price)} | ลด {fmt_pct(p.discount_pct)})"
    else:
        price_line = f"💸 ราคา: {fmt_money(ep)} บาท | ลด {fmt_pct(p.discount_pct)}"

    rating_line = f"⭐ เรตติ้ง: {p.rating:.1f}/5" if p.rating is not None else "⭐ เรตติ้ง: -"

    cat = " / ".join([c for c in [p.category1, p.category2] if c][:2]).strip()
    cat_line = f"🏠 หมวด: {cat}" if cat else ""

    parts = [
        f"🏠⚡ {BRAND}",
        hook,
        "",
        f"🛒 {p.title}",
        cat_line,
        "",
        price_line,
        rating_line,
        "",
        f"✅ จุดเด่น: {benefit}",
        "✅ ดูรูป/รีวิวจริงก่อนซื้อได้",
        "",
        "👇 ลิงก์นายหน้า (กดแล้วเปิดในแอป Shopee ได้เลย)",
        p.affiliate_link,
        "",
        cta,
        "",
        HASHTAGS,
    ]

    out = []
    for s in parts:
        s = (s or "").strip()
        if s == "" and (not out or out[-1] == ""):
            continue
        out.append(s)
    return "\n".join(out).strip()


# -------------------------
# Facebook posting (images)
# -------------------------
def download_image_bytes(url: str) -> bytes:
    r = http_get(url, timeout=(20, 120), headers={"User-Agent": "Mozilla/5.0"}, stream=True)
    return r.content


def upload_unpublished_photo(image_bytes: bytes) -> str:
    files = {"source": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"published": "false"}
    js = graph_post(f"/{PAGE_ID}/photos", data=data, files=files)
    return js["id"]


def create_feed_post_with_media(message: str, media_fbids: List[str]) -> str:
    data = {"message": message}
    for i, mid in enumerate(media_fbids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    js = graph_post(f"/{PAGE_ID}/feed", data=data)
    return js["id"]


def post_images(p: Product, caption: str) -> str:
    imgs = p.images[:POST_IMAGES_COUNT]
    if not imgs:
        raise RuntimeError("No images to post")

    media_ids = []
    for u in imgs:
        b = download_image_bytes(u)
        mid = upload_unpublished_photo(b)
        media_ids.append(mid)
        time.sleep(1.2)

    post_id = create_feed_post_with_media(caption, media_ids)
    return post_id


def main():
    now = now_bkk()
    print("==== V31 ULTRA LOCK ====")
    print("INFO: Now(BKK) =", now.isoformat())
    print("INFO: Graph =", GRAPH_VERSION)
    print("INFO: Slots(BKK) =", SLOTS_BKK)

    state = load_state()

    # Decide slot
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        slot_used = "FIRST_RUN"
        print("INFO: First run -> post 1 immediately.")
    else:
        due = due_slots_today(state, now)
        if not due and not FORCE_POST:
            print("INFO: No due slot. Exit. (FORCE_POST=1 to test)")
            return
        slot_used = due[0] if due else "MANUAL"
        if slot_used != "MANUAL":
            print("INFO: Due slots =", due, "-> using slot", slot_used)
        else:
            print("INFO: FORCE_POST manual")

    top_items = stream_top_products(SHOPEE_CSV_URL)

    posts_done = 0
    for _ in range(POSTS_MAX_PER_RUN):
        p = pick_product(top_items, state, now)
        caption = build_caption(p)

        print("INFO: Picked:", p.title[:90], "| images:", len(p.images))
        post_id = post_images(p, caption)
        print("OK: Posted feed id =", post_id)

        if slot_used not in ("MANUAL", ""):
            mark_slot_posted(state, now, slot_used)
        if slot_used == "FIRST_RUN":
            state["first_run_done"] = True

        posts_done += 1
        time.sleep(4)

    save_state(state)
    print("INFO: Done. posts_done =", posts_done)


if __name__ == "__main__":
    main()
