import os
import re
import csv
import json
import time
import random
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import requests


# =========================
# CONFIG
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "").strip()

SLOTS_BKK = os.getenv("SLOTS_BKK", "08:30,12:00,15:00,18:30,21:30").strip()
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip()
FORCE_POST = os.getenv("FORCE_POST", "0").strip()

MIN_RATING = float(os.getenv("MIN_RATING", "4.7"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "15"))
MIN_SOLD = int(os.getenv("MIN_SOLD", "50"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "21"))
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))

AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate",
).strip()

STRICT_PAGE_MATCH = os.getenv("STRICT_PAGE_MATCH", "1").strip()
SLOT_WINDOW_MINUTES = int(os.getenv("SLOT_WINDOW_MINUTES", "12"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "25"))

STATE_FILE = "state.json"
TZ_BKK = ZoneInfo("Asia/Bangkok")

HOME_ELECTRICAL_KEYWORDS = [
    "ปลั๊ก", "ปลั๊กพ่วง", "ปลั๊กไฟ", "สวิตช์", "เบรกเกอร์", "สายไฟ", "หลอดไฟ", "โคมไฟ",
    "ไฟ", "led", "พาวเวอร์", "อะแดปเตอร์", "adapter", "ชาร์จ", "หม้อแปลง",
    "เครื่องมือ", "เครื่องมือช่าง", "สว่าน", "ไขควง", "ประแจ", "คีม", "เลื่อย",
    "เทปพันสายไฟ", "กาว", "ซิลิโคน", "สกรู", "พุก", "ช่าง", "ซ่อม", "ซ่อมบ้าน",
    "ก๊อก", "ฝักบัว", "สายยาง", "วาล์ว", "ปั๊มน้ำ", "ท่อน้ำ", "ครัว", "ห้องน้ำ",
    "socket", "plug", "extension", "switch", "breaker", "light", "lighting",
    "tool", "drill", "screwdriver", "wrench", "pliers", "repair", "hardware",
]

BLACKLIST_KEYWORDS = [
    "ครีม", "ย้อมผม", "ลิป", "เครื่องสำอาง", "สกินแคร์",
    "ตุ๊กตา", "ของเล่น", "kawaii", "คาวาอี้",
    "เสื้อ", "กางเกง", "ชุดชั้นใน", "เดรส", "แฟชั่น",
    "โทรศัพท์", "ไอโฟน", "iphone", "samsung", "หูฟังเกมมิ่ง",
    "อาหารเสริม", "ลดน้ำหนัก", "วิตามิน",
]


# =========================
# HELPERS
# =========================
def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"{ts} {msg}", flush=True)


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


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


def parse_discount_pct(price: Optional[float], original: Optional[float], explicit: Optional[float]) -> Optional[float]:
    if explicit is not None and explicit >= 0:
        return explicit
    if price is None or original is None or original <= 0:
        return None
    pct = (1 - (price / original)) * 100
    if pct < 0:
        return None
    return round(pct, 2)


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def load_state() -> Dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state: Dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def now_bkk() -> datetime:
    return datetime.now(TZ_BKK)


def parse_slots(slots_str: str) -> List[Tuple[int, int]]:
    out = []
    for part in (slots_str or "").split(","):
        part = part.strip()
        m = re.match(r"^(\d{1,2}):(\d{2})$", part)
        if not m:
            continue
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            out.append((hh, mm))
    return out


def is_due_slot(now: datetime, slots: List[Tuple[int, int]], window_min: int) -> bool:
    for hh, mm in slots:
        slot_time = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        delta = abs((now - slot_time).total_seconds()) / 60.0
        if delta <= window_min:
            return True
    return False


def should_post_this_run(state: Dict) -> bool:
    if FORCE_POST == "1":
        log("INFO: FORCE_POST=1 -> will post")
        return True

    if state.get("first_run_done") != True and FIRST_RUN_POST_1 == "1":
        log("INFO: First run detected -> FORCE 1 post immediately")
        return True

    slots = parse_slots(SLOTS_BKK)
    if not slots:
        log("WARN: No valid slots")
        return False

    now = now_bkk()
    due = is_due_slot(now, slots, SLOT_WINDOW_MINUTES)
    if not due:
        log(f"INFO: Not in slot window. now(BKK)={now.strftime('%H:%M:%S')} slots={SLOTS_BKK}")
        return False

    nearest = min(
        [f"{hh:02d}:{mm:02d}" for hh, mm in slots],
        key=lambda t: abs(
            (
                now
                - now.replace(
                    hour=int(t[:2]),
                    minute=int(t[3:]),
                    second=0,
                    microsecond=0,
                )
            ).total_seconds()
        ),
    )
    slot_key = now.strftime("%Y-%m-%d") + ":" + nearest
    last_key = state.get("last_post_slot_key")
    if last_key == slot_key:
        log(f"INFO: Already posted in this slot ({slot_key})")
        return False

    return True


# =========================
# CSV STREAM
# =========================
def detect_columns(headers: List[str]) -> Dict[str, Optional[str]]:
    lower_map = {h: h.lower().strip() for h in headers}

    def pick(cands: List[str]) -> Optional[str]:
        for h, lh in lower_map.items():
            for c in cands:
                if c in lh:
                    return h
        return None

    title = pick(["product name", "ชื่อสินค้า", "name", "title"])
    url = pick(["product link", "ลิงก์สินค้า", "url", "link"])
    price = pick(["price", "ราคา"])
    price_original = pick(["original", "ราคาปกติ", "list price", "ปกติ"])
    discount_pct = pick(["discount", "ส่วนลด", "%"])
    rating = pick(["rating", "เรตติ้ง", "คะแนน"])
    sold = pick(["sold", "ขายแล้ว", "จำนวนขาย"])
    product_id = pick(["product id", "itemid", "item_id", "productid", "รหัสสินค้า"])
    shop_id = pick(["shop id", "shopid", "shop_id", "รหัสร้าน"])

    image_headers = []
    for h, lh in lower_map.items():
        if "image" in lh or "รูป" in lh or "img" in lh or "ภาพ" in lh:
            image_headers.append(h)

    return {
        "title": title,
        "url": url,
        "price": price,
        "price_original": price_original,
        "discount_pct": discount_pct,
        "rating": rating,
        "sold": sold,
        "product_id": product_id,
        "shop_id": shop_id,
        "image_headers": image_headers,
    }


def extract_ids_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    m = re.search(r"/product/(\d+)/(\d+)", url)
    if m:
        return m.group(2), m.group(1)

    m = re.search(r"-i\.(\d+)\.(\d+)", url)
    if m:
        return m.group(2), m.group(1)

    return None, None


def stream_csv_rows(url: str) -> Tuple[List[str], List[Dict[str, str]]]:
    log("INFO: streaming Shopee CSV ...")
    with requests.get(url, stream=True, timeout=HTTP_TIMEOUT) as r:
        r.raise_for_status()
        lines_iter = r.iter_lines(decode_unicode=True)

        header_line = None
        for line in lines_iter:
            if line is None:
                continue
            s = line.strip()
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
            s = line.strip()
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


# =========================
# PRODUCT MODEL
# =========================
@dataclass
class Product:
    title: str
    price: Optional[float]
    price_original: Optional[float]
    discount_pct: Optional[float]
    rating: Optional[float]
    sold: Optional[int]
    url: str
    image_urls: List[str]
    product_id: Optional[str]
    shop_id: Optional[str]
    raw: Dict[str, str]


def build_affiliate_redirect(origin_link: str) -> str:
    q = {
        "origin_link": origin_link,
        "affiliate_id": SHOPEE_AFFILIATE_ID,
        "utm_source": AFF_UTM_SOURCE,
        "afftag": AFF_TAG,
    }
    return "https://shopee.ee/an_redir?" + urlencode(q, quote_via=quote)


def title_matches_page(title: str) -> bool:
    t = (title or "").lower()

    for bad in BLACKLIST_KEYWORDS:
        if bad.lower() in t:
            return False

    if STRICT_PAGE_MATCH == "1":
        for kw in HOME_ELECTRICAL_KEYWORDS:
            if kw.lower() in t:
                return True
        return False

    return True


def read_products_streaming(url: str) -> List[Product]:
    headers, rows = stream_csv_rows(url)
    cols = detect_columns(headers)
    log(f"INFO: detected columns: { {k: v for k,v in cols.items() if k!='image_headers'} }")
    log(f"INFO: image headers candidates: {len(cols.get('image_headers', []))}")

    products: List[Product] = []
    for row in rows:
        title = normalize_spaces(str(row.get(cols["title"], "") if cols["title"] else ""))
        if not title:
            continue

        url0 = normalize_spaces(str(row.get(cols["url"], "") if cols["url"] else ""))
        if not url0:
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
            pid2, sid2 = extract_ids_from_url(url0)
            product_id = product_id or (pid2 or "")
            shop_id = shop_id or (sid2 or "")

        product_id = product_id if product_id else None
        shop_id = shop_id if shop_id else None

        image_urls: List[str] = []
        for h in cols.get("image_headers", []):
            v = normalize_spaces(str(row.get(h, "")))
            if not v:
                continue
            parts = re.split(r"[,\s]+", v)
            for p in parts:
                p = p.strip()
                if p.startswith("http"):
                    image_urls.append(p)

        seen = set()
        image_urls = [x for x in image_urls if not (x in seen or seen.add(x))]

        products.append(
            Product(
                title=title,
                price=price,
                price_original=original,
                discount_pct=discount_pct,
                rating=rating,
                sold=sold,
                url=url0,
                image_urls=image_urls,
                product_id=product_id,
                shop_id=shop_id,
                raw=row,
            )
        )

    log(f"INFO: parsed products={len(products)}")
    return products


def passes_filters(p: Product) -> bool:
    if not title_matches_page(p.title):
        return False

    if p.rating is not None and p.rating < MIN_RATING:
        return False

    if p.discount_pct is not None and p.discount_pct < MIN_DISCOUNT_PCT:
        return False

    if p.sold is not None and p.sold < MIN_SOLD:
        return False

    if p.price is not None and (p.price < PRICE_MIN or p.price > PRICE_MAX):
        return False

    if not p.image_urls:
        return False

    return True


def is_recently_posted(state: Dict, p: Product) -> bool:
    posted = state.get("posted", {})
    key = p.product_id or sha1(p.url)
    if key not in posted:
        return False
    try:
        last_ts = datetime.fromisoformat(posted[key])
    except Exception:
        return False
    return datetime.now(timezone.utc) - last_ts < timedelta(days=REPOST_AFTER_DAYS)


def mark_posted(state: Dict, p: Product) -> None:
    if "posted" not in state:
        state["posted"] = {}
    key = p.product_id or sha1(p.url)
    state["posted"][key] = datetime.now(timezone.utc).isoformat()


# =========================
# FACEBOOK GRAPH API
# =========================
def graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{GRAPH_VERSION}/{path.lstrip('/')}"


def fb_upload_photo_unpublished(image_url: str) -> str:
    endpoint = graph_url(f"{PAGE_ID}/photos")
    data = {
        "url": image_url,
        "published": "false",
        "access_token": PAGE_ACCESS_TOKEN,
    }
    resp = requests.post(endpoint, data=data, timeout=HTTP_TIMEOUT)
    try:
        j = resp.json()
    except Exception:
        raise RuntimeError(f"FB upload photo failed HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400 or "error" in j:
        raise RuntimeError(f"FB upload photo error: {j}")
    media_id = j.get("id")
    if not media_id:
        raise RuntimeError(f"FB upload photo missing id: {j}")
    return media_id


def fb_create_feed_post_with_media(message: str, media_fbids: List[str]) -> str:
    endpoint = graph_url(f"{PAGE_ID}/feed")
    attached_media = [{"media_fbid": mid} for mid in media_fbids]
    data = {
        "message": message,
        "attached_media": json.dumps(attached_media),
        "access_token": PAGE_ACCESS_TOKEN,
    }
    resp = requests.post(endpoint, data=data, timeout=HTTP_TIMEOUT)
    try:
        j = resp.json()
    except Exception:
        raise RuntimeError(f"FB create post failed HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400 or "error" in j:
        raise RuntimeError(f"FB create post error: {j}")
    post_id = j.get("id")
    if not post_id:
        raise RuntimeError(f"FB create post missing id: {j}")
    return post_id


def build_post_message(p: Product) -> str:
    price_txt = f"{int(p.price):,} บาท" if p.price is not None else "เช็คราคาในลิงก์"
    disc_txt = f"ลด {int(p.discount_pct)}%" if p.discount_pct is not None else ""
    rating_txt = f"{p.rating:.1f}/5" if p.rating is not None else "—"
    sold_txt = f"{p.sold} ชิ้น" if p.sold is not None else "—"
    aff_link = build_affiliate_redirect(p.url)

    lines = [
        f"🏠⚡ {BRAND}",
        "✅ คัดตัวฮิตรีวิวดี ราคาโดน",
        "",
        f"🛒 {p.title}",
        "",
        f"💸 โปรวันนี้: {price_txt} {f'({disc_txt})' if disc_txt else ''}".strip(),
        f"⭐ เรตติ้ง: {rating_txt}",
        f"📦 ขายแล้ว: {sold_txt}",
        "",
        "✅ จุดเด่น: เหมาะกับใช้งานในบ้าน/งานช่างทั่วไป",
        "✅ ดูรูป/รีวิวจริงก่อนซื้อได้",
        "",
        "👉 " + aff_link,
        "",
        "สนใจทักแชทได้ครับ เดี๋ยวช่วยเลือกให้ 💬",
        "",
        HASHTAGS,
    ]
    return "\n".join(lines)


# =========================
# PICK PRODUCT
# =========================
def pick_product_to_post(state: Dict, products: List[Product]) -> Optional[Product]:
    candidates = []
    for p in products:
        if not passes_filters(p):
            continue
        if is_recently_posted(state, p):
            continue
        candidates.append(p)

    log(f"INFO: candidates after filters & repost guard: {len(candidates)}")
    if not candidates:
        return None

    def score(p: Product) -> float:
        s = 0.0
        if p.rating is not None:
            s += p.rating * 10
        if p.sold is not None:
            s += min(p.sold, 10000) / 100.0
        if p.discount_pct is not None:
            s += p.discount_pct / 2.0
        s += random.random()
        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def validate_env() -> None:
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
        raise RuntimeError(f"Missing required ENV/Secrets: {', '.join(missing)}")


def env_summary() -> None:
    safe = {
        "GRAPH_VERSION": GRAPH_VERSION,
        "PAGE_ID": "***" if PAGE_ID else "",
        "PAGE_ACCESS_TOKEN": "***" if PAGE_ACCESS_TOKEN else "",
        "SHOPEE_CSV_URL": "***" if SHOPEE_CSV_URL else "",
        "SHOPEE_AFFILIATE_ID": "***" if SHOPEE_AFFILIATE_ID else "",
        "SLOTS_BKK": SLOTS_BKK,
        "POSTS_MAX_PER_RUN": POSTS_MAX_PER_RUN,
        "FIRST_RUN_POST_1": FIRST_RUN_POST_1,
        "FORCE_POST": FORCE_POST,
        "MIN_RATING": MIN_RATING,
        "MIN_DISCOUNT_PCT": MIN_DISCOUNT_PCT,
        "MIN_SOLD": MIN_SOLD,
        "PRICE_MIN": PRICE_MIN,
        "PRICE_MAX": PRICE_MAX,
        "REPOST_AFTER_DAYS": REPOST_AFTER_DAYS,
        "POST_IMAGES_COUNT": POST_IMAGES_COUNT,
        "AFF_UTM_SOURCE": AFF_UTM_SOURCE,
        "AFF_TAG": AFF_TAG,
        "BRAND": BRAND,
        "STRICT_PAGE_MATCH": STRICT_PAGE_MATCH,
    }
    for k, v in safe.items():
        log(f"{k}: {v}")


def keepalive(seconds: int = 60, step: int = 20) -> None:
    for i in range(0, seconds, step):
        log(f"INFO: keepalive tick={i // step + 1} elapsed={i}s (runner alive)")
        time.sleep(step)


def main():
    log("INFO: start " + datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S UTC %Y"))
    env_summary()
    validate_env()

    state = load_state()

    if not should_post_this_run(state):
        log("INFO: No due slot -> exit")
        return

    log("INFO: preparing to read Shopee CSV (streaming)")
    keepalive(seconds=60, step=20)

    products = read_products_streaming(SHOPEE_CSV_URL)

    posts_done = 0
    while posts_done < POSTS_MAX_PER_RUN:
        p = pick_product_to_post(state, products)
        if not p:
            log("INFO: No eligible product to post -> exit")
            state["first_run_done"] = True
            save_state(state)
            return

        imgs = [u for u in p.image_urls if u.startswith("http")][:max(1, POST_IMAGES_COUNT)]
        if not imgs:
            log("WARN: picked product has no usable images -> mark posted to skip")
            mark_posted(state, p)
            save_state(state)
            continue

        message = build_post_message(p)

        log(f"INFO: Posting product: title='{p.title[:80]}' imgs={len(imgs)}")
        media_fbids = []
        for idx, img_url in enumerate(imgs, start=1):
            log(f"INFO: upload photo {idx}/{len(imgs)}")
            mid = fb_upload_photo_unpublished(img_url)
            media_fbids.append(mid)

        post_id = fb_create_feed_post_with_media(message, media_fbids)
        log(f"INFO: Posted successfully. post_id={post_id}")

        mark_posted(state, p)
        posts_done += 1

        now = now_bkk()
        slots = parse_slots(SLOTS_BKK)
        if slots:
            nearest = min(
                [f"{hh:02d}:{mm:02d}" for hh, mm in slots],
                key=lambda t: abs(
                    (
                        now
                        - now.replace(
                            hour=int(t[:2]),
                            minute=int(t[3:]),
                            second=0,
                            microsecond=0,
                        )
                    ).total_seconds()
                ),
            )
            state["last_post_slot_key"] = now.strftime("%Y-%m-%d") + ":" + nearest

        state["first_run_done"] = True
        save_state(state)

        log(f"INFO: Done. posts_done={posts_done}")

    log("INFO: Completed run.")


if __name__ == "__main__":
    main()
