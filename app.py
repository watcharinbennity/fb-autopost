import os
import csv
import io
import json
import time
import random
import datetime
from typing import Dict, List, Tuple, Optional

import requests
from dateutil import tz


# =========================
# Config (Env)
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))

CSV_TIMEOUT_SEC = int(os.getenv("CSV_TIMEOUT_SEC", "45"))
CSV_RETRIES = int(os.getenv("CSV_RETRIES", "5"))

END_MONTH_BOOST_DAYS = int(os.getenv("END_MONTH_BOOST_DAYS", "3"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))

STATE_FILE = "state.json"
MAX_STATE_ITEMS = 5000

# เพจ BEN Home & Electrical: โทนแฮชแท็ก
HASHTAGS = [
    "#BENHomeElectrical",
    "#ของใช้ในบ้าน",
    "#อุปกรณ์ไฟฟ้า",
    "#เครื่องมือช่าง",
    "#งานช่าง",
    "#ซ่อมบ้าน",
    "#ของดีบอกต่อ",
]

SELLING_HOOKS = [
    "ของมันต้องมีติดบ้าน 🏠✨",
    "งานช่างเล็ก-ใหญ่ ทำเองได้ง่ายขึ้น 🔧",
    "คุ้มสุดในงบ ใช้ได้จริง 💪",
    "ของเข้าใหม่/ของฮิต รีบดูเลย 👀",
    "พร้อมส่ง ใช้งานได้จริง ไม่จกตา ✅",
]

CTA = [
    "กดดูรายละเอียด/สั่งซื้อได้ที่ลิงก์ 👉",
    "สนใจคลิกเลย 👇",
    "ดูราคาโปรที่นี่ 👉",
]

URGENCY = [
    "ของมีจำนวนจำกัด รีบจัดก่อนหมด!",
    "โปรเปลี่ยนได้ตลอด รีบเช็คตอนนี้!",
    "ราคาดีๆ แบบนี้ ไม่บ่อยนะ!",
]

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) fb-autopost/3.0"


# =========================
# Utilities
# =========================
def log(msg: str) -> None:
    print(msg, flush=True)


def must_env(name: str, value: str) -> None:
    if not value:
        raise SystemExit(f"ERROR: Missing env: {name}")


def load_state() -> Dict:
    if not os.path.exists(STATE_FILE):
        return {"posted_keys": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "posted_keys" not in data or not isinstance(data["posted_keys"], list):
            data["posted_keys"] = []
        return data
    except Exception:
        return {"posted_keys": []}


def save_state(state: Dict) -> None:
    # trim
    keys = state.get("posted_keys", [])
    if len(keys) > MAX_STATE_ITEMS:
        state["posted_keys"] = keys[-MAX_STATE_ITEMS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_end_of_month_boost(now_bkk: datetime.datetime) -> bool:
    # ถ้าวันนี้อยู่ในช่วงท้ายเดือน N วัน
    next_day = now_bkk.date() + datetime.timedelta(days=1)
    # ถ้าวันพรุ่งนี้เป็นเดือนใหม่ แปลว่าวันนี้คือวันสุดท้ายของเดือน
    last_day = (next_day.month != now_bkk.month)
    if last_day:
        return True
    # หรือถ้าเหลือ <= END_MONTH_BOOST_DAYS ถึงสิ้นเดือน
    # หา last date ของเดือนนี้
    first_next_month = (now_bkk.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
    last_date = first_next_month.date() - datetime.timedelta(days=1)
    remaining = (last_date - now_bkk.date()).days
    return remaining <= END_MONTH_BOOST_DAYS


def safe_float(x: str) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return 0.0


def safe_int(x: str) -> int:
    try:
        return int(float(str(x).replace(",", "").strip()))
    except Exception:
        return 0


def pick_first(*vals: str) -> str:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


# =========================
# CSV Fetch + Normalize
# =========================
def fetch_csv_text(url: str) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/csv,text/plain,*/*",
    }

    last_err = None
    for attempt in range(1, CSV_RETRIES + 1):
        try:
            log(f"INFO: CSV fetch attempt {attempt}/{CSV_RETRIES} (timeout={CSV_TIMEOUT_SEC}s)")
            r = requests.get(url, headers=headers, timeout=CSV_TIMEOUT_SEC, allow_redirects=True)
            r.raise_for_status()

            # บางลิงก์ส่งเป็น bytes แปลกๆ ให้เดา encoding
            r.encoding = r.encoding or "utf-8"
            text = r.text
            if not text.strip():
                raise RuntimeError("Empty CSV response")
            return text
        except Exception as e:
            last_err = e
            wait = min(2 ** attempt, 20)
            log(f"WARN: CSV fetch failed: {e} | retry in {wait}s")
            time.sleep(wait)

    raise SystemExit(f"ERROR: Cannot fetch CSV after {CSV_RETRIES} tries: {last_err}")


def normalize_rows(csv_text: str) -> List[Dict[str, str]]:
    f = io.StringIO(csv_text)
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        raise SystemExit("ERROR: CSV has no header/fieldnames.")

    # normalize headers: lowercase + strip
    fieldnames = [fn.strip() for fn in reader.fieldnames]
    log(f"INFO: CSV columns ({len(fieldnames)}): {fieldnames[:25]}{'...' if len(fieldnames)>25 else ''}")

    rows = []
    for row in reader:
        if not row:
            continue
        norm = {}
        for k, v in row.items():
            if k is None:
                continue
            nk = k.strip()
            norm[nk] = (v or "").strip()
        rows.append(norm)

    if not rows:
        raise SystemExit("ERROR: CSV has 0 rows.")
    return rows


def extract_images(row: Dict[str, str]) -> List[str]:
    # เก็บทุกคอลัมน์ที่ชื่อขึ้นต้นด้วย image_link
    imgs = []
    for k, v in row.items():
        if not v:
            continue
        kk = k.strip().lower()
        if kk.startswith("image_link"):
            url = v.strip()
            if url.startswith("http"):
                imgs.append(url)

    # กันซ้ำ เรียงตามที่เจอ
    seen = set()
    uniq = []
    for u in imgs:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


def normalize_product(row: Dict[str, str]) -> Optional[Dict]:
    # รองรับหลายฟอร์แมต: name/url อาจไม่มี แต่ Shopee export มักมี title + product_link
    name = pick_first(row.get("name", ""), row.get("title", ""), row.get("product_name", ""))
    url = pick_first(row.get("url", ""), row.get("product_link", ""), row.get("link", ""))

    images = extract_images(row)

    # ต้องมีขั้นต่ำ
    if not name or not url or len(images) < 1:
        return None

    # ตัวเลขสำหรับทำ weight
    discount_pct = safe_float(pick_first(row.get("discount_percentage", ""), row.get("discount", "")))
    sold = safe_int(pick_first(row.get("item_sold", ""), row.get("sold", "")))
    like = safe_int(pick_first(row.get("like", ""), row.get("likes", "")))
    shop_rating = safe_float(pick_first(row.get("shop_rating", ""), row.get("rating", "")))
    price = safe_float(pick_first(row.get("sale_price", ""), row.get("price", "")))

    # คีย์กันซ้ำ
    itemid = pick_first(row.get("itemid", ""), row.get("item_id", ""))
    modelid = pick_first(row.get("model_ids", ""), row.get("model_id", ""))
    dedupe_key = f"{itemid}|{modelid}|{url}".strip("|")

    return {
        "name": name,
        "url": url,
        "images": images,
        "discount_pct": discount_pct,
        "sold": sold,
        "like": like,
        "shop_rating": shop_rating,
        "price": price,
        "dedupe_key": dedupe_key,
        "raw": row,
    }


def build_catalog(rows: List[Dict[str, str]]) -> List[Dict]:
    products = []
    for r in rows:
        p = normalize_product(r)
        if p:
            products.append(p)

    if not products:
        # โชว์ตัวอย่างเพื่อ debug
        preview = rows[0] if rows else {}
        raise SystemExit(
            "ERROR: No usable rows in CSV. Need: (title/name) + (product_link/url) + at least 1 image_link*. "
            f"Preview row keys: {list(preview.keys())[:30]}"
        )
    return products


# =========================
# Pick product (Weighted + End-month promo)
# =========================
def compute_weight(p: Dict, boost_end_month: bool) -> float:
    # weight base
    w = 1.0

    # ยอดขาย/ไลก์ช่วยดัน
    w += min(p["sold"], 5000) / 250.0     # sold 250 = +1
    w += min(p["like"], 5000) / 500.0     # like 500 = +1

    # เรตติ้งร้าน
    w += max(0.0, p["shop_rating"] - 4.0) * 2.0  # 4.5 => +1

    # ส่วนลด
    w += min(p["discount_pct"], 80.0) / 10.0     # 10% => +1

    # สิ้นเดือน: ถ้ามีส่วนลดถึงขั้นต่ำ ให้คูณ
    if boost_end_month and p["discount_pct"] >= MIN_DISCOUNT_PCT:
        w *= 2.5

    return max(w, 0.1)


def pick_product(products: List[Dict], posted_keys: set, boost_end_month: bool) -> Dict:
    # กันซ้ำก่อน
    candidates = [p for p in products if p["dedupe_key"] not in posted_keys]
    if not candidates:
        # ถ้าซ้ำหมด ให้ยอมวนใหม่บางส่วน
        candidates = products[:]

    weights = [compute_weight(p, boost_end_month) for p in candidates]
    chosen = random.choices(candidates, weights=weights, k=1)[0]
    return chosen


# =========================
# Caption generator (Thai pro + reach)
# =========================
def format_price(p: float) -> str:
    if p <= 0:
        return ""
    # ราคาเป็นเลขกลม ๆ
    if p >= 100:
        return f"{int(round(p)):,}"
    return f"{p:.0f}"


def build_caption(p: Dict, boost_end_month: bool) -> str:
    hook = random.choice(SELLING_HOOKS)
    cta = random.choice(CTA)
    urg = random.choice(URGENCY)

    price_txt = format_price(p["price"])
    discount_txt = f"-{int(p['discount_pct'])}% " if p["discount_pct"] >= 1 else ""

    # เน้นสิ้นเดือน
    month_tag = ""
    if boost_end_month:
        month_tag = "🔥 โหมดสิ้นเดือน: เน้นของโปร/คุ้มสุด!\n"

    lines = []
    lines.append(hook)
    lines.append(month_tag.rstrip())
    lines.append(f"🛒 {p['name']}")
    if discount_txt or price_txt:
        meta = "💸 "
        if discount_txt:
            meta += f"{discount_txt}"
        if price_txt:
            meta += f"ราคาเริ่มต้น {price_txt} บาท"
        lines.append(meta.strip())

    lines.append("✅ เหมาะกับงานบ้าน/งานช่าง ใช้จริง คุ้มจริง")
    lines.append(f"📌 {urg}")
    lines.append(f"{cta} {p['url']}")
    lines.append("")
    lines.append(" ".join(HASHTAGS))

    # ลบบรรทัดว่างเกิน
    lines = [x for x in lines if x is not None]
    caption = "\n".join([x for x in lines if x != ""])
    return caption.strip()


# =========================
# Facebook posting (3 images in 1 post)
# =========================
def graph_post(path: str, data: Dict, files=None, timeout=60) -> Dict:
    url = f"{GRAPH_BASE}/{path.lstrip('/')}"
    r = requests.post(url, data=data, files=files, timeout=timeout)
    try:
        js = r.json()
    except Exception:
        raise SystemExit(f"ERROR: Graph non-JSON response: {r.status_code} {r.text[:300]}")

    if r.status_code >= 400 or ("error" in js):
        raise SystemExit(f"ERROR: Graph API error: {js}")

    return js


def upload_photo_unpublished(page_id: str, image_url: str, access_token: str) -> str:
    # published=false เพื่อเอาไป attach_media ทีหลัง
    data = {
        "url": image_url,
        "published": "false",
        "access_token": access_token,
    }
    js = graph_post(f"{page_id}/photos", data=data, timeout=90)
    # returns {"id": "..."}
    return js["id"]


def create_feed_post_with_media(page_id: str, caption: str, media_fbid_list: List[str], access_token: str) -> str:
    data = {
        "message": caption,
        "access_token": access_token,
    }
    # attached_media[0]={"media_fbid":"..."}
    for i, mid in enumerate(media_fbid_list):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid}, ensure_ascii=False)

    js = graph_post(f"{page_id}/feed", data=data, timeout=90)
    return js["id"]


# =========================
# Main
# =========================
def main():
    must_env("PAGE_ID", PAGE_ID)
    must_env("PAGE_ACCESS_TOKEN", PAGE_ACCESS_TOKEN)
    must_env("SHOPEE_CSV_URL", SHOPEE_CSV_URL)

    # เวลาไทย
    bkk = tz.gettz("Asia/Bangkok")
    now_bkk = datetime.datetime.now(tz=bkk)
    boost = is_end_of_month_boost(now_bkk)
    log(f"INFO: Now (BKK) = {now_bkk.isoformat()}")
    log(f"INFO: End-month boost = {boost} (END_MONTH_BOOST_DAYS={END_MONTH_BOOST_DAYS})")
    log(f"INFO: POST_IMAGES_COUNT = {POST_IMAGES_COUNT}")

    state = load_state()
    posted_keys = set(state.get("posted_keys", []))

    # Fetch CSV
    log("INFO: Fetching CSV...")
    csv_text = fetch_csv_text(SHOPEE_CSV_URL)

    rows = normalize_rows(csv_text)
    catalog = build_catalog(rows)
    log(f"INFO: Catalog usable products = {len(catalog)}")

    posts_done = 0
    for n in range(POSTS_PER_RUN):
        product = pick_product(catalog, posted_keys, boost)
        images = product["images"][:]
        random.shuffle(images)
        images = images[: max(1, POST_IMAGES_COUNT)]

        caption = build_caption(product, boost)

        log(f"INFO: Selected: {product['name']}")
        log(f"INFO: Images: {len(images)}")
        log("INFO: Uploading photos unpublished...")

        media_ids = []
        for img_url in images:
            mid = upload_photo_unpublished(PAGE_ID, img_url, PAGE_ACCESS_TOKEN)
            media_ids.append(mid)

        log("INFO: Creating feed post with attached media...")
        post_id = create_feed_post_with_media(PAGE_ID, caption, media_ids, PAGE_ACCESS_TOKEN)

        # update state
        posted_keys.add(product["dedupe_key"])
        state["posted_keys"] = list(posted_keys)
        save_state(state)

        posts_done += 1
        log(f"SUCCESS: Posted {post_id}")

        # กันรัวเกิน
        time.sleep(3)

    log(f"INFO: Done. posts={posts_done}")


if __name__ == "__main__":
    main()
