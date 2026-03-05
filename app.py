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

# Shopee Affiliate (หน้านาย)
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()

# Schedule (Bangkok)
TZ_BKK = timezone(timedelta(hours=7))
# แนะนำ 6 รอบ/วัน (เนียน ๆ ไม่สแปม) — ปรับได้ที่ env SLOTS_BKK
SLOTS_BKK = os.getenv("SLOTS_BKK", "07:30,09:00,12:00,16:30,18:30,21:00").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "2"))  # ต่อ 1 run โพสต์ได้กี่โพสต์ (กันสแปม)
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

# Selection filters
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))
MIN_SOLD = int(os.getenv("MIN_SOLD", "30"))  # ใช้ “คัด” แต่จะไม่โชว์คำว่าขายแล้วในแคปชัน
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

# Media
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
PREFER_VIDEO = os.getenv("PREFER_VIDEO", "0").strip().lower() in ("1", "true", "yes")  # ปิดไว้ก่อนเพื่อเสถียร
VIDEO_MAX_MB = int(os.getenv("VIDEO_MAX_MB", "80"))

# CSV streaming
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "250"))

# Caption
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate"
).strip()

# เน้นให้ตรงเพจ: ไฟฟ้า/อุปกรณ์ไฟ/เครื่องมือ/ซ่อมบ้าน/DIY/โซลาร์
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|ปลั๊กพ่วง|สายไฟ|เบรกเกอร์|ตู้ไฟ|ตู้คอนซูเมอร์|ตู้โหลด|หลอดไฟ|โคม|สวิตช์|เต้ารับ|มิเตอร์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|ชาร์จ|เครื่องมือ|สว่าน|ค้อน|ประแจ|คีม|ไขควง|เทปพันสาย|คัทเอาท์|รีเลย์|คอนแทคเตอร์|DIY|ซ่อมบ้าน|งานช่าง)"
).strip()

# กันของหลุดหมวด
BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(ครีม|เครื่องสำอาง|บำรุงผิว|ย้อมผม|วิกผม|เสื้อผ้า|กางเกง|รองเท้า|กระเป๋า|ชุดนอน|ผ้าห่ม|หมอน|อาหารเสริม|เวย์|บุหรี่|แอลกอฮอล์|เซ็กซี่|18\+|ของเล่นผู้ใหญ่|คอนแทคเลนส์|ลดน้ำหนัก)"
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
        "posted_slots": {},
        "posted_at": {},        # url -> iso
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
    ถ้าเลยเวลาแล้ว แต่ยังไม่โพสต์ -> ถือว่า “due”
    จะคืนรายการ slot ที่เลยแล้วและยังไม่ถูกโพสต์ เรียงตามเวลา
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
def http_get(url: str, timeout=(25, 180), headers=None, stream=False) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=headers, stream=stream)
    r.raise_for_status()
    return r


def graph_post(path: str, data=None, files=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    r = requests.post(url, params=params, data=data, files=files, timeout=(20, 80))
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: {js}")
    return js


# =========================
# SHOPEE AFF LINK
# =========================
def build_affiliate_url(raw_url: str) -> str:
    """
    ทำให้เป็นลิงก์นายหน้าแบบเสถียร:
    - ถ้าเป็น product_link เช่น https://shopee.co.th/product/{shopid}/{itemid} -> ใส่ affiliate params
    - ถ้าเป็น shope.ee/an_redir?origin_link=... -> ใส่ affiliate params ลงใน origin_link และคง an_redir ไว้
    """
    raw_url = (raw_url or "").strip()
    if not raw_url:
        return ""

    try:
        u = urlparse(raw_url)
        qs = dict(parse_qsl(u.query, keep_blank_values=True))

        # กรณีเป็น an_redir
        if "shope.ee" in (u.netloc or "") and u.path.startswith("/an_redir") and "origin_link" in qs:
            origin = qs.get("origin_link", "")
            origin_parsed = urlparse(origin)
            origin_qs = dict(parse_qsl(origin_parsed.query, keep_blank_values=True))
            origin_qs["affiliate_id"] = AFFILIATE_ID
            origin_qs["utm_source"] = AFF_UTM_SOURCE
            origin_qs["afftag"] = AFF_TAG
            new_origin = urlunparse(origin_parsed._replace(query=urlencode(origin_qs, doseq=True)))
            qs["origin_link"] = new_origin
            return urlunparse(u._replace(query=urlencode(qs, doseq=True)))

        # กรณีเป็นลิงก์ shopee ปกติ
        qs["affiliate_id"] = AFFILIATE_ID
        qs["utm_source"] = AFF_UTM_SOURCE
        qs["afftag"] = AFF_TAG
        return urlunparse(u._replace(query=urlencode(qs, doseq=True)))
    except Exception:
        return raw_url


# =========================
# PRODUCT
# =========================
@dataclass
class Product:
    title: str
    url: str
    images: List[str]
    price: Optional[float]
    sale_price: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    sold: Optional[int]
    category: str
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


def text(x) -> str:
    return ("" if x is None else str(x)).strip()


def extract_images(row: Dict) -> List[str]:
    imgs = []
    # จากตัวอย่างคุณมี image_link, image_link_3, image_link_4 ... image_link_10
    for i in range(1, 11):
        v = text(row.get(f"image_link_{i}", ""))
        if v.startswith("http"):
            imgs.append(v)
    v0 = text(row.get("image_link", ""))
    if v0.startswith("http"):
        imgs.append(v0)
    v_add = text(row.get("additional_image_link", ""))
    if v_add.startswith("http"):
        imgs.append(v_add)

    # unique keep order
    seen = set()
    out = []
    for u in imgs:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def pick_url(row: Dict) -> str:
    # จากหัวข้อจริงของคุณมี product_link และ product_short link (มี space)
    u = text(row.get("product_link", "")) or text(row.get("product_short link", "")) or text(row.get("url", ""))
    return u


def normalize_row(row: Dict) -> Product:
    title = text(row.get("title", "")) or text(row.get("name", ""))
    url = pick_url(row)
    images = extract_images(row)

    price = fnum(row.get("price"))
    sale_price = fnum(row.get("sale_price"))
    discount_pct = fnum(row.get("discount_percentage"))

    rating = fnum(row.get("item_rating")) or fnum(row.get("rating"))
    sold = fint(row.get("item_sold")) or fint(row.get("historical_sold")) or fint(row.get("sold"))
    category = text(row.get("global_category1", "")) + " " + text(row.get("global_category2", "")) + " " + text(row.get("global_category3", ""))

    return Product(
        title=title,
        url=url,
        images=images,
        price=price,
        sale_price=sale_price,
        discount_pct=discount_pct,
        rating=rating,
        sold=sold,
        category=category.strip(),
        raw=row,
    )


def effective_price(p: Product) -> Optional[float]:
    return p.sale_price if p.sale_price is not None else p.price


def pass_keywords(p: Product) -> bool:
    hay = f"{p.title} {p.category}"
    if BLOCK_PAT and BLOCK_PAT.search(hay):
        return False
    if ALLOW_PAT:
        return bool(ALLOW_PAT.search(hay))
    return True


def product_pass(p: Product, state: dict, now: datetime) -> bool:
    if not p.title or not p.url:
        return False
    if len(p.images) < 1:
        return False

    if not pass_keywords(p):
        return False

    ep = effective_price(p)
    if ep is None or not (PRICE_MIN <= ep <= PRICE_MAX):
        return False
    if p.rating is not None and p.rating < MIN_RATING:
        return False
    if p.sold is not None and p.sold < MIN_SOLD:
        return False
    if p.discount_pct is not None and p.discount_pct < MIN_DISCOUNT_PCT:
        return False

    # กันซ้ำภายใน REPOST_AFTER_DAYS
    posted_at = state.get("posted_at", {}).get(p.url)
    if posted_at:
        try:
            last = datetime.fromisoformat(posted_at)
            if last.tzinfo is None:
                last = last.replace(tzinfo=TZ_BKK)
            if now - last < timedelta(days=REPOST_AFTER_DAYS):
                return False
        except Exception:
            pass

    return True


def score_product(p: Product) -> float:
    """
    คะแนนเน้น:
    - เรตติ้งสูง
    - ส่วนลดสูง
    - sold ใช้ช่วยคัด แต่ไม่โชว์ในโพสต์
    """
    r = p.rating if p.rating is not None else 4.0
    d = p.discount_pct if p.discount_pct is not None else 0.0
    s = p.sold if p.sold is not None else 0
    ep = effective_price(p) or 9999.0

    r_score = max(0.0, min(1.0, (r - 4.0) / 1.0))
    d_score = max(0.0, min(1.0, d / 70.0))
    s_score = max(0.0, min(1.0, (s ** 0.5) / 70.0))

    # ให้ราคาช่วงกลางๆ ดูดีขึ้นนิด
    price_score = 1.0 - max(0.0, min(1.0, (ep - PRICE_MIN) / max(1.0, (PRICE_MAX - PRICE_MIN)))) * 0.15

    base = (0.52 * r_score) + (0.33 * d_score) + (0.15 * s_score)
    base *= price_score
    base *= random.uniform(0.97, 1.03)
    return base


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
        if not product_pass(p, state, now):
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
        raise SystemExit("ERROR: No usable products found. ลองลด MIN_* หรือปรับ ALLOW/BLOCK/PRICE ได้")
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
    state.setdefault("posted_at", {})[chosen.url] = now_bkk().isoformat()
    return chosen


# =========================
# CAPTION (เอา "ขายแล้ว" ออก)
# =========================
HOOKS = [
    "🔥 ของมันต้องมีติดบ้าน!",
    "⚡ สายช่างต้องมี ช่วยให้งานไวขึ้นจริง",
    "✅ คัดตัวฮิตรีวิวดี ราคาโดน",
    "🏡 ของใช้/อุปกรณ์ไฟฟ้าที่ทำให้ชีวิตง่ายขึ้น",
    "🎯 เลือกให้แล้ว “คุ้มสุด” สำหรับงบนี้",
]

BENEFITS = [
    "ใช้งานง่าย มือใหม่ก็ทำเองได้",
    "ประหยัดเวลา งานเสร็จไวขึ้น",
    "คุ้มราคา คุณภาพเกินตัว",
    "เหมาะกับงานบ้าน/งานช่างทั่วไป",
    "รีวิวดี น่าใช้จริง",
]

CTA = [
    "กดลิงก์ดูโปร/โค้ดส่วนลดตอนนี้เลย 👇",
    "ดูรูป + รีวิวจริง + ราคาล่าสุดในลิงก์ได้เลย ✅",
    "อยากได้แบบไหน ทักแชทได้ เดี๋ยวช่วยเลือกให้ 💬",
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

    aff_url = build_affiliate_url(p.url)

    if p.sale_price is not None and p.price is not None and p.sale_price < p.price:
        price_line = f"💸 โปรวันนี้: {fmt_money(p.sale_price)} บาท (ปกติ {fmt_money(p.price)} | ลด {fmt_pct(p.discount_pct)})"
    else:
        price_line = f"💸 ราคา: {fmt_money(effective_price(p))} บาท | ลด {fmt_pct(p.discount_pct)}"

    rating_line = f"⭐ เรตติ้ง: {p.rating:.1f}/5" if p.rating is not None else "⭐ เรตติ้ง: -"

    # ❌ ไม่ใส่ “ขายแล้ว” ตามที่คุณสั่ง
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
        "👇 ลิงก์นายหน้า (โปร/โค้ดอาจเปลี่ยนไว)",
        aff_url,
        "",
        cta,
        "",
        HASHTAGS,
    ]
    return "\n".join([x for x in parts if x is not None]).strip()


# =========================
# FACEBOOK POST (IMAGES 1-3)
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
    imgs = p.images[:max(1, POST_IMAGES_COUNT)]
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
    print("==== V30 ULTRA (BKK) ====")
    print("INFO: Now =", now.isoformat())
    print("INFO: Graph =", GRAPH_VERSION)
    print("INFO: Slots(BKK) =", SLOTS_BKK)
    print("INFO: Filters: rating>=", MIN_RATING, "discount>=", MIN_DISCOUNT_PCT,
          "sold>=", MIN_SOLD, "price=[", PRICE_MIN, "..", PRICE_MAX, "]")
    print("INFO: Affiliate =", AFFILIATE_ID, "| tag =", AFF_TAG)

    state = load_state()

    # First run: ให้โพสต์ 1 โพสต์ทันที (ตามที่คุณสั่ง)
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False) and not FORCE_POST:
        print("INFO: First run detected -> will post 1 immediately.")
        slot_plan = ["FIRST_RUN"]
    else:
        due = due_slots_today(state, now)
        if not due and not FORCE_POST:
            print("INFO: No due slot. Exit. (Set FORCE_POST=1 to test)")
            return
        slot_plan = due if due else ["MANUAL"]

    # ดึง top pool
    top_items = stream_top_products(SHOPEE_CSV_URL, state, now)

    posts_done = 0
    # catch-up: ถ้าวันนี้พลาดหลาย slot ให้ไล่โพสต์ตามลำดับ (จำกัด POSTS_MAX_PER_RUN)
    for slot_used in slot_plan[:POSTS_MAX_PER_RUN]:
        p = pick_product(top_items, state)
        caption = build_caption(p)

        print("INFO: Slot =", slot_used, "| Picked:", p.title[:90], "| images:", len(p.images))
        post_id = post_images(p, caption)
        print("OK: Posted feed id =", post_id)

        if slot_used not in ("MANUAL", "FIRST_RUN"):
            mark_slot_posted(state, now, slot_used)

        posts_done += 1
        time.sleep(4)

    # mark first run done
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        state["first_run_done"] = True

    save_state(state)
    print("INFO: Done. posts_done =", 
