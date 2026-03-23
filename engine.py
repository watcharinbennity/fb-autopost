import requests, json, os, time

MAX_ROWS = 100000
TIMEOUT = 20

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
        print("Streaming CSV...")
        res = requests.get(url, stream=True, timeout=TIMEOUT)

        for i, line in enumerate(res.iter_lines()):
            if not line:
                continue

            if i == 0:
                continue  # skip header

            if i > MAX_ROWS:
                print("Reached MAX_ROWS")
                break

            try:
                row = line.decode("utf-8", errors="ignore").split(",")
                yield row
            except:
                continue

    except Exception as e:
        print("CSV ERROR:", e)


# ---------------- SELECT PRODUCT ----------------
def choose_product():
    posted = load_posted()

    best = None
    best_score = 0
    count = 0

    for row in iter_csv_rows(CSV_URL):
        try:
            if len(row) < 8:
                continue

            name = row[1]
            image = row[2]
            sold = float(row[3] or 0)
            rating = float(row[4] or 0)
            price = float(row[5] or 0)
            com = float(row[6] or 0)
            link = row[7]

            pid = name  # ใช้ชื่อกันซ้ำ

            count += 1

            # ✅ filter เบาๆ (ไม่ตันแล้ว)
            if rating < 4.0:
                continue

            if sold < 50:
                continue

            if pid in posted:
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

    print("SCAN DONE:", count)

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
    print("Posting to:", page_id)

    img = download_image(image_url)

    if img:
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
            print("POST IMAGE:", data)

            if "post_id" in data:
                return data["post_id"]

        except Exception as e:
            print("POST IMAGE ERROR:", e)

    # fallback text
    try:
        res = requests.post(
            f"https://graph.facebook.com/v25.0/{page_id}/feed",
            data={
                "message": caption,
                "access_token": token
            }
        )

        data = res.json()
        print("POST TEXT:", data)

        return data.get("id")

    except Exception as e:
        print("POST TEXT ERROR:", e)

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
    print("RUN PAGE:", page_id)

    product = choose_product()

    if not product:
        print("❌ No product")
        return

    print("✅ CHOSEN:", product["name"])

    caption = generate_caption(product)

    post_id = post_image(page_id, token, product["image"], caption)

    if post_id:
        time.sleep(3)
        comment_link(post_id, token, product["link"])


def run_all_pages():
    run_page(PAGE_ID, TOKEN)

    if PAGE_ID_2 and TOKEN_2:
        run_page(PAGE_ID_2, TOKEN_2)
