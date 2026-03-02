import os
import json
import time
import random
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import pandas as pd

# -----------------------------
# ENV / Config
# -----------------------------
STATE_FILE = os.getenv("STATE_FILE", "state.json").strip()

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ = os.getenv("TZ", "Asia/Bangkok").strip()
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))
TOP_POOL = int(os.getenv("TOP_POOL", "200"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

CAPTION_STYLE = os.getenv("CAPTION_STYLE", "short").strip().lower()
HASHTAGS = os.getenv("HASHTAGS", "#BENHomeAndElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #ดีลดี #Shopee").strip()

UA = "fb-autopost/ben-home-electrical"


# -----------------------------
# Helpers: time/state
# -----------------------------
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


# -----------------------------
# Helpers: CSV
# -----------------------------
def fetch_csv(url: str) -> pd.DataFrame:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()

    # รองรับ BOM
    content = r.content
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    from io import StringIO
    df = pd.read_csv(StringIO(text))

    # normalize columns
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df = df.fillna("")
    return df


def pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = set(df.columns)
    for c in candidates:
        if c in cols:
            return c
    return None


def detect_columns(df: pd.DataFrame) -> dict:
    # รองรับชื่อคอลัมน์หลายแบบ
    title = pick_col(df, ["title", "name", "product_name", "item_name"])
    url = pick_col(df, ["url", "link", "product_url", "product_link", "deeplink", "deep_link"])
    price = pick_col(df, ["price", "current_price", "sale_price", "promo_price", "discount_price"])
    original = pick_col(df, ["original_price", "list_price", "normal_price", "old_price"])

    if not title or not url:
        raise RuntimeError(
            "CSV ต้องมีคอลัมน์ชื่อสินค้าและลิงก์ (title/name และ url/link)\n"
            f"พบคอลัมน์: {list(df.columns)}"
        )

    return {"title": title, "url": url, "price": price, "original": original}


def to_number(x):
    try:
        s = str(x).replace(",", "").strip()
        if s == "" or s.lower() == "nan":
            return None
        return float(s)
    except Exception:
        return None


def score_discount(row: dict, cols: dict) -> float:
    """
    ให้คะแนน: ถ้ามี original และ price จะคิด % ลด
    ไม่มีข้อมูลลด -> ให้คะแนนสุ่มเล็กน้อย
    """
    p = to_number(row.get(cols["price"])) if cols["price"] else None
    o = to_number(row.get(cols["original"])) if cols["original"] else None

    if o and p and o > 0 and p > 0 and p <= o:
        return (o - p) / o * 100.0
    return random.random() * 5.0


def make_key(url: str, title: str) -> str:
    url = (url or "").strip()
    title = (title or "").strip()
    return url if url else title


def recently_posted(posted: dict, key: str, now: dt.datetime) -> bool:
    ts = posted.get(key)
    if not ts:
        return False
    try:
        last = dt.datetime.fromisoformat(ts)
        if last.tzinfo is None:
            last = last.replace(tzinfo=ZoneInfo(TZ))
        days = (now - last).total_seconds() / 86400.0
        return days < REPOST_AFTER_DAYS
    except Exception:
        return False


# -----------------------------
# Caption (เอาคำว่า "นายหน้า" ออกแล้ว)
# -----------------------------
def format_money(x: float | None) -> str | None:
    if x is None:
        return None
    if float(x).is_integer():
        return f"฿{int(x):,}"
    return f"฿{x:,.2f}"


def build_caption(title: str, url: str, price: float | None, original: float | None) -> str:
    title = (title or "").strip()
    url = (url or "").strip()

    price_txt = format_money(price)
    orig_txt = format_money(original)

    # คำนวณ % ลดถ้ามี
    disc_line = ""
    if original and price and original > 0 and price > 0 and price <= original:
        disc_pct = int(round((original - price) / original * 100))
        disc_line = f"🔥 {price_txt} (จาก {orig_txt}) ลด ~{disc_pct}%"
    elif price_txt and orig_txt and price_txt != orig_txt:
        disc_line = f"🔥 {price_txt} (จาก {orig_txt})"
    elif price_txt:
        disc_line = f"💸 ราคา {price_txt}"

    note_short = "⚠️ ราคา/โปร/สต๊อกอาจเปลี่ยนแปลง โปรดตรวจสอบที่หน้าสินค้าก่อนสั่งซื้อ"

    if CAPTION_STYLE == "full":
        lines = [
            "🏠⚡ ดีลของใช้ในบ้าน & อุปกรณ์ไฟฟ้า",
            f"✅ {title}" if title else "✅ ดีลแนะนำวันนี้",
            disc_line if disc_line else "💸 เช็คราคาในลิงก์",
            f"👉 {url}" if url else "",
            "",
            note_short,
            HASHTAGS if HASHTAGS else "",
        ]
    else:
        lines = [
            f"🏠⚡ {title}" if title else "🏠⚡ ดีลแนะนำวันนี้",
            disc_line if disc_line else "",
            f"👉 {url}" if url else "",
            note_short,
            HASHTAGS if HASHTAGS else "",
        ]

    lines = [x for x in lines if x]
    return "\n".join(lines).strip()


# -----------------------------
# Facebook Post
# -----------------------------
def fb_post(message: str, link: str) -> dict:
    if not PAGE_ID or not PAGE_ACCESS_TOKEN:
        raise RuntimeError("Missing PAGE_ID or PAGE_ACCESS_TOKEN")

    endpoint = f"https://graph.facebook.com/v20.0/{PAGE_ID}/feed"
    payload = {
        "message": message,
        "link": link,
        "access_token": PAGE_ACCESS_TOKEN,
    }

    r = requests.post(endpoint, data=payload, headers={"User-Agent": UA}, timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.status_code >= 400 or "error" in data:
        raise RuntimeError(f"Facebook API error: {data}")

    return data


# -----------------------------
# Main
# -----------------------------
def main():
    if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
        raise SystemExit("Missing ENV: PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL")

    now = now_local()
    print(f"[INFO] now={now.isoformat()} TZ={TZ}")
    print(f"[INFO] POSTS_PER_RUN={POSTS_PER_RUN} TOP_POOL={TOP_POOL} REPOST_AFTER_DAYS={REPOST_AFTER_DAYS}")
    print(f"[INFO] CAPTION_STYLE={CAPTION_STYLE}")

    state = load_state()
    posted = state.get("posted", {})

    df = fetch_csv(SHOPEE_CSV_URL)
    cols = detect_columns(df)

    # เตรียมแถวเป็น dict
    rows = df.to_dict(orient="records")

    # กรองที่มี title และ url
    clean = []
    for r in rows:
        title = str(r.get(cols["title"], "")).strip()
        url = str(r.get(cols["url"], "")).strip()
        if title and url and url.lower() != "nan":
            clean.append(r)

    if not clean:
        print("[WARN] No valid products in CSV.")
        return

    # ให้คะแนนตามส่วนลด แล้วเลือก top_pool
    for r in clean:
        r["_score"] = score_discount(r, cols)

    clean.sort(key=lambda x: x.get("_score", 0), reverse=True)
    pool = clean[: min(TOP_POOL, len(clean))]
    random.shuffle(pool)

    posted_count = 0

    for r in pool:
        if posted_count >= POSTS_PER_RUN:
            break

        title = str(r.get(cols["title"], "")).strip()
        url = str(r.get(cols["url"], "")).strip()

        key = make_key(url, title)
        if not key:
            continue

        if recently_posted(posted, key, now):
            continue

        price = to_number(r.get(cols["price"])) if cols["price"] else None
        original = to_number(r.get(cols["original"])) if cols["original"] else None

        message = build_caption(title=title, url=url, price=price, original=original)

        print("[INFO] Posting preview:\n" + message + "\n")
        res = fb_post(message, link=url)
        print("[OK] Posted:", res)

        posted[key] = now.isoformat()
        state["posted"] = posted
        save_state(state)

        posted_count += 1
        time.sleep(2)

    print(f"[DONE] posted_count={posted_count}")


if __name__ == "__main__":
    main()
