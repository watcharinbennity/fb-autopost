import requests, json, os, time

MAX_ROWS = 100000
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


# ------------------ TARGET FILTER ------------------
def is_target_product(name):
    name = name.lower()

    camera = ["camera", "กล้อง", "cctv", "ip camera"]
    robot = ["robot vacuum", "หุ่นยนต์ดูดฝุ่น"]
    plug = ["smart plug", "ปลั๊ก", "wifi plug"]

    if any(k in name for k in camera):
        return "camera"

    if any(k in name for k in robot):
        return "robot"

    if any(k in name for k in plug):
        return "plug"

    return None


# ------------------ SELECT PRODUCT ------------------
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

            if commission < 30:
                continue

            score = (sold * 2) + (rating * 100) + (commission * 5)

            if score > best_score:
                best_score = score
                best = {
                    "id": pid,
                    "name": name,
                    "image": image,
                    "sold": sold,
                    "rating": rating,
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
    return f"""🔥 ของมันต้องมี!

{p['name']}

⭐ {p['rating']} | ขายแล้ว {int(p['sold'])}
💸 คุ้มสุดตอนนี้!

👉 เช็กราคาล่าสุดที่ลิงก์ด้านล่าง

#Shopee #ของดีบอกต่อ"""


# ------------------ DOWNLOAD IMAGE ------------------
def download_image(url):
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.content
    except:
        return None


# ------------------ POST ------------------
def post_image(page_id, token, image_url, caption):
    img = download_image(image_url)

    if not img:
        print("Image fail → fallback text")
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
        print("Post error:", e)

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

    print("CHOSEN:", product["name"])

    post_id = post_image(page_id, token, product["image"], caption)

    if post_id:
        time.sleep(3)
        comment_link(post_id, token, product["link"])


# ------------------ MAIN ------------------
def run_all_pages():
    run_page(PAGE_ID, TOKEN)

    if PAGE_ID_2 and TOKEN_2:
        run_page(PAGE_ID_2, TOKEN_2)
