import os
import json
import time
import random
import datetime as dt
from typing import Dict, Any, Optional, List, Tuple

import requests
import pandas as pd


STATE_FILE = "state.json"


def today_th_date_str() -> str:
    # แสดงเป็น "วันที่ เดือน ปี" แบบไทย (ปี พ.ศ.)
    thai_months = [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    now = dt.datetime.now()
    day = now.day
    month_name = thai_months[now.month - 1]
    year_be = now.year + 543
    return f"{day} {month_name} {year_be}"


def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"last_posted": {}, "category_monthly": {}, "caption_stats": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("last_posted", {})
        data.setdefault("category_monthly", {})
        data.setdefault("caption_stats", {})
        return data
    except Exception:
        return {"last_posted": {}, "category_monthly": {}, "caption_stats": {}}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def env_required(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise Exception(f"❌ Missing env var: {name}")
    return v


def pick_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols:
            return cols[cand.lower()]
    return None


def to_float(x) -> float:
    try:
        if pd.isna(x):
            return 0.0
        s = str(x).strip()
        s = s.replace(",", "")
        s = s.replace("%", "")
        return float(s)
    except Exception:
        return 0.0


def to_int(x) -> int:
    try:
        if pd.isna(x):
            return 0
        s = str(x).strip().replace(",", "")
        return int(float(s))
    except Exception:
        return 0


def normalize_url(u: str) -> str:
    if not u:
        return ""
    u = str(u).strip()
    return u


def get_month_key(now: Optional[dt.datetime] = None) -> str:
    now = now or dt.datetime.now()
    return f"{now.year:04d}-{now.month:02d}"


def download_csv(url: str) -> pd.DataFrame:
    print("⬇️ Downloading Shopee CSV...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(pd.io.common.BytesIO(r.content))
    print(f"✅ CSV loaded: {len(df)} rows")
    return df


def build_score(row: Dict[str, Any], rating: float, sold: int, discount_pct: float, price: float) -> float:
    # สเกลคะแนนให้เน้น: เรตติ้ง + ยอดขาย + ส่วนลด + ราคาตัดสินใจง่าย
    score = 0.0
    score += max(0.0, (rating - 4.5)) * 40.0        # เรต 4.5->0, 5.0->20
    score += min(50.0, (sold / 1000.0) * 50.0)      # sold 1000 = +50
    score += min(40.0, (discount_pct / 50.0) * 40.0)  # ลด 50% = +40

    # ราคา: ชอบช่วงกลาง/ไม่แพงเกิน (ปรับได้)
    if 49 <= price <= 799:
        score += 12.0
    elif price <= 1500:
        score += 6.0

    # กันของเสี่ยง: ดาวต่ำ/ขายน้อย
    if rating > 0 and rating < 4.3:
        score -= 25.0
    if sold > 0 and sold < 30:
        score -= 10.0

    return score


def caption_templates() -> List[Tuple[str, str]]:
    # (template_id, template_text)
    # NOTE: ไม่ใส่เวลา (ตามที่คุณขอเอาเวลาออก)
    templates = [
        ("A", "วันนี้เจอของน่าใช้มาก ⭐ รีวิวดี / คนซื้อเยอะ\n🔥 ช่วงนี้ลดอยู่ด้วย คุ้มจัด\nกดดูราคากับรายละเอียดได้เลย 👇\n{url}"),
        ("B", "ของฮิตจริง… เห็นยอดขายแล้วไม่แปลกใจ 💰\n⭐ เรตติ้งดี ใช้งานง่าย\n🔥 โปรแรงอยู่ตอนนี้ รีบเช็คราคา 👇\n{url}"),
        ("C", "ใครกำลังหา “ของคุ้มๆ” แนะนำตัวนี้เลย\n⭐ คะแนนรีวิวดีมาก\n🔥 ลดแรง (คุ้มกว่าปกติ)\nลิงก์อยู่ตรงนี้ 👇\n{url}"),
        ("D", "ตัวนี้เหมาะกับคนอยากได้ของดีแต่ไม่อยากจ่ายแพง\n⭐ รีวิวแน่น / 💰 ขายดี\nกดดูราคา ณ ตอนนี้ได้เลย 👇\n{url}"),
        ("E", "โปรมาแล้ว 🔥 ลดแรงกว่าที่คิด\nของขายดี + รีวิวดี ⭐\nสนใจลองกดเข้าไปดูรายละเอียดได้เลย 👇\n{url}"),
        ("F", "แปะของน่าซื้อให้ดูครับ/ค่ะ 😊\n⭐ เรตติ้งดี / 💰 ยอดขายสูง / 🔥 ราคาดี\nดูรายละเอียด+ราคาได้ที่ลิงก์ 👇\n{url}"),
        ("G", "ถ้าอยากได้ของที่ “คนใช้จริงแล้วชอบ” ตัวนี้น่าสนใจมาก ⭐\nช่วงนี้ลดอยู่ด้วย 🔥\nกดดูราคาได้เลย 👇\n{url}"),
        ("H", "ตัวนี้คัดมาให้แล้วว่าคุ้ม ✅\n⭐ รีวิวสูง 🔥 ลดแรง 💰 ขายดี\nไปดูรายละเอียดก่อนตัดสินใจได้เลย 👇\n{url}"),
    ]
    return templates


def build_caption(url: str, state: Dict[str, Any]) -> Tuple[str, str]:
    templates = caption_templates()
    tid, text = random.choice(templates)

    # สุ่มประโยคเปิดเล็กๆ ให้ดูมนุษย์ขึ้น
    openers = [
        "อัปเดตของน่าซื้อวันนี้ 😊",
        "แนะนำของคุ้มๆ อีกตัวครับ/ค่ะ",
        "เจอโปรดีเลยเอามาแปะให้",
        "ของนี้มาแรงช่วงนี้",
        "ตัวนี้คนถามเยอะ เลยรวมให้",
    ]
    if random.random() < 0.6:
        text = random.choice(openers) + "\n\n" + text

    msg = text.format(url=url)

    # เก็บสถิติ template
    state["caption_stats"][tid] = state["caption_stats"].get(tid, 0) + 1
    return tid, msg


def should_repost(last_posted_iso: Optional[str], repost_after_days: int) -> bool:
    if not last_posted_iso:
        return True
    try:
        last_dt = dt.datetime.fromisoformat(last_posted_iso)
        return (dt.datetime.now() - last_dt).days >= repost_after_days
    except Exception:
        return True


def post_to_facebook_feed(page_id: str, token: str, message: str, link: str) -> Dict[str, Any]:
    url = f"https://graph.facebook.com/v25.0/{page_id}/feed"
    payload = {"message": message, "link": link, "access_token": token}
    r = requests.post(url, data=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return {"status_code": r.status_code, "data": data}


def post_to_facebook_photo(page_id: str, token: str, caption: str, image_url: str) -> Dict[str, Any]:
    url = f"https://graph.facebook.com/v25.0/{page_id}/photos"
    payload = {
        "url": image_url,
        "caption": caption,
        "published": "true",
        "access_token": token
    }
    r = requests.post(url, data=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return {"status_code": r.status_code, "data": data}


def main():
    page_id = env_required("PAGE_ID")
    token = env_required("PAGE_ACCESS_TOKEN")
    csv_url = env_required("SHOPEE_CSV_URL")

    repost_after_days = int(os.getenv("REPOST_AFTER_DAYS", "15"))
    posts_per_run = int(os.getenv("POSTS_PER_RUN", "2"))
    min_delay = int(os.getenv("MIN_DELAY_SECONDS", "120"))
    max_delay = int(os.getenv("MAX_DELAY_SECONDS", "360"))

    state = load_state()

    df = download_csv(csv_url)

    # เดาคอลัมน์ (รองรับหลายชื่อ)
    col_name = pick_col(df, ["product_name", "name", "title", "สินค้า", "ชื่อสินค้า"])
    col_url = pick_col(df, ["product_link", "url", "link", "affiliate_link", "ลิงก์"])
    col_img = pick_col(df, ["image_link", "image", "img", "image_url", "รูป", "ลิงก์รูป"])
    col_rating = pick_col(df, ["rating", "คะแนน", "ดาว", "avg_rating"])
    col_sold = pick_col(df, ["sold", "ยอดขาย", "total_sold", "orders", "ยอดสั่งซื้อ"])
    col_disc = pick_col(df, ["discount", "discount_percent", "เปอร์เซ็นต์ส่วนลด", "ส่วนลด", "discount_pct"])
    col_price = pick_col(df, ["price", "ราคา", "sale_price", "ราคาขาย"])
    col_cat = pick_col(df, ["category", "หมวดหมู่", "cat", "หมวด"])

    if not col_url:
        raise Exception("❌ หา column ลิงก์สินค้าไม่เจอ (ต้องมี url/link/product_link อย่างน้อย 1 ชื่อ)")

    # ทำ list candidates
    candidates = []
    for i, row in df.iterrows():
        url = normalize_url(row.get(col_url, ""))
        if not url:
            continue

        name = str(row.get(col_name, "")).strip() if col_name else ""
        image_url = normalize_url(row.get(col_img, "")) if col_img else ""
        rating = to_float(row.get(col_rating, 0)) if col_rating else 0.0
        sold = to_int(row.get(col_sold, 0)) if col_sold else 0
        discount_pct = to_float(row.get(col_disc, 0)) if col_disc else 0.0
        price = to_float(row.get(col_price, 0)) if col_price else 0.0
        category = str(row.get(col_cat, "")).strip() if col_cat else ""

        # product_id ใช้ url เป็นหลัก (กันซ้ำ)
        product_id = url

        last_posted_iso = state["last_posted"].get(product_id)
        if not should_repost(last_posted_iso, repost_after_days):
            continue

        score = build_score(row, rating, sold, discount_pct, price)

        candidates.append({
            "product_id": product_id,
            "name": name,
            "url": url,
            "image_url": image_url,
            "rating": rating,
            "sold": sold,
            "discount_pct": discount_pct,
            "price": price,
            "category": category,
            "score": score
        })

    if not candidates:
        print("ℹ️ ไม่มีสินค้าที่เข้าเงื่อนไข (อาจเพราะยังไม่ครบ 15 วันหรือ CSV ว่าง)")
        return

    # เลือก top และสุ่มเล็กน้อยให้ไม่ซ้ำ pattern
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_pool = candidates[: max(20, posts_per_run * 5)]
    picks = random.sample(top_pool, k=min(posts_per_run, len(top_pool)))

    month_key = get_month_key()
    state["category_monthly"].setdefault(month_key, {})

    print(f"🗓️ {today_th_date_str()}")
    print(f"🧠 Selected {len(picks)} posts this run (pool={len(candidates)})")

    for idx, item in enumerate(picks, start=1):
        tid, msg = build_caption(item["url"], state)

        # เพิ่มรายละเอียดสั้นๆ ให้ดูมนุษย์ขึ้น (ไม่ยาว ไม่เป็นบอท)
        extras = []
        if item["rating"] > 0:
            extras.append(f"⭐ {item['rating']:.1f}")
        if item["discount_pct"] > 0:
            extras.append(f"🔥 ลด {item['discount_pct']:.0f}%")
        if item["sold"] > 0:
            extras.append(f"💰 ขาย {item['sold']:,}+")
        if extras and random.random() < 0.7:
