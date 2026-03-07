import os
import csv
import json
import requests
from datetime import datetime, timezone, timedelta

from ai_engine import (
    choose_product,
    generate_best_caption,
    viral_caption,
    engagement_caption,
)
from product_filter import filter_products, score_title
from viral_engine import (
    generate_viral_fallback,
    generate_engagement_fallback,
)

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"
POSTED_LOG_FILE = "posted_log.json"
HTTP_TIMEOUT = 20
MAX_ROWS = 500
TH_TZ = timezone(timedelta(hours=7))

RAW_BASE_URL = os.getenv(
    "RAW_BASE_URL",
    "https://raw.githubusercontent.com/watcharinbootprasan/fb-autopost/main/assets"
)
DEFAULT_FALLBACK_IMAGE = f"{RAW_BASE_URL}/home_electrical_5.jpg"


def log(msg):
    print(msg, flush=True)


def load_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_state():
    data = load_json_file(STATE_FILE, {"posted": []})
    if "posted" not in data or not isinstance(data["posted"], list):
        data["posted"] = []
    return data


def save_state(state):
    save_json_file(STATE_FILE, state)


def load_posted_log():
    data = load_json_file(POSTED_LOG_FILE, [])
    return data if isinstance(data, list) else []


def save_posted_log(data):
    save_json_file(POSTED_LOG_FILE, data[-1000:])


def append_posted_log(mode, post_id, name="", link="", price="", rating="", sold="", used_fallback=False, final_score="", topic=""):
    logs = load_posted_log()
    logs.append({
        "time_th": datetime.now(TH_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "post_id": post_id,
        "used_fallback": used_fallback,
        "topic": topic,
        "name": name,
        "link": link,
        "price": price,
        "rating": rating,
        "sold": sold,
        "final_score": final_score,
    })
    save_posted_log(logs)


def clean_link(url):
    if not url:
        return ""
    return url.split("?")[0].strip()


def aff_link(url):
    base = clean_link(url)
    return f"{base}?affiliate_id={AFF_ID}" if AFF_ID else base


def read_csv():
    log("STEP 1: download csv")
    r = requests.get(CSV_URL, timeout=HTTP_TIMEOUT, stream=True)
    r.raise_for_status()

    lines = (
        line.decode("utf-8-sig", errors="ignore")
        for line in r.iter_lines()
        if line
    )

    reader = csv.DictReader(lines)
    rows = []

    for i, row in enumerate(reader):
        rows.append(row)
        if i >= MAX_ROWS:
            break

    log(f"STEP 2: csv rows loaded = {len(rows)}")
    return rows


def build_fallback_product(rows, state):
    posted = set(state.get("posted", []))
    candidates = []

    for r in rows:
        title = (r.get("title") or "").strip()
        link = (r.get("product_link") or "").strip()
        image = (r.get("image_link") or "").strip()

        if not title or not link or not image:
            continue
        if link in posted:
            continue

        candidates.append((score_title(title), {
            "name": title,
            "link": link,
            "image": image,
            "price": r.get("sale_price") or r.get("price") or "",
            "rating": r.get("item_rating") or "0",
            "sold": r.get("item_sold") or "0",
            "final_score": 0,
        }))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def fallback_product_caption(product, link):
    return f"""⚡ แนะนำจาก BEN Home & Electrical

{product['name']}

⭐ รีวิว {product['rating']}
🔥 ขายแล้ว {product['sold']}
💰 ราคา {product['price']} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate"""


def build_product_caption(product):
    link = aff_link(product["link"])

    log("STEP 5: generate ai best caption")
    caption = generate_best_caption(product)

    if caption:
        if link not in caption:
            caption = f"{caption}\n\n🛒 สั่งซื้อ\n{link}"
        return caption

    log("STEP 6: fallback caption")
    return fallback_product_caption(product, link)


def ensure_image_url(url):
    if not url:
        return DEFAULT_FALLBACK_IMAGE

    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and len(r.content) > 1000:
            return url
    except Exception:
        pass

    return DEFAULT_FALLBACK_IMAGE


def upload_photo(url):
    log("STEP 7: upload photo")
    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r = requests.post(
        endpoint,
        data={
            "url": url,
            "published": "false",
            "access_token": TOKEN,
        },
        timeout=HTTP_TIMEOUT,
    )

    data = r.json()
    log(f"upload response: {data}")

    if "id" not in data:
        raise RuntimeError(data)

    return data["id"]


def post_image(media, text):
    log("STEP 8: create post")
    endpoint = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r = requests.post(
        endpoint,
        data={
            "message": text,
            "attached_media[0]": json.dumps({"media_fbid": media}),
            "access_token": TOKEN,
        },
        timeout=HTTP_TIMEOUT,
    )

    data = r.json()
    log(f"post response: {data}")
    return data


def comment_link(post_id, link):
    log("STEP 9: comment link")
    endpoint = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    r = requests.post(
        endpoint,
        data={
            "message": f"🛒 สั่งซื้อ\n{link}",
            "access_token": TOKEN,
        },
        timeout=HTTP_TIMEOUT,
    )

    log(f"comment response: {r.json()}")


def decide_mode():
    now = datetime.now(TH_TZ)
    h = now.hour
    m = now.minute
    t = h * 60 + m

    # 09:00 viral
    if 8 * 60 <= t <= 10 * 60:
        return "viral"

    # 12:00 product
    if 11 * 60 <= t <= 13 * 60:
        return "product"

    # 18:30 product
    if 18 * 60 <= t <= 19 * 60:
        return "product"

    # 21:00 engagement
    if 20 * 60 <= t <= 22 * 60:
        return "engagement"

    return None


def main():
    if not PAGE_ID:
        raise ValueError("Missing PAGE_ID")
    if not TOKEN:
        raise ValueError("Missing PAGE_ACCESS_TOKEN")
    if not CSV_URL:
        raise ValueError("Missing SHOPEE_CSV_URL")

    state = load_state()
    first_run = len(state.get("posted", [])) == 0

    if first_run:
        mode = "product"
        log("FIRST RUN -> FORCE PRODUCT POST")
    else:
        mode = decide_mode()
        if not mode:
            log("SKIP TIME")
            return

    if mode == "viral":
        caption, image, topic = generate_viral_fallback()

        ai_text = viral_caption(topic)
        if ai_text:
            caption = ai_text

        image = ensure_image_url(image)
        media = upload_photo(image)
        res = post_image(media, caption)

        if "id" in res:
            append_posted_log(mode="viral", post_id=res["id"], topic=topic)
        return

    if mode == "engagement":
        caption, image = generate_engagement_fallback()

        ai_text = engagement_caption()
        if ai_text:
            caption = ai_text

        image = ensure_image_url(image)
        media = upload_photo(image)
        res = post_image(media, caption)

        if "id" in res:
            append_posted_log(mode="engagement", post_id=res["id"])
        return

    rows = read_csv()

    log("STEP 3: filter products")
    products = filter_products(rows, state)
    log(f"STEP 4: valid products = {len(products)}")

    used_fallback = False

    if products:
        product = choose_product(products)
        log(f"CHOSEN BY AI: {product['name']}")
    else:
        log("NO PRODUCT - fallback nearest category")
        product = build_fallback_product(rows, state)
        if not product:
            log("FALLBACK FAILED")
            return
        used_fallback = True
        log(f"CHOSEN BY FALLBACK: {product['name']}")

    caption = build_product_caption(product)

    product["image"] = ensure_image_url(product["image"])
    media = upload_photo(product["image"])
    res = post_image(media, caption)

    if "id" in res:
        link = aff_link(product["link"])
        comment_link(res["id"], link)
        state["posted"].append(product["link"])
        save_state(state)
        append_posted_log(
            mode="product",
            post_id=res["id"],
            name=product["name"],
            link=product["link"],
            price=product["price"],
            rating=product["rating"],
            sold=product["sold"],
            used_fallback=used_fallback,
            final_score=product.get("final_score", "")
        )
        log("POST SUCCESS")
    else:
        log("POST FAILED")


if __name__ == "__main__":
    main()
