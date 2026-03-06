import os
import csv
import json
import random
import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"

# ลดจำนวนแถวลงก่อน เพื่อลดภาระ Actions
MAX_ROWS = 800

# เอาแค่ตัวเลือกดี ๆ พอ ไม่ต้องเก็บมหาศาล
TOP_CANDIDATES = 80

# จำกัดจำนวนรูปต่อโพสต์
MAX_IMAGES_PER_POST = 2

ALLOW_KEYWORDS = [
    "ไฟ", "ปลั๊ก", "สายไฟ", "หลอดไฟ", "สวิตช์",
    "เครื่องมือ", "สว่าน", "ไขควง", "คีม",
    "DIY", "บ้าน", "โคม", "โซล่า", "อินเวอร์เตอร์",
    "UPS", "แบตเตอรี่"
]

CAPTIONS = [
    """🔥 ของมันต้องมีติดบ้าน

{name}

💰 ราคา {price} บาท
⭐ {rating}/5
📦 {sold} คนซื้อแล้ว

👇 ดูสินค้า
{link}

#BENHomeElectrical #ShopeeAffiliate""",

    """⚡ สินค้าขายดีใน Shopee

{name}

💰 {price} บาท
⭐ รีวิว {rating}/5
📦 ขายแล้ว {sold}

{link}

#ของใช้ในบ้าน #เครื่องมือช่าง""",

    """🏠 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน

{name}

💰 ราคา {price} บาท
⭐ {rating}/5

👉 สั่งซื้อ
{link}"""
]


def log(msg):
    print(msg, flush=True)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "posted" not in data or not isinstance(data["posted"], list):
                return {"posted": []}
            return data
    except Exception as e:
        log(f"load_state error: {e}")
        return {"posted": []}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception as e:
        log(f"save_state error: {e}")


def allow_product(name):
    name = (name or "").lower()
    return any(k.lower() in name for k in ALLOW_KEYWORDS)


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def read_products():
    log("STEP 1: download csv")

    if not CSV_URL:
        raise ValueError("Missing SHOPEE_CSV_URL")

    products = []

    with requests.get(CSV_URL, timeout=60, stream=True) as r:
        r.raise_for_status()

        lines = (line.decode("utf-8-sig", errors="ignore") for line in r.iter_lines() if line)
        reader = csv.DictReader(lines)

        for i, row in enumerate(reader):
            if i >= MAX_ROWS:
                break

            name = row.get("product_name") or row.get("name") or ""
            price = row.get("price") or "0"
            link = row.get("product_link") or ""
            rating = safe_float(row.get("item_rating") or "0")
            sold = safe_int(row.get("historical_sold") or "0")

            img1 = row.get("image_link")
            img2 = row.get("image_link_2")
            img3 = row.get("image_link_3")

            if not name or not link or not img1:
                continue

            if not allow_product(name):
                continue

            images = [img for img in [img1, img2, img3] if img]

            products.append({
                "name": name.strip(),
                "price": price,
                "link": link.strip(),
                "rating": rating,
                "sold": sold,
                "images": images[:MAX_IMAGES_PER_POST]
            })

    log(f"STEP 2: products loaded = {len(products)}")
    return products


def score(p):
    return (p["sold"] / 10.0) + (p["rating"] * 15.0) + random.random() * 5.0


def choose_product(products, state):
    if not products:
        return None

    posted = set(state.get("posted", []))

    # คัด candidate ก่อน ไม่ต้องใช้งานหนักเกิน
    unposted = [p for p in products if p["link"] not in posted]
    pool = unposted if unposted else products

    # เรียงเฉพาะชุดที่จำกัด
    pool = sorted(pool, key=score, reverse=True)[:TOP_CANDIDATES]

    chosen = random.choice(pool)
    log(f"STEP 3: chosen product = {chosen['name'][:80]}")
    return chosen


def aff_link(link):
    if not AFF_ID:
        return link
    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={link}"


def caption(p):
    temp = random.choice(CAPTIONS)
    return temp.format(
        name=p["name"],
        price=p["price"],
        rating=f"{p['rating']:.1f}",
        sold=p["sold"],
        link=aff_link(p["link"])
    )


def upload_photo(url):
    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"
    payload = {
        "url": url,
        "published": "false",
        "access_token": TOKEN
    }

    r = requests.post(endpoint, data=payload, timeout=60)
    data = r.json()

    if "id" not in data:
        raise RuntimeError(f"upload_photo failed: {data}")

    return data["id"]


def post_images(p):
    media = []

    log("STEP 4: upload images")

    for img in p["images"][:MAX_IMAGES_PER_POST]:
        try:
            mid = upload_photo(img)
            media.append(mid)
            log(f"uploaded image id = {mid}")
        except Exception as e:
            log(f"upload image failed: {e}")

    if not media:
        log("no image uploaded, skip posting")
        return None

    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": caption(p),
        "access_token": TOKEN
    }

    for i, m in enumerate(media):
        payload[f"attached_media[{i}]"] = f'{{"media_fbid":"{m}"}}'

    log("STEP 5: create post")
    r = requests.post(endpoint, data=payload, timeout=60)
    data = r.json()

    if "id" not in data:
        log(f"post_images failed: {data}")
        return None

    return data["id"]


def comment_link(post_id, p):
    endpoint = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    payload = {
        "message": f"🔗 ลิงก์สั่งซื้อ\n{aff_link(p['link'])}",
        "access_token": TOKEN
    }

    try:
        r = requests.post(endpoint, data=payload, timeout=60)
        log(f"comment result: {r.json()}")
    except Exception as e:
        log(f"comment failed: {e}")


def validate_env():
    missing = []
    if not PAGE_ID:
        missing.append("PAGE_ID")
    if not TOKEN:
        missing.append("PAGE_ACCESS_TOKEN")
    if not CSV_URL:
        missing.append("SHOPEE_CSV_URL")

    if missing:
        raise ValueError(f"Missing env vars: {', '.join(missing)}")


def main():
    log("START APP")
    validate_env()

    state = load_state()
    products = read_products()

    if not products:
        log("No products found")
        return

    p = choose_product(products, state)
    if not p:
        log("No product selected")
        return

    post_id = post_images(p)

    if post_id:
        log(f"post created: {post_id}")
        comment_link(post_id, p)

        state["posted"].append(p["link"])

        # กัน state โตเกินไป
        state["posted"] = state["posted"][-500:]
        save_state(state)
    else:
        log("Post failed, state not updated")


if __name__ == "__main__":
    main()
