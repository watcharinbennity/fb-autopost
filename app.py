import os
import io
import json
import random
import time
import csv
from datetime import datetime, timedelta, timezone

import requests

# ============ CONFIG ============
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0")  # ✅ จำ: v25.0
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = "state.json"
MAX_STATE_ITEMS = 5000

CSV_CONNECT_TIMEOUT = 20
CSV_READ_TIMEOUT = 60

IMG_CONNECT_TIMEOUT = 20
IMG_READ_TIMEOUT = 60

GRAPH_CONNECT_TIMEOUT = 20
GRAPH_READ_TIMEOUT = 60

POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
END_MONTH_BOOST_DAYS = int(os.getenv("END_MONTH_BOOST_DAYS", "3"))
POSTS_THIS_RUN = int(os.getenv("POSTS_THIS_RUN", "1"))

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
    "ของมันต้องมีติดบ้าน 🏡",
    "งานช่างเล็ก-ใหญ่ ทำเองได้ง่ายขึ้น 🔧",
    "คัดมาให้แล้ว ราคาโดน คุณภาพดี 💪",
    "พร้อมส่ง ใช้งานได้จริง 👍",
    "ของเข้าไว หมดไว ทักมาก่อนนะ 🔥",
]

CTA_LINES = [
    "สนใจทักแชทได้เลยครับ 💬",
    "กดลิงก์ดูรายละเอียด/สั่งซื้อได้ทันที ✅",
    "มีโปร/โค้ดส่วนลดเปลี่ยนตามรอบ กดเช็คในลิงก์เลย 🎟️",
]

# ============ ENV ============
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL")

if not PAGE_ID:
    raise SystemExit("ERROR: Missing env: PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    raise SystemExit("ERROR: Missing env: PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    raise SystemExit("ERROR: Missing env: SHOPEE_CSV_URL")

# ============ UTILS ============
def now_bkk() -> datetime:
    return datetime.now(timezone(timedelta(hours=7)))

def is_end_month_boost(now: datetime) -> bool:
    # Boost ช่วงท้ายเดือน END_MONTH_BOOST_DAYS วัน
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    last_day = next_month - timedelta(days=1)
    return (last_day.day - now.day) < END_MONTH_BOOST_DAYS

def is_campaign_day(now: datetime) -> bool:
    # วันแคมเปญรายเดือน (โหด ๆ): 1.1 / 2.2 / ... / 12.12 + 15 + 25 (เสริม)
    md = f"{now.month}.{now.day}"
    return md in {f"{m}.{m}" for m in range(1, 13)} or now.day in {15, 25}

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"used_ids": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"used_ids": []}

def save_state(state: dict) -> None:
    # trim
    used = state.get("used_ids", [])
    if len(used) > MAX_STATE_ITEMS:
        state["used_ids"] = used[-MAX_STATE_ITEMS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def http_get(url: str, timeout=(20, 60), headers=None, stream=False):
    r = requests.get(url, timeout=timeout, headers=headers, stream=stream)
    r.raise_for_status()
    return r

def graph_post(path: str, data=None, files=None) -> dict:
    url = f"{GRAPH_BASE}{path}"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    r = requests.post(url, params=params, data=data, files=files, timeout=(GRAPH_CONNECT_TIMEOUT, GRAPH_READ_TIMEOUT))
    # Graph ชอบส่ง error เป็น json แม้ status != 200
    try:
        js = r.json()
    except Exception:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or ("error" in js):
        raise RuntimeError(f"GRAPH ERROR: {js}")
    return js

# ============ CSV PARSE (Shopee) ============
def normalize_row(row: dict) -> dict:
    """
    รองรับ CSV Shopee หลากชื่อคอลัมน์:
      - name: name / title
      - url: url / product_link
      - images: image_link_1..10 / image_link / image_link_3.. / image_link
    """
    name = (row.get("name") or row.get("title") or "").strip()
    url = (row.get("url") or row.get("product_link") or "").strip()

    # collect images
    imgs = []
    # image_link_1..10 (บางไฟล์เป็น image_link_3..)
    for i in range(1, 11):
        k = f"image_link_{i}"
        v = (row.get(k) or "").strip()
        if v:
            imgs.append(v)

    # fallback single image_link
    v0 = (row.get("image_link") or "").strip()
    if v0:
        imgs.append(v0)

    # unique keep order
    seen = set()
    imgs2 = []
    for u in imgs:
        if u and u not in seen:
            seen.add(u)
            imgs2.append(u)

    return {"name": name, "url": url, "images": imgs2, "raw": row}

def fetch_csv_rows() -> list[dict]:
    print("INFO: Fetching CSV...")
    # stream + limit memory
    r = http_get(SHOPEE_CSV_URL, timeout=(CSV_CONNECT_TIMEOUT, CSV_READ_TIMEOUT), stream=True)
    # อ่านเป็น bytes แล้ว decode ทีเดียว (เผื่อไฟล์ใหญ่)
    content = r.content
    print(f"INFO: CSV bytes = {len(content)}; content-type={r.headers.get('content-type','')}")
    # รองรับ utf-8-sig
    text = content.decode("utf-8-sig", errors="replace")

    f = io.StringIO(text)
    reader = csv.DictReader(f)
    rows = []
    for row in reader:
        rows.append(row)
    print(f"INFO: CSV rows = {len(rows)}")
    return rows

def build_candidates(rows: list[dict]) -> list[dict]:
    normalized = [normalize_row(r) for r in rows]
    usable = []
    for n in normalized:
        if not n["name"] or not n["url"]:
            continue
        if len(n["images"]) < 1:
            continue
        usable.append(n)

    if not usable:
        # debug help
        sample_cols = list(rows[0].keys()) if rows else []
        raise SystemExit(
            "ERROR: CSV has no usable rows. Need name/title + url/product_link + at least 1 image_link(_N).\n"
            f"DEBUG: first row columns = {sample_cols[:50]}"
        )

    return usable

def pick_product(candidates: list[dict], state: dict) -> dict:
    used = set(state.get("used_ids", []))
    # product unique key: url
    fresh = [p for p in candidates if p["url"] not in used]
    pool = fresh if fresh else candidates

    chosen = random.choice(pool)
    # mark used
    state.setdefault("used_ids", []).append(chosen["url"])
    return chosen

# ============ CONTENT ============
def build_caption(product: dict, now: datetime) -> str:
    boost = is_end_month_boost(now)
    campaign = is_campaign_day(now)

    title = product["name"].strip()
    link = product["url"].strip()

    opener = random.choice(SELLING_HOOKS)
    cta = random.choice(CTA_LINES)

    promo_lines = []
    if campaign:
        promo_lines.append("🎉 วันนี้มีลุ้นโปรแคมเปญประจำเดือน รีบเช็คโค้ดส่วนลดในลิงก์!")
    if boost:
        promo_lines.append("🔥 โค้งสุดท้ายปลายเดือน! ของใช้จำเป็นจัดให้คุ้ม ๆ")

    bullets = [
        "✅ คัดของน่าใช้สำหรับบ้าน/งานช่าง",
        "✅ ดูรูป+รายละเอียดครบ กดลิงก์ได้เลย",
        "✅ สนใจหลายชิ้น ทักมาให้ช่วยแนะนำได้",
    ]

    tags = " ".join(HASHTAGS)

    parts = [
        f"{opener}",
        "",
        f"🛒 {title}",
        "",
        *promo_lines,
        "",
        *bullets,
        "",
        f"👉 {link}",
        "",
        f"{cta}",
        "",
        tags,
    ]
    # ล้างบรรทัดว่างซ้อน
    out = []
    for p in parts:
        if p == "" and (not out or out[-1] == ""):
            continue
        out.append(p)
    return "\n".join(out).strip()

# ============ FACEBOOK POST (3 images) ============
def download_image_bytes(url: str) -> bytes:
    r = http_get(url, timeout=(IMG_CONNECT_TIMEOUT, IMG_READ_TIMEOUT), stream=True, headers={
        "User-Agent": "Mozilla/5.0"
    })
    return r.content

def upload_unpublished_photo(page_id: str, image_bytes: bytes) -> str:
    # POST /{page_id}/photos with published=false
    files = {"source": ("image.jpg", image_bytes, "image/jpeg")}
    data = {"published": "false"}
    js = graph_post(f"/{page_id}/photos", data=data, files=files)
    # returns id (photo id) or post_id sometimes
    return js["id"]

def create_feed_post_with_media(page_id: str, message: str, media_fbids: list[str]) -> str:
    data = {"message": message}
    # attached_media[0]={"media_fbid":"..."}
    for i, mid in enumerate(media_fbids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    js = graph_post(f"/{page_id}/feed", data=data)
    return js["id"]

def post_product(product: dict, now: datetime) -> str:
    imgs = product["images"][:POST_IMAGES_COUNT]
    if len(imgs) < POST_IMAGES_COUNT:
        # ถ้าไม่พอ 3 รูป ก็โพสต์เท่าที่มี (กันพัง)
        pass

    caption = build_caption(product, now)

    media_ids = []
    for u in imgs:
        img_bytes = download_image_bytes(u)
        mid = upload_unpublished_photo(PAGE_ID, img_bytes)
        media_ids.append(mid)

    post_id = create_feed_post_with_media(PAGE_ID, caption, media_ids)
    return post_id

# ============ MAIN ============
def main():
    now = now_bkk()
    print(f"INFO: Now (BKK) = {now.isoformat()}")
    print(f"INFO: End-month boost = {is_end_month_boost(now)} (END_MONTH_BOOST_DAYS={END_MONTH_BOOST_DAYS})")
    print(f"INFO: Campaign day = {is_campaign_day(now)}")
    print(f"INFO: POST_IMAGES_COUNT = {POST_IMAGES_COUNT}")

    state = load_state()

    rows = fetch_csv_rows()
    candidates = build_candidates(rows)

    for n in range(POSTS_THIS_RUN):
        product = pick_product(candidates, state)
        print(f"INFO: Picked: {product['name'][:80]} | {product['url']}")
        pid = post_product(product, now)
        print(f"OK: Posted feed id = {pid}")
        # กันยิงถี่
        time.sleep(5)

    save_state(state)

if __name__ == "__main__":
    main()
