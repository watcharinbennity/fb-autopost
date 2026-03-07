import json
import random
import os
import requests
from datetime import datetime, timedelta, timezone

from shopee_scraper import update_products

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
OPENAI = os.getenv("OPENAI_API_KEY")

PRODUCT_FILE = "products.json"
POSTED_FILE = "posted_products.json"
LOG_FILE = "post_log.json"

CAPTION_FILE = "captions_2000.txt"
VIRAL_FILE = "viral_posts_300.json"
REELS_FILE = "reels_ideas_100.json"

ASSET_DIR = "assets"
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


def load_captions():
    try:
        with open(CAPTION_FILE, "r", encoding="utf-8") as f:
            lines = [x.strip() for x in f.read().splitlines() if x.strip()]
            return lines if lines else ["⚡ {name} ของดีสำหรับบ้าน"]
    except Exception:
        return ["⚡ {name} ของดีสำหรับบ้าน"]


def log_post(post_type, name):
    data = load_json(LOG_FILE)
    data.append({
        "type": post_type,
        "name": name,
        "time": str(datetime.now(TH_TZ))
    })
    save_json(LOG_FILE, data)


def analyze_posts():
    logs = load_json(LOG_FILE)
    stats = {}
    for log in logs:
        t = log.get("type", "unknown")
        stats[t] = stats.get(t, 0) + 1
    return stats


def is_first_run():
    posted = load_json(POSTED_FILE)
    return len(posted) == 0


def get_mode_by_time():
    now = datetime.now(TH_TZ)
    h = now.hour
    m = now.minute
    minute_of_day = h * 60 + m

    # 09:00 - 09:59
    if 9 * 60 <= minute_of_day < 10 * 60:
        return "viral"

    # 12:00 - 12:59
    if 12 * 60 <= minute_of_day < 13 * 60:
        return "product"

    # 18:30 - 19:29
    if 18 * 60 + 30 <= minute_of_day < 19 * 60 + 30:
        return "product"

    # 21:00 - 21:59
    if 21 * 60 <= minute_of_day < 22 * 60:
        return "engage"

    return None


def pick_product():
    products = load_json(PRODUCT_FILE)
    posted = set(load_json(POSTED_FILE))

    good = [
        p for p in products
        if p.get("link")
        and p["link"] not in posted
        and float(p.get("rating", 0)) >= 4.0
        and int(p.get("sold", 0)) >= 10
    ]

    if not good:
        return None

    good.sort(
        key=lambda x: (
            int(x.get("sold", 0)),
            float(x.get("rating", 0)),
        ),
        reverse=True
    )

    top = good[:30] if len(good) >= 30 else good
    product = random.choice(top)

    posted.add(product["link"])
    save_json(POSTED_FILE, list(posted))
    return product


def ai_caption(name):
    captions = load_captions()

    if not OPENAI:
        return random.choice(captions).replace("{name}", name)

    prompt = f"""
เขียนโพสต์ Facebook ขายสินค้า

สินค้า: {name}

ให้โพสต์สั้น น่าสนใจ กระตุ้นให้คลิก
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
        return random.choice(captions).replace("{name}", name)


def viral_caption():
    posts = load_json(VIRAL_FILE)

    if posts:
        post = random.choice(posts)
        if isinstance(post, dict) and post.get("caption"):
            return post["caption"]

    fallback_topics = [
        "ไฟโซล่าดีไหม",
        "ปลั๊กไฟแบบไหนปลอดภัย",
        "เครื่องมือช่างที่ควรมีติดบ้าน",
        "5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน",
        "หลอดไฟ LED ประหยัดไฟจริงไหม"
    ]

    topic = random.choice(fallback_topics)
    return f"⚡ {topic}\n\nบ้านคุณคิดว่ายังไง ?\n\nคอมเมนต์หน่อย"


def engage_caption():
    questions = [
        "บ้านคุณใช้ปลั๊กไฟกี่ตัว ?",
        "เคยใช้ไฟโซล่าหรือยัง ?",
        "เครื่องมือช่างที่ใช้บ่อยคืออะไร ?",
        "บ้านคุณใช้หลอดไฟ LED หรือยัง ?"
    ]
    return random.choice(questions)


def reels_idea():
    reels = load_json(REELS_FILE)
    if reels:
        return random.choice(reels)
    return {"hook": "ไฟโซล่าดีไหม", "idea": "อธิบายข้อดีสั้น ๆ แล้วปิดด้วย call to action"}


def save_reels_script(idea):
    with open("reels_script.txt", "w", encoding="utf-8") as f:
        f.write(str(idea))


def ensure_image_exists(path):
    if os.path.exists(path):
        return path

    fallback_candidates = [
        os.path.join(ASSET_DIR, "home_electrical_5.jpg"),
        os.path.join(ASSET_DIR, "home_electrical_5.jpeg"),
        os.path.join(ASSET_DIR, "solar.jpg"),
        os.path.join(ASSET_DIR, "safe_plug.jpg"),
        os.path.join(ASSET_DIR, "tools.jpg"),
        os.path.join(ASSET_DIR, "led_save_power.jpg"),
    ]

    for candidate in fallback_candidates:
        if os.path.exists(candidate):
            print(f"IMAGE FALLBACK -> {candidate}", flush=True)
            return candidate

    raise FileNotFoundError(
        f"ไม่พบไฟล์รูป: {path} | assets: {os.listdir(ASSET_DIR) if os.path.isdir(ASSET_DIR) else 'missing'}"
    )


def get_image(category):
    if category == "solar":
        path = os.path.join(ASSET_DIR, "solar.jpg")
    elif category == "plug":
        path = os.path.join(ASSET_DIR, "safe_plug.jpg")
    elif category == "tools":
        path = os.path.join(ASSET_DIR, "tools.jpg")
    elif category == "led":
        path = os.path.join(ASSET_DIR, "led_save_power.jpg")
    else:
        path = os.path.join(ASSET_DIR, "home_electrical_5.jpg")

    return ensure_image_exists(path)


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
        print("POST TEXT:", r.text, flush=True)
        return None


def comment(post_id, link):
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    data = {
        "message": f"🛒 สั่งซื้อ\n{link}",
        "access_token": TOKEN
    }
    try:
        r = requests.post(url, data=data, timeout=20)
        print("COMMENT RESPONSE:", r.json(), flush=True)
    except Exception as e:
        print("COMMENT ERROR:", e, flush=True)


def run():
    print("Updating Shopee products...", flush=True)
    update_products()

    print("PWD:", os.getcwd(), flush=True)
    print("FILES:", os.listdir("."), flush=True)

    if os.path.isdir(ASSET_DIR):
        print("ASSETS:", os.listdir(ASSET_DIR), flush=True)

    if is_first_run():
        mode = "product"
        print("FIRST RUN -> FORCE PRODUCT", flush=True)
    else:
        mode = get_mode_by_time()

    print("MODE:", mode, flush=True)

    if not mode:
        print("SKIP: not in posting window", flush=True)
        return

    if mode == "product":
        product = pick_product()

        if product:
            caption = ai_caption(product["name"])
            image = get_image(product.get("category", ""))

            post_id = post(caption, image)

            if post_id:
                comment(post_id, product["link"])

            log_post("product", product["name"])
            print("POST STATS:", analyze_posts(), flush=True)
            return

        print("NO PRODUCT FOUND", flush=True)
        return

    if mode == "viral":
        caption = viral_caption()
        image = ensure_image_exists(os.path.join(ASSET_DIR, "home_electrical_5.jpg"))

        post(caption, image)
        log_post("viral", "content")
        print("POST STATS:", analyze_posts(), flush=True)
        return

    if mode == "engage":
        caption = engage_caption()
        image = ensure_image_exists(os.path.join(ASSET_DIR, "home_electrical_5.jpg"))

        post(caption, image)
        log_post("engagement", "question")
        print("POST STATS:", analyze_posts(), flush=True)
        return

    # เผื่อใช้ภายหลัง
    if mode == "reels":
        idea = reels_idea()
        save_reels_script(idea)
        print("REELS IDEA:", idea, flush=True)

        log_post("reels", "idea")
        print("POST STATS:", analyze_posts(), flush=True)
        return


if __name__ == "__main__":
    run()
