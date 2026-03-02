# app.py
# Facebook Page autopost (Shopee CSV) - BEN Home & Electrical
#
# Required ENV (GitHub Secrets):
#   PAGE_ID
#   PAGE_ACCESS_TOKEN
#   SHOPEE_CSV_URL
#
# Optional ENV:
#   TZ=Asia/Bangkok
#   POSTS_PER_RUN=1
#   TOP_POOL=200
#   REPOST_AFTER_DAYS=14
#   STATE_FILE=state.json
#   CAPTION_STYLE=short|full
#   HASHTAGS="#BENHomeAndElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #ดีลดี #Shopee"

import os
import io
import json
import random
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import pandas as pd

GRAPH = "https://graph.facebook.com/v19.0"

STATE_FILE = os.getenv("STATE_FILE", "state.json")
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ = os.getenv("TZ", "Asia/Bangkok").strip()
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))
TOP_POOL = int(os.getenv("TOP_POOL", "200"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))
CAPTION_STYLE = os.getenv("CAPTION_STYLE", "short").strip().lower()
HASHTAGS = os.getenv("HASHTAGS", "").strip()


def die(msg: str):
    raise SystemExit(msg)


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted": {}}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_csv(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    # Some CSVs come as bytes or with BOM
    content = r.content
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    df = pd.read_csv(io.StringIO(text))
    # normalize columns
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def pick_columns(df: pd.DataFrame) -> dict:
    # Try common Shopee export column names
    # You can customize mapping here if your CSV column names differ.
    colmap = {
        "name": ["name", "product_name", "title", "สินค้า", "ชื่อสินค้า"],
        "url": ["url", "link", "product_url", "ลิงก์", "ลิงค์", "product link"],
        "price": ["price", "sale_price", "current_price", "ราคา", "ราคาปัจจุบัน"],
        "image": ["image", "image_url", "img", "thumbnail", "รูป", "รูปภาพ"],
        "shop": ["shop", "shop_name", "ร้านค้า", "ชื่อร้าน"],
    }

    def find_col(cands):
        for c in cands:
            if c in df.columns:
                return c
        return None

    out = {k: find_col(v) for k, v in colmap.items()}
    if not out["name"] or not out["url"]:
        die(
            f"CSV ต้องมีคอลัมน์ชื่อสินค้าและลิงก์ (พบ columns: {list(df.columns)})\n"
            "แก้โดยเปลี่ยนหัวคอลัมน์ให้มี name/title และ url/link อย่างน้อย"
        )
    return out


def norm_id(s: str) -> str:
    return str(s).strip()


def is_recently_posted(state: dict, item_id: str, now: dt.datetime) -> bool:
    posted = state.get("posted", {})
    if item_id not in posted:
        return False
    try:
        last = dt.datetime.fromisoformat(posted[item_id])
    except Exception:
        return False
    return (now - last).days < REPOST_AFTER_DAYS


def build_caption(row: dict, cols: dict) -> str:
    name = str(row.get(cols["name"], "")).strip()
    url = str(row.get(cols["url"], "")).strip()
    price = str(row.get(cols["price"], "")).strip() if cols.get("price") else ""
    shop = str(row.get(cols["shop"], "")).strip() if cols.get("shop") else ""

    # Business-style copy: "นายหน้า/รวมดีล" + no guarantee
    lines = []
    lines.append("🔥 รวมดีลของใช้ในบ้าน & อุปกรณ์ไฟฟ้า")
    lines.append("🛒 ลิงก์จาก Shopee (นายหน้า) — ราคาอาจเปลี่ยนตามร้านค้า")
    if shop:
        lines.append(f"🏪 ร้าน: {shop}")
    if price and price != "nan":
        lines.append(f"💰 ราคา: {price}")
    lines.append("")
    lines.append(f"✅ {name}")
    lines.append(f"👉 {url}")

    if CAPTION_STYLE == "full":
        lines.append("")
        lines.append("หมายเหตุ: เพจเป็นผู้รวบรวมดีล/นายหน้า การสั่งซื้อ-จัดส่ง-รับประกันเป็นของร้านค้า/แพลตฟอร์มโดยตรง")

    if HASHTAGS:
        lines.append("")
        lines.append(HASHTAGS)

    return "\n".join(lines).strip()


def post_to_facebook_page(message: str, link: str = "") -> dict:
    # Using /{page_id}/feed with message (and optional link)
    endpoint = f"{GRAPH}/{PAGE_ID}/feed"
    data = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN,
    }
    if link:
        data["link"] = link

    r = requests.post(endpoint, data=data, timeout=30)
    try:
        payload = r.json()
    except Exception:
        payload = {"error": {"message": r.text}}

    if r.status_code >= 400:
        raise RuntimeError(f"Facebook API error {r.status_code}: {payload}")
    return payload


def main():
    if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
        die("Missing ENV: ต้องตั้ง PAGE_ID, PAGE_ACCESS_TOKEN, SHOPEE_CSV_URL ใน GitHub Secrets")

    tz = ZoneInfo(TZ)
    now = dt.datetime.now(tz)

    state = load_state()
    if "posted" not in state:
        state["posted"] = {}

    df = fetch_csv(SHOPEE_CSV_URL)
    cols = pick_columns(df)

    # Build pool
    df2 = df.copy()

    # Optional: sort by price (if numeric) to prefer mid/low
    if cols.get("price") and cols["price"] in df2.columns:
        try:
            df2["_price_num"] = pd.to_numeric(df2[cols["price"]], errors="coerce")
            df2 = df2.sort_values(by="_price_num", ascending=True)
        except Exception:
            pass

    # Limit to TOP_POOL
    df2 = df2.head(TOP_POOL)

    # Shuffle a bit so it doesn't always pick same row
    idxs = list(df2.index)
    random.shuffle(idxs)

    posted_count = 0

    for i in idxs:
        row = df2.loc[i].to_dict()

        # Determine item_id (use url if no id)
        item_id = norm_id(row.get(cols["url"]))
        if not item_id:
            continue

        if is_recently_posted(state, item_id, now):
            continue

        caption = build_caption(row, cols)
        link = str(row.get(cols["url"], "")).strip()

        res = post_to_facebook_page(message=caption, link=link)
        print("Posted:", res)

        state["posted"][item_id] = now.isoformat()
        posted_count += 1

        if posted_count >= POSTS_PER_RUN:
            break

    save_state(state)
    print(f"Done. posted_count={posted_count}")


if __name__ == "__main__":
    main()
