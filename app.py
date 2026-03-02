import os
import io
import json
import random
import time
import datetime as dt
import requests
import pandas as pd

# ======================
# CONFIG
# ======================
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL")

POSTS_PER_RUN = 1
STATE_FILE = "state.json"

# ======================
# TIME (Thailand)
# ======================
TH_TZ = dt.timezone(dt.timedelta(hours=7))

def now_th():
    return dt.datetime.now(TH_TZ)

# ======================
# STATE
# ======================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_index": 0}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)

# ======================
# LOAD PRODUCTS
# ======================
def load_products():
    df = pd.read_csv(SHOPEE_CSV_URL)
    df = df.dropna(subset=["product_link", "product_name"])
    return df.to_dict("records")

# ======================
# POST CONTENT
# ======================
QUESTION_POSTS = [
    "งานระบบไฟฟ้า ปัญหาที่เจอบ่อยที่สุดคืออะไร?",
    "เลือกอุปกรณ์ไฟฟ้า ดูราคาหรือความปลอดภัยก่อน?",
    "มือใหม่งานไฟฟ้า พลาดตรงไหนกันบ่อย?"
]

def build_post(product):
    post_type = random.choice(["question", "sell"])

    if post_type == "question":
        return random.choice(QUESTION_POSTS)

    return f"""🛒 ของมันต้องมีช่วงนี้
{product['product_name']}

💰 {product.get('price','')}
⭐ {product.get('rating','')}

กดดูรายละเอียดได้ที่ลิงก์นี้ 👇
{product['product_link']}
"""

# ======================
# FACEBOOK POST
# ======================
def fb_post(message):
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/feed"
    payload = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN
    }
    r = requests.post(url, data=payload)
    if r.status_code != 200:
        raise Exception(r.text)
    return r.json()

# ======================
# MAIN
# ======================
def main():
    state = load_state()
    products = load_products()

    idx = state["last_index"] % len(products)
    product = products[idx]

    message = build_post(product)
    fb_post(message)

    state["last_index"] += 1
    save_state(state)

    print("✅ Posted successfully")

if __name__ == "__main__":
    main()
