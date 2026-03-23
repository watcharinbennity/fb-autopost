import requests, json, os, random, time

MAX_ROWS = 120000
TIMEOUT = 15

PAGE_ID = os.getenv("PAGE_ID")
TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

PAGE_ID_2 = os.getenv("PAGE_ID_2")
TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2")

CSV_URL = os.getenv("SHOPEE_CSV_URL")

POSTED_FILE = "posted.json"


# ------------------ STORAGE ------------------
def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    return set(json.load(open(POSTED_FILE)))


def save_posted(data):
    json.dump(list(data), open(POSTED_FILE, "w"))


# ------------------ CSV STREAM ------------------
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


# ------------------ SCORING ------------------
def score_product(sold, rating, commission, price):
    return (sold * 2.5) + (rating * 120) + (commission * 10) - (price * 0.1)


# ------------------ PRODUCT SELECT ------------------
def choose_product():
    posted = load_posted()
    best = None
    best_score = 0

    for row in iter_csv_rows(CSV_URL):
        try:
            pid = row[0]
            name = row[1]
            image = row[2]
            sold = float(row[3])
            rating = float(row[4])
            price = float(row[5])
            commission = float(row[6])
            link = row[7]

            if pid in posted:
                continue

            if rating < 4 or sold < 10:
                continue

            score = score_product(sold, rating, commission, price)

            if score > best_score:
                best_score = score
                best = {
                    "id": pid,
                    "name": name,
                    "image": image,
                    "sold": sold,
                    "rating": rating,
                    "price": price,
                    "commission": commission,
                    "link": link
                }

        except:
            continue

    if best:
        posted.add(best["id"])
        save_posted(posted)

    return best


# ------------------ CAPTION ------------------
def generate_caption(p):
    hooks = [
        "🔥 ของมันต้องมี!",
        "⚡ ลดแรงวันนี้!",
        "💥 ตัวฮิตขายดี!",
        "🚀 สายช่างห้ามพลาด!",
        "🛠️ ของดีใช้จริง!",
    ]

    return f"""{random.choice(hooks)}

{p['name']}

⭐ {p['rating']} | ขายแล้ว {int(p['sold'])}
💸 คุ้มสุดตอนนี้!

👉 เช็กราคาล่าสุดที่ลิงก์ด้านล่าง

#Shopee #ของดีบอกต่อ #เครื่องใช้ไฟฟ้า"""


# ------------------ DOWNLOAD IMAGE ------------------
def download_image(url):
    try:
        res = requests.get(url, timeout=TIMEOUT)
        if res.status_code == 200:
            return res.content
    except:
        return None


# ------------------ POST ------------------
def post_image(page_id, token, image_url, caption):
    img = download_image(image_url)

    if not img:
        print("Image fail → fallback text")
        return post_text(page_id, token, caption)

    for i in range(3):  # retry
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
                return data["post_id"]

        except Exception as e:
            print("Retry:", i, e)

        time.sleep(2)

    print("Image post fail → fallback")
    return post_text(page_id, token, caption)


def post_text(page_id, token, caption):
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/feed",
            data={
                "message": caption,
                "access_token": token
            },
            timeout=TIMEOUT
        )
        return res.json().get("id")
    except:
        return None


# ------------------ COMMENT ------------------
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


# ------------------ RUN PAGE ------------------
def run_page(page_id, token):
    print("RUN:", page_id)

    product = choose_product()

    if not product:
        print("No product")
        return

    caption = generate_caption(product)

    post_id = post_image(page_id, token, product["image"], caption)

    if post_id:
        time.sleep(3)
        comment_link(post_id, token, product["link"])


# ------------------ MAIN ------------------
def run_all_pages():
    run_page(PAGE_ID, TOKEN)

    if PAGE_ID_2 and TOKEN_2:
        run_page(PAGE_ID_2, TOKEN_2)
