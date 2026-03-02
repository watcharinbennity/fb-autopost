import os
import io
import json
import math
import random
import time          # 👈 เพิ่มบรรทัดนี้
import datetime as dt
import requests
import pandas as pd
STATE_FILE = "state.json"

# -----------------------
# Config from ENV
# -----------------------
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "15"))
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))  # เทส 1 โพสต์/รัน
TOP_POOL = int(os.getenv("TOP_POOL", "80"))           # เลือกจาก top กี่ตัวเพื่อสุ่มกันซ้ำ pattern

if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
    raise Exception("❌ Missing PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL")

APP_OPEN_INSTRUCTION = """\
📌 วิธีสั่งซื้อ (สำคัญ)
1️⃣ กดลิงก์สินค้าในโพสต์
2️⃣ ถ้าเปิดแล้วเห็นแค่รูป/หน้าเว็บใน Facebook
3️⃣ กด ⋮ มุมขวาบน แล้วเลือก “เปิดในแอป Shopee”
✅ ทำตามนี้จะเข้าหน้าสินค้า และลิงก์ยังนับโปร/คอมได้
""".strip()

# -----------------------
# State
# -----------------------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_posted": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "last_posted" not in data or not isinstance(data["last_posted"], dict):
            data["last_posted"] = {}
        return data
    except Exception:
        return {"last_posted": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def iso_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=7))).isoformat(timespec="seconds")

def can_repost(last_iso: str | None, days: int) -> bool:
    if not last_iso:
        return True
    try:
        last_dt = dt.datetime.fromisoformat(last_iso)
    except Exception:
        return True
    now = dt.datetime.now(last_dt.tzinfo) if last_dt.tzinfo else dt.datetime.now()
    return (now - last_dt).days >= days

# -----------------------
# CSV helpers
# -----------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def first_exist(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None

def safe_float(x, default=0.0) -> float:
    try:
        if pd.isna(x):
            return default
        s = str(x).strip().replace(",", "").replace("%", "")
        return float(s)
    except Exception:
        return default

def safe_int(x, default=0) -> int:
    try:
        if pd.isna(x):
            return default
        s = str(x).strip().lower().replace(",", "")
        # รองรับ 1.2k / 3m
        if s.endswith("k"):
            return int(float(s[:-1]) * 1000)
        if s.endswith("m"):
            return int(float(s[:-1]) * 1000000)
        return int(float(s))
    except Exception:
        return default

def score_item(rating: float, sold: int, discount_pct: float, price: float) -> float:
    # คะแนนเน้น "ขายได้": rating + sold + discount + ราคาไม่แรงเกิน
    s = 0.0
    s += max(0.0, rating - 4.5) * 40.0
    s += min(60.0, math.log1p(max(sold, 0)) * 8.0)
    s += min(40.0, discount_pct * 100.0)  # discount_pct 0.3 => +30
    if 49 <= price <= 799:
        s += 8.0
    elif price <= 1500:
        s += 4.0
    return s

# -----------------------
# Caption (ไม่ดูเป็นบอท)
# -----------------------
HOOKS = [
    "🔥 ดีลวันนี้ต้องรีบเก็บ!",
    "⭐ ตัวนี้รีวิวดี คนซื้อเยอะ",
    "💥 ราคาดี น่าโดนมาก",
    "🛒 ของมันต้องมีช่วงนี้",
    "⚡ เจอโปรดีเลยเอามาแปะให้",
]
CTAS = [
    "กดดูรายละเอียดในลิงก์ได้เลย 👇",
    "เช็คราคา/โปรตอนนี้ในลิงก์ 👇",
    "ของหมดไว แนะนำรีบเช็คโปร 👇",
    "ดูรีวิวจริงก่อนตัดสินใจได้เลย 👇",
]
TAGS = [
    "#โปรดีบอกต่อ #ของมันต้องมี #ช้อปปี้",
    "#ดีลคุ้ม #Shopee #ลดราคา",
    "#ของฮิต #ราคาดี #ช้อปออนไลน์",
]

def build_caption(name: str, rating: float, sold: int, discount_pct: float, price: float, url: str) -> str:
    parts = []
    parts.append(random.choice(HOOKS))
    if name:
        parts.append(f"✅ {name}")

    line2 = []
    if price > 0:
        line2.append(f"💰 {price:,.0f} บาท")
    if discount_pct >= 0.10:
        line2.append(f"🔥 ลด {discount_pct*100:.0f}%")
    if rating > 0:
        line2.append(f"⭐ {rating:.1f}")
    if sold > 0:
        line2.append(f"💰 ขายแล้ว {sold:,}+")
    if line2:
        parts.append(" / ".join(line2))

    parts.append("")
    parts.append(random.choice(CTAS))
    parts.append(url)
    parts.append("")
    parts.append(APP_OPEN_INSTRUCTION)
    parts.append("")
    parts.append(random.choice(TAGS))

    caption = "\n".join([p for p in parts if str(p).strip() != ""]).strip()

    # กันยาวเกิน (ปลอดภัยไว้ก่อน)
    if len(caption) > 1900:
        caption = caption[:1890].rstrip() + "…"
    return caption

# -----------------------
# Facebook post (ลิงก์หน้าสินค้าเท่านั้น)
# -----------------------
def fb_post_link(caption: str, product_url: str) -> dict:
    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": caption,
        "link": product_url,
        "access_token": PAGE_ACCESS_TOKEN,
    }
    r = requests.post(url, data=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    print("STATUS:", r.status_code)
    print("RESPONSE:", data)

    if r.status_code != 200:
        raise Exception(f"❌ Facebook post failed: {data}")
    return data

# -----------------------
# Main
# -----------------------
def main():
    state = load_state()
    last_posted = state.get("last_posted", {})

    print("⬇️ Downloading Shopee CSV...")
    resp = requests.get(SHOPEE_CSV_URL, timeout=120)
    resp.raise_for_status()
    df = pd.read_csv(io.BytesIO(resp.content), low_memory=False)
    df = normalize_columns(df)
    print(f"✅ CSV loaded: {len(df)} rows")

    # หา “คอลัมน์ลิงก์หน้าสินค้า” (สำคัญสุด)
    col_link = first_exist(df, ["product_link", "link", "url", "item_link", "product_url"])
    col_name = first_exist(df, ["item_name", "product_name", "name", "title"])
    col_rating = first_exist(df, ["item_rating", "rating", "rating_star"])
    col_sold = first_exist(df, ["itemsold", "sold", "historical_sold", "sold_count"])
    col_disc = first_exist(df, ["discount", "discount_percent", "discount_rate"])
    col_price = first_exist(df, ["item_price", "price", "sale_price", "current_price"])

    if not col_link:
        raise Exception(f"❌ หา column ลิงก์หน้าสินค้าไม่เจอ (ในไฟล์มี: {list(df.columns)[:40]})")

    candidates = []
    for _, row in df.iterrows():
        link = str(row.get(col_link, "")).strip()
        if not link or not link.startswith("http"):
            continue

        # กันโพสต์ซ้ำใน 15 วัน (key ใช้ link)
        if not can_repost(last_posted.get(link), REPOST_AFTER_DAYS):
            continue

        name = str(row.get(col_name, "")).strip() if col_name else ""
        rating = safe_float(row.get(col_rating, 0.0)) if col_rating else 0.0
        sold = safe_int(row.get(col_sold, 0)) if col_sold else 0
        disc_raw = row.get(col_disc, 0.0) if col_disc else 0.0
        discount_pct = safe_float(disc_raw) / (100.0 if safe_float(disc_raw) > 1 else 1.0)  # รองรับ 30 หรือ 0.3
        price = safe_float(row.get(col_price, 0.0)) if col_price else 0.0

        # กรองขั้นต่ำให้ขายง่าย
        if rating and rating < 4.5:
            continue
        if sold and sold < 30:
            continue

        s = score_item(rating, sold, discount_pct, price)
        candidates.append((s, link, name, rating, sold, discount_pct, price))

    if not candidates:
        print("⚠️ ไม่มีสินค้าที่เข้าเงื่อนไข (หรือยังไม่ครบวัน repost)")
        return

    candidates.sort(key=lambda x: x[0], reverse=True)

    # เลือกจาก top pool แล้วสุ่มเล็กน้อยกันโพสต์ซ้ำ pattern
    pool = candidates[: min(len(candidates), TOP_POOL)]
    picks = random.sample(pool, k=min(POSTS_PER_RUN, len(pool)))

    posted = 0
    for s, link, name, rating, sold, discount_pct, price in picks:
        caption = build_caption(name, rating, sold, discount_pct, price, link)

        print(f"📤 Posting ({posted+1}/{len(picks)}) score={s:.1f}")
        res = fb_post_link(caption, link)

        # บันทึกเวลาโพสต์
        last_posted[link] = iso_now()
        posted += 1

        # หน่วงนิดนึงกันรัว
        time.sleep(3)

    state["last_posted"] = last_posted
    save_state(state)
    print(f"✅ Done. Posted {posted} item(s). state.json updated.")

if __name__ == "__main__":
    main()
