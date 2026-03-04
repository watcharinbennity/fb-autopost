import os
import re
import io
import json
import time
import random
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -----------------------
# Config (ENV)
# -----------------------
STATE_FILE = os.getenv("STATE_FILE", "state.json")

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ = os.getenv("TZ", "Asia/Bangkok")

POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "2"))
TOP_POOL = int(os.getenv("TOP_POOL", "200"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

BRAND = os.getenv("BRAND", "BEN Home & Electrical")
CAPTION_STYLE = os.getenv("CAPTION_STYLE", "short").strip().lower()
HASHTAGS = os.getenv("HASHTAGS", "#BENHomeAndElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #ดีลดี #Shopee #ลดราคา")

ALLOW_KEYWORDS = os.getenv("ALLOW_KEYWORDS", "").strip()
BLOCK_KEYWORDS = os.getenv("BLOCK_KEYWORDS", "").strip()

# ต้องมีรูปเท่านั้น
REQUIRE_IMAGE = os.getenv("REQUIRE_IMAGE", "1").strip() != "0"

# Auto Pro filters
MIN_RATING = float(os.getenv("MIN_RATING", "4.6"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "10"))  # %
MIN_SOLD = int(os.getenv("MIN_SOLD", "50"))
REQUIRE_COUPON = os.getenv("REQUIRE_COUPON", "0").strip() == "1"  # 1=ต้องมีคูปอง/โค้ดเท่านั้น

# Graph API version (ต้องเป็น v25.0)
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

# -----------------------
# Helpers
# -----------------------
def now_th() -> dt.datetime:
    return dt.datetime.now(ZoneInfo(TZ))

def die(msg: str, code: int = 1):
    print("FATAL:", msg)
    raise SystemExit(code)

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted_ids": {}, "posted_posts": [], "last_run_iso": ""}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted_ids": {}, "posted_posts": [], "last_run_iso": ""}

def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

SESSION = make_session()

def normalize_text(x) -> str:
    if x is None:
        return ""
    s = str(x)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def to_float(x) -> float:
    s = normalize_text(x)
    if not s:
        return 0.0
    s = s.replace(",", "")
    m = re.search(r"(\d+(\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0

def to_int(x) -> int:
    s = normalize_text(x)
    if not s:
        return 0
    s = s.replace(",", "")
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else 0

def compile_pat(expr: str):
    if not expr:
        return None
    return re.compile(expr, flags=re.IGNORECASE)

ALLOW_PAT = compile_pat(ALLOW_KEYWORDS)
BLOCK_PAT = compile_pat(BLOCK_KEYWORDS)

def is_allowed(title: str, category: str) -> bool:
    text = f"{title} {category}".strip()
    if BLOCK_PAT and BLOCK_PAT.search(text):
        return False
    if ALLOW_PAT:
        return bool(ALLOW_PAT.search(text))
    return True

def pick_columns(df: pd.DataFrame) -> dict:
    cols = {c.lower().strip(): c for c in df.columns}

    def find(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    return {
        "title": find("title", "name", "product_name"),
        "price": find("price", "sale_price", "discount_price"),
        "img": find("image", "image_url", "image_link", "img", "thumbnail", "images"),
        "url": find("url", "product_url", "link", "product_link"),
        "category": find("category", "cat", "category_name"),
        "rating": find("rating", "score", "stars"),
        "sold": find("sold", "sales", "total_sold", "sold_count"),
        "discount": find("discount", "discount_pct", "off", "discount_percent"),
        "coupon": find("coupon", "voucher", "promo_code", "discount_code", "code"),
    }

def extract_first_image(img_field: str) -> str:
    s = normalize_text(img_field)
    if not s:
        return ""
    parts = re.split(r"[;,|]\s*", s)
    for p in parts:
        p = p.strip()
        if p.startswith("http"):
            return p
    return ""

def fetch_csv(url: str) -> pd.DataFrame:
    print("Fetching CSV...")
    r = SESSION.get(url, timeout=25)
    print("CSV status:", r.status_code)
    if r.status_code >= 400:
        die(f"CSV download failed status={r.status_code} (check SHOPEE_CSV_URL)")
    content = r.content
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")
    df = pd.read_csv(io.StringIO(text))
    if df.empty:
        die("CSV is empty")
    return df

def build_caption(it: dict) -> str:
    title = it["title"]
    price = it["price"]
    url = it["url"]
    rating = it.get("rating", 0.0)
    sold = it.get("sold", 0)
    discount = it.get("discount", 0.0)
    coupon = it.get("coupon", "")

    if CAPTION_STYLE == "full":
        lines = [
            f"🏠⚡ {BRAND}",
            f"📌 {title}",
            f"⭐ {rating:.1f} | ขายแล้ว {sold}",
        ]
        if discount > 0:
            lines.append(f"🔥 ลด {discount:.0f}%")
        if coupon:
            lines.append(f"🎟 โค้ด/คูปอง: {coupon}")
        if price:
            lines.append(f"💰 ราคา: {price}")
        if url:
            lines.append(f"🔗 สั่งซื้อ: {url}")
        lines.append(HASHTAGS)
        return "\n".join([x for x in lines if x])

    parts = [f"📌 {title}"]
    meta = []
    if discount > 0:
        meta.append(f"ลด {discount:.0f}%")
    if rating > 0:
        meta.append(f"⭐{rating:.1f}")
    if sold > 0:
        meta.append(f"ขายแล้ว {sold}")
    if meta:
        parts.append(" | ".join(meta))
    if coupon:
        parts.append(f"🎟 {coupon}")
    if price:
        parts.append(f"💰 {price}")
    if url:
        parts.append(f"🔗 {url}")
    parts.append(HASHTAGS)
    return "\n".join([p for p in parts if p])

def fb_post_photo(page_id: str, access_token: str, image_url: str, caption: str) -> dict:
    # v25.0
    endpoint = f"{GRAPH_BASE}/{page_id}/photos"
    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": access_token,
        "published": "true",
    }
    r = SESSION.post(endpoint, data=payload, timeout=25)
    data = r.json() if "application/json" in r.headers.get("content-type", "") else {"raw": r.text}
    if r.status_code >= 400 or ("error" in data):
        raise RuntimeError(f"FB post failed: status={r.status_code} resp={data}")
    return data

def fb_get_permalink(object_id: str, access_token: str) -> str:
    # v25.0
    endpoint = f"{GRAPH_BASE}/{object_id}"
    params = {
        "fields": "permalink_url",
        "access_token": access_token,
    }
    r = SESSION.get(endpoint, params=params, timeout=25)
    data = r.json() if "application/json" in r.headers.get("content-type", "") else {}
    if r.status_code >= 400 or ("error" in data):
        return ""
    return data.get("permalink_url", "") or ""

def auto_pro_pass(it: dict) -> bool:
    if it.get("rating", 0.0) < MIN_RATING:
        return False
    if it.get("sold", 0) < MIN_SOLD:
        return False
    if it.get("discount", 0.0) < MIN_DISCOUNT_PCT:
        return False
    if REQUIRE_COUPON and not it.get("coupon", "").strip():
        return False
    return True

def main():
    print("== fb-autopost AUTO PRO ==")
    t = now_th()
    print("time(th):", t.isoformat())
    print("graph_version:", GRAPH_VERSION)

    if not PAGE_ID or not PAGE_ACCESS_TOKEN or not SHOPEE_CSV_URL:
        die("Missing ENV: PAGE_ID / PAGE_ACCESS_TOKEN / SHOPEE_CSV_URL")

    state = load_state()
    posted = state.get("posted_ids", {})
    posted_posts = state.get("posted_posts", [])
    cutoff = t - dt.timedelta(days=REPOST_AFTER_DAYS)

    df = fetch_csv(SHOPEE_CSV_URL)
    col = pick_columns(df)

    if not col["title"]:
        die("CSV missing title/name column")
    if REQUIRE_IMAGE and not col["img"]:
        die("CSV missing image column (image_url/image_link/images) but REQUIRE_IMAGE=1")

    df2 = df.head(TOP_POOL).copy()

    items = []
    for _, row in df2.iterrows():
        title = normalize_text(row[col["title"]]) if col["title"] else ""
        price = normalize_text(row[col["price"]]) if col["price"] else ""
        url = normalize_text(row[col["url"]]) if col["url"] else ""
        category = normalize_text(row[col["category"]]) if col["category"] else ""
        img = extract_first_image(row[col["img"]]) if col["img"] else ""

        rating = to_float(row[col["rating"]]) if col["rating"] else 0.0
        sold = to_int(row[col["sold"]]) if col["sold"] else 0
        discount = to_float(row[col["discount"]]) if col["discount"] else 0.0
        coupon = normalize_text(row[col["coupon"]]) if col["coupon"] else ""

        if not title:
            continue
        if REQUIRE_IMAGE and not img:
            continue
        if not is_allowed(title, category):
            continue

        item_id = url if url else title

        last_iso = posted.get(item_id)
        if last_iso:
            try:
                last_dt = dt.datetime.fromisoformat(last_iso)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=ZoneInfo(TZ))
            except Exception:
                last_dt = None
            if last_dt and last_dt > cutoff:
                continue

        it = {
            "id": item_id,
            "title": title,
            "price": price,
            "url": url,
            "category": category,
            "img": img,
            "rating": rating,
            "sold": sold,
            "discount": discount,
            "coupon": coupon,
        }

        if not auto_pro_pass(it):
            continue

        items.append(it)

    if not items:
        print("No eligible items (after Auto Pro filters). Nothing to post.")
        state["last_run_iso"] = t.isoformat()
        save_state(state)
        return

    random.shuffle(items)
    to_post = items[:POSTS_PER_RUN]

    success = 0
    for it in to_post:
        caption = build_caption(it)
        print("\n--- Posting ---")
        print("title:", it["title"])
        print("rating/sold/discount/coupon:", it["rating"], it["sold"], it["discount"], it["coupon"])
        print("img:", it["img"])
        try:
            resp = fb_post_photo(PAGE_ID, PAGE_ACCESS_TOKEN, it["img"], caption)
            obj_id = resp.get("id", "")
            permalink = fb_get_permalink(obj_id, PAGE_ACCESS_TOKEN) if obj_id else ""
            print("posted_resp:", resp)
            print("permalink:", permalink)

            posted[it["id"]] = t.isoformat()
            posted_posts.append({
                "time": t.isoformat(),
                "item_id": it["id"],
                "object_id": obj_id,
                "permalink": permalink,
                "title": it["title"],
            })
            success += 1
        except Exception as e:
            print("POST ERROR:", str(e))

        time.sleep(2)

    state["posted_ids"] = posted
    state["posted_posts"] = posted_posts[-200:]
    state["last_run_iso"] = t.isoformat()
    save_state(state)

    print(f"\nDone. success={success}/{len(to_post)}")

if __name__ == "__main__":
    main()
