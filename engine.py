import requests, json, os, time

MAX_ROWS = 100000
TIMEOUT = 15

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

PAGE_ID_2 = os.getenv("PAGE_ID_2")
TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2")

CSV_URL = os.getenv("SHOPEE_CSV_URL")

POSTED_FILE = "posted.json"


# ---------------- STORAGE ----------------
def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    return set(json.load(open(POSTED_FILE)))


def save_posted(data):
    json.dump(list(data), open(POSTED_FILE, "w"))


# ---------------- CSV STREAM ----------------
def iter_csv_rows(url):
    try:
        res = requests.get(url, stream=True, timeout=TIMEOUT)
        for i, line in enumerate(res.iter_lines()):
            if i == 0:
                continue
            if i > MAX_ROWS:
                break
            try:
                yield line.decode().split(",")
            except:
                continue
    except Exception as e:
        print("CSV ERROR:", e)


# ---------------- FILTER (ล็อคสินค้า) ----------------
def is_target_product(name):
    name = name.lower()

    if any(k in name for k in ["camera", "กล้อง", "cctv"]):
        return "camera"

    if any(k in name for k in ["robot vacuum", "หุ่นยนต์"]):
        return "robot"

    if any(k in name for k in ["plug", "ปลั๊ก"]):
        return "plug"

    return None


# ---------------- SELECT ----------------
def choose_product():
    posted = load_posted()
    best = None
    best_score = 0

    for row in iter_csv_rows(CSV_URL):
        try:
            pid, name, image, sold, rating, price, com, link = row[:8]

            sold = float(sold)
            rating = float(rating)
            com = float(com)

            group = is_target_product(name)
            if not group:
                continue

            if pid in posted:
                continue

            if rating < 4.5:
                continue

            if group == "camera" and sold < 500:
                continue

            if group == "robot" and sold < 200:
                continue

            if group == "plug" and sold < 1000:
                continue

            if com < 30:
                continue

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
                    "link": link
                }

        except:
            continue

    if best:
        posted.add(best["id"])
        save_posted(posted)

    return best


# ---------------- CAPTION ----------------
def generate_caption(p):
    return f"""🔥 ของมันต้องมี!

{p['name']}

⭐ {p['rating']} | ขายแล้ว {int(p['sold'])}
💸 คุ้มสุดตอนนี้!

👉 เช็กราคาล่าสุดที่ลิงก์ด้านล่าง

#Shopee #ของดีบอกต่อ"""


# ---------------- IMAGE ----------------
def download_image(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.content
    except:
        return None


# ---------------- POST ----------------
def post_image(page_id, token, image_url, caption):
    img = download_image(image_url)

    if not img:
        return post_text(page_id, token, caption)

    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/photos",
            files={"source": ("img.jpg", img)},
            data={
                "caption": caption,
                "access_token": token
            },
            timeout=TIMEOUT
        )

        data = res.json()
        print("POST:", data)

        if "id" in data:
            return data.get("post_id")

    except Exception as e:
        print("POST ERROR:", e)

    return post_text(page_id, token, caption)


def post_text(page_id, token, caption):
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/feed",
            data={
                "message": caption,
                "access_token": token
            }
        )
        return res.json().get("id")
    except:
        return None


# ---------------- COMMENT ----------------
def comment_link(post_id, token, link):
    try:
        requests.post(
            f"https://graph.facebook.com/v25.0/{post_id}/comments",
            data={
                "message": f"🛒 สั่งซื้อ 👉 {link}",
                "access_token": token
            }
        )
    except:
        pass


# ---------------- RUN ----------------
def run_page(page_id, token):
    print("RUN:", page_id)

    product = choose_product()

    if not product:
        print("No product")
        return

    print("CHOSEN:", product["name"])

    caption = generate_caption(product)

    post_id = post_image(page_id, token, product["image"], caption)

    if post_id:
        time.sleep(3)
        comment_link(post_id, token, product["link"])


def run_all_pages():
    run_page(PAGE_ID, TOKEN)

    if PAGE_ID_2 and TOKEN_2:
        run_page(PAGE_ID_2, TOKEN_2)
