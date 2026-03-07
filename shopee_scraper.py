import json
import os
import time
import random
import requests
from urllib.parse import quote

PRODUCT_FILE = "products.json"
SITE = os.getenv("SHOPEE_SITE", "shopee.co.th")
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "").strip()

KEYWORDS = [
    ("ไฟโซล่า", "solar"),
    ("ปลั๊กไฟ", "plug"),
    ("เครื่องมือช่าง", "tools"),
    ("สว่านไร้สาย", "tools"),
    ("หลอดไฟ LED", "led"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": f"https://{SITE}/",
}


def attach_affiliate_id(link: str) -> str:
    if not AFFILIATE_ID:
        return link
    sep = "&" if "?" in link else "?"
    return f"{link}{sep}affiliate_id={AFFILIATE_ID}"


def load_products() -> list:
    try:
        with open(PRODUCT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_products(products: list) -> None:
    with open(PRODUCT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


def dedupe_products(products: list) -> list:
    seen = set()
    out = []
    for p in products:
        link = p.get("link", "").strip()
        if not link or link in seen:
            continue
        seen.add(link)
        out.append(p)
    return out


def parse_item(item: dict, category: str) -> dict | None:
    basic = item.get("item_basic") or item

    name = (basic.get("name") or "").strip()
    shopid = basic.get("shopid")
    itemid = basic.get("itemid")

    if not name or shopid is None or itemid is None:
        return None

    rating = 0.0
    sold = 0

    item_rating = basic.get("item_rating")
    if isinstance(item_rating, dict):
        rating = float(item_rating.get("rating_star") or 0)

    sold = int(
        basic.get("historical_sold")
        or basic.get("sold")
        or 0
    )

    price_raw = basic.get("price_min") or basic.get("price") or 0
    try:
        price = round(float(price_raw) / 100000, 2) if price_raw else 0
    except Exception:
        price = 0

    link = f"https://{SITE}/product/{shopid}/{itemid}"
    link = attach_affiliate_id(link)

    return {
        "name": name,
        "category": category,
        "rating": rating,
        "sold": sold,
        "price": price,
        "link": link,
    }


def search_shopee(keyword: str, category: str, limit: int = 20) -> list:
    url = (
        f"https://{SITE}/api/v4/search/search_items"
        f"?by=sales&keyword={quote(keyword)}&limit={limit}&newest=0&order=desc"
        f"&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"
    )

    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    data = r.json()
    items = data.get("items") or []

    products = []
    for item in items:
        parsed = parse_item(item, category)
        if parsed:
            products.append(parsed)

    return products


def update_products() -> list:
    all_products = []

    for keyword, category in KEYWORDS:
        try:
            items = search_shopee(keyword, category, limit=20)
            all_products.extend(items)
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            print(f"SCRAPER ERROR [{keyword}]: {e}", flush=True)

    old_products = load_products()

    # merge เก่ากับใหม่ เผื่อรอบนี้ scrape ได้น้อย
    merged = all_products + old_products
    merged = dedupe_products(merged)

    # เน้นตัวที่ rating/sold สูง
    merged.sort(
        key=lambda x: (
            float(x.get("sold", 0)),
            float(x.get("rating", 0)),
        ),
        reverse=True
    )

    save_products(merged)
    print(f"UPDATED PRODUCTS: {len(merged)}", flush=True)
    return merged


if __name__ == "__main__":
    update_products()
