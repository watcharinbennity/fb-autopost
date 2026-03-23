import requests, json, os, random

MAX_ROWS = 100000

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

PAGE_ID_2 = os.getenv("PAGE_ID_2")
TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2")

CSV_URL = os.getenv("SHOPEE_CSV_URL")

POSTED_FILE = "posted.json"


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    return set(json.load(open(POSTED_FILE)))


def save_posted(data):
    json.dump(list(data), open(POSTED_FILE, "w"))


def iter_csv_rows(url):
    res = requests.get(url, stream=True)
    for i, line in enumerate(res.iter_lines()):
        if i == 0:
            continue
        if i > MAX_ROWS:
            break
        try:
            yield line.decode().split(",")
        except:
            continue


def choose_product():
    posted = load_posted()

    for row in iter_csv_rows(CSV_URL):
        try:
            product_id = row[0]
            name = row[1]
            image = row[2]
            sold = float(row[3])
            rating = float(row[4])

            if product_id in posted:
                continue

            if rating >= 4 and sold >= 10:
                posted.add(product_id)
                save_posted(posted)

                return {
                    "name": name,
                    "image": image,
                    "sold": sold,
                    "rating": rating
                }
        except:
            continue

    return None


def generate_caption(product):
    return f"""🔥 ของดีต้องมี!
{product['name']}

⭐ {product['rating']} | ขายแล้ว {int(product['sold'])}
👉 เช็กราคาล่าสุดที่ลิงก์ด้านล่าง

#ของดีบอกต่อ #เครื่องใช้ไฟฟ้า #Shopee"""


def post_image(page_id, token, image_url, caption):
    try:
        img = requests.get(image_url, timeout=10)
        files = {"source": ("image.jpg", img.content)}

        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/photos",
            files=files,
            data={
                "caption": caption,
                "access_token": token
            },
            timeout=30
        )

        print("POST RESULT:", res.text)

        if res.status_code != 200:
            raise Exception("Upload failed")

    except Exception as e:
        print("Image post failed:", e)

        # 🔥 fallback
        requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/feed",
            data={
                "message": caption,
                "access_token": token
            }
        )


def run_page(page_id, token):
    print(f"Running page {page_id}")

    product = choose_product()

    if not product:
        print("No product found")
        return

    caption = generate_caption(product)

    print("Chosen:", product["name"])

    post_image(page_id, token, product["image"], caption)


def run_all_pages():
    run_page(PAGE_ID, TOKEN)

    if PAGE_ID_2 and TOKEN_2:
        run_page(PAGE_ID_2, TOKEN_2)
