# app.py
# Facebook Page autopost (Shopee CSV) via GitHub Actions
# Required ENV (GitHub Secrets):
#   PAGE_ID
#   PAGE_ACCESS_TOKEN
#   SHOPEE_CSV_URL
#
# Optional ENV:
#   TZ=Asia/Bangkok
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

STATE_FILE = os.getenv("STATE_FILE", "state.json")

# -------------------------
# Config from ENV
# -------------------------
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ = os.getenv("TZ", "Asia/Bangkok").strip()

REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14") or "14")
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "3") or "3")
TOP_POOL = int(os.getenv("TOP_POOL", "200") or "200")

CAPTION_STYLE = os.getenv("CAPTION_STYLE", "short").strip().lower()
HASHTAGS = os.getenv("HASHTAGS", "#ดีลคุ้ม #Shopee #ลดราคา").strip()


# -------------------------
# Helpers: state
# -------------------------
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"posted": {}}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def now_local() -> dt.datetime:
    return dt.datetime.now(tz=ZoneInfo(TZ))


# -------------------------
# Helpers: CSV normalize
# -------------------------
def pick_first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None


def load_products() -> pd.DataFrame:
    if not SHOPEE_CSV_URL:
        raise RuntimeError("SHOPEE_CSV_URL is empty")

    print("⬇️ Downloading Shopee CSV...")
    r = requests.get(SHOPEE_CSV_URL, timeout=60)
    r.raise_for_status()

    content = r.content
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    df = pd.read_csv(io.StringIO(text))
    print(f"✅ CSV loaded: {len(df)} rows")

    name_col = pick_first_existing_column(
        df,
        ["product_name", "product name", "name", "item_name", "item name", "product_title", "product title", "title"],
    )
    link_col = pick_first_existing_column(
        df,
        ["product_link", "product link", "link", "url", "affiliate_link", "affiliate link", "deeplink", "deep_link"],
    )
    price_col = pick_first_existing_column(df, ["price", "sale_price", "sale price", "final_price", "final price"])
    rating_col = pick_first_existing_column(df, ["rating", "score", "product_rating", "product rating"])

    if not name_col or not link_col:
        raise RuntimeError(
            "ไม่เจอคอลัมน์ชื่อสินค้า/ลิงก์ใน CSV\n"
            f"คอลัมน์ที่มี: {list(df.columns)}\n"
            "ต้องมีอย่างน้อย: product_name (หรือ name/title) และ product_link (หรือ link/url)"
        )

    out = pd.DataFrame()
    out["product_name"] = df[name_col].astype(str).fillna("").str.strip()
    out["product_link"] = df[link_col].astype(str).fillna("").str.strip()

    out["price"] = df[price_col] if price_col else None
    out["rating"] = df[rating_col] if rating_col else None

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
        raise RuntimeError("PAGE_ID / PAGE_ACCESS_TOKEN is empty")

    url = f"https://graph.facebook.com/v25.0/{PAGE_ID}/feed"
    payload = {"message": message, "link": link, "access_token": PAGE_ACCESS_TOKEN}

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

    lines = ["🛒 ของมันต้องมีช่วงนี้", f"✅ {name}"]

    meta = []
    if price is not None and not math.isnan(price):
        meta.append(f"💰 {int(price):,} บาท")
    if rating is not None and not math.isnan(rating):
        meta.append(f"⭐ {rating:.1f}")
    if meta:
        lines.append(" / ".join(meta))

    lines.append("กดดูรายละเอียด 👇")
    lines.append(link)
    if HASHTAGS:
        lines.append(HASHTAGS)

    caption = "\n".join([l for l in lines if l])
    return caption[:1800]


# -------------------------
# Main
# -------------------------
def main():
    print("TZ =", TZ)
    print("Now =", now_local().isoformat())

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
        print("😴 ไม่มีสินค้าที่เข้าเงื่อนไขแล้ว")
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
