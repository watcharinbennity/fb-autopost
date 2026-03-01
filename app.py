import os
import json
import math
import random
import re
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd

STATE_FILE = "state.json"

TH_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
]

def thai_date_no_time(dt: datetime) -> str:
    tz_th = timezone(timedelta(hours=7))
    dt_th = dt.astimezone(tz_th)
    return f"{dt_th.day} {TH_MONTHS[dt_th.month]} {dt_th.year + 543}"

def now_th():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7)))

def must_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise Exception(f"❌ Missing env: {name}")
    return v

def safe_float(x, default=0.0):
    try:
        if pd.isna(x): return default
        return float(x)
    except Exception:
        return default

def safe_int(x, default=0):
    try:
        if pd.isna(x): return default
        s = str(x).strip().lower().replace(",", "")
        m = re.match(r"^(\d+(\.\d+)?)(k|m)?$", s)
        if m:
            num = float(m.group(1))
            suf = m.group(3)
            if suf == "k": num *= 1000
            elif suf == "m": num *= 1000000
            return int(num)
        return int(float(s))
    except Exception:
        return default

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_posted": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "last_posted" not in data:
        data["last_posted"] = {}
    return data

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def pick_cols(df: pd.DataFrame):
    cols = set(df.columns)
    def first_exist(candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    return {
        "itemid": first_exist(["itemid", "item_id", "itemid_str"]),
        "name": first_exist(["item_name", "name", "product_name", "itemname"]),
        "rating": first_exist(["item_rating", "rating", "itemrating"]),
        "sold": first_exist(["itemsold", "sold", "historical_sold", "item_sold", "sold_count"]),
        "price": first_exist(["item_price", "price", "sale_price", "current_price"]),
        "price_before": first_exist(["item_price_before_discount", "price_before_discount", "original_price"]),
        "image": first_exist(["image_link", "image", "image_url", "imageurl"]),
        "link": first_exist(["product_link", "link", "item_link", "producturl", "product_url"]),
        "video": first_exist(["video_link", "video_url", "videourl"]),
    }

def monthly_trend_keywords(month: int):
    """
    ให้บอทจัดการหมวด "เดือนนี้ทำยอด" ด้วยคีย์เวิร์ดตามฤดูกาลไทย
    (ปรับ/เพิ่มได้ตามแนวเพจ)
    """
    if month == 3:
        return ["สงกรานต์", "เที่ยว", "เดินทาง", "กระเป๋าเดินทาง", "รองเท้าแตะ", "กันน้ำ", "ครีมกันแดด", "พัดลม", "หน้าร้อน"]
    if month == 4:
        return ["สงกรานต์", "ปืนฉีดน้ำ", "กันน้ำ", "แว่นกันแดด", "หมวก", "รองเท้าแตะ", "พัดลม", "แอร์พกพา"]
    if month == 5:
        return ["หน้าฝน", "ร่ม", "เสื้อกันฝน", "รองเท้ากันลื่น", "กันเชื้อรา", "กันยุง", "ไล่ยุง"]
    if month == 6:
        return ["หน้าฝน", "ร่ม", "เสื้อกันฝน", "กันยุง", "ของใช้ในบ้าน", "จัดระเบียบ"]
    if month == 10:
        return ["10.10", "โปร", "ลดราคา", "ของมันต้องมี", "ของใช้ในบ้าน", "อุปกรณ์ครัว"]
    if month == 11:
        return ["11.11", "โปร", "ลดราคา", "ช้อปปิ้ง", "ของขวัญ", "ไอที", "แก็ดเจ็ต"]
    if month == 12:
        return ["ของขวัญ", "ปีใหม่", "คริสต์มาส", "ชุดเที่ยว", "กระเป๋า", "เครื่องใช้ไฟฟ้า"]
    # ค่าเริ่มต้น (เดือนอื่น ๆ): เน้นขายง่ายทั่วไป
    return ["ขายดี", "ฮิต", "ของใช้", "อุปกรณ์", "ราคาดี", "โปร", "ลด"]

def match_trend(name: str, keywords: list[str]) -> bool:
    n = name.lower()
    return any(k.lower() in n for k in keywords)

def score_item(rating: float, sold: int, discount_pct: float) -> float:
    return (rating * 2.0) + (math.log1p(max(sold, 0)) * 1.7) + (discount_pct * 10.0)

def build_caption(name: str, price: float, price_before: float, rating: float, sold: int, link: str) -> str:
    today = thai_date_no_time(datetime.now(timezone.utc))
    discount_pct = 0.0
    if price_before and price_before > 0 and price_before > price > 0:
        discount_pct = (price_before - price) / price_before

    hooks = [
        "🔥 ดีลวันนี้ต้องรีบเก็บ!",
        "⭐ ของฮิตช่วงนี้ คนสั่งเยอะ",
        "💥 ราคาลงแรง น่าโดนมาก",
        "🛒 ตัวนี้กำลังมาแรง",
        "⚡ ถ้าเล็งอยู่ แนะนำกดดูโปรตอนนี้",
    ]
    ctas = [
        "กดดูโปร/สั่งซื้อที่ลิงก์ได้เลย 👇",
        "เช็คส่วนลดในลิงก์ก่อนหมดโปร 👇",
        "อยากได้ราคาโปร กดลิงก์ดูเลย 👇",
        "กดลิงก์ดูรายละเอียด/ราคา 👇",
    ]
    hashtags = [
        "#โปรดีบอกต่อ #ของมันต้องมี #ช้อปปี้ #ลดราคา",
        "#ดีลคุ้ม #Shopee #ช้อปออนไลน์",
        "#ของฮิต #ราคาดี #โปรแรง",
    ]

    hook = random.choice(hooks)
    cta = random.choice(ctas)
    tag = random.choice(hashtags)

    price_txt = f"{price:,.0f} บาท" if price else "เช็คราคาในลิงก์"
    before_txt = f"{price_before:,.0f} บาท" if price_before else ""
    disc_txt = f"ลด {discount_pct*100:.0f}%" if discount_pct >= 0.10 else ""

    lines = [
        f"{hook}",
        f"📅 {today}",
        f"✅ {name}",
        f"💰 ราคา: {price_txt}" + (f" (ปกติ {before_txt})" if before_txt and price_before > price else ""),
        (f"🔥 {disc_txt}" if disc_txt else ""),
        (f"⭐ เรตติ้ง: {rating:.1f} | 💰 ขายแล้ว: {sold:,} ชิ้น" if rating or sold else ""),
        "",
        f"{cta}",
        f"{link}",
        "",
        f"{tag}",
    ]
    caption = "\n".join([x for x in lines if x and str(x).strip()])
    return caption.strip()

def fb_post_photo(page_id: str, token: str, image_url: str, caption: str):
    url = f"https://graph.facebook.com/v25.0/{page_id}/photos"
    data = {"access_token": token, "url": image_url, "caption": caption, "published": "true"}
    return requests.post(url, data=data, timeout=60)

def fb_post_feed(page_id: str, token: str, message: str, link: str):
    url = f"https://graph.facebook.com/v25.0/{page_id}/feed"
    data = {"access_token": token, "message": message, "link": link}
    return requests.post(url, data=data, timeout=60)

def main():
    page_id = must_env("PAGE_ID")
    token = must_env("PAGE_ACCESS_TOKEN")
    csv_url = must_env("SHOPEE_CSV_URL")

    posts_per_run = int(os.getenv("POSTS_PER_RUN", "1"))
    repost_after_days = int(os.getenv("REPOST_AFTER_DAYS", "15"))

    state = load_state()
    last_posted: dict[str, str] = state.get("last_posted", {})

    # เงื่อนไข: โพสต์ซ้ำได้เมื่อครบ N วัน
    cutoff = now_th() - timedelta(days=repost_after_days)

    def recently_posted(item_id: str) -> bool:
        ts = last_posted.get(item_id)
        if not ts:
            return False
        try:
            dt = datetime.fromisoformat(ts)
        except Exception:
            return False
        return dt > cutoff

    print("⬇️ Downloading Shopee CSV...")
    resp = requests.get(csv_url, timeout=180)
    resp.raise_for_status()

    best = []
    best_limit = 400

    first_chunk = True
    mapping = None

    # หมวดเดือนนี้ให้บอทเลือกเอง
    month = now_th().month
    trend_keys = monthly_trend_keywords(month)

    for chunk in pd.read_csv(pd.io.common.BytesIO(resp.content), chunksize=50000, low_memory=False):
        chunk = normalize_columns(chunk)
        if first_chunk:
            mapping = pick_cols(chunk)
            first_chunk = False
            if not mapping["name"] or not mapping["link"]:
                raise Exception(f"❌ CSV columns not supported. Found columns: {list(chunk.columns)[:50]}")

        col_itemid = mapping["itemid"]
        col_name = mapping["name"]
        col_rating = mapping["rating"]
        col_sold = mapping["sold"]
        col_price = mapping["price"]
        col_price_before = mapping["price_before"]
        col_image = mapping["image"]
        col_link = mapping["link"]
        col_video = mapping["video"]

        for _, row in chunk.iterrows():
            item_id = str(row[col_itemid]) if col_itemid and col_itemid in row else ""
            name = str(row[col_name]) if col_name in row else ""
            link = str(row[col_link]) if col_link in row else ""

            if not item_id or not name or not link:
                continue

            # กันโพสต์ซ้ำภายใน 15 วัน
            if recently_posted(item_id):
                continue

            # ให้บอท “เลือกหมวดเดือนนี้” ด้วย keyword match
            # ถ้าไม่ match เลย ยังมีสิทธิ์ติดได้ แต่คะแนนจะน้อยกว่า
            is_trend = match_trend(name, trend_keys)

            rating = safe_float(row[col_rating], 0.0) if col_rating and col_rating in row else 0.0
            sold = safe_int(row[col_sold], 0) if col_sold and col_sold in row else 0

            price = safe_float(row[col_price], 0.0) if col_price and col_price in row else 0.0
            price_before = safe_float(row[col_price_before], 0.0) if col_price_before and col_price_before in row else 0.0

            discount_pct = 0.0
            if price_before and price_before > 0 and price_before > price > 0:
                discount_pct = (price_before - price) / price_before

            # เกณฑ์ขั้นต่ำเพื่อ “ขายได้มากขึ้น”
            if rating < 4.5:
                continue
            if sold < 50:
                continue
            if discount_pct < 0.10 and sold < 300:
                continue

            image_url = str(row[col_image]) if col_image and col_image in row else ""
            video_url = str(row[col_video]) if col_video and col_video in row else ""

            base = score_item(rating, sold, discount_pct)
            # trend boost: ถ้าเข้าหมวดเดือนนี้ เพิ่มคะแนน
            s = base + (2.5 if is_trend else 0.0)
