import os
import io
import csv
import json
import random
import requests
from datetime import datetime, timezone, timedelta

# ======================
# CONFIG
# ======================
GRAPH_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL")

STATE_FILE = "state.json"

STREAM_SAMPLE = int(os.getenv("STREAM_SAMPLE", "25000"))
POST_IMAGES = int(os.getenv("POST_IMAGES_COUNT", "3"))
POST_TIMES = os.getenv("POST_TIMES", "09:00,12:15,15:30,18:30,21:00").split(",")

# ======================
# VALIDATE ENV
# ======================
if not PAGE_ID:
    raise SystemExit("ERROR: Missing env: PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    raise SystemExit("ERROR: Missing env: PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    raise SystemExit("ERROR: Missing env: SHOPEE_CSV_URL")

# ======================
# MARKETING TEXT
# ======================
HOOKS = [
    "🔥 ของมันต้องมีติดบ้าน",
    "⚡ งานช่างง่ายขึ้นด้วยไอเท็มนี้",
    "🏠 ของใช้ในบ้านที่ควรมี",
    "💪 เครื่องมือดี งานก็ง่าย",
    "🧰 ช่างมือโปรยังใช้",
    "✨ ไอเท็มยอดนิยมตอนนี้",
]

CTA = [
    "👉 กดดูรายละเอียด / ราคา ล่าสุด",
    "👉 เช็คราคาและโปรโมชั่นล่าสุด",
    "👉 กดสั่งซื้อผ่านลิงก์นี้ได้เลย",
    "👉 ดูรีวิวและราคาได้ที่ลิงก์",
]

HASHTAGS = [
    "#BENHomeElectrical",
    "#ของใช้ในบ้าน",
    "#เครื่องมือช่าง",
    "#อุปกรณ์ไฟฟ้า",
    "#งานช่าง",
    "#ซ่อมบ้าน",
    "#ของดีบอกต่อ",
    "#เครื่องมือช่างราคาดี",
]

# ======================
# TIME
# ======================
def now_bkk():
    return datetime.now(timezone(timedelta(hours=7)))

def is_post_time():
    now = now_bkk().strftime("%H:%M")
    return now in POST_TIMES

# ======================
# STATE (รองรับ state เก่า)
# ======================
def normalize_state(state: dict) -> dict:
    """
    รองรับ state เก่าหลายแบบ:
    - {"used_ids":[...]}  -> map เป็น used
    - {"used":[...]}      -> ok
    - ว่าง/พัง            -> reset
    """
    if not isinstance(state, dict):
        state = {}

    # map key เก่า -> ใหม่
    if "used" not in state:
        if "used_ids" in state and isinstance(state["used_ids"], list):
            state["used"] = state["used_ids"]
        else:
            state["used"] = []

    if "first" not in state:
        # ถ้า state เดิมเคยมี used แล้ว ให้ถือว่าไม่ใช่ first run
        state["first"] = (len(state["used"]) == 0)

    # ทำให้แน่ใจว่าเป็น list
    if not isinstance(state["used"], list):
        state["used"] = []

    return state

def load_state():
    if not os.path.exists(STATE_FILE):
        return normalize_state({"used": [], "first": True})

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return normalize_state(raw)
    except Exception:
        return normalize_state({"used": [], "first": True})

def save_state(state):
    state = normalize_state(state)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ======================
# STREAM CSV (SAFE)
# ======================
def stream_products():
    print("INFO: Streaming Shopee CSV...")

    r = requests.get(
        SHOPEE_CSV_URL,
        stream=True,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=(20, 120),
        allow_redirects=True,
    )
    r.raise_for_status()

    wrapper = io.TextIOWrapper(r.raw, encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(wrapper)

    sample = []
    for row in reader:
        name = (row.get("title") or row.get("name") or "").strip()
        url = (row.get("product_link") or row.get("url") or "").strip()

        if not name or not url:
            continue

        images = []
        for n in range(1, 11):
            key = f"image_link_{n}"
            v = (row.get(key) or "").strip()
            if v:
                images.append(v)

        v0 = (row.get("image_link") or "").strip()
        if v0:
            images.append(v0)

        # unique
        images = list(dict.fromkeys([x for x in images if x]))

        if len(images) == 0:
            continue

        sample.append({"name": name, "url": url, "images": images})

        if len(sample) >= STREAM_SAMPLE:
            break

    if not sample:
        raise SystemExit("ERROR: No usable products from CSV (check columns title/name, product_link/url, image_link_*).")

    print("INFO: Products sampled =", len(sample))
    return sample

# ======================
# PRODUCT RANKING
# ======================
def rank_products(products):
    ranked = []
    for p in products:
        score = random.random()
        name = p["name"].lower()

        # โหดแบบมีแนวโน้มขาย: ลดราคา/โปร/เครื่องมือ/เซ็ต
        if "sale" in name or "ลด" in name or "โปรโมชั่น" in name:
            score += 0.6
        if "pro" in name or "professional" in name:
            score += 0.3
        if "tool" in name or "เครื่องมือ" in name:
            score += 0.35
        if "set" in name or "ชุด" in name:
            score += 0.25
        if "kit" in name:
            score += 0.2

        ranked.append((score, p))

    ranked.sort(reverse=True, key=lambda x: x[0])
    return [x[1] for x in ranked]

# ======================
# PICK PRODUCT
# ======================
def pick_product(products, state):
    state = normalize_state(state)
    ranked = rank_products(products)

    used = set(state.get("used", []))
    fresh = [p for p in ranked if p["url"] not in used]
    pool = fresh if fresh else ranked

    # เลือกจาก top 200 เพิ่มคุณภาพ/โอกาสขาย
    product = random.choice(pool[: min(200, len(pool))])

    state["used"].append(product["url"])
    return product

# ======================
# CAPTION
# ======================
def build_caption(product):
    hook = random.choice(HOOKS)
    cta = random.choice(CTA)
    tags = " ".join(HASHTAGS)

    return f"""
{hook}

🛒 {product['name']}

{cta}
{product['url']}

{tags}
""".strip()

# ======================
# IMAGE
# ======================
def download_image(url):
    r = requests.get(url, timeout=(20, 120), headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.content

# ======================
# FACEBOOK GRAPH
# ======================
def upload_photo(img_bytes):
    url = f"{GRAPH_BASE}/{PAGE_ID}/photos"
    files = {"source": ("img.jpg", img_bytes, "image/jpeg")}
    data = {"published": "false"}

    r = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        data=data,
        files=files,
        timeout=(20, 120),
    )

    js = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in js:
        raise RuntimeError(f"GRAPH upload_photo ERROR: {js}")

    return js["id"]

def create_post(message, media_ids):
    url = f"{GRAPH_BASE}/{PAGE_ID}/feed"
    data = {"message": message}

    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})

    r = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        data=data,
        timeout=(20, 120),
    )

    js = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in js:
        raise RuntimeError(f"GRAPH create_post ERROR: {js}")

    return js["id"]

# ======================
# POST PRODUCT
# ======================
def post_product(product):
    imgs = product["images"][:POST_IMAGES]
    caption = build_caption(product)

    media = []
    for u in imgs:
        img = download_image(u)
        mid = upload_photo(img)
        media.append(mid)

    pid = create_post(caption, media)
    return pid

# ======================
# MAIN
# ======================
def main():
    print("Affiliate Bot V8.1 (FIX state)")

    state = load_state()
    print("INFO: state keys =", list(state.keys()))

    # first run: โพสต์ทันที
    if state.get("first", True):
        print("INFO: First run post")
        products = stream_products()
        product = pick_product(products, state)
        pid = post_product(product)
        print("OK: Post ID:", pid)
        state["first"] = False
        save_state(state)
        return

    if not is_post_time():
        print("INFO: Not post time. Now =", now_bkk().strftime("%H:%M"))
        return

    products = stream_products()
    product = pick_product(products, state)
    pid = post_product(product)
    print("OK: Post success:", pid)

    save_state(state)

if __name__ == "__main__":
    main()
