import os
import io
import json
import random
import time
import csv
from datetime import datetime, timezone, timedelta

import requests

GRAPH_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

# --- Config ---
POST_IMAGES_COUNT = 3
CSV_TIMEOUT = 60
IMG_TIMEOUT = 60
GRAPH_TIMEOUT = 60

STATE_FILE = "state.json"
MAX_STATE_ITEMS = 5000  # กันไฟล์โตเกิน

# Reach + Sales hashtags สำหรับ BEN Home & Electrical
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
    "ของมันต้องมีติดบ้าน 🏠",
    "งานซ่อมเล็ก-ใหญ่ ทำเองได้ง่ายขึ้น 🔧",
    "ตัวช่วยงานช่าง ใช้ดี คุ้มราคา 💪",
    "พร้อมส่ง ใช้งานได้จริง ไม่จกตา ✅",
]

CTA_LINES = [
    "👉 กดดูรายละเอียด/สั่งซื้อที่ลิงก์ในโพสต์",
    "👉 สนใจทักแชทได้เลย เดี๋ยวช่วยแนะนำรุ่นให้ครับ",
    "👉 ของมีจำกัด แนะนำกดเก็บไว้ก่อนนะครับ",
]

ENGAGEMENT_LINES = [
    "💬 คอมเมนต์ว่าอยากได้ “งานช่างแบบไหน” เดี๋ยวผมแนะนำของให้",
    "📌 เซฟโพสต์ไว้ เผื่อใช้ตอนต้องซ่อม/ติดตั้ง",
    "❤️ ถ้าชอบแนวนี้ กดติดตามเพจไว้ มีของเด็ดลงทุกวัน",
]

def env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise SystemExit(f"ERROR: Missing env: {name}")
    return v

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted_keys": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "posted_keys" not in data or not isinstance(data["posted_keys"], list):
            return {"posted_keys": []}
        return data
    except Exception:
        return {"posted_keys": []}

def save_state(state: dict) -> None:
    # trim
    state["posted_keys"] = state.get("posted_keys", [])[-MAX_STATE_ITEMS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_csv_text(url: str) -> str:
    r = requests.get(url, timeout=CSV_TIMEOUT)
    r.raise_for_status()
    # เผื่อเป็น utf-8-sig
    return r.content.decode("utf-8-sig", errors="replace")

def normalize_row(row: dict) -> dict:
    # รองรับ Shopee CSV ของคุณ: product_link/title/image_link_*
    # และรองรับแบบทั่วไป: url/name/image
    name = row.get("title") or row.get("name") or ""
    url = row.get("product_link") or row.get("url") or ""

    # ดึงรูปจากหลายคอลัมน์ (Shopee มักมี image_link, image_link_3..image_link_10 ฯลฯ)
    image_cols = []
    for k in row.keys():
        lk = k.lower()
        if lk == "image" or lk == "image_link" or lk.startswith("image_link_"):
            image_cols.append(k)

    def sort_key(col):
        # image_link ก่อน, แล้ว image_link_3.. ตามเลข
        if col.lower() == "image_link":
            return (0, 0)
        if col.lower().startswith("image_link_"):
            try:
                n = int(col.split("_")[-1])
            except Exception:
                n = 999
            return (1, n)
        return (2, 999)

    image_cols.sort(key=sort_key)

    images = []
    for c in image_cols:
        v = (row.get(c) or "").strip()
        if v and v not in images:
            images.append(v)

    # ราคา (ถ้ามี)
    price = row.get("sale_price") or row.get("price") or ""
    shop_name = row.get("shop_name") or ""

    # key กันโพสต์ซ้ำ
    unique_key = (row.get("itemid") or "") or (row.get("modelid") or "") or url or name

    return {
        "name": str(name).strip(),
        "url": str(url).strip(),
        "images": images,
        "price": str(price).strip(),
        "shop_name": str(shop_name).strip(),
        "key": str(unique_key).strip(),
        "raw": row,
    }

def parse_products(csv_text: str) -> list:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        raise SystemExit("ERROR: CSV empty or unreadable")

    products = []
    for r in rows:
        p = normalize_row(r)
        # ต้องมี name+url และมีรูปอย่างน้อย 1
        if p["name"] and p["url"] and len(p["images"]) >= 1:
            products.append(p)

    if not products:
        # โชว์คอลัมน์เพื่อ debug
        cols = list(rows[0].keys()) if rows else []
        raise SystemExit(
            "ERROR: No usable rows in CSV.\n"
            f"- Found columns: {cols}\n"
            "- Need at least: title(or name), product_link(or url), and image_link(or image_link_*)"
        )
    return products

def pick_product(products: list, state: dict) -> dict:
    posted = set(state.get("posted_keys", []))
    candidates = [p for p in products if p["key"] and p["key"] not in posted]

    # ถ้าโพสต์หมดแล้ว ให้รีเซ็ตวนใหม่ (โปรฯ: ไม่หยุดงาน)
    if not candidates:
        state["posted_keys"] = []
        candidates = products[:]

    return random.choice(candidates)

def build_caption(p: dict) -> str:
    hook = random.choice(SELLING_HOOKS)
    cta = random.choice(CTA_LINES)
    engage = random.choice(ENGAGEMENT_LINES)

    title = p["name"]
    url = p["url"]
    price = p["price"]
    shop = p["shop_name"]

    lines = []
    lines.append(hook)
    lines.append("")
    lines.append(f"🧰 {title}")

    if price:
        lines.append(f"💰 ราคา: {price}")

    if shop:
        lines.append(f"🏪 ร้าน: {shop}")

    lines.append("")
    lines.append(cta)
    lines.append(url)
    lines.append("")
    lines.append(engage)
    lines.append("")
    lines.append(" ".join(HASHTAGS))

    # ไม่ยาวเกินไป เน้นอ่านง่าย + engage
    return "\n".join(lines).strip()

def download_image(url: str) -> tuple:
    """
    โหลดรูปมาเป็น bytes เพื่ออัปโหลดแบบ multipart (กันปัญหา url รูปไม่ direct/โดนบล็อก)
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://shopee.co.th/",
    }
    r = requests.get(url, headers=headers, timeout=IMG_TIMEOUT)
    r.raise_for_status()
    ct = (r.headers.get("Content-Type") or "").lower()
    if "image/" not in ct:
        # บางที CDN ตอบเป็น octet-stream ก็ยังเป็นรูปได้ แต่กันพลาดหนัก ๆ
        # ถ้าอยากปล่อยผ่าน ให้คอมเมนต์บรรทัดนี้
        pass
    # ตั้งชื่อไฟล์ให้ graph รู้ type
    ext = ".jpg"
    if "png" in ct:
        ext = ".png"
    elif "webp" in ct:
        ext = ".webp"
    filename = f"img{ext}"
    return filename, r.content

def graph_post(url: str, data: dict, files: dict = None, timeout: int = GRAPH_TIMEOUT) -> dict:
    r = requests.post(url, data=data, files=files, timeout=timeout)
    try:
        j = r.json()
    except Exception:
        raise SystemExit(f"ERROR: Graph non-JSON response: {r.status_code} {r.text[:300]}")
    if "error" in j:
        raise SystemExit(f"ERROR: Graph API: {json.dumps(j, ensure_ascii=False)}")
    return j

def upload_photo_unpublished(page_id: str, token: str, image_url: str) -> str:
    # โหลดรูป → อัปโหลดด้วย source (เสถียรกว่าใช้ url ตรง ๆ)
    filename, content = download_image(image_url)
    files = {"source": (filename, content)}
    data = {
        "access_token": token,
        "published": "false",
    }
    j = graph_post(f"{GRAPH_BASE}/{page_id}/photos", data=data, files=files)
    return j["id"]  # photo id

def create_multi_photo_post(page_id: str, token: str, photo_ids: list, caption: str) -> dict:
    attached = [{"media_fbid": pid} for pid in photo_ids]
    data = {
        "access_token": token,
        "message": caption,
        "attached_media": json.dumps(attached, ensure_ascii=False),
    }
    j = graph_post(f"{GRAPH_BASE}/{page_id}/feed", data=data)
    return j

def main():
    page_id = env("PAGE_ID")
    token = env("PAGE_ACCESS_TOKEN")
    csv_url = env("SHOPEE_CSV_URL")

    print("INFO: Fetching CSV...")
    csv_text = fetch_csv_text(csv_url)
    products = parse_products(csv_text)
    print(f"INFO: Products usable: {len(products)}")

    state = load_state()
    p = pick_product(products, state)

    caption = build_caption(p)

    # เลือก 3 รูปแรกที่มีจริง
    images = [u for u in p["images"] if u.strip()][:POST_IMAGES_COUNT]
    if len(images) < 1:
        raise SystemExit("ERROR: selected product has no images")

    print("INFO: Uploading images (unpublished)...")
    photo_ids = []
    for idx, img_url in enumerate(images, start=1):
        print(f"  - Upload {idx}/{len(images)}")
        pid = upload_photo_unpublished(page_id, token, img_url)
        photo_ids.append(pid)
        time.sleep(1)  # กัน rate

    print("INFO: Creating feed post with attached_media...")
    post = create_multi_photo_post(page_id, token, photo_ids, caption)

    post_id = post.get("id", "")
    print(f"SUCCESS: posted: {post_id}")

    # บันทึก state กันโพสต์ซ้ำ
    key = p["key"]
    if key:
        state.setdefault("posted_keys", []).append(key)
        save_state(state)
        print("INFO: state.json updated")

if __name__ == "__main__":
    main()
