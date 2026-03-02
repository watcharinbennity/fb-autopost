import os
import json
import time
import random
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import pandas as pd


STATE_FILE = os.getenv("STATE_FILE", "state.json")

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ = os.getenv("TZ", "Asia/Bangkok")
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))
TOP_POOL = int(os.getenv("TOP_POOL", "200"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

CAPTION_STYLE = os.getenv("CAPTION_STYLE", "short").strip().lower()
HASHTAGS = os.getenv("HASHTAGS", "").strip()

UA = "fb-autopost/1.0 (+github-actions)"


def now_local() -> dt.datetime:
    return dt.datetime.now(tz=ZoneInfo(TZ))


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "posted" not in data or not isinstance(data["posted"], dict):
            data["posted"] = {}
        return data
    except Exception:
        return {"posted": {}}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_csv(url: str) -> pd.DataFrame:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()

    # pandas อ่านจาก bytes ได้โดยตรง
    from io import BytesIO
    bio = BytesIO(r.content)

    # รองรับ csv ที่อาจมี bom
    try:
        df = pd.read_csv(bio, encoding="utf-8-sig")
    except Exception:
        bio.seek(0)
        df = pd.read_csv(bio)

    # ทำชื่อคอลัมน์ให้เป็นมาตรฐาน (lower, strip)
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def pick_columns(df: pd.DataFrame) -> dict:
    """
    พยายาม map คอลัมน์จาก CSV ให้เข้ากับข้อมูลที่ต้องใช้:
    - title/name
    - price
    - promo_price/sale_price
    - url/link
    - image
    """
    def find_col(candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    col_title = find_col(["title", "name", "product", "product_name", "สินค้า", "ชื่อสินค้า"])
    col_price = find_col(["price", "original_price", "ราคาปกติ"])
    col_sale = find_col(["sale_price", "promo_price", "discount_price", "ราคาขาย", "ราคาโปร"])
    col_url = find_col(["url", "link", "product_url", "shopee_url"])
    col_img = find_col(["image", "image_url", "img", "thumbnail", "thumb"])

    return {
        "title": col_title,
        "price": col_price,
        "sale": col_sale,
        "url": col_url,
        "img": col_img,
    }


def to_number(x):
    try:
        if pd.isna(x):
            return None
        s = str(x).replace(",", "").strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def score_row(row, cols: dict) -> float:
    """
    ให้คะแนนเพื่อสุ่มจาก TOP_POOL:
    - ถ้ามีราคาปกติ + ราคาโปร จะให้คะแนนตาม % ลด
    - ถ้าไม่มี ก็สุ่มคะแนนเล็กน้อย
    """
    p = to_number(row.get(cols["price"])) if cols["price"] else None
    s = to_number(row.get(cols["sale"])) if cols["sale"] else None

    if p and s and p > 0 and s > 0 and s <= p:
        disc = (p - s) / p  # 0..1
        return disc * 100.0
    return random.random() * 5.0


def item_key(row, cols: dict) -> str:
    """
    ใช้ key กันโพสต์ซ้ำ:
    - ถ้ามี url ใช้ url
    - ถ้าไม่มี ใช้ title
    """
    u = str(row.get(cols["url"])).strip() if cols["url"] else ""
    t = str(row.get(cols["title"])).strip() if cols["title"] else ""
    return u if u and u.lower() != "nan" else t


def is_recently_posted(state: dict, key: str, now: dt.datetime) -> bool:
    posted = state.get("posted", {})
    ts = posted.get(key)
    if not ts:
        return False
    try:
        last = dt.datetime.fromisoformat(ts)
        if last.tzinfo is None:
            last = last.replace(tzinfo=ZoneInfo(TZ))
        delta_days = (now - last).total_seconds() / 86400.0
        return delta_days < REPOST_AFTER_DAYS
    except Exception:
        return False


def format_caption(row, cols: dict) -> str:
    title = str(row.get(cols["title"])).strip() if cols["title"] else "ดีลแนะนำ"
    url = str(row.get(cols["url"])).strip() if cols["url"] else ""
    p = to_number(row.get(cols["price"])) if cols["price"] else None
    s = to_number(row.get(cols["sale"])) if cols["sale"] else None

    # ทำราคาให้สวย
    def fmt_price(x):
        if x is None:
            return None
        if x.is_integer():
            return f"฿{int(x):,}"
        return f"฿{x:,.2f}"

    p_txt = fmt_price(p)
    s_txt = fmt_price(s)

    # ข้อความแบบ “นายหน้า” ไม่รับประกัน/ให้เช็กกับร้าน
    note = (
        "📌 เราเป็นผู้รวบรวมดีล/ลิงก์จากร้านค้า (นายหน้า) ไม่ได้เป็นผู้ผลิต/ร้านโดยตรง\n"
        "✅ ราคา/สต๊อก/เงื่อนไข อาจเปลี่ยนได้ โปรดตรวจสอบที่หน้าร้านก่อนสั่งซื้อ\n"
        "💬 สอบถามแนะนำสินค้าได้ครับ"
    )

    if CAPTION_STYLE == "full":
        parts = [f"🏠⚡ {title}"]
        if s_txt and p_txt and p and s and p > 0 and s > 0 and s <= p:
            disc_pct = int(round((p - s) / p * 100))
            parts.append(f"🔥 โปร {s_txt} (จาก {p_txt}) ลด ~{disc_pct}%")
        elif s_txt:
            parts.append(f"🔥 ราคาโปร {s_txt}")
        elif p_txt:
            parts.append(f"ราคา {p_txt}")

        if url and url.lower() != "nan":
            parts.append(f"👉 ดูดีล/สั่งซื้อ: {url}")

        parts.append("")
        parts.append(note)
        if HASHTAGS:
            parts.append(HASHTAGS)

        return "\n".join(parts).strip()

    # short (ค่า default)
    line1 = f"🏠⚡ {title}"
    line2 = ""
    if s_txt and p_txt and p and s and p > 0 and s > 0 and s <= p:
        disc_pct = int(round((p - s) / p * 100))
        line2 = f"🔥 {s_txt} (จาก {p_txt}) ลด ~{disc_pct}%"
    elif s_txt:
        line2 = f"🔥 ราคาโปร {s_txt}"
    elif p_txt:
        line2 = f"ราคา {p_txt}"

    # short จะไม่ยาว แต่ยังใส่หมายเหตุสั้น ๆ
    short_note = "📌 นายหน้า/รวมดีล ตรวจสอบราคา-สต๊อกที่หน้าร้าน | ทักสอบถามได้"
    lines = [line1]
    if line2:
        lines.append(line2)
    if url and url.lower() != "nan":
        lines.append(f"👉 {url}")
    lines.append(short_note)
    if HASHTAGS:
        lines.append(HASHTAGS)

    return "\n".join(lines).strip()


def post_to_facebook_page(message: str, link: str | None = None) -> str:
    """
    โพสต์ลงเพจผ่าน Graph API: /{page_id}/feed
    คืนค่า post_id
    """
    if not PAGE_ID or not PAGE_ACCESS_TOKEN:
        raise RuntimeError("Missing PAGE_ID or PAGE_ACCESS_TOKEN")

    url = f"https://graph.facebook.com/v20.0/{PAGE_ID}/feed"
    payload = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN,
    }
    # ถ้ามี link ในข้อความอยู่แล้ว ใส่ซ้ำก็ได้ แต่ให้ใส่แยกจะช่วย preview
    if link:
        payload["link"] = link

    r = requests.post(url, data=payload, headers={"User-Agent": UA}, timeout=30)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.status_code >= 400 or "error" in data:
        raise RuntimeError(f"Facebook API error: {data}")

    post_id = data.get("id")
    if not post_id:
        raise RuntimeError(f"Facebook API response missing id: {data}")
    return post_id


def main():
    start = now_local()
    print(f"[INFO] start: {start.isoformat()} TZ={TZ}")
    print(f"[INFO] POSTS_PER_RUN={POSTS_PER_RUN} TOP_POOL={TOP_POOL} REPOST_AFTER_DAYS={REPOST_AFTER_DAYS}")
    print(f"[INFO] CAPTION_STYLE={CAPTION_STYLE}")

    if not SHOPEE_CSV_URL:
        raise RuntimeError("Missing SHOPEE_CSV_URL")

    state = load_state()
    df = fetch_csv(SHOPEE_CSV_URL)

    if df.empty:
        print("[WARN] CSV empty. exit.")
        return

    cols = pick_columns(df)
    if not cols["title"] or not cols["url"]:
        print(f"[WARN] CSV columns found: {list(df.columns)}")
        raise RuntimeError("CSV must have at least a title/name column and a url/link column.")

    # score + sort
    df["_score"] = df.apply(lambda r: score_row(r, cols), axis=1)
    df = df.sort_values("_score", ascending=False)

    pool = df.head(max(1, TOP_POOL)).copy()

    # สุ่มใน pool เพื่อไม่ให้ซ้ำเดิมเกินไป
    pool = pool.sample(frac=1.0, random_state=int(time.time()) % 2**32).reset_index(drop=True)

    posted_count = 0
    for _, row in pool.iterrows():
        if posted_count >= POSTS_PER_RUN:
            break

        key = item_key(row, cols)
        if not key or str(key).strip() == "" or str(key).lower() == "nan":
            continue

        now = now_local()
        if is_recently_posted(state, key, now):
            continue

        caption = format_caption(row, cols)
        link = str(row.get(cols["url"])).strip()

        print(f"[INFO] posting: key={key[:80]}")
        post_id = post_to_facebook_page(caption, link=link)

        state["posted"][key] = now.isoformat()
        save_state(state)

        print(f"[OK] posted: {post_id}")
        posted_count += 1
        time.sleep(2)

    print(f"[DONE] posted_count={posted_count}")


if __name__ == "__main__":
    main()
