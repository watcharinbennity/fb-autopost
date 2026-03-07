import os
import csv
import json
import random
import urllib.parse

import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")

AFF_ID = "15328100363"

STATE_FILE = "state.json"
POST_FILE = "posted_products.json"

MAX_SCAN_ROWS = 5000
MAX_ROWS = 2500
HTTP_TIMEOUT = 20
TOP_POOL = 30

KEYWORDS = [
    "led", "lamp", "solar", "ไฟ", "โคม", "ปลั๊ก", "สายไฟ", "สวิตช์",
    "tool", "ไขควง", "สว่าน", "multimeter", "adapter", "spotlight",
    "ไฟโซล่า", "ไฟประดับ", "หลอดไฟ", "รางปลั๊ก", "เต้ารับ"
]

CAPTIONS = [
    """⚡ แนะนำจาก BEN Home & Electrical

{name}

⭐ รีวิว {rating}
🔥 ขายแล้ว {sold}
💰 ราคา {price} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate""",

    """🔥 สินค้าขายดี

{name}

⭐ {rating}
📦 ขายแล้ว {sold}
💰 {price} บาท

👉 {link}

#BENHomeElectrical #ShopeeAffiliate""",

    """🏠 ของมันต้องมีติดบ้าน

{name}

⭐ รีวิว {rating}
🔥 ยอดขาย {sold}
💰 ราคา {price} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #อุปกรณ์ไฟฟ้า #ShopeeAffiliate"""
]


def log(msg):
    print(msg, flush=True)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def safe_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return 0.0


def safe_int(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0


def load_state():
    state = load_json(STATE_FILE, {"posted": []})
    if "posted" not in state:
        state["posted"] = state.get("posted_links", [])
    if not isinstance(state["posted"], list):
        state["posted"] = []
    return state


def save_state(state):
    state["posted"] = state["posted"][-1000:]
    save_json(STATE_FILE, state)


def append_posted_product(p):
    data = load_json(POST_FILE, [])
    if not isinstance(data, list):
        data = []

    data.append({
        "title": p["title"],
        "product_link": p["link"],
        "image_link": p["image"],
        "rating": p["rating"],
        "sold": p["sold"],
        "price": p["price"]
    })

    data = data[-1000:]
    save_json(POST_FILE, data)


def clean_product_link(product_url):
    url = (product_url or "").strip()
    if not url:
        return ""

    # ตัด query / fragment ออกก่อน
    url = url.split("#")[0]
    url = url.split("?")[0]

    # รองรับลิงก์แบบ product_short_link ถ้ามี
    url = url.replace("product_short link", "").strip()

    return url


def convert_affiliate_link(product_url):
    clean = clean_product_link(product_url)
    encoded = urllib.parse.quote(clean, safe="")
    return f"https://shopee.ee/an_redir?affiliate_id={AFF_ID}&origin_link={encoded}"


def allow_title(name):
    text = (name or "").lower()
    return any(k in text for k in KEYWORDS)


def revenue_score(item):
    rating = safe_float(item["rating"])
    sold = safe_int(item["sold"])
    price = safe_float(item["price"])

    score = 0.0
    score += rating * 40
    score += sold * 0.65

    if 20 <= price <= 99:
        score += 35
    elif 100 <= price <= 299:
        score += 45
    elif 300 <= price <= 699:
        score += 20
    elif 700 <= price <= 1500:
        score += 8

    if sold >= 1000:
        score += 50
    elif sold >= 500:
        score += 30
    elif sold >= 100:
        score += 15

    if rating >= 4.9:
        score += 25
    elif rating >= 4.8:
        score += 15
    elif rating >= 4.5:
        score += 8

    return round(score, 2)


def read_feed():
    if not CSV_URL:
        raise ValueError("Missing SHOPEE_CSV_URL")

    log("STEP1 read csv")

    r = requests.get(CSV_URL, timeout=HTTP_TIMEOUT, stream=True)
    r.raise_for_status()

    line_iter = (
        line.decode("utf-8-sig", errors="ignore")
        for line in r.iter_lines()
        if line
    )

    reader = csv.DictReader(line_iter)

    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_SCAN_ROWS:
            break
        rows.append(row)

    random.shuffle(rows)
    rows = rows[:MAX_ROWS]

    log(f"rows {len(rows)}")
    return rows


def build_pool(rows, state):
    posted = set(state["posted"])
    pool = []

    for row in rows:
        title = (row.get("title") or "").strip()
        link = clean_product_link(row.get("product_link", ""))
        image = (row.get("image_link") or "").strip()
        rating = safe_float(row.get("item_rating", 0))
        sold = safe_int(row.get("item_sold", 0))
        price_text = (row.get("sale_price") or row.get("price") or "").strip()

        if not title or not link or not image:
            continue

        if link in posted:
            continue

        if not allow_title(title):
            continue

        if rating < 4.2:
            continue

        if sold < 30:
            continue

        item = {
            "title": title,
            "link": link,
            "image": image,
            "rating": rating,
            "sold": sold,
            "price": price_text
        }
        item["score"] = revenue_score(item)
        pool.append(item)

    log(f"valid {len(pool)}")
    return pool


def choose_product(pool):
    if not pool:
        return None

    ranked = sorted(pool, key=lambda x: x["score"], reverse=True)
    top = ranked[:TOP_POOL]

    log("TOP CANDIDATES:")
    for i, p in enumerate(top[:5], start=1):
        log(
            f"{i}. sold={p['sold']} rating={p['rating']} "
            f"price={p['price']} score={p['score']} title={p['title'][:80]}"
        )

    return random.choice(top)


def caption(p, aff_link):
    c = random.choice(CAPTIONS)
    return c.format(
        name=p["title"],
        rating=p["rating"],
        sold=p["sold"],
        price=p["price"],
        link=aff_link
    )


def upload_photo(image_url):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r = requests.post(
        url,
        data={
            "url": image_url,
            "published": "false",
            "access_token": TOKEN
        },
        timeout=HTTP_TIMEOUT
    ).json()

    if "id" not in r:
        raise RuntimeError(r)

    return r["id"]


def create_post(media_id, text):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r = requests.post(
        url,
        data={
            "message": text,
            "attached_media[0]": json.dumps({"media_fbid": media_id}),
            "access_token": TOKEN
        },
        timeout=HTTP_TIMEOUT
    ).json()

    return r


def comment_link(post_id, link):
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    r = requests.post(
        url,
        data={
            "message": f"🛒 ลิงก์สินค้า\n{link}",
            "access_token": TOKEN
        },
        timeout=HTTP_TIMEOUT
    ).json()

    return r


def main():
    if not PAGE_ID or not TOKEN:
        raise ValueError("Missing PAGE_ID or PAGE_ACCESS_TOKEN")

    state = load_state()
    rows = read_feed()
    pool = build_pool(rows, state)

    if not pool:
        log("no product")
        return

    p = choose_product(pool)
    if not p:
        log("no chosen product")
        return

    aff_link = convert_affiliate_link(p["link"])
    text = caption(p, aff_link)

    log("upload image")
    media = upload_photo(p["image"])

    log("create post")
    res = create_post(media, text)
    log(res)

    if "id" in res:
        comment_res = comment_link(res["id"], aff_link)
        log(comment_res)

        state["posted"].append(p["link"])
        save_state(state)
        append_posted_product(p)

        log("post success")


if __name__ == "__main__":
    main()
