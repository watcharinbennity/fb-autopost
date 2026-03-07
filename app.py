import json
import random
import os
import requests
from datetime import datetime, timedelta, timezone

from shopee_scraper import update_products

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI = os.getenv("OPENAI_API_KEY")

ASSET_DIR = "assets"

PRODUCT_FILE = "products.json"
POSTED_FILE = "posted_products.json"
LOG_FILE = "post_log.json"

TH_TZ = timezone(timedelta(hours=7))


def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def log_post(post_type, name):
    logs = load_json(LOG_FILE)

    if not isinstance(logs, list):
        logs = []

    logs.append({
        "type": post_type,
        "name": name,
        "time": str(datetime.now(TH_TZ))
    })

    save_json(LOG_FILE, logs)


def analyze_posts():
    logs = load_json(LOG_FILE)
    stats = {}

    if not isinstance(logs, list):
        return stats

    for item in logs:
        if not isinstance(item, dict):
            continue

        t = item.get("type", "unknown")
        stats[t] = stats.get(t, 0) + 1

    return stats


def is_first_run():
    posted_raw = load_json(POSTED_FILE)
    posted = normalize_posted_products(posted_raw)
    return len(posted) == 0


def get_mode_by_time():
    now = datetime.now(TH_TZ)
    minute = now.hour * 60 + now.minute

    # 09:00 - 09:59
    if 9 * 60 <= minute < 10 * 60:
        return "viral"

    # 12:00 - 12:59
    if 12 * 60 <= minute < 13 * 60:
        return "product"

    # 18:30 - 19:29
    if 18 * 60 + 30 <= minute < 19 * 60 + 30:
        return "product"

    # 21:00 - 21:59
    if 21 * 60 <= minute < 22 * 60:
        return "engage"

    return None


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

    # กันซ้ำโดยคงลำดับเดิม
    return list(dict.fromkeys(cleaned))


def pick_product():
    products = load_json(PRODUCT_FILE)

    if not isinstance(products, list):
        products = []

    posted_raw = load_json(POSTED_FILE)
    posted_clean = normalize_posted_products(posted_raw)
    posted = set(posted_clean)

    good = []

    for p in products:
        if not isinstance(p, dict):
            continue

        link = p.get("link")
        if not link:
            continue

        if link in posted:
            continue

        try:
            rating = float(p.get("rating", 0))
        except Exception:
            rating = 0

        try:
            sold = int(p.get("sold", 0))
        except Exception:
            sold = 0

        if rating >= 4 and sold >= 10:
            good.append(p)

    if not good:
        return None

    good.sort(
        key=lambda x: (
            int(x.get("sold", 0)),
            float(x.get("rating", 0))
        ),
        reverse=True
    )

    pool = good[:20] if len(good) >= 20 else good
    product = random.choice(pool)

    posted.add(product["link"])
    save_json(POSTED_FILE, list(posted))

    return product


def ai_caption(name):
    fallback = [
        f"⚡ {name}\n\nของดีที่ควรมีติดบ้าน",
        f"🔥 {name}\n\nของมันต้องมี",
        f"🛠 {name}\n\nใครใช้อยู่บ้าง",
        f"⚡ {name}\n\nแนะนำเลยตัวนี้",
        f"🔥 {name}\n\nของดีราคาคุ้ม"
    ]

    if not OPENAI:
        return random.choice(fallback)

    prompt = f"""
เขียนโพสต์ Facebook ขายสินค้า

สินค้า: {name}

ให้โพสต์สั้น กระตุ้นให้คลิก
""".strip()

    try:
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
        data = r.json()
        return data["output"][0]["content"][0]["text"]
    except Exception:
        return random.choice(fallback)


def viral_caption():
    posts = [
        "⚡ ไฟโซล่าดีไหม\n\nบ้านใครใช้อยู่บ้าง",
        "🔌 ปลั๊กไฟแบบไหนปลอดภัยที่สุด",
        "🛠 เครื่องมือช่างที่ควรมีติดบ้าน",
        "💡 หลอดไฟ LED ประหยัดไฟจริงไหม",
        "🏠 5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน"
    ]
    return random.choice(posts)


def engage_caption():
    posts = [
        "บ้านคุณใช้หลอดไฟ LED หรือยัง",
        "เครื่องมือช่างที่ใช้บ่อยคืออะไร",
        "เคยใช้ไฟโซล่าหรือยัง",
        "บ้านคุณใช้ปลั๊กไฟกี่ตัว",
        "ของใช้ไฟฟ้าชิ้นไหนสำคัญสุดในบ้าน"
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
    with open("reels_script.txt", "w", encoding="utf-8") as f:
        f.write(text)


def ensure_image_exists(path):
    if os.path.exists(path):
        return path

    fallback = [
        os.path.join(ASSET_DIR, "solar.jpg"),
        os.path.join(ASSET_DIR, "safe_plug.jpg"),
        os.path.join(ASSET_DIR, "tools.jpg"),
        os.path.join(ASSET_DIR, "home_electrical_5.jpg"),
        os.path.join(ASSET_DIR, "led_save_power.jpg"),
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
        print(r.text, flush=True)
        return None


def comment(post_id, link):
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
    print("Updating Shopee products", flush=True)
    update_products()

    mode = None

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

        cap = ai_caption(product["name"])
        img = get_image(product.get("category", ""))

        post_id = post(cap, img)

        if post_id:
            comment(post_id, product["link"])

        log_post("product", product["name"])
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
    run()
