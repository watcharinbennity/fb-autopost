import os
import io
import csv
import json
import time
import random
import re
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

import requests

# =========================
# Config
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

POSTS_COUNT = int(os.getenv("POSTS_COUNT", "1"))
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))

END_MONTH_BOOST_DAYS = int(os.getenv("END_MONTH_BOOST_DAYS", "3"))
STATE_FILE = "state.json"
MAX_STATE_ITEMS = 5000

# Timeouts
CSV_TIMEOUT = (10, 60)      # connect, read
IMG_TIMEOUT = (10, 60)
GRAPH_TIMEOUT = (10, 60)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"

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
    "ของดีราคาคุ้ม ใช้งานได้จริง 🔥",
    "ช่างเลือกใช้เอง คุณภาพเน้น ๆ 🛠️",
    "งานเล็กงานใหญ่ เอาอยู่ 💪",
    "โปรวันนี้ รีบก่อนหมด! ⏳",
]

CTA = [
    "ทักแชท/คอมเมนต์ได้เลย เดี๋ยวแนะนำรุ่นให้ครับ 😊",
    "กดลิงก์ดูรายละเอียด/สั่งซื้อได้ทันที 👇",
    "มีหลายแบบหลายราคา เลือกให้เหมาะกับงานได้เลยครับ 👇",
]

CAMPAIGN_DAYS = {"03-03", "04-04", "05-05", "06-06", "07-07", "08-08", "09-09", "10-10", "11-11", "12-12"}


def die(msg: str):
    print(f"ERROR: {msg}")
    raise SystemExit(1)


def now_bkk_iso():
    # GitHub runner is UTC; emulate BKK time (+7)
    return datetime.now(timezone.utc).astimezone(timezone.utc).isoformat()


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    # trim
    seen = state.get("seen", [])
    if len(seen) > MAX_STATE_ITEMS:
        state["seen"] = seen[-MAX_STATE_ITEMS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_end_month_boost(bkk_dt: datetime) -> bool:
    # last day of month:
    first_next = (bkk_dt.replace(day=1) + relativedelta(months=1))
    last_day = first_next - relativedelta(days=1)
    return (last_day.day - bkk_dt.day) < END_MONTH_BOOST_DAYS


def is_campaign_day(bkk_dt: datetime) -> bool:
    mmdd = bkk_dt.strftime("%m-%d")
    return mmdd in CAMPAIGN_DAYS


def fetch_csv_text(url: str) -> str:
    if not url:
        die("Missing env: SHOPEE_CSV_URL")

    print("INFO: Fetching CSV...")
    headers = {"User-Agent": UA, "Accept": "text/csv,text/plain,*/*"}

    # retry with backoff
    for attempt in range(1, 6):
        try:
            print(f"INFO: CSV fetch attempt {attempt}/5 (timeout={CSV_TIMEOUT[1]}s)")
            r = requests.get(url, headers=headers, timeout=CSV_TIMEOUT, allow_redirects=True)
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")

            # If got HTML login page, fail clearly
            sample = (r.text or "")[:200].lower()
            if "text/html" in ct or "<html" in sample:
                raise RuntimeError("CSV URL returned HTML (login/blocked/redirect). Please use a direct CSV public link.")

            return r.text
        except Exception as e:
            print(f"INFO: CSV fetch failed: {e}")
            if attempt == 5:
                die(f"Cannot fetch CSV after retries. Last error: {e}")
            time.sleep(2 * attempt)

    die("Unreachable")
    return ""


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (s or "").strip().lower())


def pick_first(row: dict, keys: list[str]) -> str:
    for k in keys:
        v = row.get(k, "")
        if v is None:
            continue
        v = str(v).strip()
        if v:
            return v
    return ""


def parse_csv_rows(csv_text: str) -> list[dict]:
    buf = io.StringIO(csv_text)
    reader = csv.DictReader(buf)
    if not reader.fieldnames:
        die("CSV has no header / unreadable.")

    # normalize headers
    raw_fields = reader.fieldnames
    fields = [norm_key(x) for x in raw_fields]
    mapping = dict(zip(raw_fields, fields))

    rows = []
    for r in reader:
        nr = {}
        for rk, rv in r.items():
            nr[mapping.get(rk, norm_key(rk))] = (rv or "").strip()
        rows.append(nr)

    if not rows:
        die("CSV has 0 rows.")
    return rows


def extract_product(row: dict) -> dict | None:
    # Accept many possible schemas
    name = pick_first(row, ["name", "title", "product_name", "item_name"])
    url = pick_first(row, ["url", "product_link", "link", "item_url", "short_link", "affiliate_link"])
    if not name or not url:
        return None

    # find images from many patterns
    img_keys = []
    # common: image_link_1..n
    for i in range(1, 21):
        img_keys.append(f"image_link_{i}")
        img_keys.append(f"image_{i}")
        img_keys.append(f"img_{i}")
        img_keys.append(f"image_link{i}")
    img_keys += ["image_link", "image", "img", "thumbnail", "thumb", "image_url"]

    images = []
    for k in img_keys:
        v = row.get(k, "")
        if v and isinstance(v, str):
            v = v.strip()
            if v.startswith("http"):
                images.append(v)

    # some feeds store comma-separated images
    if not images:
        v = pick_first(row, ["images", "image_urls", "image_list"])
        if v and "http" in v:
            parts = re.split(r"[,\s]+", v)
            images = [p.strip() for p in parts if p.strip().startswith("http")]

    # keep unique
    seen = set()
    uniq = []
    for u in images:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    images = uniq

    # Score helpers
    def to_float(x):
        try:
            return float(str(x).replace("%", "").replace(",", "").strip())
        except Exception:
            return 0.0

    def to_int(x):
        try:
            return int(float(str(x).replace(",", "").strip()))
        except Exception:
            return 0

    discount = to_float(pick_first(row, ["discount_percentage", "discount", "discount_percent"]))
    sold = to_int(pick_first(row, ["item_sold", "sold", "sold_count"]))
    stock = to_int(pick_first(row, ["stock", "available_stock"]))
    price = pick_first(row, ["sale_price", "price", "final_price"])

    return {
        "name": name,
        "url": url,
        "images": images,
        "discount": discount,
        "sold": sold,
        "stock": stock,
        "price": price,
    }


def choose_products(products: list[dict], count: int, state: dict, boost: bool) -> list[dict]:
    seen = set(state.get("seen", []))

    # filter has >=1 image
    usable = [p for p in products if p.get("images")]
    if not usable:
        die("No usable products (need at least 1 image URL).")

    # avoid repeats if possible
    fresh = [p for p in usable if p["url"] not in seen]
    pool = fresh if len(fresh) >= count else usable

    # scoring for boost days: prefer discount & sold
    def score(p):
        base = random.random()
        if boost:
            base += (p.get("discount", 0) / 10.0)
            base += (min(p.get("sold", 0), 5000) / 2000.0)
        # prefer in-stock
        if p.get("stock", 0) > 0:
            base += 0.2
        return base

    pool_sorted = sorted(pool, key=score, reverse=True)
    chosen = pool_sorted[:count]
    return chosen


def build_caption(p: dict, boost: bool) -> str:
    hook = random.choice(SELLING_HOOKS)
    cta = random.choice(CTA)

    name = p["name"].strip()
    url = p["url"].strip()

    lines = []
    lines.append(hook)
    lines.append("")
    lines.append(f"🛒 **{name}**")

    if p.get("price"):
        lines.append(f"💰 ราคา: {p['price']}")

    if boost and p.get("discount", 0) > 0:
        lines.append(f"🏷️ โปรลด: {p['discount']}% (ช่วงแคมเปญ/ปลายเดือน)")

    # Benefits (generic but “มืออาชีพ”)
    lines.append("✅ จุดเด่น:")
    lines.append("• ใช้งานคุ้มค่า วัสดุดี")
    lines.append("• เหมาะกับงานบ้าน/งานช่างทั่วไป")
    lines.append("• ถ้าไม่แน่ใจรุ่นไหน ทักมาได้ ช่วยเลือกให้")

    lines.append("")
    lines.append(f"👉 ดูรายละเอียด/สั่งซื้อ: {url}")
    lines.append("")
    lines.append(cta)
    lines.append("")
    lines.append(" ".join(HASHTAGS))

    return "\n".join(lines)


def graph_post_unpublished_photo(image_url: str) -> str:
    endpoint = f"{GRAPH_BASE}/{PAGE_ID}/photos"
    data = {
        "url": image_url,
        "published": "false",
        "access_token": PAGE_ACCESS_TOKEN,
    }
    r = requests.post(endpoint, data=data, timeout=GRAPH_TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"Upload photo failed: HTTP {r.status_code} {r.text[:200]}")
    j = r.json()
    pid = j.get("id")
    if not pid:
        raise RuntimeError(f"Upload photo failed: no id {j}")
    return pid


def graph_create_feed_post(message: str, photo_ids: list[str]) -> str:
    endpoint = f"{GRAPH_BASE}/{PAGE_ID}/feed"
    attached = [{"media_fbid": pid} for pid in photo_ids]
    data = {
        "message": message,
        "attached_media": json.dumps(attached, ensure_ascii=False),
        "access_token": PAGE_ACCESS_TOKEN,
    }
    r = requests.post(endpoint, data=data, timeout=GRAPH_TIMEOUT)
    if r.status_code >= 400:
        raise RuntimeError(f"Create post failed: HTTP {r.status_code} {r.text[:200]}")
    j = r.json()
    post_id = j.get("id")
    if not post_id:
        raise RuntimeError(f"Create post failed: no id {j}")
    return post_id


def main():
    if not PAGE_ID:
        die("Missing env: PAGE_ID")
    if not PAGE_ACCESS_TOKEN:
        die("Missing env: PAGE_ACCESS_TOKEN")

    # BKK logic
    bkk = datetime.now(timezone.utc) + relativedelta(hours=7)
    boost = is_end_month_boost(bkk) or is_campaign_day(bkk)

    print(f"INFO: Now (BKK) = {bkk.isoformat()}")
    print(f"INFO: End-month boost = {is_end_month_boost(bkk)} (END_MONTH_BOOST_DAYS={END_MONTH_BOOST_DAYS})")
    print(f"INFO: Campaign day = {is_campaign_day(bkk)}")
    print(f"INFO: BOOST MODE = {boost}")
    print(f"INFO: POST_IMAGES_COUNT = {POST_IMAGES_COUNT}")

    state = load_state()
    state.setdefault("seen", [])

    csv_text = fetch_csv_text(SHOPEE_CSV_URL)
    rows = parse_csv_rows(csv_text)

    products = []
    for r in rows:
        p = extract_product(r)
        if p:
            products.append(p)

    if not products:
        die("CSV has no usable products. Need columns for name/title + url/link + at least 1 image URL.")

    # choose products to post
    chosen = choose_products(products, POSTS_COUNT, state, boost=boost)

    for idx, p in enumerate(chosen, start=1):
        imgs = p["images"][:]
        random.shuffle(imgs)
        imgs = imgs[:max(1, POST_IMAGES_COUNT)]

        caption = build_caption(p, boost=boost)

        print(f"INFO: Posting {idx}/{POSTS_COUNT}")
        print(f"INFO: Selected: {p['name']}")
        print(f"INFO: Images used: {len(imgs)}")

        # upload photos unpublished
        photo_ids = []
        for u in imgs:
            try:
                pid = graph_post_unpublished_photo(u)
                photo_ids.append(pid)
            except Exception as e:
                print(f"INFO: Photo upload failed for {u[:60]}... err={e}")

        if not photo_ids:
            print("INFO: No photos uploaded successfully -> skip this product")
            continue

        # create feed post with attached_media
        post_id = graph_create_feed_post(caption, photo_ids)
        print(f"SUCCESS: Posted {post_id}")

        # mark seen
        state["seen"].append(p["url"])
        save_state(state)

        # small delay
        time.sleep(2)

    print("DONE")


if __name__ == "__main__":
    main()
