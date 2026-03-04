import os
import io
import csv
import json
import random
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

# =========================
# ENV / CONFIG
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

PAGE_ID = (os.getenv("PAGE_ID") or "").strip()
PAGE_ACCESS_TOKEN = (os.getenv("PAGE_ACCESS_TOKEN") or "").strip()
SHOPEE_CSV_URL = (os.getenv("SHOPEE_CSV_URL") or "").strip()

STATE_FILE = "state.json"

POST_SCHEDULE_BKK = os.getenv("POST_SCHEDULE_BKK", "09:00,12:15,15:30,18:30,21:00").strip()
MAX_CATCHUP_PER_RUN = int(os.getenv("MAX_CATCHUP_PER_RUN", "1"))  # ชดเชยได้กี่สล็อตต่อรัน
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))

STREAM_SCAN_ROWS = int(os.getenv("STREAM_SCAN_ROWS", "30000"))
PICK_TOP_N = int(os.getenv("PICK_TOP_N", "400"))

MIN_RATING = float(os.getenv("MIN_RATING", "4.5"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "20"))
MIN_IMAGES = int(os.getenv("MIN_IMAGES", "3"))

AUTO_COMMENT = (os.getenv("AUTO_COMMENT", "true").lower() == "true")
FIRST_RUN_POST_NOW = (os.getenv("FIRST_RUN_POST_NOW", "true").lower() == "true")

# timeouts (connect, read)
CSV_TIMEOUT = (25, 180)
IMG_TIMEOUT = (25, 180)
GRAPH_TIMEOUT = (25, 180)

BKK = timezone(timedelta(hours=7))

if not PAGE_ID:
    raise SystemExit("ERROR: Missing env: PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    raise SystemExit("ERROR: Missing env: PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    raise SystemExit("ERROR: Missing env: SHOPEE_CSV_URL")

# =========================
# CAPTION ENGINE (หลายสไตล์)
# =========================
HASHTAGS = [
    "#BENHomeElectrical",
    "#ของใช้ในบ้าน",
    "#อุปกรณ์ไฟฟ้า",
    "#เครื่องมือช่าง",
    "#งานช่าง",
    "#ซ่อมบ้าน",
    "#ของดีบอกต่อ",
]

HOOKS = [
    "🔥 ของมันต้องมีติดบ้าน",
    "⚡ งานช่างง่ายขึ้นด้วยไอเท็มนี้",
    "🏠 ของใช้ในบ้านที่ควรมี",
    "💪 เครื่องมือดี งานก็ง่าย",
    "🧰 ช่างประจำบ้านควรมี",
    "✅ คัดของดีสำหรับบ้าน/งานช่าง",
]

CTA = [
    "👉 กดดูรายละเอียด / ราคา ล่าสุด",
    "👉 เช็คราคาและโค้ดส่วนลดในลิงก์",
    "👉 ดูรีวิวจริง + ราคา ณ ตอนนี้",
    "👉 กดสั่งซื้อได้จากลิงก์นี้",
]

BULLETS = [
    "✅ ใช้ได้จริง คุ้มราคา",
    "✅ เหมาะกับบ้าน/งานช่าง",
    "✅ ดูรูป+รายละเอียดครบในลิงก์",
    "✅ สนใจหลายชิ้น ทักมาให้ช่วยเลือกได้",
]

COMMENT_TEMPLATES = [
    "📌 ลิงก์สั่งซื้อ/ดูโปรล่าสุดอยู่ตรงนี้ครับ 👇\n{link}",
    "🔥 เช็คโค้ดลด + ราคา ณ ตอนนี้ได้ที่ลิงก์ 👇\n{link}",
    "✅ ดูรีวิว + รายละเอียดเต็มในลิงก์นี้ครับ 👇\n{link}",
]

# =========================
# TIME / SCHEDULE (Smart + Catch-up)
# =========================
def now_bkk() -> datetime:
    return datetime.now(BKK)

def parse_schedule(s: str):
    out = []
    for t in s.split(","):
        t = t.strip()
        if not t:
            continue
        hh, mm = t.split(":")
        out.append((int(hh), int(mm)))
    return sorted(set(out))

SCHEDULE = parse_schedule(POST_SCHEDULE_BKK)

def slot_key(day: datetime, hh: int, mm: int) -> str:
    return f"{day.strftime('%Y-%m-%d')} {hh:02d}:{mm:02d}"

def list_pending_slots(now: datetime, state: dict):
    """
    คืนรายการสล็อตของ 'วันนี้' ที่ควรโพสต์แล้ว (now >= slot_time) แต่ยังไม่โพสต์
    เรียงจากเก่า -> ใหม่ เพื่อชดเชยแบบเป็นลำดับ
    """
    posted = set(state.get("posted_slots", []))
    pending = []
    for hh, mm in SCHEDULE:
        key = slot_key(now, hh, mm)
        if key in posted:
            continue
        slot_time = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now >= slot_time:
            pending.append(key)
    return pending

# =========================
# STATE (รองรับ state เก่า + กันโต)
# =========================
def cleanup_state(state: dict, keep_days: int = 10):
    cutoff = (now_bkk() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    state["posted_slots"] = [s for s in state.get("posted_slots", []) if len(s) >= 10 and s[:10] >= cutoff][-5000:]
    state["used_urls"] = state.get("used_urls", [])[-8000:]

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted_slots": [], "used_urls": [], "first_run_done": False}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        if not isinstance(st, dict):
            st = {}
    except Exception:
        st = {}

    # รองรับ key เก่า
    if "used_urls" not in st:
        if isinstance(st.get("used"), list):
            st["used_urls"] = st["used"]
        elif isinstance(st.get("used_ids"), list):
            st["used_urls"] = st["used_ids"]
        else:
            st["used_urls"] = []
    if "posted_slots" not in st or not isinstance(st["posted_slots"], list):
        st["posted_slots"] = []

    if "first_run_done" not in st:
        st["first_run_done"] = False

    cleanup_state(st)
    return st

def save_state(state: dict):
    cleanup_state(state)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# =========================
# CSV STREAM (ทน + รองรับ delimiter)
# =========================
def detect_delimiter(sample: str) -> str:
    for d in [",", "\t", ";", "|"]:
        if sample.count(d) >= 2:
            return d
    return ","

def to_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip().replace(",", "")
        if not s:
            return None
        return float(s)
    except Exception:
        return None

def to_int(x):
    try:
        if x is None:
            return None
        s = str(x).strip().replace(",", "")
        if not s:
            return None
        return int(float(s))
    except Exception:
        return None

def normalize_row(row: dict) -> dict:
    name = (row.get("name") or row.get("title") or row.get("product_name") or row.get("item_name") or "").strip()
    url = (row.get("product_link") or row.get("url") or row.get("link") or row.get("affiliate_link") or "").strip()

    imgs = []
    for i in range(1, 11):
        v = (row.get(f"image_link_{i}") or "").strip()
        if v:
            imgs.append(v)
    v0 = (row.get("image_link") or row.get("image") or "").strip()
    if v0:
        imgs.append(v0)
    images = list(dict.fromkeys([u for u in imgs if u]))

    sale_price = to_float(row.get("sale_price") or row.get("final_price") or row.get("saleprice"))
    price = to_float(row.get("price") or row.get("original_price") or row.get("ori_price"))
    rating = to_float(row.get("item_rating") or row.get("rating") or row.get("product_rating"))
    sold = to_int(row.get("item_sold") or row.get("sold") or row.get("historical_sold"))

    discount_pct = to_float(row.get("discount_percentage") or row.get("discount_percent") or row.get("discount"))
    if discount_pct is None and price and sale_price and price > 0 and sale_price <= price:
        discount_pct = round((price - sale_price) / price * 100, 0)
    if sale_price is None and price is not None:
        sale_price = price

    return {
        "name": name,
        "url": url,
        "images": images,
        "sale_price": sale_price,
        "price": price,
        "discount_pct": discount_pct,
        "rating": rating,
        "sold": sold,
        "raw": row,
    }

def stream_candidates(max_rows: int) -> list[dict]:
    print("INFO: Streaming Shopee CSV...")
    r = requests.get(SHOPEE_CSV_URL, stream=True, timeout=CSV_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    raw = b""
    for chunk in r.iter_content(chunk_size=65536):
        if not chunk:
            continue
        raw += chunk
        if len(raw) >= 200000:
            break

    sample_text = raw.decode("utf-8-sig", errors="replace")
    delim = detect_delimiter(sample_text[:2000])
    print(f"INFO: delimiter='{delim}' sample_bytes={len(raw)} content-type={r.headers.get('content-type','')}")

    r2 = requests.get(SHOPEE_CSV_URL, stream=True, timeout=CSV_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    r2.raise_for_status()
    text_stream = io.TextIOWrapper(r2.raw, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.DictReader(text_stream, delimiter=delim)

    goods = []
    scanned = 0
    for row in reader:
        scanned += 1
        p = normalize_row(row)

        if not p["name"] or not p["url"]:
            continue
        if len(p["images"]) < MIN_IMAGES:
            continue

        rating = p["rating"] if p["rating"] is not None else 0.0
        disc = p["discount_pct"] if p["discount_pct"] is not None else 0.0

        if rating < MIN_RATING:
            continue
        if disc < MIN_DISCOUNT_PCT:
            continue

        goods.append(p)
        if scanned >= max_rows:
            break

    print(f"INFO: scanned={scanned} qualified={len(goods)}")
    if not goods:
        cols = reader.fieldnames or []
        raise SystemExit(
            "ERROR: No qualified products. ลองลด MIN_RATING / MIN_DISCOUNT_PCT หรือเช็คคอลัมน์ใน CSV\n"
            f"DEBUG columns={cols[:80]}"
        )
    return goods

# =========================
# RANK / PICK (ขายจริง)
# =========================
def score_product(p: dict) -> float:
    disc = p["discount_pct"] or 0.0
    rating = p["rating"] or 0.0
    sold = p["sold"] or 0
    # เน้น: ลดแรง + เรตติ้ง + ยอดขาย
    return (disc * 2.0) + (rating * 10.0) + (min(sold, 5000) / 400.0) + random.random()

def pick_product(cands: list[dict], state: dict) -> dict:
    used = set(state.get("used_urls", []))
    fresh = [p for p in cands if p["url"] not in used]
    pool = fresh if fresh else cands

    ranked = sorted(pool, key=score_product, reverse=True)
    top = ranked[: min(PICK_TOP_N, len(ranked))]
    chosen = random.choice(top)

    state.setdefault("used_urls", []).append(chosen["url"])
    return chosen

# =========================
# CAPTION (ราคา/เรตติ้ง/ส่วนลด + ไม่ดูบอท)
# =========================
def fmt_money(x):
    if x is None:
        return None
    try:
        return f"{int(round(float(x))):,}"
    except Exception:
        return None

def short_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

def build_caption(p: dict) -> str:
    hook = random.choice(HOOKS)
    cta = random.choice(CTA)
    tags = " ".join(HASHTAGS)

    # สุ่ม bullet 2-3 บรรทัดกันซ้ำ
    bullets = random.sample(BULLETS, k=random.choice([2, 3]))

    price_now = fmt_money(p.get("sale_price"))
    price_old = fmt_money(p.get("price"))
    disc = p.get("discount_pct")
    rating = p.get("rating")
    sold = p.get("sold")

    lines = [hook, "", f"🛒 {p['name']}"]

    meta = []
    if rating is not None:
        meta.append(f"⭐ {rating:.1f}/5")
    if disc is not None:
        meta.append(f"🔥 ลด {int(round(disc))}%")
    if sold is not None and sold > 0:
        meta.append(f"📦 ขายแล้ว {sold:,}+")
    if meta:
        lines.append("")
        lines.append(" / ".join(meta))

    if price_now:
        if price_old and price_old != price_now:
            lines.append(f"💰 ราคาโปร {price_now} บาท (จาก {price_old})")
        else:
            lines.append(f"💰 ราคา {price_now} บาท")

    lines.append("")
    lines.extend(bullets)

    lines.extend([
        "",
        cta,
        f"👉 {p['url']}",
    ])

    domain = short_domain(p["url"])
    if domain:
        lines.append(f"🔎 แหล่งซื้อ: {domain}")

    lines.extend(["", tags])
    out = "\n".join(lines).strip()
    return out[:1800]

# =========================
# GRAPH API (upload 3 photos + create post + auto comment)
# =========================
def graph_post(path: str, data=None, files=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    r = requests.post(url, params=params, data=data, files=files, timeout=GRAPH_TIMEOUT)
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: {js}")
    return js

def download_image_bytes(url: str) -> bytes:
    r = requests.get(url, timeout=IMG_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.content

def upload_unpublished_photo(image_bytes: bytes) -> str:
    files = {"source": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"published": "false"}
    js = graph_post(f"/{PAGE_ID}/photos", data=data, files=files)
    return js["id"]

def create_feed_post_with_media(message: str, media_fbids: list[str]) -> str:
    data = {"message": message}
    for i, mid in enumerate(media_fbids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    js = graph_post(f"/{PAGE_ID}/feed", data=data)
    return js["id"]  # feed post id

def create_comment_on_post(post_id: str, message: str) -> str:
    js = graph_post(f"/{post_id}/comments", data={"message": message})
    return js.get("id", "")

def post_product(p: dict) -> str:
    caption = build_caption(p)
    imgs = p["images"][:POST_IMAGES_COUNT]

    media_ids = []
    for u in imgs:
        img_bytes = download_image_bytes(u)
        mid = upload_unpublished_photo(img_bytes)
        media_ids.append(mid)
        time.sleep(1)

    post_id = create_feed_post_with_media(caption, media_ids)
    print("INFO: Created post_id =", post_id)

    if AUTO_COMMENT:
        comment = random.choice(COMMENT_TEMPLATES).format(link=p["url"])
        try:
            cid = create_comment_on_post(post_id, comment)
            print("INFO: Commented id =", cid)
        except Exception as e:
            print("WARN: Comment failed:", str(e))

    return post_id

# =========================
# MAIN (V14: catch-up missed slots)
# =========================
def main():
    now = now_bkk()
    print("V14 AUTO SALES ENGINE")
    print("Graph =", GRAPH_VERSION)
    print("Now(BKK) =", now.strftime("%Y-%m-%d %H:%M:%S"))
    print("Schedule =", POST_SCHEDULE_BKK)
    print("Catchup/run =", MAX_CATCHUP_PER_RUN)

    state = load_state()

    # โพสต์แรกทันที (ครั้งเดียว) เพื่อทดสอบ/เริ่มระบบ
    if FIRST_RUN_POST_NOW and not state.get("first_run_done", False):
        print("INFO: First run -> post now (one time).")
        cands = stream_candidates(max_rows=STREAM_SCAN_ROWS)
        p = pick_product(cands, state)
        post_id = post_product(p)
        state["first_run_done"] = True
        # ยังไม่ต้อง mark posted_slots ใน first run (เพราะไม่ได้ผูกกับเวลา)
        save_state(state)
        print("DONE: first run post =", post_id)
        return

    pending = list_pending_slots(now, state)
    if not pending:
        print("SKIP: No pending slot (ยังไม่ถึงเวลาถัดไป หรือโพสต์ครบแล้ว)")
        save_state(state)
        return

    # ชดเชยตามลำดับเก่า -> ใหม่ แต่จำกัดจำนวนต่อรัน
    to_do = pending[:max(1, MAX_CATCHUP_PER_RUN)]
    print("PENDING slots =", pending)
    print("WILL DO slots =", to_do)

    # โหลด + คัดของดีครั้งเดียว แล้วโพสต์หลายสล็อตได้ (ประหยัดเวลา)
    cands = stream_candidates(max_rows=STREAM_SCAN_ROWS)

    for slot in to_do:
        p = pick_product(cands, state)
        print(f"POST FOR SLOT {slot} -> {p['name'][:90]} | rating={p.get('rating')} disc={p.get('discount_pct')}")
        post_id = post_product(p)
        print("POSTED:", post_id)
        state.setdefault("posted_slots", []).append(slot)
        time.sleep(6)

    save_state(state)
    print("DONE.")

if __name__ == "__main__":
    main()
