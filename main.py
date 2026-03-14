import os
import re
import io
import csv
import json
import random
import requests
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# =========================
# BASIC CONFIG
# =========================
TZ_TH = timezone(timedelta(hours=7))

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v25.0").strip()

SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

POST_MODE = os.getenv("POST_MODE", "").strip().lower()   # viral/product/engage/academy
FORCE_PRODUCT = os.getenv("FORCE_PRODUCT", "false").lower() == "true"

POSTED_JSON_PATH = "posted.json"
LOG_FILE = "post_log.txt"

MAX_ROWS = 50000
MIN_RATING = 4.0
MIN_SOLD = 10.0

# =========================
# THEME LOCK: BEN HOME & ELECTRICAL
# =========================
ALLOW_KEYWORDS = [
    # lighting
    "ไฟ", "หลอดไฟ", "โคมไฟ", "โคม", "led", "lamp", "light", "floodlight",
    "ไฟฉาย", "ไฟโซล่า", "ไฟสนาม", "ไฟถนน", "สปอตไลท์", "ไฟเพดาน", "ไฟติดผนัง",

    # electrical
    "ไฟฟ้า", "electrical", "ปลั๊ก", "ปลั๊กไฟ", "ปลั๊กพ่วง", "socket", "power strip",
    "เต้ารับ", "เบรกเกอร์", "breaker", "mcb", "rcbo", "fuse", "คัทเอาท์",
    "สวิตช์", "สวิตช์ไฟ", "switch", "สายไฟ", "wire", "cable", "ตู้ไฟ",
    "consumer unit", "ตู้คอนซูมเมอร์", "แรงดัน", "voltage tester",

    # tools
    "tool", "tools", "เครื่องมือ", "เครื่องมือช่าง", "ช่าง", "ไขควง", "ไขควงวัดไฟ",
    "คีม", "คีมตัด", "คีมปอกสาย", "สว่าน", "drill", "มัลติมิเตอร์", "multimeter",
    "tester", "ประแจ", "ประแจเลื่อน", "ค้อน", "เลื่อย", "คัตเตอร์", "ตลับเมตร",
]

BLOCK_KEYWORDS = [
    "กระเป๋า", "bag", "tote bag", "fashion", "แฟชั่น", "beauty", "cosmetic", "makeup",
    "ลิป", "ครีม", "รองเท้า", "เสื้อ", "เสื้อผ้า", "dress", "กระโปรง", "น้ำหอม",
    "ของเล่น", "toy", "ตุ๊กตา", "แม่และเด็ก", "baby", "อาหาร", "snack", "เครื่องสำอาง",
    "หมอน", "เครื่องนอน", "ผ้าห่ม", "แก้วน้ำ", "ขวดน้ำ", "เคสมือถือ", "โทรศัพท์",
    "เครื่องประดับ", "กระเป๋าเครื่องสำอาง",
]

CAPTION_TEMPLATES = [
    "งานไฟ งานช่าง งานติดตั้ง ต้องมีตัวช่วยดี ๆ 👨‍🔧⚡\n{title}\n\nเหมาะกับสายช่างและคนที่ชอบทำงานเองที่บ้าน\nเช็กราคาล่าสุดที่ลิงก์ด้านล่าง",
    "ไอเท็มสายไฟฟ้า/เครื่องมือที่น่าใช้ 🔧⚡\n{title}\n\nใช้งานสะดวก เหมาะทั้งงานบ้านและงานช่าง\nเช็กราคาล่าสุดที่ลิงก์ด้านล่าง",
    "ของดีสาย BEN Home & Electrical ⚡\n{title}\n\nคัดมาให้แล้วสำหรับสายไฟ สายช่าง สายติดตั้ง\nเช็กราคาล่าสุดที่ลิงก์ด้านล่าง",
    "ตัวช่วยงานช่างที่น่าสนใจ 👷‍♂️\n{title}\n\nดูใช้งานง่าย น่ามีติดบ้านติดร้านไว้\nเช็กราคาล่าสุดที่ลิงก์ด้านล่าง",
]

ENGAGE_CAPTIONS = [
    "ที่บ้านคุณมีอุปกรณ์ไฟฟ้าหรือเครื่องมือชิ้นไหนที่ขาดไม่ได้บ้างครับ? ⚡🔧",
    "ถ้าจะเลือกซื้อปลั๊กพ่วงหรือเครื่องมือช่าง 1 ชิ้น คุณดูอะไรเป็นอย่างแรก? 👇",
    "อยากให้ช่างเบนทำคลิปสอนเรื่องไฟฟ้าหัวข้อไหนต่อ คอมเมนต์มาได้เลยครับ ⚡",
]

ACADEMY_CAPTIONS = [
    "BEN Home & Electrical Academy ⚡\nเรียนไฟฟ้าแบบเข้าใจง่าย ใช้ได้จริง ค่อย ๆ ไต่ระดับไปด้วยกันครับ",
    "มาเรียนรู้เรื่องไฟฟ้าไปพร้อมกับช่างเบน ⚡\nเริ่มจากพื้นฐาน แล้วค่อยต่อยอดแบบเป็นขั้นเป็นตอน",
]

VIRAL_IMAGES_DIR = "viral_assets"
ENGAGE_IMAGES_DIR = "engage_assets"
ACADEMY_IMAGES_DIR = "academy_assets"

# =========================
# HELPERS
# =========================
def log(msg: str) -> None:
    line = f"[{datetime.now(TZ_TH).strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        s = str(v).replace(",", "").strip()
        return float(s)
    except Exception:
        return default


def pick_first(row: Dict[str, Any], keys: List[str], default: str = "") -> str:
    lower_map = {k.lower(): k for k in row.keys()}
    for key in keys:
        real_key = lower_map.get(key.lower())
        if real_key:
            value = row.get(real_key, "")
            if str(value).strip():
                return str(value).strip()
    return default


def best_price(row: Dict[str, Any]) -> float:
    candidates = [
        "price", "sale price", "price_min", "price max", "final_price", "discount_price",
        "ราคาขาย", "ราคา"
    ]
    vals = []
    for c in candidates:
        v = pick_first(row, [c], "")
        fv = to_float(v, 0.0)
        if fv > 0:
            vals.append(fv)
    return min(vals) if vals else 0.0


def load_posted() -> Dict[str, Any]:
    if not os.path.exists(POSTED_JSON_PATH):
        return {"posted_product_ids": [], "posted_titles": []}
    with open(POSTED_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_posted(data: Dict[str, Any]) -> None:
    with open(POSTED_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_blocked_title(title: str) -> bool:
    t = normalize_text(title)
    return any(normalize_text(k) in t for k in BLOCK_KEYWORDS)


def is_allowed_title(title: str) -> bool:
    t = normalize_text(title)
    if is_blocked_title(title):
        return False
    return any(normalize_text(k) in t for k in ALLOW_KEYWORDS)


def score_product(product: Dict[str, Any]) -> float:
    score = 0.0
    score += product["rating"] * 30
    score += min(product["sold"], 5000) * 0.05
    if product["price"] > 0:
        score += 5
    return score


def list_media_files(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        return []
    out = []
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            out.append(path)
    return sorted(out)


def choose_local_image(folder: str) -> Optional[str]:
    files = list_media_files(folder)
    return random.choice(files) if files else None


# =========================
# CSV
# =========================
def fetch_csv_rows(csv_url: str, max_rows: int = MAX_ROWS) -> List[Dict[str, Any]]:
    if not csv_url:
        raise ValueError("Missing SHOPEE_CSV_URL")

    log(f"Downloading CSV... max_rows={max_rows}")
    r = requests.get(csv_url, timeout=120)
    r.raise_for_status()

    content = r.content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(content))

    rows = []
    for i, row in enumerate(reader, start=1):
        rows.append(row)
        if i >= max_rows:
            break

    log(f"Loaded {len(rows)} rows")
    return rows


def extract_product(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = pick_first(row, ["product_name", "title", "name", "ชื่อสินค้า"], "")
    if not title:
        return None

    if not is_allowed_title(title):
        return None

    rating = to_float(pick_first(row, ["rating", "item_rating", "คะแนน"], "0"))
    sold = to_float(pick_first(row, ["sold", "historical_sold", "sales", "ขายแล้ว"], "0"))
    if rating < MIN_RATING or sold < MIN_SOLD:
        return None

    pid = pick_first(row, ["itemid", "product_id", "item_id", "id"], title)
    short_link = pick_first(
        row,
        ["product_short link", "product_short_link", "short_link", "short link", "affiliate_short_link"],
        "",
    )
    product_url = pick_first(
        row,
        ["product_link", "product_url", "url", "link", "affiliate_link"],
        "",
    )
    image = pick_first(
        row,
        ["image", "image_url", "image link", "image_link", "img_url", "picture", "image_url_1"],
        "",
    )

    result = {
        "id": str(pid).strip(),
        "title": title.strip(),
        "rating": rating,
        "sold": sold,
        "price": best_price(row),
        "short_link": short_link.strip() or product_url.strip(),
        "image": image.strip(),
    }
    result["score"] = score_product(result)
    return result


def choose_best_product(rows: List[Dict[str, Any]], posted: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    posted_ids = set(posted.get("posted_product_ids", []))
    posted_titles = {normalize_text(x) for x in posted.get("posted_titles", [])}

    candidates = []
    for row in rows:
        p = extract_product(row)
        if not p:
            continue
        if p["id"] in posted_ids:
            continue
        if normalize_text(p["title"]) in posted_titles:
            continue
        if not p["short_link"]:
            continue
        if not p["image"]:
            continue
        candidates.append(p)

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[:30]
    chosen = random.choice(top[:10] if len(top) >= 10 else top)
    log(f"Chosen product: {chosen['title']} | sold={chosen['sold']} | rating={chosen['rating']}")
    return chosen


# =========================
# FACEBOOK
# =========================
def download_image_bytes(url: str) -> bytes:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def fb_post_photo_bytes(image_bytes: bytes, caption: str) -> str:
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PAGE_ID}/photos"
    files = {"source": ("image.jpg", image_bytes)}
    data = {
        "caption": caption,
        "published": "true",
        "access_token": PAGE_ACCESS_TOKEN,
    }
    r = requests.post(url, files=files, data=data, timeout=120)
    r.raise_for_status()
    result = r.json()
    post_id = result.get("post_id") or result.get("id", "")
    log(f"Posted photo OK => {post_id}")
    return post_id


def fb_comment(post_id: str, message: str) -> None:
    if not post_id or not message.strip():
        return
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{post_id}/comments"
    data = {"message": message, "access_token": PAGE_ACCESS_TOKEN}
    r = requests.post(url, data=data, timeout=60)
    r.raise_for_status()
    log("Comment OK")


# =========================
# CAPTIONS
# =========================
def generate_product_caption(product: Dict[str, Any]) -> str:
    template = random.choice(CAPTION_TEMPLATES)
    return template.format(title=product["title"])


def generate_viral_caption() -> str:
    samples = [
        "เรื่องไฟฟ้าใกล้ตัวกว่าที่คิด ⚡\nรู้ไว้ ใช้จริง ปลอดภัยกว่าเดิม",
        "งานไฟ งานช่าง เริ่มจากความเข้าใจพื้นฐานที่ถูกต้อง ⚡",
        "ถ้าอยากเข้าใจไฟฟ้าแบบง่าย ๆ ติดตามช่างเบนไว้ได้เลยครับ 🔧⚡",
    ]
    return random.choice(samples)


def generate_engage_caption() -> str:
    return random.choice(ENGAGE_CAPTIONS)


def generate_academy_caption() -> str:
    return random.choice(ACADEMY_CAPTIONS)


# =========================
# MODE
# =========================
def current_mode() -> str:
    if FORCE_PRODUCT:
        return "product"

    if POST_MODE in {"viral", "product", "engage", "academy"}:
        return POST_MODE

    now = datetime.now(TZ_TH)
    hm = now.strftime("%H:%M")

    if hm == "09:00":
        return "viral"
    if hm == "12:00":
        return "product"
    if hm == "18:30":
        return "product"
    if hm == "21:00":
        return "engage"

    return "product"


# =========================
# FLOWS
# =========================
def post_product_flow() -> None:
    posted = load_posted()
    rows = fetch_csv_rows(SHOPEE_CSV_URL, max_rows=MAX_ROWS)
    product = choose_best_product(rows, posted)
    if not product:
        raise RuntimeError("No valid product found after BEN category filter")

    caption = generate_product_caption(product)
    image_bytes = download_image_bytes(product["image"])
    post_id = fb_post_photo_bytes(image_bytes, caption)

    comment_message = f"🛒 สั่งซื้อสินค้า\n{product['short_link']}"
    fb_comment(post_id, comment_message)

    posted["posted_product_ids"].append(product["id"])
    posted["posted_titles"].append(product["title"])
    posted["posted_product_ids"] = posted["posted_product_ids"][-5000:]
    posted["posted_titles"] = posted["posted_titles"][-5000:]
    save_posted(posted)


def post_local_image_flow(folder: str, caption: str) -> None:
    image_path = choose_local_image(folder)
    if not image_path:
        raise RuntimeError(f"No image found in folder: {folder}")
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    fb_post_photo_bytes(image_bytes, caption)


def post_viral_flow() -> None:
    post_local_image_flow(VIRAL_IMAGES_DIR, generate_viral_caption())


def post_engage_flow() -> None:
    post_local_image_flow(ENGAGE_IMAGES_DIR, generate_engage_caption())


def post_academy_flow() -> None:
    post_local_image_flow(ACADEMY_IMAGES_DIR, generate_academy_caption())


# =========================
# MAIN
# =========================
def validate_env() -> None:
    missing = []
    if not PAGE_ID:
        missing.append("PAGE_ID")
    if not PAGE_ACCESS_TOKEN:
        missing.append("PAGE_ACCESS_TOKEN")
    if not GRAPH_API_VERSION:
        missing.append("GRAPH_API_VERSION")
    if missing:
        raise ValueError("Missing env vars: " + ", ".join(missing))


def main() -> None:
    validate_env()
    mode = current_mode()
    log(f"Running mode => {mode}")

    if mode == "product":
        post_product_flow()
    elif mode == "viral":
        post_viral_flow()
    elif mode == "engage":
        post_engage_flow()
    elif mode == "academy":
        post_academy_flow()
    else:
        raise RuntimeError(f"Unsupported mode: {mode}")


if __name__ == "__main__":
    main()
