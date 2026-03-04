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
MAX_STATE_ITEMS = 8000

CSV_CONNECT_TIMEOUT = 20
CSV_READ_TIMEOUT = 120
IMG_CONNECT_TIMEOUT = 20
IMG_READ_TIMEOUT = 60
GRAPH_CONNECT_TIMEOUT = 20
GRAPH_READ_TIMEOUT = 60

POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
END_MONTH_BOOST_DAYS = int(os.getenv("END_MONTH_BOOST_DAYS", "3"))
POSTS_THIS_RUN = int(os.getenv("POSTS_THIS_RUN", "1"))

# Filters (ขายง่าย)
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "15"))
MIN_SOLD = int(os.getenv("MIN_SOLD", "50"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "79"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "1999"))

# CSV streaming limits
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "200"))

# Post schedule (BKK)
SLOTS_BKK = ["09:00", "12:15", "15:30", "18:30", "21:00"]

HASHTAGS = [
    "#BENHomeElectrical",
    "#BENHomeElectricalTH",
    "#ของใช้ในบ้าน",
    "#อุปกรณ์ไฟฟ้า",
    "#เครื่องมือช่าง",
    "#งานช่าง",
    "#ซ่อมบ้าน",
    "#ของดีบอกต่อ",
    "#ShopeeAffiliate",
]

SELLING_HOOKS = [
    "ของมันต้องมีติดบ้าน 🏡",
    "งานช่างเล็ก-ใหญ่ ทำเองได้ง่ายขึ้น 🔧",
    "คัดมาให้แล้ว ราคาโดน คุณภาพดี 💪",
    "พร้อมส่ง ใช้งานได้จริง 👍",
    "ของเข้าไว หมดไว ทักมาก่อนนะ 🔥",
    "ตัวฮิตของสายช่าง/บ้าน ใช้แล้วคุ้มแน่นอน ⚡",
]

CTA_LINES = [
    "สนใจทักแชทได้เลยครับ 💬",
    "กดลิงก์ดูรายละเอียด/สั่งซื้อได้ทันที ✅",
    "มีโปร/โค้ดส่วนลดเปลี่ยนตามรอบ กดเช็คในลิงก์เลย 🎟️",
    "ดูรีวิวจริง + ราคา ณ ตอนนี้ในลิงก์ได้เลย 👇",
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
        # Backward-compat safety
        if not isinstance(s, dict):
            return base
        s.setdefault("used_urls", s.get("used_ids", []))  # support old key
        s.setdefault("posted_slots", {})
        if "used_ids" in s and "used_urls" not in s:
            s["used_urls"] = s["used_ids"]
        # normalize types
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
# HTTP
# =========================
def http_get(url: str, timeout=(20, 120), headers=None, stream=False) -> requests.Response:
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
# PRODUCT MODEL
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
    # image_link_1..10 (บางไฟล์อาจเริ่มที่ 3)
    for i in range(1, 11):
        k = f"image_link_{i}"
        v = str(row.get(k, "")).strip()
        if v:
            imgs.append(v)
    # fallback: image_link
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


def normalize_row(row: Dict) -> Product:
    name = (row.get("name") or row.get("title") or "").strip()
    url = (row.get("url") or row.get("product_link") or "").strip()
    images = extract_images(row)

    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))

    # discount: prefer discount_percentage from shopee csv
    dp = fnum(row.get("discount_percentage"))
    if dp is None and price and sale_price and price > 0:
        dp = (price - sale_price) * 100.0 / price

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))
    sold = fint(row.get("item_sold")) or fint(row.get("historical_sold")) or fint(row.get("sold"))

    return Product(
        name=name,
        url=url,
        images=images,
        price=price,
        sale_price=sale_price,
        discount_pct=dp,
        rating=rating,
        sold=sold,
        raw=row,
    )


def product_pass(p: Product) -> bool:
    if not p.name or not p.url:
        return False
    if len(p.images) < 1:
        return False

    # price range check (use sale_price if available else price)
    effective_price = p.sale_price if p.sale_price is not None else p.price
    if effective_price is None:
        return False
    if not (PRICE_MIN <= effective_price <= PRICE_MAX):
        return False

    # rating/sold/discount may be missing in some rows -> allow but score lower
    if p.rating is not None and p.rating < MIN_RATING:
        return False
    if p.sold is not None and p.sold < MIN_SOLD:
        return False
    if p.discount_pct is not None and p.discount_pct < MIN_DISCOUNT_PCT:
        return False

    return True


def score_product(p: Product, now: datetime) -> float:
    """
    คะแนน: เน้นขายง่าย
    - rating สูง
    - ส่วนลดสูง
    - sold สูง
    - แคมเปญวัน (1.1/2.2/..12.12 + 15 + 25) boost
    - ปลายเดือน boost
    """
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    s = p.sold if p.sold is not None else 0

    # normalize
    r_score = clamp((r - 4.0) / 1.0, 0, 1)  # 4.0..5.0
    d_score = clamp(d / 60.0, 0, 1)         # 0..60%
    s_score = clamp((s ** 0.5) / 60.0, 0, 1)  # sqrt scale

    base = (0.45 * r_score) + (0.35 * d_score) + (0.20 * s_score)

    if is_campaign_day(now):
        base *= 1.12
    if is_end_month_boost(now):
        base *= 1.08

    # small randomness to diversify
    base *= random.uniform(0.97, 1.03)
    return base


# =========================
# CSV STREAMING (NO FULL LOAD)
# =========================
def stream_products_from_csv(url: str, now: datetime, max_rows: int) -> List[Tuple[float, Product]]:
    print("INFO: Streaming Shopee CSV ...")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,application/octet-stream,*/*",
    }
    r = http_get(url, timeout=(CSV_CONNECT_TIMEOUT, CSV_READ_TIMEOUT), headers=headers, stream=True)

    # Some servers gzip; requests handles if decode_content True
    r.raw.decode_content = True
    ctype = r.headers.get("content-type", "")
    clen = r.headers.get("content-length", "")
    print(f"INFO: CSV headers: content-type={ctype} content-length={clen}")

    # Convert stream bytes -> text lines
    text_stream = io.TextIOWrapper(r.raw, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.DictReader(text_stream)

    top: List[Tuple[float, Product]] = []
    rows_seen = 0

    for row in reader:
        rows_seen += 1
        if rows_seen > max_rows:
            print(f"INFO: Stop streaming at max_rows={max_rows}")
            break

        p = normalize_row(row)
        if not product_pass(p):
            continue

        sc = score_product(p, now)

        # Keep topK by score (small pool) to later do weighted random
        if len(top) < TOPK_POOL:
            top.append((sc, p))
        else:
            # replace worst if current better
            worst_i = min(range(len(top)), key=lambda i: top[i][0])
            if sc > top[worst_i][0]:
                top[worst_i] = (sc, p)

        if rows_seen % 50000 == 0:
            print(f"INFO: rows_seen={rows_seen} | top_pool={len(top)}")

    print(f"INFO: rows_seen={rows_seen} | top_pool={len(top)}")
    return top


def weighted_choice(items: List[Tuple[float, Product]]) -> Product:
    # weights = scores
    total = sum(max(0.001, sc) for sc, _ in items)
    pick = random.uniform(0, total)
    upto = 0.0
    for sc, p in items:
        w = max(0.001, sc)
        upto += w
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
# CAPTION
# =========================
def fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "-"
    try:
        return f"{x:,.0f}"
    except Exception:
        return str(x)


def fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "-"
    try:
        return f"{x:.0f}%"
    except Exception:
        return str(x)


def build_caption(p: Product, now: datetime) -> str:
    opener = random.choice(SELLING_HOOKS)
    cta = random.choice(CTA_LINES)

    boost = is_end_month_boost(now)
    campaign = is_campaign_day(now)

    promo_lines = []
    if campaign:
        promo_lines.append("🎉 รอบแคมเปญประจำเดือน! เช็คโค้ด/โปรในลิงก์ตอนนี้คุ้มสุด ๆ")
    if boost:
        promo_lines.append("🔥 โค้งสุดท้ายปลายเดือน ของจำเป็นจัดให้คุ้ม ๆ")

    # info lines (ราคา/ส่วนลด/เรตติ้ง/ยอดขาย)
    price_line = ""
    if p.sale_price is not None and p.price is not None and p.sale_price < p.price:
        price_line = f"💸 ราคาโปร: {fmt_money(p.sale_price)} บาท (ปกติ {fmt_money(p.price)} | ลด {fmt_pct(p.discount_pct)})"
    else:
        effective = p.sale_price if p.sale_price is not None else p.price
        price_line = f"💸 ราคา: {fmt_money(effective)} บาท | ลด {fmt_pct(p.discount_pct)}"

    rating_line = f"⭐ เรตติ้ง: {p.rating:.1f}/5" if p.rating is not None else "⭐ เรตติ้ง: -"
    sold_line = f"📦 ขายแล้ว: {p.sold:,} ชิ้น" if p.sold is not None else "📦 ขายแล้ว: -"

    bullets = [
        "✅ คัดของน่าใช้สำหรับบ้าน/งานช่าง",
        "✅ มีรูป+รายละเอียดครบ กดลิงก์ดูได้เลย",
        "✅ สนใจหลายชิ้น ทักมาให้ช่วยเลือกได้ครับ",
    ]

    tags = " ".join(HASHTAGS)

    parts = [
        opener,
        "",
        f"🛒 {p.name}",
        "",
        price_line,
        rating_line,
        sold_line,
        "",
        *promo_lines,
        "",
        *bullets,
        "",
        f"👉 {p.url}",
        "",
        cta,
        "",
        tags,
    ]

    # remove double blank lines
    out = []
    for s in parts:
        if s == "" and (not out or out[-1] == ""):
            continue
        out.append(s)

    return "\n".join(out).strip()


# =========================
# FACEBOOK POST (3 IMAGES)
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


def post_product(p: Product, now: datetime) -> str:
    caption = build_caption(p, now)

    imgs = p.images[:POST_IMAGES_COUNT]
    if len(imgs) == 0:
        raise RuntimeError("No images to post")

    media_ids = []
    for u in imgs:
        img_bytes = download_image_bytes(u)
        mid = upload_unpublished_photo(PAGE_ID, img_bytes)
        media_ids.append(mid)

    post_id = create_feed_post_with_media(PAGE_ID, caption, media_ids)
    return post_id


# =========================
# MAIN
# =========================
def main():
    print("==== V16 ULTRA ====")
    now = now_bkk()
    print(f"INFO: Now (BKK) = {now.isoformat()}")
    print(f"INFO: Graph = {GRAPH_VERSION}")
    print(f"INFO: End-month boost = {is_end_month_boost(now)} (END_MONTH_BOOST_DAYS={END_MONTH_BOOST_DAYS})")
    print(f"INFO: Campaign day = {is_campaign_day(now)}")
    print(f"INFO: POST_IMAGES_COUNT = {POST_IMAGES_COUNT}")
    print(f"INFO: POSTS_THIS_RUN = {POSTS_THIS_RUN}")
    print(f"INFO: Filters: rating>={MIN_RATING}, discount>={MIN_DISCOUNT_PCT}%, sold>={MIN_SOLD}, price=[{PRICE_MIN}..{PRICE_MAX}]")

    state = load_state()

    # Catch-up schedule logic (โพสต์ชดเชยถ้ายังไม่ได้โพสต์ตามเวลา)
    due = due_slots_today(state, now)
    if due:
        print(f"INFO: Due slots today (not posted yet) = {due}")
    else:
        print("INFO: No due slots (already posted for passed times).")
        # For manual dispatch, allow posting anyway if user wants
        if os.getenv("FORCE_POST", "").strip().lower() not in ("1", "true", "yes"):
            return

    top_items = stream_products_from_csv(SHOPEE_CSV_URL, now, STREAM_MAX_ROWS)
    if not top_items:
        raise SystemExit("ERROR: No usable products found from CSV with current filters.")

    posts_done = 0
    for i in range(POSTS_THIS_RUN):
        # If running on schedule and due list exists -> post for earliest due
        slot_used = None
        if due:
            slot_used = due[0]  # earliest missed slot
            due = due[1:]
            print(f"INFO: Posting for due slot = {slot_used}")

        p = pick_product(top_items, state)
        print(f"INFO: Picked: {p.name[:90]} | rating={p.rating} discount={p.discount_pct} sold={p.sold}")

        post_id = post_product(p, now)
        print(f"OK: Posted feed id = {post_id}")

        if slot_used:
            mark_slot_posted(state, now, slot_used)

        posts_done += 1
        time.sleep(5)

    save_state(state)
    print(f"INFO: Done. posts_done={posts_done}")


if __name__ == "__main__":
    main()
