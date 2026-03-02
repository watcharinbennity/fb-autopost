import os
import io
import json
import random
import time
import datetime as dt
import requests
import pandas as pd

# =========================
# CONFIG
# =========================
STATE_FILE = "state.json"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))   # เทส = 1
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "15"))

# =========================
# STATE
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"posted": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# =========================
# FACEBOOK POST
# =========================
def fb_post(message, link):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/feed"
    payload = {
        "message": message,
        "link": link,
        "access_token": PAGE_ACCESS_TOKEN
    }
    r = requests.post(url, data=payload, timeout=30)
    data = r.json()

    if r.status_code != 200:
        raise Exception(f"Facebook post failed: {data}")

    return data

# =========================
# CONTENT
# =========================
def build_caption(row):
    templates = [
        f"""⭐ ตัวนี้รีวิวดี คนซื้อซ้ำเยอะ

{row['product_name']}
💰 ราคา {row['price']} บาท
⭐ คะแนน {row['rating']}

ดูรายละเอียดในลิงก์ 👇""",

        f"""🧴 ของมันต้องมีช่วงนี้

{row['product_name']}
ราคา {row['price']} บาท
รีวิว {row['rating']} ⭐

กดดูรายละเอียดได้เลย 👇""",

        f"""ของดีบอกต่อ 👌

{row['product_name']}
รีวิวดี ราคาคุ้ม

ดูรายละเอียด 👇"""
    ]
    return random.choice(templates)

# =========================
# MAIN
# =========================
def main():
    if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
        raise Exception("ENV ไม่ครบ (PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL)")

    print("⬇ Downloading Shopee CSV...")
    csv_bytes = requests.get(SHOPEE_CSV_URL, timeout=60).content
    df = pd.read_csv(io.BytesIO(csv_bytes))

    print(f"✅ CSV loaded: {len(df)} rows")

    state = load_state()
    now = dt.datetime.utcnow()

    candidates = []
    for _, r in df.iterrows():
        pid = str(r["product_id"])
        last = state["posted"].get(pid)

        if last:
            last_time = dt.datetime.fromisoformat(last)
            if (now - last_time).days < REPOST_AFTER_DAYS:
                continue

        candidates.append(r)

    random.shuffle(candidates)

    posted = 0
    for row in candidates[:POSTS_PER_RUN]:
        caption = build_caption(row)
        link = row["product_link"]

        print(f"🚀 Posting: {row['product_name']}")
        res = fb_post(caption, link)
        print("✅ POSTED:", res.get("id"))

        state["posted"][str(row["product_id"])] = now.isoformat()
        save_state(state)

        posted += 1
        time.sleep(3)

    print(f"🎉 Done. Posted {posted} post(s)")

if __name__ == "__main__":
    main()
