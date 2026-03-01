import os
import json
import random
import time
import io
import requests
import pandas as pd
from datetime import datetime, timedelta

# =========================
# ENV
# =========================
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL")

REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "15"))
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "2"))

if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
    raise Exception("❌ Missing PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL")

STATE_FILE = "state.json"

# =========================
# LOAD / SAVE STATE
# =========================
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_posted": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

state = load_state()

# =========================
# LOAD CSV
# =========================
print("⬇️ Downloading Shopee CSV...")
r = requests.get(SHOPEE_CSV_URL, timeout=60)
r.raise_for_status()

df = pd.read_csv(io.BytesIO(r.content), low_memory=False)
print(f"✅ CSV loaded: {len(df)} rows")

# =========================
# NORMALIZE COLUMNS
# =========================
def col(name):
    for c in df.columns:
        if name.lower() in c.lower():
            return c
    return None

COL_NAME = col("product") or col("name")
COL_PRICE = col("price")
COL_SALES = col("sold") or col("sales")
COL_RATING = col("rating")
COL_LINK = col("link")
COL_IMAGE = col("image")

# =========================
# FILTER CANDIDATES
# =========================
now = datetime.utcnow()
candidates = []

for _, row in df.iterrows():
    pid = str(row.get(COL_LINK, "")).strip()
    if not pid:
        continue

    last = state["last_posted"].get(pid)
    if last:
        last_dt = datetime.fromisoformat(last)
        if now - last_dt < timedelta(days=REPOST_AFTER_DAYS):
            continue

    candidates.append(row)

if not candidates:
    print("⚠️ ไม่มีสินค้าที่เข้าเงื่อนไข")
    exit(0)

# =========================
# SORT BY PERFORMANCE
# =========================
def score(row):
    score = 0
    try:
        score += float(row.get(COL_SALES, 0)) * 2
        score += float(row.get(COL_RATING, 0)) * 10
    except:
        pass
    return score

candidates.sort(key=score, reverse=True)
selected = candidates[:POSTS_PER_RUN]

# =========================
# CAPTION GENERATOR
# =========================
HOOKS = [
    "🔥 ตัวนี้กำลังมาแรง!",
    "⭐ รีวิวแน่น คนซื้อเพียบ",
    "💥 ราคาดีจนต้องรีบกด",
    "📦 ของมันต้องมี",
]

CTA = [
    "กดดูรายละเอียดเลย 👇",
    "เช็คราคาได้ที่ลิงก์นี้ 👇",
    "ของหมดไว อย่าช้า 👇",
]

EXTRAS = [
    "เหมาะกับใช้เองและซื้อฝาก",
    "ส่งไว แพ็คดี",
    "ร้านคะแนนสูง น่าเชื่อถือ",
]

def build_caption(row):
    parts = []
    parts.append(random.choice(HOOKS))

    name = str(row.get(COL_NAME, "")).strip()
    if name:
        parts.append(f"🛒 {name}")

    price = row.get(COL_PRICE)
    if pd.notna(price):
        parts.append(f"💰 ราคาเพียง {price}")

    rating = row.get(COL_RATING)
    if pd.notna(rating):
        parts.append(f"⭐ เรตติ้ง {rating}/5")

    sales = row.get(COL_SALES)
    if pd.notna(sales):
        parts.append(f"🔥 ขายแล้ว {sales}+ ชิ้น")

    if random.random() < 0.7:
        parts.append(random.choice(EXTRAS))

    parts.append(random.choice(CTA))

    return "\n".join(parts)

# =========================
# POST TO FACEBOOK
# =========================
GRAPH_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

posted = 0

for row in selected:
    link = str(row.get(COL_LINK, "")).strip()
    image = str(row.get(COL_IMAGE, "")).strip()

    caption = build_caption(row)
    caption += f"\n\n👉 {link}"

    payload = {
        "access_token": PAGE_ACCESS_TOKEN,
        "caption": caption,
        "published": "true",
    }

    files = None
    if image and image.startswith("http"):
        payload["url"] = image
    else:
        payload["caption"] += "\n(ไม่มีรูปสินค้า)"

    print("📤 Posting to Facebook...")
    res = requests.post(GRAPH_URL, data=payload, files=files, timeout=60)
    if res.status_code != 200:
        print("❌ Post failed:", res.text)
        continue

    result = res.json()
    print("✅ Posted:", result.get("id"))

    state["last_posted"][link] = now.isoformat()
    posted += 1
    time.sleep(5)

save_state(state)

print(f"🎉 เสร็จสิ้น โพสต์ทั้งหมด {posted} รายการ")
