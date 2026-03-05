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
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse, quote

import requests

# =========================================================
# V30.2 ULTRA — BEN Home & Electrical Shopee Affiliate Autopost
# Graph: v25.0
# FIX:
# - REMOVE "ขายแล้ว" line completely
# - Stronger filtering to match page niche (block camera/flash/etc.)
# - Category allow + keyword allow + keyword block
# - Catch-up posting if past slot not posted
# - First run posts 1 post
# =========================================================

# =========================
# CONFIG (ENV)
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = os.getenv("STATE_FILE", "state.json")
MAX_STATE_ITEMS = int(os.getenv("MAX_STATE_ITEMS", "9000"))

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

# Shopee Affiliate (ค่าหน้านาย)
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()

# Timezone Bangkok
TZ_BKK = timezone(timedelta(hours=7))

# เวลาโพสต์ (BKK)
SLOTS_BKK = os.getenv("SLOTS_BKK", "09:00,12:00,18:30,21:00").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

# Filters
MIN_RATING = float(os.getenv("MIN_RATING", "4.7"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "15"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))

# Media
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))

# CSV streaming
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "220"))

# Caption
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate"
).strip()

# Keyword filters (เข้มขึ้น)
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|ปลั๊กพ่วง|สายไฟ|เบรกเกอร์|หลอดไฟ|โคม|สวิตช์|เต้ารับ|มิเตอร์|กราวด์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|ชาร์จ|หัวชาร์จ|อะแดปเตอร์|สายชาร์จ|พาวเวอร์แบงค์|เครื่องมือ|สว่าน|ค้อน|ประแจ|คีม|ไขควง|ตลับเมตร|คัตเตอร์|เทปพันสายไฟ|กาว|ซิลิโคน|พุก|น็อต|รีเวท|งานช่าง|ซ่อม|DIY|อุปกรณ์ติดตั้ง|อุปกรณ์ไฟฟ้า)"
).strip()

# บล็อกของหลุดหมวด (เพิ่ม: กล้อง/แฟลช/ถ่ายภาพ/แฟชั่น/เตียงนอน/ย้อมผม ฯลฯ)
BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(กางเกง|เสื้อ|แฟชั่น|กระเป๋า|รองเท้า|เครื่องสำอาง|สกินแคร์|น้ำหอม|ย้อมผม|ครีม|ลิป|เล็บ|ขนตา|คอนแทคเลนส์|อาหารเสริม|บุหรี่|แอลกอฮอล์|ชุดผ้าปู|ที่นอน|หมอน|ผ้าห่ม|ตุ๊กตา|ของเล่นเด็ก|เกม|กล้อง|camera|flash|godox|ttl|hss|lens|tripod|drone|apex|coros|band|strap|watch)"
).strip()

# Category allow (เอาเฉพาะหมวดที่เข้ากับเพจ)
# ถ้าหมวดใน CSV เป็นอังกฤษ เช่น "Cables, Chargers & Converters" จะผ่าน
CATEGORY_ALLOW = os.getenv(
    "CATEGORY_ALLOW",
    r"(Cables|Chargers|Converters|Lighting|Home Improvement|Tools|Hardware|Electrical|Power|Batteries|Solar|DIY|Repair|เครื่องมือ|ช่าง|ไฟฟ้า|อุปกรณ์ไฟฟ้า|หลอดไฟ|ปลั๊ก|สายไฟ|เบรกเกอร์|สวิตช์)"
).strip()

# Timeouts
CSV_TIMEOUT = (25, 180)
IMG_TIMEOUT = (20, 80)
GRAPH_TIMEOUT = (20, 80)

# =========================
# GUARDS
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
        "posted_slots": {},
        "posted_at": {},
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
    r = SESSION.post(url, params=params, data=data, files=files, timeout=GRAPH_TIMEOUT)
    js = r.json()
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: {js}")
    return js

# =========================
# AFFILIATE LINK
# =========================
def ensure_aff_params(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url

    def with_params(base_url: str) -> str:
        u = urlparse(base_url)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        q["affiliate_id"] = AFFILIATE_ID
        q["utm_source"] = AFF_UTM_SOURCE
        q["afftag"] = AFF_TAG
        new_q = urlencode(q, doseq=True)
        return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))

    if "shope.ee/an_redir" in url:
        return with_params(url)

    if "shopee.co.th/" in url and "/product/" in url:
        origin = url
        redir = "https://shope.ee/an_redir?origin_link=" + quote(origin, safe="")
        return with_params(redir)

    return with_params(url)

# =========================
# PRODUCT
# =========================
@dataclass
class Product:
    title: str
    product_link: str
    product_short: str
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

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

ALLOW_RE = re.compile(ALLOW_KEYWORDS, flags=re.IGNORECASE) if ALLOW_KEYWORDS else None
BLOCK_RE = re.compile(BLOCK_KEYWORDS, flags=re.IGNORECASE) if BLOCK_KEYWORDS else None
CAT_ALLOW_RE = re.compile(CATEGORY_ALLOW, flags=re.IGNORECASE) if CATEGORY_ALLOW else None

def extract_images(row: Dict) -> List[str]:
    imgs = []
    for k in ["image_link", "image_link_3", "image_link_4", "image_link_5", "image_link_6",
              "image_link_7", "image_link_8", "image_link_9", "image_link_10"]:
        v = str(row.get(k, "")).strip()
        if v:
            imgs.append(v)

    addi = str(row.get("additional_image_link", "")).strip()
    if addi.startswith("http"):
        imgs.append(addi)

    seen = set()
    out = []
    for u in imgs:
        if u and u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def normalize_row(row: Dict) -> Product:
    title = (row.get("title") or row.get("name") or "").strip()
    product_link = (row.get("product_link") or row.get("url") or "").strip()
    product_short = (row.get("product_short link") or row.get("product_short_link") or row.get("product_short") or "").strip()

    images = extract_images(row)

    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))
    discount_pct = fnum(row.get("discount_percentage"))
    if discount_pct is None and price and sale_price and price > 0 and sale_price < price:
        discount_pct = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))

    cat1 = str(row.get("global_category1", "")).strip()
    cat2 = str(row.get("global_category2", "")).strip()
    cat3 = str(row.get("global_category3", "")).strip()
    brand = str(row.get("global_brand", "")).strip()
    category_text = " ".join([x for x in [cat1, cat2, cat3, brand] if x])

    return Product(
        title=title,
        product_link=product_link,
        product_short=product_short,
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

def pass_filters(p: Product) -> bool:
    if not p.title:
        return False
    if not p.images:
        return False

    ep = effective_price(p)
    if ep is None or not (PRICE_MIN <= ep <= PRICE_MAX):
        return False

    if p.rating is not None and p.rating < MIN_RATING:
        return False
    if p.discount_pct is not None and p.discount_pct < MIN_DISCOUNT_PCT:
        return False

    blob = f"{p.title} {p.category_text}".strip()

    if BLOCK_RE and BLOCK_RE.search(blob):
        return False
    if ALLOW_RE and not ALLOW_RE.search(blob):
        return False

    # Category allow (กันของหลุดหมวดแบบเข้ม)
    if CAT_ALLOW_RE and not CAT_ALLOW_RE.search(p.category_text):
        return False

    return True

def score_product(p: Product) -> float:
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    ep = effective_price(p) or PRICE_MAX

    r_score = clamp((r - 4.0) / 1.0, 0, 1)
    d_score = clamp(d / 70.0, 0, 1)
    price_score = 1.0 - clamp((ep - PRICE_MIN) / max(1.0, (PRICE_MAX - PRICE_MIN)), 0, 1) * 0.15

    base = (0.60 * r_score) + (0.40 * d_score)
    base *= price_score
    base *= random.uniform(0.97, 1.03)
    return base

# =========================
# CSV STREAMING
# =========================
def stream_top_products(csv_url: str, now: datetime, state: dict) -> List[Tuple[float, Product]]:
    print("INFO: Streaming Shopee CSV ...")
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*", "Connection": "keep-alive"}

    r = http_get(csv_url, timeout=CSV_TIMEOUT, headers=headers, stream=True)
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
        if not pass_filters(p):
            continue

        key_url = (p.product_short or p.product_link).strip()
        last_iso = state.get("posted_at", {}).get(key_url)
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=TZ_BKK)
                if now - last_dt < timedelta(days=REPOST_AFTER_DAYS):
                    continue
            except Exception:
                pass

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
        raise SystemExit("ERROR: No usable products found. (ลองลด MIN_* หรือปรับ CATEGORY_ALLOW/BLOCK_KEYWORDS)")
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
    fresh = [(sc, p) for sc, p in top_items if (p.product_short or p.product_link) not in used]
    pool = fresh if fresh else top_items

    chosen = weighted_choice(pool)
    chosen_key = (chosen.product_short or chosen.product_link).strip()
    if chosen_key:
        state.setdefault("used_urls", []).append(chosen_key)
    return chosen

# =========================
# CAPTION (NO "ขายแล้ว")
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
    "วัสดุดี ใช้ได้นาน",
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
    aff_url = ensure_aff_params(p.product_short or p.product_link)

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
        "👉 " + aff_url,
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
# FACEBOOK POST: IMAGES
# =========================
def download_image_bytes(url: str) -> bytes:
    r = http_get(url, timeout=IMG_TIMEOUT, stream=True, headers={"User-Agent": "Mozilla/5.0"})
    return r.content

def upload_unpublished_photo(page_id: str, image_bytes: bytes) -> str:
    files = {"source": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"published": "false"}
    js = graph_post(f"/{page_id}/photos", data=data, files=files)
    return js["id"]

def create_feed_post_with_media(page_id: str, message: str, media_fbids: List[str]) -> str:
    data = {"message": message, "published": "true"}
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

# =========================
# MAIN
# =========================
def main():
    now = now_bkk()
    print("==== V30.2 ULTRA ====")
    print("INFO: Now(BKK) =", now.isoformat())
    print("INFO: Graph =", GRAPH_VERSION)
    print("INFO: SLOTS_BKK =", SLOTS_BKK)
    print("INFO: Affiliate =", AFFILIATE_ID, "| utm_source =", AFF_UTM_SOURCE, "| afftag =", AFF_TAG)

    state = load_state()

    # First run -> post 1 immediately
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        print("INFO: First run detected -> will post 1 immediately.")
        slot_used = "FIRST_RUN"
    else:
        due = due_slots_today(state, now)
        if not due and not FORCE_POST:
            print("INFO: No due slot. Exit. (Set FORCE_POST=1 to test)")
            return
        slot_used = due[0] if due else "MANUAL"
        print("INFO: slot_used =", slot_used)

    top_items = stream_top_products(SHOPEE_CSV_URL, now, state)

    posts_target = 1 if slot_used == "FIRST_RUN" else max(1, POSTS_MAX_PER_RUN)
    posts_done = 0

    for _ in range(posts_target):
        p = pick_product(top_items, state)
        caption = build_caption(p)

        print("INFO: Picked:", p.title[:90], "| rating:", p.rating, "| discount:", p.discount_pct)
        print("INFO: Category:", p.category_text)

        post_id = post_images(p, caption)
        print("OK: Posted FEED id =", post_id)

        key_url = (p.product_short or p.product_link).strip()
        if key_url:
            state.setdefault("posted_at", {})[key_url] = now.isoformat()

        if slot_used not in ("MANUAL", "FIRST_RUN"):
            mark_slot_posted(state, now, slot_used)

        posts_done += 1
        time.sleep(5)

    if slot_used == "FIRST_RUN":
        state["first_run_done"] = True

    save_state(state)
    print("INFO: Done. posts_done =", posts_done)

if __name__ == "__main__":
    main()
