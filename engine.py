import csv
import requests
import json
import os
import time

MAX_ROWS = 100000
TIMEOUT = 20

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

PAGE_ID_2 = os.getenv("PAGE_ID_2")
TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2")

CSV_URL = os.getenv("SHOPEE_CSV_URL")

POSTED_FILE = "posted.json"


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_posted(data):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(data), f, ensure_ascii=False)


def iter_csv_rows(url):
    try:
        print("Streaming CSV...")
        res = requests.get(url, stream=True, timeout=TIMEOUT)
        res.raise_for_status()

        lines = (
            line.decode("utf-8-sig", errors="ignore")
            for line in res.iter_lines()
            if line
        )

        reader = csv.DictReader(lines)

        first_row = True
        for i, row in enumerate(reader, start=1):
            if i > MAX_ROWS:
                print("Reached MAX_ROWS")
                break

            if first_row:
                print("COLUMNS:", list(row.keys()))
                first_row = False

            yield row

    except Exception as e:
        print("CSV ERROR:", e)


def pick(row, keys, default=""):
    lower_map = {str(k).strip().lower(): k for k in row.keys()}
    for key in keys:
        real = lower_map.get(key.lower())
        if real is not None:
            value = row.get(real, "")
            if str(value).strip():
                return str(value).strip()
    return default


def to_float(value):
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def choose_product():
    posted = load_posted()

    best = None
    best_score = -1
    count = 0
    debug_count = 0

    for row in iter_csv_rows(CSV_URL):
        try:
            name = pick(row, [
                "product_name", "item_name", "name", "title", "product title", "ชื่อสินค้า"
            ])
            image = pick(row, [
                "image_url", "image", "main_image", "product_image", "image link", "img_url"
            ])
            sold = to_float(pick(row, [
                "historical_sold", "sold", "sales", "sold_count", "item_sold"
            ], "0"))
            rating = to_float(pick(row, [
                "rating", "item_rating", "product_rating", "avg_rating"
            ], "0"))
            price = to_float(pick(row, [
                "price", "final_price", "product_price", "sale_price"
            ], "0"))
            com = to_float(pick(row, [
                "commission", "commission_value", "est_commission", "estimated_commission"
            ], "0"))
            link = pick(row, [
                "product_short link", "product_short_link",
                "short_link", "affiliate_link", "link", "product_link", "product short link"
            ])
            pid = pick(row, [
                "itemid", "item_id", "product_id", "id"
            ], name)

            count += 1

            if debug_count < 10:
                print(
                    "DEBUG:",
                    {
                        "name": name,
                        "image": image[:80] if image else "",
                        "sold": sold,
                        "rating": rating,
                        "price": price,
                        "commission": com,
                        "link": link[:80] if link else "",
                        "pid": pid,
                    }
                )
                debug_count += 1

            if not name or not image or not link:
                continue

            if pid in posted:
                continue

            # ปิด filter ชั่วคราวเพื่อตรวจว่าอ่านข้อมูลตรงก่อน
            # if rating < 4.0:
            #     continue
            #
            # if sold < 50:
            #     continue

            score = (sold * 2) + (rating * 100) + (com * 5)

            if score > best_score:
                best_score = score
                best = {
                    "id": pid,
                    "name": name,
                    "image": image,
                    "sold": sold,
                    "rating": rating,
                    "commission": com,
                    "price": price,
                    "link": link
                }

        except Exception as e:
            print("ROW ERROR:", e)
            continue

    print("SCAN DONE:", count)

    if best:
        posted.add(best["id"])
        save_posted(posted)

    return best


def generate_caption(p):
    return f"""🔥 ของมันต้องมี!

{p['name']}

⭐ {p['rating']} | ขายแล้ว {int(p['sold'])}
💸 คุ้มสุดตอนนี้!

👉 เช็กราคาล่าสุดที่ลิงก์ด้านล่าง

#Shopee #ของดีบอกต่อ"""


def download_image(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        print("DOWNLOAD IMAGE ERROR:", e)
    return None


def post_image(page_id, token, image_url, caption):
    print("Posting to:", page_id)

    img = download_image(image_url)

    if img:
        try:
            res = requests.post(
                f"https://graph.facebook.com/v25.0/{page_id}/photos",
                files={"source": ("img.jpg", img, "image/jpeg")},
                data={
                    "caption": caption,
                    "access_token": token
                },
                timeout=TIMEOUT
            )

            data = res.json()
            print("POST IMAGE:", data)

            if "post_id" in data:
                return data["post_id"]

            if "id" in data:
                return data["id"]

        except Exception as e:
            print("POST IMAGE ERROR:", e)

    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/feed",
            data={
                "message": caption,
                "access_token": token
            },
            timeout=TIMEOUT
        )
        data = res.json()
        print("POST TEXT:", data)
        return data.get("id")
    except Exception as e:
        print("POST TEXT ERROR:", e)

    return None


def comment_link(post_id, token, link):
    try:
        requests.post(
            f"https://graph.facebook.com/v25.0/{post_id}/comments",
            data={
                "message": f"🛒 สั่งซื้อ 👉 {link}",
                "access_token": token
            },
            timeout=TIMEOUT
        )
    except Exception as e:
        print("COMMENT ERROR:", e)


def run_page(page_id, token):
    print("RUN PAGE:", page_id)

    product = choose_product()

    if not product:
        print("❌ No product")
        return

    print("✅ CHOSEN:", product["name"])
    print("IMAGE URL:", product["image"])
    print("LINK:", product["link"])

    caption = generate_caption(product)

    post_id = post_image(page_id, token, product["image"], caption)

    if post_id:
        time.sleep(3)
        comment_link(post_id, token, product["link"])


def run_all_pages():
    run_page(PAGE_ID, TOKEN)

    if PAGE_ID_2 and TOKEN_2:
        run_page(PAGE_ID_2, TOKEN_2)
