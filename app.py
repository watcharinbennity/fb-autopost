import os
import csv
import json
import random
import requests

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
CSV_URL = os.getenv("SHOPEE_CSV_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AFF_ID = os.getenv("SHOPEE_AFFILIATE_ID")

STATE_FILE = "state.json"
HTTP_TIMEOUT = 30


def log(x):
    print(x, flush=True)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted": []}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"posted": []}

    if "posted" not in data or not isinstance(data["posted"], list):
        data["posted"] = []

    return data


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def clean_link(url):
    if not url:
        return ""
    return url.strip().split("?")[0]


def convert_affiliate_link(product_url):
    base = clean_link(product_url)
    if not AFF_ID:
        return base
    return f"{base}?affiliate_id={AFF_ID}"


def read_csv():
    if not CSV_URL:
        raise ValueError("Missing SHOPEE_CSV_URL secret")

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
        if i >= 2000:
            break

    random.shuffle(rows)
    log(f"rows={len(rows)}")
    return rows


def score_product(row):
    try:
        rating = float(row.get("item_rating") or 0)
    except Exception:
        rating = 0.0

    try:
        sold = int(float(row.get("item_sold") or 0))
    except Exception:
        sold = 0

    try:
        price = float(str(row.get("sale_price") or row.get("price") or 0).replace(",", ""))
    except Exception:
        price = 0.0

    score = rating * 40 + sold * 0.6

    if 20 <= price <= 299:
        score += 20
    elif 300 <= price <= 699:
        score += 8

    if sold >= 100:
        score += 10

    return score


def choose_product(rows, state):
    pool = []

    for row in rows:
        link = clean_link(row.get("product_link"))
        image = (row.get("image_link") or "").strip()
        title = (row.get("title") or "").strip()

        if not link or not image or not title:
            continue

        if link in state["posted"]:
            continue

        pool.append((score_product(row), row))

    if not pool:
        return None

    pool.sort(key=lambda x: x[0], reverse=True)
    row = random.choice(pool[:30])[1]

    return {
        "title": row.get("title") or "",
        "link": clean_link(row.get("product_link") or ""),
        "image": row.get("image_link") or "",
        "price": row.get("sale_price") or row.get("price") or "",
        "rating": row.get("item_rating") or "",
        "sold": row.get("item_sold") or ""
    }


def ai_caption(product):
    if not OPENAI_API_KEY:
        return None

    prompt = f"""
เขียนแคปชั่นขายสินค้าให้เพจ BEN Home & Electrical ภาษาไทย

สินค้า: {product['title']}
ราคา: {product['price']} บาท
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

เงื่อนไข:
- ไม่เกิน 8 บรรทัด
- มี emoji พอดี
- โทนน่าเชื่อถือ
- ปิดท้าย hashtag 2-3 อัน
- ยังไม่ต้องใส่ลิงก์
"""

    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4.1-mini",
                "input": prompt
            },
            timeout=HTTP_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        return data["output"][0]["content"][0]["text"].strip()
    except Exception as e:
        log(f"ai caption failed: {e}")
        return None


def fallback_caption(product, link):
    return f"""⚡ แนะนำจาก BEN Home & Electrical

{product['title']}

⭐ รีวิว {product['rating']}
🔥 ขายแล้ว {product['sold']}
💰 ราคา {product['price']} บาท

🛒 สั่งซื้อ
{link}

#BENHomeElectrical #ShopeeAffiliate"""


def ensure_link_in_post(text, link):
    text = (text or "").strip()
    if link in text:
        return text
    return f"{text}\n\n🛒 สั่งซื้อ\n{link}"


def upload_photo(image):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"

    r = requests.post(
        url,
        data={
            "url": image,
            "published": "false",
            "access_token": TOKEN
        },
        timeout=HTTP_TIMEOUT
    )
    data = r.json()
    log({"upload_photo": data})

    if "id" not in data:
        raise RuntimeError(f"upload photo failed: {data}")

    return data["id"]


def create_post(media, text):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"

    r = requests.post(
        url,
        data={
            "message": text,
            "attached_media[0]": json.dumps({"media_fbid": media}),
            "access_token": TOKEN
        },
        timeout=HTTP_TIMEOUT
    )
    data = r.json()
    log({"create_post": data})
    return data


def comment_link(post_id, link):
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"

    r = requests.post(
        url,
        data={
            "message": f"🛒 ลิงก์สั่งซื้อ\n{link}",
            "access_token": TOKEN
        },
        timeout=HTTP_TIMEOUT
    )
    data = r.json()
    log({"comment_link": data})
    return data


def main():
    if not PAGE_ID:
        raise ValueError("Missing PAGE_ID secret")
    if not TOKEN:
        raise ValueError("Missing PAGE_ACCESS_TOKEN secret")
    if not CSV_URL:
        raise ValueError("Missing SHOPEE_CSV_URL secret")

    state = load_state()
    rows = read_csv()

    if not rows:
        log("CSV EMPTY")
        return

    product = choose_product(rows, state)

    if not product:
        log("fallback first row")
        r = rows[0]
        product = {
            "title": r.get("title") or "",
            "link": clean_link(r.get("product_link") or ""),
            "image": r.get("image_link") or "",
            "price": r.get("sale_price") or r.get("price") or "",
            "rating": r.get("item_rating") or "",
            "sold": r.get("item_sold") or ""
        }

    if not product["link"] or not product["image"]:
        log(f"invalid fallback product: {product}")
        return

    aff_link = convert_affiliate_link(product["link"])

    caption = ai_caption(product)
    if not caption:
        caption = fallback_caption(product, aff_link)

    caption = ensure_link_in_post(caption, aff_link)

    log(f"chosen={product['title']}")
    log(f"product_link={product['link']}")
    log(f"aff_link={aff_link}")

    media = upload_photo(product["image"])
    res = create_post(media, caption)

    if "id" in res:
        comment_link(res["id"], aff_link)
        state["posted"].append(product["link"])
        save_state(state)
        log("POST SUCCESS")
    else:
        log("POST FAILED")


if __name__ == "__main__":
    main()
