#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import json
import re
import random
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import requests


# =========================
# ENV / CONFIG
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()

SLOTS_BKK = os.getenv("SLOTS_BKK", "08:30,12:00,15:00,18:30,21:30").strip()
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1").strip())
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip() == "1"
FORCE_POST = os.getenv("FORCE_POST", "0").strip() == "1"

MIN_RATING = float(os.getenv("MIN_RATING", "4.7").strip())
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "15").strip())
MIN_SOLD = int(os.getenv("MIN_SOLD", "50").strip())
PRICE_MIN = float(os.getenv("PRICE_MIN", "59").strip())
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999").strip())
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "21").strip())
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3").strip())

AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()

BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate"
).strip()

STRICT_PAGE_MATCH = os.getenv("STRICT_PAGE_MATCH", "1").strip() == "1"
SLOT_WINDOW_MINUTES = int(os.getenv("SLOT_WINDOW_MINUTES", "12").strip())
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "60").strip())
STATE_FILE = os.getenv("STATE_FILE", "state.json").strip()

TZ_BKK = ZoneInfo("Asia/Bangkok")


# =========================
# KEYWORDS
# =========================
ALLOW_KEYWORDS = [
    "ปลั๊ก", "ปลั๊กไฟ", "ปลั๊กพ่วง", "รางปลั๊ก", "สวิตช์", "เบรกเกอร์", "สายไฟ",
    "หลอดไฟ", "โคมไฟ", "ไฟ", "led", "ไฟโซล่า", "โซล่า", "solar",
    "อะแดปเตอร์", "adapter", "หัวชาร์จ", "ชาร์จ", "ปลั๊กกันไฟกระชาก",
    "ไขควง", "สว่าน", "ประแจ", "คีม", "เลื่อย", "เครื่องมือ", "เครื่องมือช่าง",
    "งานช่าง", "ซ่อมบ้าน", "กาว", "ซิลิโคน", "เทปพันสายไฟ", "สกรู", "พุก",
    "ก๊อกน้ำ", "ฝักบัว", "สายยาง", "วาล์ว", "ท่อน้ำ", "ปั๊มน้ำ",
    "ชั้นวาง", "ที่แขวน", "ราว", "กล่องเก็บของ", "ของใช้ในบ้าน",
    "socket", "plug", "extension", "switch", "breaker", "light", "lighting",
    "tool", "drill", "screwdriver", "wrench", "pliers", "repair", "hardware",
]

BLOCK_KEYWORDS = [
    "ย้อมผม", "ครีม", "ลิป", "สกินแคร์", "เครื่องสำอาง", "น้ำหอม",
    "ตุ๊กตา", "ของเล่น", "kawaii", "คาวาอี้",
    "เสื้อ", "กางเกง", "เดรส", "แฟชั่น", "รองเท้า", "กระเป๋า",
    "โทรศัพท์", "iphone", "ไอโฟน", "samsung", "มือถือ", "แท็บเล็ต",
    "อาหารเสริม", "วิตามิน", "ลดน้ำหนัก", "ชา", "กาแฟ", "ขนม",
    "กล้อง", "เลนส์", "แฟลช", "camera", "lens",
]


# =========================
# LOG / UTILS
# =========================
def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"{ts} {msg}", flush=True)


def mask(s: str, keep: int = 3) -> str:
    if not s:
        return ""
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "*" * (len(s) - keep)


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def safe_int(x, default: int = 0) -> int:
    try:
        s = str(x).strip().replace(",", "")
        if not s:
            return default
        return int(float(s))
    except Exception:
        return default


def safe_float(x, default: float = 0.0) -> float:
    try:
        s = str(x).strip().replace(",", "")
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def to_number(x) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s = s.replace(",", "").replace("฿", "").replace("บาท", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def now_bkk() -> datetime:
    return datetime.now(TZ_BKK)


def parse_slots(slots_str: str) -> List[Tuple[int, int]]:
    slots = []
    for x in slots_str.split(","):
        x = x.strip()
        if not x:
            continue
        m = re.match(r"^(\d{1,2}):(\d{2})$", x)
        if not m:
            continue
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            slots.append((hh, mm))
    return slots


def is_due_slot(now_dt: datetime, slots: List[Tuple[int, int]], window_minutes: int) -> bool:
    for hh, mm in slots:
        slot_dt = now_dt.replace(hour=hh, minute=mm, second=0, microsecond=0)
        delta_min = abs((now_dt - slot_dt).total_seconds()) / 60.0
        if delta_min <= window_minutes:
            return True
    return False


def nearest_slot_key(now_dt: datetime, slots: List[Tuple[int, int]]) -> str:
    best = None
    best_delta = None
    for hh, mm in slots:
        slot_dt = now_dt.replace(hour=hh, minute=mm, second=0, microsecond=0)
        delta = abs((now_dt - slot_dt).total_seconds())
        key = f"{now_dt.strftime('%Y-%m-%d')}:{hh:02d}:{mm:02d}"
        if best is None or delta < best_delta:
            best = key
            best_delta = delta
    return best or f"{now_dt.strftime('%Y-%m-%d')}:manual"


# =========================
# STATE
# =========================
def load_state() -> Dict:
    if not os.path.exists(STATE_FILE):
        return {"posted": {}, "last_run_ts": None, "first_run_done": False, "last_post_slot_key": None}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted": {}, "last_run_ts": None, "first_run_done": False, "last_post_slot_key": None}


def save_state(state: Dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def already_posted_recently(state: Dict, pid: str) -> bool:
    posted = state.get("posted", {}).get(pid)
    if not posted:
        return False
    ts = posted.get("ts")
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return False
    return (now_bkk() - dt).total_seconds() < REPOST_AFTER_DAYS * 86400


# =========================
# CSV STREAMING
# =========================
def stream_csv_rows(url: str) -> Tuple[List[str], List[Dict[str, str]]]:
    log("INFO: streaming Shopee CSV ...")
    with requests.get(url, stream=True, timeout=HTTP_TIMEOUT) as r:
        r.raise_for_status()
        lines_iter = r.iter_lines(decode_unicode=False)

        header_line = None
        for line in lines_iter:
            if line is None:
                continue
            if isinstance(line, bytes):
                s = line.decode("utf-8-sig", errors="replace").strip()
            else:
                s = str(line).strip()
            if s:
                header_line = s
                break

        if not header_line:
            raise RuntimeError("CSV stream: missing header line")

        delim = ","
        for cand in [",", "\t", ";", "|"]:
            if cand in header_line:
                delim = cand
                break

        headers = next(csv.reader([header_line], delimiter=delim))
        headers = [h.strip() for h in headers if h is not None]
        if not headers:
            raise RuntimeError("CSV stream: empty headers")

        rows: List[Dict[str, str]] = []
        for line in lines_iter:
            if line is None:
                continue

            if isinstance(line, bytes):
                s = line.decode("utf-8", errors="replace").strip()
            else:
                s = str(line).strip()

            if not s:
                continue

            try:
                parsed = next(csv.reader([s], delimiter=delim))
            except Exception:
                continue

            row = {}
            for i, h in enumerate(headers):
                row[h] = parsed[i] if i < len(parsed) else ""
            rows.append(row)

        log(f"INFO: streamed rows={len(rows)}")
        return headers, rows


def find_key(row: Dict[str, str], candidates: List[str]) -> Optional[str]:
    keys = list(row.keys())
    for c in candidates:
        c2 = c.lower().strip()
        for k in keys:
            if k.lower().strip() == c2:
                return k
    for c in candidates:
        c2 = c.lower().strip()
        for k in keys:
            if c2 in k.lower():
                return k
    return None


# =========================
# PRODUCT
# =========================
@dataclass
class Product:
    itemid: str
    shopid: str
    name: str
    link: str
    price: int
    ori_price: int
    discount_pct: int
    rating: float
    sold: int
    images: List[str]


def extract_ids_from_url(url: str) -> Tuple[str, str]:
    m = re.search(r"/product/(\d+)/(\d+)", url)
    if m:
        return m.group(2), m.group(1)
    m = re.search(r"-i\.(\d+)\.(\d+)", url)
    if m:
        return m.group(2), m.group(1)
    return "", ""


def normalize_product(row: Dict[str, str]) -> Product:
    k_itemid = find_key(row, ["itemid", "item_id", "product_id", "item id"])
    k_shopid = find_key(row, ["shopid", "shop_id", "shop id"])
    k_link = find_key(row, ["product_link", "link", "url", "product url", "product_url"])
    k_name = find_key(row, ["product_name", "name", "title", "product title"])
    k_price = find_key(row, ["price", "sale_price", "current_price"])
    k_ori_price = find_key(row, ["original_price", "ori_price", "price_before_discount"])
    k_discount = find_key(row, ["discount", "discount_pct", "discount_percent", "discount percentage"])
    k_rating = find_key(row, ["rating", "product_rating", "rating_star", "rating score"])
    k_sold = find_key(row, ["sold", "sold_count", "historical_sold", "total sold"])
    k_image1 = find_key(row, ["image", "image_1", "image1", "main_image", "image url", "image_url"])
    k_image2 = find_key(row, ["image_2", "image2"])
    k_image3 = find_key(row, ["image_3", "image3"])
    k_image4 = find_key(row, ["image_4", "image4"])

    itemid = normalize_spaces(row.get(k_itemid, "") if k_itemid else "")
    shopid = normalize_spaces(row.get(k_shopid, "") if k_shopid else "")
    name = normalize_spaces(row.get(k_name, "") if k_name else "")
    link = normalize_spaces(row.get(k_link, "") if k_link else "")

    price = safe_int(row.get(k_price, "") if k_price else "", 0)
    ori_price = safe_int(row.get(k_ori_price, "") if k_ori_price else "", 0)
    rating = safe_float(row.get(k_rating, "") if k_rating else "", 0.0)
    sold = safe_int(row.get(k_sold, "") if k_sold else "", 0)

    if k_discount:
        discount_pct = safe_int(row.get(k_discount, ""), 0)
    elif ori_price > 0 and price > 0 and ori_price >= price:
        discount_pct = int(round((ori_price - price) * 100 / max(ori_price, 1)))
    else:
        discount_pct = 0

    images = []
    for k in [k_image1, k_image2, k_image3, k_image4]:
        if k and row.get(k, "").strip():
            images.append(row.get(k, "").strip())

    if not link and shopid and itemid:
        link = f"https://shopee.co.th/product/{shopid}/{itemid}"

    if (not itemid or not shopid) and link:
        itemid2, shopid2 = extract_ids_from_url(link)
        itemid = itemid or itemid2
        shopid = shopid or shopid2

    return Product(
        itemid=itemid,
        shopid=shopid,
        name=name,
        link=link,
        price=price,
        ori_price=ori_price,
        discount_pct=discount_pct,
        rating=rating,
        sold=sold,
        images=images,
    )


def title_matches_page(title: str) -> bool:
    t = (title or "").lower()

    for bad in BLOCK_KEYWORDS:
        if bad.lower() in t:
            return False

    if not STRICT_PAGE_MATCH:
        return True

    for kw in ALLOW_KEYWORDS:
        if kw.lower() in t:
            return True
    return False


def passes_filters(p: Product) -> bool:
    if not p.name or not p.link:
        return False
    if not p.images:
        return False
    if not title_matches_page(p.name):
        return False
    if p.price and (p.price < PRICE_MIN or p.price > PRICE_MAX):
        return False
    if p.rating and p.rating < MIN_RATING:
        return False
    if p.discount_pct and p.discount_pct < MIN_DISCOUNT_PCT:
        return False
    if p.sold and p.sold < MIN_SOLD:
        return False
    return True


def build_affiliate_link(origin_link: str) -> str:
    enc = quote(origin_link, safe="")
    return (
        "https://shopee.ee/an_redir?"
        f"origin_link={enc}"
        f"&affiliate_id={quote(SHOPEE_AFFILIATE_ID)}"
        f"&utm_source={quote(AFF_UTM_SOURCE)}"
        f"&afftag={quote(AFF_TAG)}"
    )


def format_post_message(p: Product) -> str:
    aff = build_affiliate_link(p.link)

    lines = []
    lines.append("🏠⚡ BEN Home & Electrical")
    lines.append("🔥 ของดีงานช่าง / ของใช้ในบ้าน คัดมาให้แล้ว")
    lines.append("")
    lines.append(f"🛒 {p.name}")
    lines.append("")

    if p.discount_pct > 0 and p.ori_price > p.price > 0:
        lines.append(f"💰 โปรวันนี้ {p.price:,} บาท")
        lines.append(f"❌ ปกติ {p.ori_price:,} บาท")
        lines.append(f"🔥 ลด {p.discount_pct}%")
    elif p.price > 0:
        lines.append(f"💰 ราคา {p.price:,} บาท")

    if p.rating > 0:
        lines.append(f"⭐ เรตติ้ง {p.rating:.1f}/5")
    if p.sold > 0:
        lines.append(f"📦 ขายแล้ว {p.sold:,} ชิ้น")

    lines.append("")
    lines.append("✔ รีวิวดี")
    lines.append("✔ ของใช้งานจริงในบ้าน")
    lines.append("✔ งานช่าง งานซ่อม งานไฟฟ้า")
    lines.append("")
    lines.append("👉 กดดูราคาล่าสุดใน Shopee")
    lines.append(aff)
    lines.append("")
    lines.append("💬 ทักแชทถามได้ครับ")
    lines.append("")
    lines.append(HASHTAGS)

    return "\n".join(lines)


def pick_candidates(products: List[Product], state: Dict, k: int = 40) -> List[Product]:
    good = []
    for p in products:
        pid = p.itemid or p.link
        if not pid:
            continue
        if not passes_filters(p):
            continue
        if already_posted_recently(state, pid):
            continue
        good.append(p)

    def score(p: Product) -> float:
        return (
            p.discount_pct * 3.0
            + min(p.sold, 10000) / 50.0
            + p.rating * 10.0
            + random.random()
        )

    good.sort(key=score, reverse=True)
    return good[:k]


# =========================
# FACEBOOK
# =========================
def fb_upload_photo(image_url: str) -> str:
    endpoint = f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/photos"
    payload = {
        "access_token": PAGE_ACCESS_TOKEN,
        "url": image_url,
        "published": "false",
    }
    r = requests.post(endpoint, data=payload, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if "id" not in data:
        raise RuntimeError(f"photo upload failed: {data}")
    return data["id"]


def fb_create_feed_post(message: str, media_fbids: List[str]) -> str:
    endpoint = f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/feed"
    payload = {
        "access_token": PAGE_ACCESS_TOKEN,
        "message": message,
    }
    for i, mid in enumerate(media_fbids):
        payload[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})

    r = requests.post(endpoint, data=payload, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if "id" not in data:
        raise RuntimeError(f"post create failed: {data}")
    return data["id"]


# =========================
# MAIN
# =========================
def print_env_summary():
    log(f"GRAPH_VERSION: {GRAPH_VERSION}")
    log(f"PAGE_ID: {mask(PAGE_ID)}")
    log(f"PAGE_ACCESS_TOKEN: {mask(PAGE_ACCESS_TOKEN)}")
    log(f"SHOPEE_CSV_URL: {mask(SHOPEE_CSV_URL)}")
    log(f"SHOPEE_AFFILIATE_ID: {mask(SHOPEE_AFFILIATE_ID)}")
    log(f"SLOTS_BKK: {SLOTS_BKK}")
    log(f"POSTS_MAX_PER_RUN: {POSTS_MAX_PER_RUN}")
    log(f"FIRST_RUN_POST_1: {1 if FIRST_RUN_POST_1 else 0}")
    log(f"FORCE_POST: {1 if FORCE_POST else 0}")
    log(f"MIN_RATING: {MIN_RATING}")
    log(f"MIN_DISCOUNT_PCT: {MIN_DISCOUNT_PCT}")
    log(f"MIN_SOLD: {MIN_SOLD}")
    log(f"PRICE_MIN: {PRICE_MIN}")
    log(f"PRICE_MAX: {PRICE_MAX}")
    log(f"REPOST_AFTER_DAYS: {REPOST_AFTER_DAYS}")
    log(f"POST_IMAGES_COUNT: {POST_IMAGES_COUNT}")
    log(f"AFF_UTM_SOURCE: {AFF_UTM_SOURCE}")
    log(f"AFF_TAG: {AFF_TAG}")
    log(f"BRAND: {BRAND}")
    log(f"HASHTAGS: {HASHTAGS}")


def ensure_required():
    missing = []
    for k, v in [
        ("PAGE_ID", PAGE_ID),
        ("PAGE_ACCESS_TOKEN", PAGE_ACCESS_TOKEN),
        ("SHOPEE_CSV_URL", SHOPEE_CSV_URL),
        ("SHOPEE_AFFILIATE_ID", SHOPEE_AFFILIATE_ID),
    ]:
        if not v:
            missing.append(k)
    if missing:
        raise RuntimeError("Missing ENV: " + ", ".join(missing))


def should_post_now(state: Dict) -> bool:
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        log("INFO: First run detected -> FORCE 1 post immediately")
        return True

    if FORCE_POST:
        log("INFO: FORCE_POST=1 -> posting now")
        return True

    slots = parse_slots(SLOTS_BKK)
    now_dt = now_bkk()

    if not is_due_slot(now_dt, slots, SLOT_WINDOW_MINUTES):
        log("INFO: not in slot window, skip")
        return False

    slot_key = nearest_slot_key(now_dt, slots)
    if state.get("last_post_slot_key") == slot_key:
        log(f"INFO: already posted in slot {slot_key}, skip")
        return False

    log("INFO: within slot window -> posting")
    return True


def keepalive(max_seconds: int = 60, interval: int = 20):
    start = time.time()
    tick = 0
    while time.time() - start < max_seconds:
        tick += 1
        log(f"INFO: keepalive tick={tick} elapsed={int(time.time()-start)}s (runner alive)")
        time.sleep(interval)


def post_one(p: Product, state: Dict) -> str:
    images = [u for u in p.images if u.startswith("http")][:max(1, POST_IMAGES_COUNT)]
    if not images:
        raise RuntimeError("No usable images found")

    media_ids = []
    for u in images:
        try:
            mid = fb_upload_photo(u)
            media_ids.append(mid)
        except Exception as e:
            log(f"WARN: upload photo failed: {e}")

    if not media_ids:
        raise RuntimeError("All photo uploads failed")

    msg = format_post_message(p)
    post_id = fb_create_feed_post(msg, media_ids)

    pid = p.itemid or p.link
    state.setdefault("posted", {})[pid] = {
        "ts": now_bkk().isoformat(),
        "fb_post_id": post_id,
        "name": p.name,
        "link": p.link,
    }
    return post_id


def main():
    log(f"INFO: start {datetime.utcnow().isoformat()}Z")
    print_env_summary()
    ensure_required()

    state = load_state()

    if not should_post_now(state):
        state["last_run_ts"] = now_bkk().isoformat()
        save_state(state)
        log("INFO: Done (no due slot)")
        return

    log("INFO: preparing to read Shopee CSV (streaming)")
    keepalive(max_seconds=40, interval=20)

    headers, raw_rows = stream_csv_rows(SHOPEE_CSV_URL)
    log(f"INFO: headers={len(headers)} raw_rows={len(raw_rows)}")

    products: List[Product] = []
    for row in raw_rows:
        try:
            products.append(normalize_product(row))
        except Exception:
            continue

    cands = pick_candidates(products, state, k=40)
    if not cands:
        log("INFO: No candidates matched filters")
        state["last_run_ts"] = now_bkk().isoformat()
        state["first_run_done"] = True
        save_state(state)
        log("INFO: Done")
        return

    random.shuffle(cands)
    to_post = cands[:max(1, POSTS_MAX_PER_RUN)]

    posts_done = 0
    for p in to_post:
        try:
            pid = p.itemid or p.link
            log(f"INFO: posting product id={pid} name={p.name[:60]}")
            post_id = post_one(p, state)
            posts_done += 1
            log(f"INFO: posted fb_post_id={post_id}")
        except Exception as e:
            log(f"ERROR: post failed: {e}")

    now_dt = now_bkk()
    state["last_run_ts"] = now_dt.isoformat()
    state["first_run_done"] = True
    state["last_post_slot_key"] = nearest_slot_key(now_dt, parse_slots(SLOTS_BKK))
    save_state(state)

    log(f"INFO: Done. posts_done={posts_done}")


if __name__ == "__main__":
    main()
