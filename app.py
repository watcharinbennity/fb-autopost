import os
import io
import json
import random
import time
import csv
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests

# =========================
# CONFIG
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0")  # ✅ v25.0
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = "state.json"
MAX_STATE_ITEMS = 9000

CSV_CONNECT_TIMEOUT = 25
CSV_READ_TIMEOUT = 180

IMG_CONNECT_TIMEOUT = 20
IMG_READ_TIMEOUT = 80

GRAPH_CONNECT_TIMEOUT = 20
GRAPH_READ_TIMEOUT = 80

POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
END_MONTH_BOOST_DAYS = int(os.getenv("END_MONTH_BOOST_DAYS", "3"))
POSTS_THIS_RUN = int(os.getenv("POSTS_THIS_RUN", "1"))

MIN_RATING = float(os.getenv("MIN_RATING", "4.7"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "20"))
MIN_SOLD = int(os.getenv("MIN_SOLD", "80"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "79"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "1990"))

STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "300000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "250"))

SLOTS_BKK = ["09:00", "12:15", "15:30", "18:30", "21:00"]

HASHTAGS = [
    "#BENHomeElectrical",
    "#ของใช้ในบ้าน",
    "#อุปกรณ์ไฟฟ้า",
    "#เครื่องมือช่าง",
    "#งานช่าง",
    "#ซ่อมบ้าน",
    "#ของดีบอกต่อ",
    "#ShopeeAffiliate",
]

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
    "รีวิวดี มีคนซื้อซ้ำเยอะ",
]

CTA = [
    "กดลิงก์ดูโปร/โค้ดส่วนลดตอนนี้เลย 👇",
    "ดูรีวิวจริง + ราคาล่าสุดในลิงก์ได้เลย ✅",
    "สนใจทักแชทได้ครับ เดี๋ยวช่วยเลือกให้ 💬",
]

# =========================
# ENV
# =========================
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL")

if not PAGE_ID:
    raise SystemExit("ERROR: Missing env: PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    raise SystemExit("ERROR: Missing env: PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    raise SystemExit("ERROR: Missing env: SHOPEE_CSV_URL")


# =========================
# TIME / STATE
# =========================
def now_bkk() -> datetime:
    return datetime.now(timezone(timedelta(hours=7)))

def parse_slot_today_bkk(now: datetime, hhmm: str) -> datetime:
    hh, mm = hhmm.split(":")
    return now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)

def is_end_month_boost(now: datetime) -> bool:
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    last_day = next_month - timedelta(days=1)
    return (last_day.day - now.day) < END_MONTH_BOOST_DAYS

def is_campaign_day(now: datetime) -> bool:
    md = f"{now.month}.{now.day}"
    return md in {f"{m}.{m}" for m in range(1, 13)} or now.day in {15, 25}

def load_state() -> dict:
    base = {"used_urls": [], "posted_slots": {}}
    if not os.path.exists(STATE_FILE):
        return base
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
        if not isinstance(s, dict):
            return base
        s.setdefault("used_urls", s.get("used_ids", []))
        s.setdefault("posted_slots", {})
        if not isinstance(s["used_urls"], list):
            s["used_urls"] = []
        if not isinstance(s["posted_slots"], dict):
            s["posted_slots"] = {}
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
def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=headers, stream=stream)
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


# =========================
# PRODUCT
# =========================
@dataclass
class Product:
    name: str
    url: str
    images: List[str]
    price: Optional[float]
    sale_price: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    sold: Optional[int]
    raw: Dict

def fnum(x) -> Optional[float]:
    try:
        if x is None: return None
        s = str(x).strip().replace(",", "")
        if s == "": return None
        return float(s)
    except Exception:
        return None

def fint(x) -> Optional[int]:
    try:
        if x is None: return None
        s = str(x).strip().replace(",", "")
        if s == "": return None
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
    seen = set()
    out = []
    for u in imgs:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def normalize_row(row: Dict) -> Product:
    name = (row.get("name") or row.get("title") or "").strip()
    url = (row.get("url") or row.get("product_link") or "").strip()
    images = extract_images(row)

    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))

    dp = fnum(row.get("discount_percentage"))
    if dp is None and price and sale_price and price > 0:
        dp = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))
    sold = fint(row.get("item_sold")) or fint(row.get("historical_sold")) or fint(row.get("sold"))

    return Product(name, url, images, price, sale_price, dp, rating, sold, row)

def effective_price(p: Product) -> Optional[float]:
    return p.sale_price if p.sale_price is not None else p.price

def product_pass(p: Product) -> bool:
    if not p.name or not p.url or len(p.images) < 1:
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

    r_score = clamp((r - 4.0) / 1.0, 0, 1)     # 4..5
    d_score = clamp(d / 70.0, 0, 1)            # 0..70
    s_score = clamp((s ** 0.5) / 70.0, 0, 1)   # sqrt scale
    price_score = 1.0 - clamp((ep - PRICE_MIN) / max(1.0, (PRICE_MAX - PRICE_MIN)), 0, 1) * 0.15
    # ↑ ของถูกนิดหน่อยได้เปรียบ แต่ไม่บ้า

    base = (0.46 * r_score) + (0.34 * d_score) + (0.20 * s_score)
    base *= price_score

    if is_campaign_day(now):
        base *= 1.15
    if is_end_month_boost(now):
        base *= 1.08

    base *= random.uniform(0.97, 1.03)
    return base


# =========================
# CSV STREAMING (TOUGH)
# =========================
def stream_top_products(url: str, now: datetime) -> List[Tuple[float, Product]]:
    print("INFO: Streaming Shopee CSV (tough mode)...")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,application/octet-stream,*/*",
        "Connection": "keep-alive",
    }
    r = http_get(url, timeout=(CSV_CONNECT_TIMEOUT, CSV_READ_TIMEOUT), headers=headers, stream=True)
    r.raw.decode_content = True

    print(f"INFO: content-type={r.headers.get('content-type','')} content-length={r.headers.get('content-length','')}")
    text_stream = io.TextIOWrapper(r.raw, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.DictReader(text_stream)

    top: List[Tuple[float, Product]] = []
    seen_rows = 0
    kept = 0

    for row in reader:
        seen_rows += 1
        if seen_rows > STREAM_MAX_ROWS:
            print(f"INFO: stop at STREAM_MAX_ROWS={STREAM_MAX_ROWS}")
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

        if seen_rows % 50000 == 0:
            print(f"INFO: rows={seen_rows} kept={kept} top_pool={len(top)}")

    print(f"INFO: done rows={seen_rows} kept={kept} top_pool={len(top)}")
    if not top:
        raise SystemExit("ERROR: No usable products after filters. (ลองลด MIN_* หรือขยายราคา)")
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


# =========================
# CAPTION (TH SELLING)
# =========================
def fmt_money(x: Optional[float]) -> str:
    if x is None: return "-"
    return f"{x:,.0f}"

def fmt_pct(x: Optional[float]) -> str:
    if x is None: return "-"
    return f"{x:.0f}%"

def build_caption(p: Product, now: datetime) -> str:
    hook = random.choice(HOOKS)
    benefit = random.choice(BENEFITS)
    cta = random.choice(CTA)

    campaign = is_campaign_day(now)
    boost = is_end_month_boost(now)

    ep = effective_price(p)
    price_line = ""
    if p.sale_price is not None and p.price is not None and p.sale_price < p.price:
        price_line = f"💸 โปรวันนี้: {fmt_money(p.sale_price)} บาท (ปกติ {fmt_money(p.price)} | ลด {fmt_pct(p.discount_pct)})"
    else:
        price_line = f"💸 ราคา: {fmt_money(ep)} บาท | ลด {fmt_pct(p.discount_pct)}"

    rating_line = f"⭐ เรตติ้ง: {p.rating:.1f}/5" if p.rating is not None else "⭐ เรตติ้ง: -"
    sold_line = f"📦 ขายแล้ว: {p.sold:,} ชิ้น" if p.sold is not None else "📦 ขายแล้ว: -"

    urgency = []
    if campaign:
        urgency.append("🎉 รอบแคมเปญ! โค้ดส่วนลด/โปรเปลี่ยนไว รีบเช็คในลิงก์")
    if boost:
        urgency.append("🔥 ปลายเดือนของจำเป็น คุ้ม ๆ ชิ้นนี้น่าเก็บ")

    tags = " ".join(HASHTAGS)

    parts = [
        hook,
        "",
        f"🛒 {p.name}",
        "",
        price_line,
        rating_line,
        sold_line,
        "",
        f"✅ จุดเด่น: {benefit}",
        "✅ เหมาะกับบ้าน/งานช่าง ใช้ได้บ่อย",
        "✅ ดูรีวิว+รูปจริงก่อนซื้อได้ในลิงก์",
        "",
        *urgency,
        "",
        f"👉 {p.url}",
        "",
        cta,
        "",
        tags
    ]

    out = []
    for s in parts:
        if s == "" and (not out or out[-1] == ""):
            continue
        out.append(s)
    return "\n".join(out).strip()


# =========================
# FACEBOOK POST
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
    for i, mid in enumerate(media_fbids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    js = graph_post(f"/{page_id}/feed", data=data)
    return js["id"]

def post_product(p: Product, now: datetime) -> str:
    caption = build_caption(p, now)
    imgs = p.images[:POST_IMAGES_COUNT]
    media_ids = []
    for u in imgs:
        img_bytes = download_image_bytes(u)
        mid = upload_unpublished_photo(PAGE_ID, img_bytes)
        media_ids.append(mid)
    return create_feed_post_with_media(PAGE_ID, caption, media_ids)


# =========================
# MAIN
# =========================
def main():
    print("==== V17 THAILAND ULTRA PRO ====")
    now = now_bkk()
    print(f"INFO: Now (BKK) = {now.isoformat()}")
    print(f"INFO: Graph = {GRAPH_VERSION}")
    print(f"INFO: Campaign day = {is_campaign_day(now)} | End-month boost = {is_end_month_boost(now)}")
    print(f"INFO: Schedule slots = {SLOTS_BKK}")

    state = load_state()
    due = due_slots_today(state, now)
    if due:
        print(f"INFO: Due slots today (catch-up) = {due}")
    else:
        print("INFO: No due slots for past times -> exit (unless FORCE_POST=1)")
        if os.getenv("FORCE_POST", "").strip().lower() not in ("1", "true", "yes"):
            return

    top_items = stream_top_products(SHOPEE_CSV_URL, now)

    for _ in range(POSTS_THIS_RUN):
        slot_used = None
        if due:
            slot_used = due.pop(0)
            print(f"INFO: Posting for due slot = {slot_used}")

        p = pick_product(top_items, state)
        print(f"INFO: Picked: {p.name[:80]} | rating={p.rating} discount={p.discount_pct} sold={p.sold} price={effective_price(p)}")

        post_id = post_product(p, now)
        print(f"OK: Posted feed id = {post_id}")

        if slot_used:
            mark_slot_posted(state, now, slot_used)

        time.sleep(5)

    save_state(state)
    print("INFO: done.")

if __name__ == "__main__":
    main()
