import os
import json
import math
import random
import datetime as dt
from typing import Dict, Any, Optional

import requests
import pandas as pd


# -------------------------
# Config
# -------------------------
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "15"))
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))

STATE_FILE = "state.json"


# -------------------------
# Helpers
# -------------------------
def today_str_th() -> str:
    # รูปแบบ: วันที่ เดือน ปี (ไม่มีเวลา)
    # ตัวอย่าง: 1/3/2569 (พ.ศ.)
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=7)))  # Thailand
    buddhist_year = now.year + 543
    return f"{now.day}/{now.month}/{buddhist_year}"


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"last_posted": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {"last_posted": {}}
    if "last_posted" not in data or not isinstance(data["last_posted"], dict):
        data["last_posted"] = {}
    return data


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def parse_date_ymd(s: str) -> Optional[dt.date]:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def can_repost(last_posted_ymd: Optional[str], days: int) -> bool:
    if not last_posted_ymd:
        return True
    d = parse_date_ymd(last_posted_ymd)
    if not d:
        return True
    return (dt.date.today() - d).days >= days


def safe_float(x, default=0.0) -> float:
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def safe_int(x, default=0) -> int:
    try:
        if pd.isna(x):
            return default
        return int(float(x))
    except Exception:
        return default


def pick_first_existing(row: pd.Series, keys) -> str:
    for k in keys:
        if k in row and pd.notna(row[k]) and str(row[k]).strip() != "":
            return str(row[k]).strip()
    return ""


def build_caption(row: pd.Series) -> str:
    name = pick_first_existing(row, ["name", "product_name", "title"])
    price = pick_first_existing(row, ["price", "sale_price", "price_min", "discount_price"])
    original = pick_first_existing(row, ["original_price", "price_before_discount"])
    discount = pick_first_existing(row, ["discount", "discount_percent", "discount_rate"])
    rating = pick_first_existing(row, ["rating", "rating_star"])
    sold = pick_first_existing(row, ["sold", "historical_sold", "sold_count"])
    category = pick_first_existing(row, ["category", "cat", "main_category"])
    link = pick_first_existing(row, ["link", "affiliate_link", "product_link", "url"])

    # ทำให้ดู "ขายจริง" ไม่เป็นบอท: ใช้สำนวนหลากหลาย + ไม่โฆษณาเกินจริง
    hooks = [
        "ของมันต้องมีรอบนี้ 😄",
        "ใครกำลังหาอยู่… เจอตัวนี้พอดี",
        "แวะมาป้ายยาชิ้นนึงแบบจริงใจ",
        "คัดมาให้จากตัวที่คนซื้อเยอะ",
        "ตัวนี้น่าหยิบมาก โดยเฉพาะช่วงโปร",
    ]

    bullets = []
    if rating:
        bullets.append(f"⭐ เรตติ้ง: {rating}")
    if discount:
        bullets.append(f"🔥 ลด: {discount}")
    elif original and price:
        bullets.append("🔥 มีโปร/ราคาดีกว่าเดิม (เช็คหน้าสินค้า)")
    if sold:
        bullets.append(f"💰 ยอดขาย: {sold}")
    if category:
        bullets.append(f"📦 หมวด: {category}")

    cta = random.choice([
        "กดดูรายละเอียด/โค้ดส่วนลดในลิงก์ได้เลยนะ",
        "เช็คราคา ณ ตอนนี้ในลิงก์ได้เลย (บางทีโปรหมดไว)",
        "ถ้าสนใจ รีบเช็คโปรก่อนหมดรอบนะ",
        "ดูรีวิวจริง ๆ แล้วค่อยตัดสินใจก็ได้ ลิงก์นี้เลย",
    ])

    lines = []
    lines.append(random.choice(hooks))
    if name:
        lines.append(f"✅ {name}")

    if price:
        if original and original != price:
            lines.append(f"ราคา: {price} (จาก {original})")
        else:
            lines.append(f"ราคา: {price}")

    if bullets:
        lines.append("")
        lines.extend([f"{b}" for b in bullets])

    lines.append("")
    lines.append(cta)
    if link:
        lines.append(link)

    lines.append("")
    lines.append(f"🗓️ อัปเดต: {today_str_th()}")
    lines.append("#Shopee #โปรวันนี้ #ของมันต้องมี #ของดีบอกต่อ")

    return "\n".join(lines).strip()


def score_row(row: pd.Series) -> float:
    # เน้นขายได้มากขึ้น: ให้คะแนนจาก rating + sold + discount
    rating = safe_float(row.get("rating", row.get("rating_star", 0)), 0.0)  # 0-5
    sold = safe_int(row.get("sold", row.get("historical_sold", row.get("sold_count", 0))), 0)
    disc = row.get("discount", row.get("discount_percent", row.get("discount_rate", 0)))
    disc_num = 0.0
    if isinstance(disc, str):
        # เช่น "35%" -> 35
        disc_num = safe_float(disc.replace("%", "").strip(), 0.0)
    else:
        disc_num = safe_float(disc, 0.0)

    # สูตรคะแนน (ปรับได้)
    s = (rating * 2.0) + (math.log10(sold + 1) * 2.5) + (disc_num / 10.0)
    return s


def post_to_facebook(message: str, link: str) -> Dict[str, Any]:
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": message,
        "link": link,
        "access_token": PAGE_ACCESS_TOKEN,
    }
    r = requests.post(url, data=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    print(f"STATUS: {r.status_code}")
    print(f"RESPONSE: {data}")
    r.raise_for_status()
    return data


# -------------------------
# Main
# -------------------------
def main():
    if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
        raise Exception("❌ Missing PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL")

    state = load_state()
    last_posted: Dict[str, str] = state.get("last_posted", {})

    print("⬇️ Downloading Shopee CSV...")
    csv_resp = requests.get(SHOPEE_CSV_URL, timeout=120)
    csv_resp.raise_for_status()

    # อ่าน CSV (กัน dtype warning)
    df = pd.read_csv(pd.io.common.BytesIO(csv_resp.content), low_memory=False)
    print(f"✅ CSV loaded: {len(df)} rows")

    # คีย์สินค้าที่ไว้กันโพสต์ซ้ำ: พยายามหา item_id / id / product_id / link
    def get_item_key(row: pd.Series) -> str:
        key = pick_first_existing(row, ["item_id", "id", "product_id"])
        if key:
            return key
        # fallback ใช้ลิงก์เป็น key
        return pick_first_existing(row, ["link", "affiliate_link", "product_link", "url"])

    # ทำ list ของสินค้าที่ "โพสต์ได้" (ยังไม่โพสต์ หรือโพสต์มาแล้ว >= 15 วัน)
    candidates = []
    for _, row in df.iterrows():
        item_key = get_item_key(row)
        link = pick_first_existing(row, ["link", "affiliate_link", "product_link", "url"])
        name = pick_first_existing(row, ["name", "product_name", "title"])

        if not item_key or not link:
            continue

        if not can_repost(last_posted.get(item_key), REPOST_AFTER_DAYS):
            continue

        # คัดของดูน่าเชื่อถือขึ้นนิดนึง (ปรับได้)
        rating = safe_float(row.get("rating", row.get("rating_star", 0)), 0.0)
        sold = safe_int(row.get("sold", row.get("historical_sold", row.get("sold_count", 0))), 0)
        if rating > 0 and rating < 4.2:
            continue
        if sold > 0 and sold < 5:
            continue

        candidates.append((score_row(row), item_key, row))

    if not candidates:
        print("ℹ️ No eligible products to post (within repost window).")
        return

    candidates.sort(key=lambda x: x[0], reverse=True)

    posted = 0
    used_keys = set()

    for score, item_key, row in candidates:
        if posted >= POSTS_PER_RUN:
            break
        if item_key in used_keys:
            continue

        link = pick_first_existing(row, ["link", "affiliate_link", "product_link", "url"])
        caption = build_caption(row)

        print("📣 Posting to Facebook...")
        resp = post_to_facebook(caption, link)

        # Update state: เก็บเป็น YYYY-MM-DD
        last_posted[item_key] = dt.date.today().strftime("%Y-%m-%d")
        used_keys.add(item_key)
        posted += 1

        post_id = resp.get
