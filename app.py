import os
import io
import csv
import json
import random
import time
from datetime import datetime, timedelta, timezone

import requests
from dateutil.relativedelta import relativedelta


GRAPH_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = "state.json"
DEFAULT_POST_IMAGES_COUNT = 5

# ปลายเดือน: กี่วันสุดท้ายให้เน้นโปรแรง
DEFAULT_END_MONTH_BOOST_DAYS = 3

# เวลาไทย
TZ_TH = timezone(timedelta(hours=7))

# แฮชแท็กแนวเพจ BEN Home & Electrical
HASHTAGS_POOL = [
    "#BENHomeElectrical",
    "#ของใช้ในบ้าน",
    "#อุปกรณ์ไฟฟ้า",
    "#เครื่องมือช่าง",
    "#งานช่าง",
    "#ช่างไฟ",
    "#ซ่อมบ้าน",
    "#แต่งบ้าน",
    "#ของดีบอกต่อ",
    "#โปรวันนี้",
    "#ราคาคุ้ม",
]

# Hook/สไตล์การขายหลายแบบ (สุ่ม)
HOOKS = [
    "🔧 ของมันต้องมีติดบ้าน!",
    "⚡ อัปเกรดงานช่างให้ไวขึ้น!",
    "🏠 ของดีไว้ซ่อมบ้าน ใช้ได้จริง",
    "🔥 โปรคุ้ม ๆ สำหรับสายช่าง",
    "💪 งานหนักก็เอาอยู่ ใช้แล้วคุ้ม",
]

BENEFITS = [
    "✅ แข็งแรง ทนงาน ใช้ได้นาน",
    "✅ ใช้ง่าย เหมาะทั้งมือใหม่และช่าง",
    "✅ คุ้มราคา คุณภาพเกินคุ้ม",
    "✅ เหมาะกับงานซ่อม/ติดตั้ง/งานช่างทั่วไป",
]

CTAS = [
    "👉 กดดูรายละเอียด/ราคาได้ที่ลิงก์",
    "👉 สนใจเช็คราคาและรีวิวที่ลิงก์นี้",
    "👉 ดูสินค้าและสั่งซื้อได้เลยที่ลิงก์",
]

COMMENT_CTAS = [
    "ลิงก์สินค้าอยู่ที่นี่ครับ 👇",
    "กดลิงก์ดูรายละเอียดได้เลย 👇",
    "เช็คราคา/รีวิวที่ลิงก์นี้ 👇",
]


def env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SystemExit(f"ERROR: Missing env: {name}")
    return v


def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted_keys": [], "posted_posts": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def http_with_retry(method, url, *, data=None, params=None, timeout=60, retries=3, sleep=2):
    last = None
    for i in range(retries):
        try:
            r = requests.request(method, url, data=data, params=params, timeout=timeout)
            return r
        except Exception as e:
            last = e
            time.sleep(sleep * (i + 1))
    raise SystemExit(f"ERROR: Network failed after retries: {last}")


def fetch_csv(csv_url: str) -> str:
    r = http_with_retry("GET", csv_url, timeout=60, retries=3)
    r.raise_for_status()
    # รองรับ UTF-8 BOM
    return r.content.decode("utf-8-sig", errors="replace")


def safe_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def normalize_row(row: dict) -> dict:
    # ชื่อสินค้า
    name = (row.get("title") or row.get("name") or "").strip()

    # ลิงก์สินค้า (จาก Shopee CSV ที่คุณมีจริงคือ product_link)
    url = (row.get("product_link") or row.get("url") or "").strip()

    # รูป: รองรับ image_link_1..image_link_10 + image_link
    images = []
    for k, v in row.items():
        if not v:
            continue
        if k == "image_link" or k.startswith("image_link_"):
            images.append(str(v).strip())

    # กันรูปซ้ำ
    images = list(dict.fromkeys([u for u in images if u]))

    # โปร/ส่วนลด
    discount_pct = safe_float(row.get("discount_percentage"))
    price = safe_float(row.get("price"))
    sale_price = safe_float(row.get("sale_price"))

    # ถ้าไม่มี discount_percentage แต่มี price/sale_price ให้คำนวณ
    if discount_pct is None and price and sale_price and price > 0 and sale_price < price:
        discount_pct = round((price - sale_price) / price * 100, 2)

    # คีย์กันซ้ำ: ใช้ itemid ก่อน ถ้าไม่มีใช้ url+name
    key = row.get("itemid") or row.get("modelid") or url or name

    return {
        "key": str(key),
        "name": name,
        "url": url,
        "images": images,
        "discount_pct": discount_pct,
        "price": price,
        "sale_price": sale_price,
    }


def parse_products(csv_text: str) -> list:
    reader = csv.DictReader(io.StringIO(csv_text))
    products = []
    for row in reader:
        p = normalize_row(row)
        if p["name"] and p["url"] and p["images"]:
            products.append(p)

    if not products:
        raise SystemExit("ERROR: CSV has no usable rows (need title/name + product_link/url + at least 1 image_link).")
    return products


def is_end_of_month(now_th: datetime, boost_days: int) -> bool:
    # วันสุดท้ายของเดือน
    first_next_month = (now_th.replace(day=1) + relativedelta(months=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    last_day = first_next_month - timedelta(days=1)
    return now_th.date() >= (last_day.date() - timedelta(days=boost_days - 1))


def pick_product(products: list, state: dict, end_month_boost_days: int) -> dict:
    now_th = datetime.now(TZ_TH)
    posted = set(state.get("posted_keys", []))

    # แยก candidate ที่ยังไม่เคยโพสต์
    fresh = [p for p in products if p["key"] not in posted]
    if not fresh:
        # รีเซ็ตกันซ้ำ ถ้าโพสต์ครบแล้ว
        state["posted_keys"] = []
        posted = set()
        fresh = products[:]

    # ช่วงปลายเดือน: เน้นสินค้าลดราคา/โปรแรง
    if is_end_of_month(now_th, end_month_boost_days):
        promo = []
        for p in fresh:
            dp = p.get("discount_pct")
            if dp is not None and dp > 0:
                promo.append(p)
            elif p.get("price") and p.get("sale_price") and p["sale_price"] < p["price"]:
                promo.append(p)

        if promo:
            # จัดอันดับด้วยส่วนลดมากสุด (ถ้าไม่มี discount_pct ใช้ price-sale_price)
            def promo_score(x):
                if x.get("discount_pct") is not None:
                    return x["discount_pct"]
                if x.get("price") and x.get("sale_price") and x["price"] > 0:
                    return (x["price"] - x["sale_price"]) / x["price"] * 100
                return 0

            promo.sort(key=promo_score, reverse=True)

            # เลือกสุ่มจาก Top N เพื่อไม่ให้ซ้ำแนวเดิม
            top_n = min(30, len(promo))
            return random.choice(promo[:top_n])

    # วันปกติ: สุ่มจากของใหม่
    return random.choice(fresh)


def build_caption(p: dict) -> str:
    # สุ่มแฮชแท็กแบบไม่เยอะเกิน (กันโดนมองว่า spam)
    tags = random.sample(HASHTAGS_POOL, k=min(6, len(HASHTAGS_POOL)))

    # สร้างบรรทัดโปร
    promo_line = ""
    if p.get("discount_pct") is not None and p["discount_pct"] > 0:
        promo_line = f"🔥 โปรลด {p['discount_pct']}% (ช่วงนี้คุ้มมาก!)"
    elif p.get("price") and p.get("sale_price") and p["sale_price"] < p["price"]:
        promo_line = "🔥 มีราคาพิเศษช่วงนี้ รีบกดดูเลย!"

    lines = []
    lines.append(random.choice(HOOKS))
    lines.append("")
    lines.append(f"🛠 {p['name']}")

    if promo_line:
        lines.append(promo_line)

    lines.append(random.choice(BENEFITS))
    lines.append(random.choice(BENEFITS))
    lines.append("")
    lines.append(random.choice(CTAS))
    lines.append(p["url"])
    lines.append("")
    lines.append(" ".join(tags))

    return "\n".join(lines)


def upload_photo_unpublished(page_id: str, token: str, image_url: str) -> str:
    endpoint = f"{GRAPH_BASE}/{page_id}/photos"
    data = {
        "url": image_url,
        "published": "false",
        "access_token": token,
    }
    r = http_with_retry("POST", endpoint, data=data, timeout=60, retries=3)
    j = r.json()
    if "error" in j:
        raise SystemExit(f"ERROR upload photo: {j}")
    return j["id"]


def create_feed_post_with_media(page_id: str, token: str, photo_ids: list, message: str) -> dict:
    endpoint = f"{GRAPH_BASE}/{page_id}/feed"
    attached_media = [{"media_fbid": pid} for pid in photo_ids]
    data = {
        "message": message,
        "attached_media": json.dumps(attached_media),
        "access_token": token,
    }
    r = http_with_retry("POST", endpoint, data=data, timeout=60, retries=3)
    j = r.json()
    if "error" in j:
        raise SystemExit(f"ERROR create post: {j}")
    return j


def comment_link(post_id: str, token: str, url: str) -> dict:
    endpoint = f"{GRAPH_BASE}/{post_id}/comments"
    msg = f"{random.choice(COMMENT_CTAS)}\n{url}"
    data = {
        "message": msg,
        "access_token": token,
    }
    r = http_with_retry("POST", endpoint, data=data, timeout=60, retries=3)
    j = r.json()
    if "error" in j:
        raise SystemExit(f"ERROR comment: {j}")
    return j


def main():
    page_id = env("PAGE_ID")
    token = env("PAGE_ACCESS_TOKEN")
    csv_url = env("SHOPEE_CSV_URL")

    post_images_count = env_int("POST_IMAGES_COUNT", DEFAULT_POST_IMAGES_COUNT)
    end_month_boost_days = env_int("END_MONTH_BOOST_DAYS", DEFAULT_END_MONTH_BOOST_DAYS)

    print("INFO: Fetching CSV...")
    csv_text = fetch_csv(csv_url)

    products = parse_products(csv_text)
    print(f"INFO: Products usable = {len(products)}")

    state = load_state()

    product = pick_product(products, state, end_month_boost_days)
    print(f"INFO: Selected = {product['name']}")

    caption = build_caption(product)

    # เลือกรูป
    imgs = product["images"][: max(1, min(10, post_images_count))]
    print(f"INFO: Using images = {len(imgs)}")

    # อัปโหลดรูปแบบ unpublished
    photo_ids = []
    for u in imgs:
        print("INFO: Uploading image...")
        pid = upload_photo_unpublished(page_id, token, u)
        photo_ids.append(pid)
        time.sleep(1)

    # สร้างโพสต์รวมรูป
    print("INFO: Creating feed post...")
    post = create_feed_post_with_media(page_id, token, photo_ids, caption)
    print("INFO: Post result:", post)

    post_id = post.get("id")  # format: PAGEID_POSTID
    if post_id:
        print("INFO: Commenting link...")
        c = comment_link(post_id, token, product["url"])
        print("INFO: Comment result:", c)

    # บันทึก state กันโพสต์ซ้ำ
    state.setdefault("posted_keys", [])
    state.setdefault("posted_posts", [])

    state["posted_keys"].append(product["key"])
    if post_id:
        state["posted_posts"].append(post_id)

    # จำกัดขนาด state ไม่ให้บวม
    state["posted_keys"] = state["posted_keys"][-5000:]
    state["posted_posts"] = state["posted_posts"][-5000:]

    save_state(state)
    print("INFO: Done.")


if __name__ == "__main__":
    main()
