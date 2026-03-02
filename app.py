# app.py
# Facebook Page autopost (Shopee CSV) via GitHub Actions
#
# Required ENV (Secrets):
#   PAGE_ID
#   PAGE_ACCESS_TOKEN
#   SHOPEE_CSV_URL
#
# Optional ENV (Variables or Secrets) - if empty, safe defaults will be used:
#   TZ=Asia/Bangkok
#   RUN_TIMES=12:00,18:00          # เวลาไทยที่ "อนุญาต" ให้โพสต์ (ถ้าไม่ตรงจะ exit)
#   RUN_TOLERANCE_MIN=10           # เผื่อเวลา +/- นาที
#   POSTS_PER_RUN=3
#   TOP_POOL=200
#   REPOST_AFTER_DAYS=14
#   STATE_FILE=state.json
#   CAPTION_STYLE=short|full
#   HASHTAGS=#ดีลคุ้ม #Shopee #ลดราคา

import os
import io
import json
import math
import random
import time
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import pandas as pd


# -------------------------
# Safe ENV helpers (กันค่าว่าง)
# -------------------------
def getenv_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    return v if v != "" else default


def getenv_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    if v == "":
        return default
    try:
        return int(v)
    except Exception:
        return default


# -------------------------
# Config from ENV
# -------------------------
STATE_FILE = getenv_str("STATE_FILE", "state.json")

PAGE_ID = getenv_str("PAGE_ID", "")
PAGE_ACCESS_TOKEN = getenv_str("PAGE_ACCESS_TOKEN", "")
SHOPEE_CSV_URL = getenv_str("SHOPEE_CSV_URL", "")

TZ = getenv_str("TZ", "Asia/Bangkok")
RUN_TIMES = getenv_str("RUN_TIMES", "12:00")  # comma-separated HH:MM
RUN_TOLERANCE_MIN = getenv_int("RUN_TOLERANCE_MIN", 10)

REPOST_AFTER_DAYS = getenv_int("REPOST_AFTER_DAYS", 14)
POSTS_PER_RUN = getenv_int("POSTS_PER_RUN", 3)
TOP_POOL = getenv_int("TOP_POOL", 200)

CAPTION_STYLE = getenv_str("CAPTION_STYLE", "short").lower()
HASHTAGS = getenv_str("HASHTAGS", "#ดีลคุ้ม #Shopee #ลดราคา")


# -------------------------
# Helpers: state
# -------------------------
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("posted", {})
                    return data
        except Exception:
            pass
    return {"posted": {}}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def now_local() -> dt.datetime:
    return dt.datetime.now(tz=ZoneInfo(TZ))


def is_time_allowed() -> bool:
    """
    Allow running only around configured RUN_TIMES (local TZ).
    Set RUN_TIMES="" to disable this guard.
    """
    if not RUN_TIMES:
        return True

    n = now_local()
    for t in [x.strip() for x in RUN_TIMES.split(",") if x.strip()]:
        try:
            hh, mm = t.split(":")
            target = n.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            delta_min = abs((n - target).total_seconds()) / 60.0
            if delta_min <= RUN_TOLERANCE_MIN:
                return True
        except Exception:
            continue
    return False


# -------------------------
# Helpers: CSV normalize
# -------------------------
def pick_first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in cols_lower:
            return cols_lower[key]
    return None


def load_products() -> pd.DataFrame:
    if not SHOPEE_CSV_URL:
        raise RuntimeError("SHOPEE_CSV_URL is empty (ต้องตั้งค่า Shopee CSV URL ใน Secrets)")

    print("⬇️ Downloading Shopee CSV...")
    r = requests.get(SHOPEE_CSV_URL, timeout=60)
    r.raise_for_status()

    content = r.content
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    # บางไฟล์คั่นด้วย ; ลองเดา delimiter ถ้าจำเป็น
    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception:
        df = pd.read_csv(io.StringIO(text), sep=";")

    print(f"✅ CSV loaded: {len(df)} rows")
    print("📄 Columns:", list(df.columns))

    # เดาชื่อคอลัมน์ให้ทนทุกแบบ
    name_col = pick_first_existing_column(
        df,
        ["product_name", "product name", "name", "item_name", "item name", "title", "product_title", "product title"],
    )
    link_col = pick_first_existing_column(
        df,
        ["product_link", "product link", "link", "url", "affiliate_link", "affiliate link", "deeplink", "deep_link"],
    )
    price_col = pick_first_existing_column(df, ["price", "sale_price", "sale price", "final_price", "final price"])
    rating_col = pick_first_existing_column(df, ["rating", "score", "product_rating", "product rating"])

    if not name_col or not link_col:
        raise RuntimeError(
            "❌ ไม่เจอคอลัมน์ชื่อสินค้า/ลิงก์ใน CSV\n"
            f"คอลัมน์ที่มี: {list(df.columns)}\n"
            "ต้องมีอย่างน้อย: product_name (หรือ name/title) และ product_link (หรือ link/url)"
        )

    out = pd.DataFrame()
    out["product_name"] = df[name_col].astype(str).fillna("").str.strip()
    out["product_link"] = df[link_col].astype(str).fillna("").str.strip()

    if price_col:
        out["price"] = df[price_col]
    else:
        out["price"] = None

    if rating_col:
        out["rating"] = df[rating_col]
    else:
        out["rating"] = None

    out = out.dropna(subset=["product_name", "product_link"])
    out = out[(out["product_name"] != "") & (out["product_link"] != "")]
    out = out.drop_duplicates(subset=["product_link"]).reset_index(drop=True)
    return out


def safe_float(x):
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


# -------------------------
# Facebook Graph API
# -------------------------
def fb_post_link(message: str, link: str) -> dict:
    if not PAGE_ID or not PAGE_ACCESS_TOKEN:
        raise RuntimeError("PAGE_ID / PAGE_ACCESS_TOKEN ว่าง (เช็ค Secrets)")

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {
        "message": message,
        "link": link,
        "access_token": PAGE_ACCESS_TOKEN,
    }

    resp = requests.post(url, data=payload, timeout=60)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}

    print("STATUS:", resp.status_code)
    print("RESPONSE:", data)

    if resp.status_code >= 400 or ("error" in data):
        raise Exception(f"❌ Facebook post failed: {data}")

    return data


# -------------------------
# Caption builder (ไม่มี 'วิธีสั่งซื้อ')
# -------------------------
def build_caption(row: pd.Series) -> str:
    name = str(row.get("product_name", "")).strip()
    link = str(row.get("product_link", "")).strip()
    price = safe_float(row.get("price"))
    rating = safe_float(row.get("rating"))

    lines = []
    lines.append("🛒 ของมันต้องมีช่วงนี้")
    lines.append(f"✅ {name}")

    meta = []
    if price is not None and not (isinstance(price, float) and math.isnan(price)):
        try:
            meta.append(f"💰 {int(price):,} บาท")
        except Exception:
            meta.append(f"💰 {price}")
    if rating is not None and not (isinstance(rating, float) and math.isnan(rating)):
        meta.append(f"⭐ {rating:.1f}")

    if meta:
        lines.append(" / ".join(meta))

    lines.append("กดดูรายละเอียด 👇")
    lines.append(link)

    if CAPTION_STYLE == "full":
        lines.append("")

    if HASHTAGS:
        lines.append(HASHTAGS)

    caption = "\n".join([l for l in lines if l is not None])
    return caption[:1800]


# -------------------------
# Main
# -------------------------
def main():
    print("TZ =", TZ)
    print("Now(local) =", now_local().isoformat())
    print("RUN_TIMES =", RUN_TIMES, "tolerance(min) =", RUN_TOLERANCE_MIN)
    print("POSTS_PER_RUN =", POSTS_PER_RUN, "TOP_POOL =", TOP_POOL, "REPOST_AFTER_DAYS =", REPOST_AFTER_DAYS)
    print("CAPTION_STYLE =", CAPTION_STYLE, "HASHTAGS =", HASHTAGS)

    if not is_time_allowed():
        print("⏭️ Not in allowed time window. Exit.")
        return

    state = load_state()
    posted = state.get("posted", {})

    products = load_products()

    cutoff = now_local() - dt.timedelta(days=REPOST_AFTER_DAYS)

    def is_eligible(link: str) -> bool:
        ts = posted.get(link)
        if not ts:
            return True
        try:
            last = dt.datetime.fromisoformat(ts)
            if last.tzinfo is None:
                last = last.replace(tzinfo=ZoneInfo(TZ))
            return last <= cutoff
        except Exception:
            return True

    products["eligible"] = products["product_link"].apply(is_eligible)
    pool = products[products["eligible"]].copy()

    if len(pool) == 0:
        print("😴 ไม่มีสินค้าที่เข้าเงื่อนไข (eligible) แล้ว")
        return

    if len(pool) > TOP_POOL:
        pool = pool.sample(n=TOP_POOL, random_state=random.randint(1, 999999)).reset_index(drop=True)
    else:
        pool = pool.sample(frac=1.0, random_state=random.randint(1, 999999)).reset_index(drop=True)

    to_post = min(POSTS_PER_RUN, len(pool))
    print(f"🚀 Will post {to_post} item(s)")

    for i in range(to_post):
        row = pool.iloc[i]
        caption = build_caption(row)
        link = row["product_link"]

        print(f"📌 Posting ({i+1}/{to_post}) ...")
        fb_post_link(caption, link)

        posted[link] = now_local().isoformat()
        time.sleep(3)

    state["posted"] = posted
    save_state(state)
    print("✅ Done.")


if __name__ == "__main__":
    main()
