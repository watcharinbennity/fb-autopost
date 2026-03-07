import json
import random
import os
import csv
import io
import requests
from datetime import datetime, timedelta, timezone

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI = os.getenv("OPENAI_API_KEY")
CSV_URL = os.getenv("SHOPEE_CSV_URL")

ASSET_DIR = "assets"

PRODUCT_FILE = "products.json"
POSTED_FILE = "posted_products.json"
LOG_FILE = "post_log.json"
REELS_SCRIPT_FILE = "reels_script.txt"

TH_TZ = timezone(timedelta(hours=7))


def load_json(path, default=None):
    if default is None:
        default = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_post(post_type, name, extra=None):
    logs = load_json(LOG_FILE, [])
    if not isinstance(logs, list):
        logs = []

    row = {
        "type": post_type,
        "name": name,
        "time": str(datetime.now(TH_TZ))
    }

    if isinstance(extra, dict):
        row.update(extra)

    logs.append(row)
    save_json(LOG_FILE, logs)


def analyze_posts():
    logs = load_json(LOG_FILE, [])
    stats = {}

    if not isinstance(logs, list):
        return stats

    for item in logs:
        if not isinstance(item, dict):
            continue
        t = item.get("type", "unknown")
        stats[t] = stats.get(t, 0) + 1

    return stats


def normalize_posted_products(raw):
    cleaned = []

    if not isinstance(raw, list):
        return cleaned

    for item in raw:
        if isinstance(item, str):
            value = item.strip()
            if value:
                cleaned.append(value)
        elif isinstance(item, dict):
            link = item.get("link")
            if isinstance(link, str) and link.strip():
                cleaned.append(link.strip())

    return list(dict.fromkeys(cleaned))


def is_first_run():
    posted_raw = load_json(POSTED_FILE, [])
    posted = normalize_posted_products(posted_raw)
    return len(posted) == 0


def get_mode_by_time():
    now = datetime.now(TH_TZ)
    minute = now.hour * 60 + now.minute

    if 9 * 60 <= minute < 10 * 60:
        return "viral"

    if 12 * 60 <= minute < 13 * 60:
        return "product"

    if 18 * 60 + 30 <= minute < 19 * 60 + 30:
        return "product"

    if 21 * 60 <= minute < 22 * 60:
        return "engage"

    return None


def detect_category(name, category=""):
    text = f"{name} {category}".lower()

    if any(k in text for k in ["โซล่า", "solar"]):
        return "solar"

    if any(k in text for k in ["ปลั๊ก", "plug", "usb", "power strip", "ปลั๊กไฟ"]):
        return "plug"

    if any(k in text for k in ["สว่าน", "ไขควง", "คีม", "ประแจ", "tools", "tool", "เครื่องมือ", "ช่าง"]):
        return "tools"

    if any(k in text for k in ["led", "หลอดไฟ", "lamp", "light bulb", "โคมไฟ"]):
        return "led"

    return "other"


def parse_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def parse_int(v, default=0):
    try:
        return int(float(v))
    except Exception:
        return default


def load_products_from_csv():
    if not CSV_URL:
        print("CSV_URL MISSING", flush=True)
        return []

    try:
        print("STEP: load csv", flush=True)

        r = requests.get(CSV_URL, timeout=20)
        r.raise_for_status()

        text = r.text
        reader = csv.DictReader(io.StringIO(text))

        products = []

        for row in reader:
            name = (
                row.get("name")
                or row.get("title")
                or row.get("product_name")
                or row.get("item_name")
                or ""
            ).strip()

            link = (
                row.get("link")
                or row.get("product_link")
                or row.get("url")
                or row.get("deeplink")
                or ""
            ).strip()

            raw_category = (
                row.get("category")
                or row.get("cat")
                or row.get("group")
                or ""
            ).strip()

            rating = parse_float(
                row.get("rating")
                or row.get("item_rating")
                or row.get("star")
                or 0
            )

            sold = parse_int(
                row.get("sold")
                or row.get("item_sold")
                or row.get("historical_sold")
                or 0
            )

            price = parse_float(
                row.get("price")
                or row.get("sale_price")
                or row.get("item_price")
                or 0
            )

            if not name or not link:
                continue

            category = detect_category(name, raw_category)

            products.append({
                "name": name,
                "category": category,
                "rating": rating,
                "sold": sold,
                "price": price,
                "link": link
            })

        print(f"CSV PRODUCTS: {len(products)}", flush=True)
        return products

    except Exception as e:
        print("CSV ERROR:", e, flush=True)
        return []


def load_products_fallback():
    data = load_json(PRODUCT_FILE, [])
    return data if isinstance(data, list) else []


def pick_product():
    csv_products = load_products_from_csv()

    if csv_products:
        products = csv_products
        print("USING PRODUCTS FROM CSV", flush=True)
    else:
        products = load_products_fallback()
        print("USING PRODUCTS FROM products.json", flush=True)

    if not products:
        print("NO PRODUCTS IN CSV AND products.json", flush=True)
        return None

    posted = set(normalize_posted_products(load_json(POSTED_FILE, [])))
    good = []

    for p in products:
        if not isinstance(p, dict):
            continue

        link = p.get("link")
        if not link:
            continue

        if link in posted:
            continue

        rating = parse_float(p.get("rating", 0))
        sold = parse_int(p.get("sold", 0))
        name = (p.get("name") or "").strip()
        category = p.get("category", "")

        if not name:
            continue

        # คัดสินค้า แต่ไม่เอายอดขายไปโชว์ในโพสต์
        if rating >= 4 and sold >= 10:
            if category in ["solar", "plug", "tools", "led", "other"]:
                good.append(p)

    if not good:
        print("NO GOOD PRODUCT AFTER FILTER", flush=True)
        return None

    good.sort(
        key=lambda x: (
            parse_float(x.get("rating", 0)),
            parse_int(x.get("sold", 0))
        ),
        reverse=True
    )

    pool = good[:30] if len(good) >= 30 else good
    product = random.choice(pool)

    posted.add(product["link"])
    save_json(POSTED_FILE, list(posted))

    return product


def ai_caption(name, category=""):
    fallback_map = {
        "solar": [
            f"⚡ {name}\n\nเหมาะกับบ้านที่อยากเพิ่มความสว่างแบบประหยัดพลังงาน",
            f"☀️ {name}\n\nตัวช่วยเพิ่มแสงสว่างรอบบ้าน ใช้งานสะดวก",
            f"⚡ {name}\n\nของน่าใช้สำหรับมุมหน้าบ้านและรอบบ้าน"
        ],
        "plug": [
            f"🔌 {name}\n\nของใช้จำเป็นที่ควรมีติดบ้านไว้",
            f"⚡ {name}\n\nใช้งานสะดวก เหมาะกับบ้านที่มีเครื่องใช้ไฟฟ้าหลายจุด",
            f"🔌 {name}\n\nตัวช่วยจัดการปลั๊กไฟให้ใช้งานง่ายขึ้น"
        ],
        "tools": [
            f"🛠 {name}\n\nเครื่องมือที่ควรมีติดบ้านไว้ใช้งาน",
            f"🔧 {name}\n\nเหมาะสำหรับงานช่างเล็ก ๆ ภายในบ้าน",
            f"🛠 {name}\n\nของน่าใช้สำหรับคนชอบทำงานเองที่บ้าน"
        ],
        "led": [
            f"💡 {name}\n\nตัวช่วยเพิ่มความสว่างในบ้านได้ดี",
            f"💡 {name}\n\nเหมาะกับคนที่อยากเปลี่ยนบรรยากาศในบ้านให้น่าอยู่ขึ้น",
            f"✨ {name}\n\nของใช้ไฟฟ้าที่ควรลองมีติดบ้าน"
        ],
        "other": [
            f"⚡ {name}\n\nของดีที่ควรมีติดบ้าน",
            f"🔥 {name}\n\nน่าใช้มากสำหรับบ้านยุคนี้",
            f"🏠 {name}\n\nตัวช่วยดี ๆ สำหรับใช้งานในบ้าน"
        ]
    }

    fallback = fallback_map.get(category, fallback_map["other"])

    if not OPENAI:
        return random.choice(fallback)

    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทยสำหรับเพจ BEN Home & Electrical

สินค้า: {name}
หมวดสินค้า: {category}

เงื่อนไข:
- สั้น
- อ่านง่าย
- น่าคลิก
- ไม่ต้องพูดถึงยอดขาย
- ไม่ต้องบอกว่าขายได้กี่ชิ้น
- ไม่ต้องใส่ราคา
- โทนเหมือนแนะนำของใช้ไฟฟ้า/ของใช้ในบ้าน
- ปิดท้ายแบบชวนดูสินค้าหรือชวนคอมเมนต์เบา ๆ
""".strip()

    try:
        print("STEP: openai caption", flush=True)
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4.1-mini",
                "input": prompt
            },
            timeout=20
        )
        r.raise_for_status()
        data = r.json()
        return data["output"][0]["content"][0]["text"]
    except Exception as e:
        print("OPENAI ERROR:", e, flush=True)
        return random.choice(fallback)


def viral_caption():
    posts = [
        "⚡ ไฟโซล่าดีไหม\n\nบ้านใครใช้อยู่บ้าง มาแชร์กันหน่อย",
        "🔌 ปลั๊กไฟแบบไหนปลอดภัยสำหรับใช้ในบ้าน",
        "🛠 เครื่องมือช่างที่ควรมีติดบ้าน มีอะไรบ้าง",
        "💡 หลอดไฟ LED ประหยัดไฟจริงไหม\n\nคุณใช้กันอยู่หรือเปล่า",
        "🏠 5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน\n\nบ้านคุณมีครบหรือยัง"
    ]
    return random.choice(posts)


def engage_caption():
    posts = [
        "บ้านคุณใช้หลอดไฟ LED หรือยัง",
        "เครื่องมือช่างที่ใช้บ่อยที่สุดในบ้านคืออะไร",
        "เคยใช้ไฟโซล่ารอบบ้านกันไหม",
        "บ้านคุณใช้ปลั๊กไฟกี่จุดในห้องนั่งเล่น",
        "ของใช้ไฟฟ้าชิ้นไหนสำคัญสุดสำหรับบ้านคุณ"
    ]
    return random.choice(posts)


def reels_idea():
    ideas = [
        "รีวิวไฟโซล่ากลางคืน",
        "ปลั๊กไฟแบบไหนปลอดภัย",
        "เครื่องมือช่างที่ควรมีติดบ้าน",
        "หลอดไฟ LED ประหยัดไฟไหม",
        "รีวิวสว่านไร้สาย"
    ]
    return random.choice(ideas)


def save_reels_script(text):
    with open(REELS_SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(text)


def ensure_image_exists(path):
    if os.path.exists(path):
        return path

    fallback = [
        os.path.join(ASSET_DIR, "solar.jpg"),
        os.path.join(ASSET_DIR, "safe_plug.jpg"),
        os.path.join(ASSET_DIR, "tools.jpg"),
        os.path.join(ASSET_DIR, "led_save_power.jpg"),
        os.path.join(ASSET_DIR, "home_electrical_5.jpg"),
    ]

    for f in fallback:
        if os.path.exists(f):
            print("IMAGE FALLBACK ->", f, flush=True)
            return f

    raise Exception("NO IMAGE FOUND")


def get_image(category):
    if category == "solar":
        return ensure_image_exists(os.path.join(ASSET_DIR, "solar.jpg"))

    if category == "plug":
        return ensure_image_exists(os.path.join(ASSET_DIR, "safe_plug.jpg"))

    if category == "tools":
        return ensure_image_exists(os.path.join(ASSET_DIR, "tools.jpg"))

    if category == "led":
        return ensure_image_exists(os.path.join(ASSET_DIR, "led_save_power.jpg"))

    return ensure_image_exists(os.path.join(ASSET_DIR, "home_electrical_5.jpg"))


def post(caption, image):
    image = ensure_image_exists(image)

    print("STEP: facebook post", flush=True)
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    with open(image, "rb") as f:
        files = {"source": f}
        data = {
            "caption": caption,
            "access_token": TOKEN
        }
        r = requests.post(url, data=data, files=files, timeout=30)

    try:
        res = r.json()
        print("POST RESPONSE:", res, flush=True)
        return res.get("post_id")
    except Exception:
        print("POST RAW:", r.text, flush=True)
        return None


def comment(post_id, link):
    print("STEP: facebook comment", flush=True)
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    data = {
        "message": f"🛒 สั่งซื้อ\n{link}",
        "access_token": TOKEN
    }

    try:
        r = requests.post(url, data=data, timeout=20)
        print("COMMENT:", r.json(), flush=True)
    except Exception as e:
        print("COMMENT ERROR:", e, flush=True)


def run():
    if is_first_run():
        mode = "product"
        print("FIRST RUN -> FORCE PRODUCT", flush=True)
    else:
        mode = get_mode_by_time()

    if mode is None:
        print("MANUAL RUN -> FORCE PRODUCT", flush=True)
        mode = "product"

    print("MODE:", mode, flush=True)

    if mode == "product":
        product = pick_product()

        if not product:
            print("NO PRODUCT", flush=True)
            return

        cap = ai_caption(product["name"], product.get("category", "other"))
        img = get_image(product.get("category", ""))

        post_id = post(cap, img)

        if post_id:
            comment(post_id, product["link"])

        log_post("product", product["name"], {
            "category": product.get("category", ""),
            "rating": product.get("rating", 0),
            "link": product.get("link", "")
        })
        print("POST STATS:", analyze_posts(), flush=True)
        return

    if mode == "viral":
        cap = viral_caption()
        img = get_image("tools")

        post(cap, img)
        log_post("viral", "viral_post")
        print("POST STATS:", analyze_posts(), flush=True)
        return

    if mode == "engage":
        cap = engage_caption()
        img = get_image("tools")

        post(cap, img)
        log_post("engage", "question")
        print("POST STATS:", analyze_posts(), flush=True)
        return

    if mode == "reels":
        idea = reels_idea()
        save_reels_script(idea)
        print("REELS IDEA:", idea, flush=True)
        log_post("reels", "idea")
        print("POST STATS:", analyze_posts(), flush=True)
        return


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print("BOT ERROR:", e, flush=True)
