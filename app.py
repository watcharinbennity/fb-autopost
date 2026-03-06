#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
fb-autopost V40 ULTRA (BEN Home & Electrical)
- Pull products from Shopee Affiliate CSV URL
- Filter to match page niche (home/electrical/tools) and avoid unrelated items
- Post to Facebook Page via Graph API v25.0 (images only)
- Add "sold" and key stats
- Robust logs + keepalive to prevent GitHub Actions cancellation
- State persistence via state.json + actions/cache
"""

import os
import re
import json
import time
import csv
import math
import random
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import quote, urlparse, parse_qs

import requests

# -----------------------------
# Helpers / Logging
# -----------------------------

def log(msg: str) -> None:
    print(msg, flush=True)

def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default

def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

BKK_TZ = timezone(timedelta(hours=7))

def now_bkk() -> datetime:
    return datetime.now(BKK_TZ)

def safe_get(d: Dict[str, Any], keys: List[str], default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default

def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def to_number(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return None
    # strip commas and currency symbols
    s = s.replace(",", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", ".", "-", "-."):
        return None
    try:
        return float(s)
    except Exception:
        return None

def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))

# -----------------------------
# Config
# -----------------------------

GRAPH_VERSION = env_str("GRAPH_VERSION", "v25.0")

PAGE_ID = env_str("PAGE_ID")
PAGE_ACCESS_TOKEN = env_str("PAGE_ACCESS_TOKEN")

SHOPEE_CSV_URL = env_str("SHOPEE_CSV_URL")
SHOPEE_AFFILIATE_ID = env_str("SHOPEE_AFFILIATE_ID", "15328100363")

AFF_UTM_SOURCE = env_str("AFF_UTM_SOURCE", "facebook")
AFF_TAG = env_str("AFF_TAG", "BENHomeElectrical")

BRAND = env_str("BRAND", "BEN Home & Electrical")
HASHTAGS = env_str(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate"
)

# posting behavior
POSTS_MAX_PER_RUN = env_int("POSTS_MAX_PER_RUN", 1)   # 1 per run (run 5 times/day)
FIRST_RUN_POST_1 = env_int("FIRST_RUN_POST_1", 1)     # first run force 1 post
FORCE_POST = env_int("FORCE_POST", 0)                 # 1 = ignore slots and post now
REPOST_AFTER_DAYS = env_int("REPOST_AFTER_DAYS", 21)

# filters
MIN_RATING = env_float("MIN_RATING", 4.7)
MIN_DISCOUNT_PCT = env_int("MIN_DISCOUNT_PCT", 15)
MIN_SOLD = env_int("MIN_SOLD", 50)
PRICE_MIN = env_int("PRICE_MIN", 59)
PRICE_MAX = env_int("PRICE_MAX", 4999)

POST_IMAGES_COUNT = env_int("POST_IMAGES_COUNT", 3)

# timeouts / keepalive
HTTP_TIMEOUT = env_int("HTTP_TIMEOUT", 60)
KEEPALIVE_SEC = env_int("KEEPALIVE_SEC", 20)

STATE_PATH = env_str("STATE_PATH", "state.json")

# run slot list (for logs); cron already schedules runs
SLOTS_BKK = [s.strip() for s in env_str("SLOTS_BKK", "08:30,12:00,15:00,18:30,21:30").split(",") if s.strip()]

# -----------------------------
# Keepalive thread (prevents "operation was canceled" due to no output)
# -----------------------------

_stop_ka = False

def keepalive():
    t0 = time.time()
    i = 0
    while not _stop_ka:
        i += 1
        elapsed = int(time.time() - t0)
        log(f"INFO: keepalive tick={i} elapsed={elapsed}s (runner alive)")
        time.sleep(KEEPALIVE_SEC)

# -----------------------------
# State
# -----------------------------

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        return {"first_run_done": False, "posted": {}, "last_run_bkk": ""}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"first_run_done": False, "posted": {}, "last_run_bkk": ""}

def save_state(state: Dict[str, Any]) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)

def mark_posted(state: Dict[str, Any], product_key: str) -> None:
    posted = state.setdefault("posted", {})
    posted[product_key] = {
        "ts_utc": now_utc().isoformat(),
        "ts_bkk": now_bkk().isoformat(),
    }

def posted_recently(state: Dict[str, Any], product_key: str, days: int) -> bool:
    posted = state.get("posted", {})
    item = posted.get(product_key)
    if not item:
        return False
    ts = item.get("ts_utc")
    if not ts:
        return False
    try:
        t = datetime.fromisoformat(ts)
        return now_utc() - t < timedelta(days=days)
    except Exception:
        return False

# -----------------------------
# Shopee CSV parsing
# -----------------------------

@dataclass
class Product:
    title: str
    price: Optional[float]
    price_original: Optional[float]
    discount_pct: Optional[int]
    rating: Optional[float]
    sold: Optional[int]
    url: str
    image_urls: List[str]
    product_id: Optional[str]
    shop_id: Optional[str]
    raw: Dict[str, Any]

def detect_columns(headers: List[str]) -> Dict[str, str]:
    # map logical field -> real header name
    hmap = {h.strip().lower(): h for h in headers}

    def pick(cands: List[str]) -> Optional[str]:
        for c in cands:
            if c in hmap:
                return hmap[c]
        # try contains
        for c in cands:
            for k, orig in hmap.items():
                if c in k:
                    return orig
        return None

    col = {}
    col["title"] = pick(["title", "product_name", "name", "item_name"])
    col["price"] = pick(["price", "sale_price", "current_price", "promotion_price"])
    col["price_original"] = pick(["original_price", "normal_price", "list_price", "price_before_discount"])
    col["discount_pct"] = pick(["discount", "discount_pct", "discount_percent", "discount_percentage"])
    col["rating"] = pick(["rating", "item_rating", "avg_rating", "rating_star"])
    col["sold"] = pick(["sold", "sales", "historical_sold", "total_sold", "sold_count"])
    col["url"] = pick(["url", "product_url", "link", "item_link"])
    col["product_id"] = pick(["product_id", "itemid", "item_id"])
    col["shop_id"] = pick(["shop_id", "shopid", "shop_id_value", "shopid_value"])

    # images: try many patterns
    # We'll collect any header that looks like image/thumbnail
    image_headers = []
    for h in headers:
        k = h.strip().lower()
        if any(x in k for x in ["image", "img", "thumbnail", "thumb", "picture", "photo"]):
            image_headers.append(h)
    col["image_headers"] = image_headers
    return col

def parse_discount_pct(price: Optional[float], original: Optional[float], explicit: Optional[float]) -> Optional[int]:
    if explicit is not None and not math.isnan(explicit):
        try:
            return int(round(float(explicit)))
        except Exception:
            pass
    if price is None or original is None or original <= 0:
        return None
    pct = (1.0 - (price / original)) * 100.0
    if pct < 0:
        return None
    return int(round(pct))

def extract_ids_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    # Shopee formats:
    # https://shopee.co.th/product/<shopid>/<itemid>
    # https://shopee.co.th/<name>-i.<shopid>.<itemid>
    try:
        u = url or ""
        m = re.search(r"/product/(\d+)/(\d+)", u)
        if m:
            return m.group(2), m.group(1)
        m = re.search(r"-i\.(\d+)\.(\d+)", u)
        if m:
            return m.group(2), m.group(1)
        return None, None
    except Exception:
        return None, None

def fetch_csv_text(url: str) -> str:
    log("INFO: downloading Shopee CSV ...")
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    log(f"INFO: CSV downloaded (bytes={len(r.content)})")
    # try utf-8 then fallback
    try:
        return r.content.decode("utf-8-sig", errors="replace")
    except Exception:
        return r.text

def read_products_from_csv_text(text: str) -> List[Product]:
    # Sniff delimiter
    sample = text[:5000]
    try:
        dialect = csv.Sniffer().sniff(sample)
        delim = dialect.delimiter
    except Exception:
        delim = ","

    reader = csv.DictReader(text.splitlines(), delimiter=delim)
    if not reader.fieldnames:
        raise RuntimeError("CSV has no headers/fieldnames")

    cols = detect_columns(reader.fieldnames)
    log(f"INFO: detected columns: { {k: v for k,v in cols.items() if k!='image_headers'} }")
    log(f"INFO: image headers candidates: {len(cols.get('image_headers', []))}")

    products: List[Product] = []
    for row in reader:
        title = normalize_spaces(str(row.get(cols["title"], "") if cols["title"] else ""))
        if not title:
            continue

        url = normalize_spaces(str(row.get(cols["url"], "") if cols["url"] else ""))
        if not url:
            continue

        price = to_number(row.get(cols["price"])) if cols["price"] else None
        original = to_number(row.get(cols["price_original"])) if cols["price_original"] else None
        discount_explicit = to_number(row.get(cols["discount_pct"])) if cols["discount_pct"] else None
        discount_pct = parse_discount_pct(price, original, discount_explicit)

        rating = to_number(row.get(cols["rating"])) if cols["rating"] else None
        sold_num = to_number(row.get(cols["sold"])) if cols["sold"] else None
        sold = int(sold_num) if sold_num is not None else None

        product_id = normalize_spaces(str(row.get(cols["product_id"], "") if cols["product_id"] else ""))
        shop_id = normalize_spaces(str(row.get(cols["shop_id"], "") if cols["shop_id"] else ""))

        if not product_id or not shop_id:
            pid2, sid2 = extract_ids_from_url(url)
            product_id = product_id or pid2 or None
            shop_id = shop_id or sid2 or None

        # images
        image_urls: List[str] = []
        for h in cols.get("image_headers", []):
            v = normalize_spaces(str(row.get(h, "")))
            if not v:
                continue
            # Sometimes multiple URLs separated by commas/spaces
            parts = re.split(r"[,\s]+", v)
            for p in parts:
                p = p.strip()
                if p.startswith("http"):
                    image_urls.append(p)

        # de-dup keep order
        seen = set()
        image_urls = [x for x in image_urls if not (x in seen or seen.add(x))]

        products.append(Product(
            title=title,
            price=price,
            price_original=original,
            discount_pct=discount_pct,
            rating=rating,
            sold=sold,
            url=url,
            image_urls=image_urls,
            product_id=product_id,
            shop_id=shop_id,
            raw=row
        ))

    log(f"INFO: parsed products={len(products)}")
    return products

# -----------------------------
# Niche filtering (BEN Home & Electrical)
# -----------------------------

ALLOW_KEYWORDS = [
    # TH
    "ไฟ", "ไฟฟ้า", "ปลั๊ก", "พ่วง", "รางปลั๊ก", "เต้ารับ", "สวิตช์", "เบรกเกอร์",
    "หลอดไฟ", "โคมไฟ", "ไฟเส้น", "led", "โซล่า", "โซลาร์เซลล์", "สายไฟ", "ปลั๊กไฟ",
    "เครื่องมือช่าง", "สว่าน", "ไขควง", "ประแจ", "คีม", "เลื่อย", "บัดกรี", "มัลติมิเตอร์",
    "ช่าง", "ซ่อมบ้าน", "บ้าน", "อุปกรณ์", "เทปพันสายไฟ", "สกรู", "พุก", "กาว", "ซิลิโคน",
    "ก๊อกน้ำ", "สายยาง", "ปั๊มน้ำ", "วาล์ว", "ประปา",
    # EN
    "electrical", "socket", "plug", "power strip", "extension", "switch", "breaker",
    "lamp", "light", "lighting", "led", "solar", "cable", "wire",
    "tool", "tools", "drill", "screwdriver", "wrench", "pliers", "multimeter",
    "repair", "home", "hardware"
]

BLOCK_KEYWORDS = [
    # TH beauty/fashion/toy etc.
    "ย้อมผม", "ครีม", "ลิป", "น้ำหอม", "สกินแคร์", "เครื่องสำอาง",
    "ชุด", "เสื้อ", "กางเกง", "กระโปรง", "รองเท้า", "แฟชั่น", "กระเป๋า",
    "ตุ๊กตา", "ของเล่น", "kawaii", "คาวาอี้", "ฟิกเกอร์",
    "อาหาร", "ขนม", "กาแฟ", "ชา", "วิตามิน", "เสริมอาหาร",
    # EN
    "cosmetic", "makeup", "skincare", "perfume", "fashion", "dress", "shirt",
    "toy", "plush", "doll", "snack", "food", "supplement"
]

def is_relevant_to_page(title: str) -> bool:
    t = title.lower()
    # block if any strong blocked keywords
    for bk in BLOCK_KEYWORDS:
        if bk.lower() in t:
            return False
    # allow if hits allow list
    hit = 0
    for ak in ALLOW_KEYWORDS:
        if ak.lower() in t:
            hit += 1
            if hit >= 1:
                return True
    return False

def product_key(p: Product) -> str:
    if p.shop_id and p.product_id:
        return f"{p.shop_id}:{p.product_id}"
    # fallback hash by url
    return re.sub(r"\W+", "", p.url.lower())[:80]

def passes_numeric_filters(p: Product) -> bool:
    if p.price is not None:
        if p.price < PRICE_MIN or p.price > PRICE_MAX:
            return False
    # if no price => allow, but prefer with price later
    if p.rating is not None and p.rating < MIN_RATING:
        return False
    if p.discount_pct is not None and p.discount_pct < MIN_DISCOUNT_PCT:
        return False
    if p.sold is not None and p.sold < MIN_SOLD:
        return False
    # if missing fields, allow but score lower
    return True

def score_product(p: Product) -> float:
    # higher is better
    score = 0.0
    if p.rating is not None:
        score += (p.rating - 4.0) * 10.0
    if p.discount_pct is not None:
        score += min(p.discount_pct, 80) * 0.3
    if p.sold is not None:
        score += min(p.sold, 5000) * 0.002
    if p.price is not None:
        # mid-range preference for tools/electrical
        if 99 <= p.price <= 1999:
            score += 5.0
        elif p.price < 99:
            score -= 1.0
    # need images
    score += min(len(p.image_urls), 5) * 2.0
    # relevance boost
    if is_relevant_to_page(p.title):
        score += 15.0
    else:
        score -= 50.0
    # small randomness to vary
    score += random.random() * 0.5
    return score

# -----------------------------
# Affiliate link builder
# -----------------------------

def build_affiliate_link(origin_link: str) -> str:
    origin_link = origin_link.strip()
    encoded = quote(origin_link, safe="")
    return (
        "https://shopee.ee/an_redir?"
        f"origin_link={encoded}"
        f"&affiliate_id={quote(str(SHOPEE_AFFILIATE_ID), safe='')}"
        f"&utm_source={quote(AFF_UTM_SOURCE, safe='')}"
        f"&afftag={quote(AFF_TAG, safe='')}"
    )

# -----------------------------
# Facebook Graph API posting (images only)
# -----------------------------

def graph_url(path: str) -> str:
    path = path.lstrip("/")
    return f"https://graph.facebook.com/{GRAPH_VERSION}/{path}"

def fb_upload_photo_unpublished(image_url: str) -> str:
    # Upload photo as unpublished and return media_fbid
    endpoint = graph_url(f"{PAGE_ID}/photos")
    data = {
        "published": "false",
        "url": image_url,
        "access_token": PAGE_ACCESS_TOKEN,
    }
    log(f"INFO: uploading image (unpublished) url={image_url[:80]}...")
    r = requests.post(endpoint, data=data, timeout=HTTP_TIMEOUT)
    if r.status_code >= 400:
        log(f"ERROR: upload photo failed status={r.status_code} body={r.text[:400]}")
        r.raise_for_status()
    j = r.json()
    fid = j.get("id")
    if not fid:
        raise RuntimeError(f"Upload photo response missing id: {j}")
    log(f"INFO: uploaded media_fbid={fid}")
    return fid

def fb_create_feed_post(message: str, media_fbids: List[str]) -> str:
    endpoint = graph_url(f"{PAGE_ID}/feed")
    attached_media = [{"media_fbid": mid} for mid in media_fbids]
    data = {
        "message": message,
        "attached_media": json.dumps(attached_media, ensure_ascii=False),
        "access_token": PAGE_ACCESS_TOKEN,
    }
    log("INFO: creating feed post with attached_media ...")
    r = requests.post(endpoint, data=data, timeout=HTTP_TIMEOUT)
    if r.status_code >= 400:
        log(f"ERROR: create post failed status={r.status_code} body={r.text[:500]}")
        r.raise_for_status()
    j = r.json()
    pid = j.get("id")
    if not pid:
        raise RuntimeError(f"Create post response missing id: {j}")
    log(f"INFO: post created id={pid}")
    return pid

# -----------------------------
# Caption generator
# -----------------------------

def format_price_thb(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{int(round(x)):,} บาท"

def build_caption(p: Product, aff_link: str) -> str:
    title = p.title
    price = format_price_thb(p.price)
    orig = format_price_thb(p.price_original)
    disc = f"{p.discount_pct}%" if p.discount_pct is not None else "-"
    rating = f"{p.rating:.1f}/5" if p.rating is not None else "-"
    sold = f"{p.sold:,} ชิ้น" if p.sold is not None else "-"

    lines = []
    lines.append(f"🏠⚡ {BRAND}")
    lines.append("✅ คัดตัวฮิตรีวิวดี ราคาโดน")
    lines.append("")
    lines.append(f"🛒 {title}")
    lines.append("")
    lines.append(f"💸 โปรวันนี้: {price} (ปกติ {orig} | ลด {disc})")
    lines.append(f"⭐ เรตติ้ง: {rating}")
    lines.append(f"📦 ขายแล้ว: {sold}")
    lines.append("")
    lines.append("✅ จุดเด่น: เหมาะกับใช้ในบ้าน/งานช่างทั่วไป")
    lines.append("✅ ดูรูป/รีวิวจริงก่อนซื้อได้")
    lines.append("")
    lines.append("👉 ลิงก์นายหน้า:")
    lines.append(aff_link)
    lines.append("")
    lines.append("สนใจทักแชทได้ครับ เดี๋ยวช่วยเลือกให้ 💬")
    lines.append("")
    lines.append(HASHTAGS)
    return "\n".join(lines)

# -----------------------------
# Selection logic
# -----------------------------

def choose_candidates(products: List[Product], state: Dict[str, Any]) -> List[Product]:
    out: List[Product] = []
    for p in products:
        if not p.image_urls:
            continue
        if not is_relevant_to_page(p.title):
            continue
        if not passes_numeric_filters(p):
            continue
        key = product_key(p)
        if posted_recently(state, key, REPOST_AFTER_DAYS):
            continue
        out.append(p)

    # score and sort
    out.sort(key=score_product, reverse=True)
    return out

# -----------------------------
# Main
# -----------------------------

def validate_env() -> None:
    missing = []
    if not PAGE_ID:
        missing.append("PAGE_ID")
    if not PAGE_ACCESS_TOKEN:
        missing.append("PAGE_ACCESS_TOKEN")
    if not SHOPEE_CSV_URL:
        missing.append("SHOPEE_CSV_URL")
    if missing:
        raise RuntimeError(f"Missing required env: {', '.join(missing)}")

def main():
    global _stop_ka
    log("INFO: start " + now_utc().strftime("%Y-%m-%d %H:%M:%S UTC"))
    log(f"INFO: GRAPH_VERSION={GRAPH_VERSION}")
    log(f"INFO: SLOTS_BKK={','.join(SLOTS_BKK)}")
    log(f"INFO: POSTS_MAX_PER_RUN={POSTS_MAX_PER_RUN} FIRST_RUN_POST_1={FIRST_RUN_POST_1} FORCE_POST={FORCE_POST}")
    log(f"INFO: filters MIN_RATING={MIN_RATING} MIN_DISCOUNT_PCT={MIN_DISCOUNT_PCT} MIN_SOLD={MIN_SOLD} PRICE={PRICE_MIN}-{PRICE_MAX}")
    log(f"INFO: POST_IMAGES_COUNT={POST_IMAGES_COUNT} REPOST_AFTER_DAYS={REPOST_AFTER_DAYS}")
    log(f"INFO: AFF_TAG={AFF_TAG} AFF_UTM_SOURCE={AFF_UTM_SOURCE} SHOPEE_AFFILIATE_ID={SHOPEE_AFFILIATE_ID}")

    validate_env()

    # keepalive thread
    t = threading.Thread(target=keepalive, daemon=True)
    t.start()

    state = load_state()
    bkk = now_bkk().strftime("%Y-%m-%d %H:%M:%S")
    state["last_run_bkk"] = bkk

    first_run = (not state.get("first_run_done", False))
    if first_run and FIRST_RUN_POST_1 == 1:
        log("INFO: First run detected -> FORCE 1 post immediately")
        force_now = True
    else:
        force_now = (FORCE_POST == 1)

    # fetch CSV
    text = fetch_csv_text(SHOPEE_CSV_URL)
    products = read_products_from_csv_text(text)

    # choose
    candidates = choose_candidates(products, state)
    log(f"INFO: candidates after filter={len(candidates)}")

    if not candidates:
        log("INFO: No candidates found (maybe filters too strict or CSV has no relevant items).")
        state["first_run_done"] = True
        save_state(state)
        _stop_ka = True
        log("INFO: done (no post)")
        return

    # how many posts this run
    n = clamp(POSTS_MAX_PER_RUN, 1, 5)
    if first_run and FIRST_RUN_POST_1 == 1:
        n = 1  # keep first run to 1

    posted_count = 0
    for idx, p in enumerate(candidates[: max(n, 1)]):
        try:
            key = product_key(p)

            # affiliate link
            aff_link = build_affiliate_link(p.url)

            # pick images
            imgs = p.image_urls[: clamp(POST_IMAGES_COUNT, 1, 10)]
            if not imgs:
                continue

            # upload images unpublished
            media_ids = []
            for i, img_url in enumerate(imgs, start=1):
                log(f"INFO: image {i}/{len(imgs)}")
                mid = fb_upload_photo_unpublished(img_url)
                media_ids.append(mid)

            # caption
            caption = build_caption(p, aff_link)

            # create post (images only)
            post_id = fb_create_feed_post(caption, media_ids)
            mark_posted(state, key)
            save_state(state)

            posted_count += 1
            log(f"INFO: posted_count={posted_count} post_id={post_id}")

            if posted_count >= n:
                break

            # small delay between posts
            time.sleep(3)

        except Exception as e:
            log(f"ERROR: failed to post item idx={idx} title={p.title[:60]} err={repr(e)}")
            # continue to next candidate (do not crash entire run)
            continue

    # mark first run done
    state["first_run_done"] = True
    save_state(state)

    _stop_ka = True
    log(f"INFO: Done. posts_done={posted_count}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {repr(e)}")
        raise
