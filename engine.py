import requests, csv, io, random, os, json

PAGE_ID = os.environ.get("PAGE_ID")
TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
CSV_URL = os.environ.get("SHOPEE_CSV_URL")

STATE_FILE = "posted.json"

# ===============================
# โหลด state กันโพสต์ซ้ำ
# ===============================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"items": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ===============================
# ยิงโพสต์
# ===============================
def post_to_facebook(image_url, caption):
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/photos"
    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": TOKEN
    }
    res = requests.post(url, data=payload).json()
    print("POST:", res)
    return res

# ===============================
# ดึง CSV
# ===============================
def stream_csv():
    r = requests.get(CSV_URL)
    r.encoding = "utf-8-sig"
    return csv.DictReader(io.StringIO(r.text))

# ===============================
# เลือกสินค้า (เน้นขายจริง)
# ===============================
def pick_product(rows, state):
    candidates = []

    for row in rows:
        try:
            sold = float(row.get("historical_sold", 0))
            rating = float(row.get("item_rating", 0))
            price = float(row.get("price", 0))
            title = row.get("item_name", "")

            short_link = row.get("product_short link", "").strip()

            # 🔥 ใช้เฉพาะ short link
            if not short_link.startswith("https://s.shopee.co.th/"):
                continue

            # 🔥 ฟิลเตอร์ขายจริง
            if sold < 50: continue
            if rating < 4.5: continue
            if price < 20: continue

            pid = row.get("itemid")
            if pid in state["items"]:
                continue

            candidates.append({
                "id": pid,
                "title": title,
                "sold": sold,
                "rating": rating,
                "price": price,
                "image": row.get("image_url"),
                "link": short_link
            })

        except:
            continue

    if not candidates:
        return None

    # 🔥 เลือกตัวขายดีที่สุด
    candidates.sort(key=lambda x: x["sold"], reverse=True)

    return random.choice(candidates[:10])  # เอาท็อป 10

# ===============================
# Caption ยิงขาย (CTR สูง)
# ===============================
def make_caption(p):
    return f"""🔥 ของโคตรขายดี คนซื้อจริง

{p['title']}

⭐ รีวิว {p['rating']} เต็มจากผู้ใช้จริง
🛒 ขายแล้ว {int(p['sold']):,} ชิ้น

⚠ ของกำลังฮิต คนกำลังหา
📌 ใช้งานจริง งานช่างต้องมี

👉 กดดูราคาล่าสุดตอนนี้
{p['link']}"""

# ===============================
# RUN
# ===============================
def run():
    state = load_state()

    print("Streaming CSV...")
    rows = list(stream_csv())

    product = pick_product(rows, state)

    if not product:
        print("❌ No product")
        return

    print("✅ CHOSEN:", product["title"])

    caption = make_caption(product)

    post_to_facebook(product["image"], caption)

    # save history
    state["items"].append(product["id"])
    save_state(state)
