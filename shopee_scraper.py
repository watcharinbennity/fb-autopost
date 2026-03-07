import json
import requests

PRODUCT_FILE = "products.json"

KEYWORDS = [
    ("ไฟโซล่า", "solar"),
    ("ปลั๊กไฟ", "plug"),
    ("เครื่องมือช่าง", "tools"),
    ("หลอดไฟ LED", "led")
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def load_products():
    try:
        with open(PRODUCT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_products(data):
    with open(PRODUCT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def search(keyword, category):
    url = f"https://shopee.co.th/api/v4/search/search_items?keyword={keyword}&limit=10"

    r = requests.get(url, headers=HEADERS, timeout=20)

    if r.status_code != 200:
        raise Exception("blocked")

    data = r.json()
    products = []

    for item in data.get("items", []):
        i = item.get("item_basic", {})

        shopid = i.get("shopid")
        itemid = i.get("itemid")
        name = i.get("name")

        if not shopid or not itemid or not name:
            continue

        products.append({
            "name": name,
            "category": category,
            "rating": 4.5,
            "sold": 100,
            "link": f"https://shopee.co.th/product/{shopid}/{itemid}"
        })

    return products


def update_products():
    current = load_products()
    results = []

    for keyword, cat in KEYWORDS:
        try:
            results += search(keyword, cat)
        except Exception:
            print("SCRAPER BLOCKED:", keyword, flush=True)

    if results:
        results += current
        results = list({p["link"]: p for p in results}.values())
        save_products(results)
        print("UPDATED PRODUCTS:", len(results), flush=True)
    else:
        print("SCRAPER FAILED -> use old products", flush=True)

        if not current:
            placeholder = [{
                "name": "ไฟโซล่า LED ติดบ้าน",
                "category": "solar",
                "rating": 4.8,
                "sold": 500,
                "link": "https://shopee.co.th"
            }]
            save_products(placeholder)import json
import requests

PRODUCT_FILE = "products.json"

KEYWORDS = [
    ("ไฟโซล่า", "solar"),
    ("ปลั๊กไฟ", "plug"),
    ("เครื่องมือช่าง", "tools"),
    ("หลอดไฟ LED", "led")
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def load_products():
    try:
        with open(PRODUCT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_products(data):
    with open(PRODUCT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def search(keyword, category):
    url = f"https://shopee.co.th/api/v4/search/search_items?keyword={keyword}&limit=10"

    r = requests.get(url, headers=HEADERS, timeout=20)

    if r.status_code != 200:
        raise Exception("blocked")

    data = r.json()
    products = []

    for item in data.get("items", []):
        i = item.get("item_basic", {})

        shopid = i.get("shopid")
        itemid = i.get("itemid")
        name = i.get("name")

        if not shopid or not itemid or not name:
            continue

        products.append({
            "name": name,
            "category": category,
            "rating": 4.5,
            "sold": 100,
            "link": f"https://shopee.co.th/product/{shopid}/{itemid}"
        })

    return products


def update_products():
    current = load_products()
    results = []

    for keyword, cat in KEYWORDS:
        try:
            results += search(keyword, cat)
        except Exception:
            print("SCRAPER BLOCKED:", keyword, flush=True)

    if results:
        results += current
        results = list({p["link"]: p for p in results}.values())
        save_products(results)
        print("UPDATED PRODUCTS:", len(results), flush=True)
    else:
        print("SCRAPER FAILED -> use old products", flush=True)

        if not current:
            placeholder = [{
                "name": "ไฟโซล่า LED ติดบ้าน",
                "category": "solar",
                "rating": 4.8,
                "sold": 500,
                "link": "https://shopee.co.th"
            }]
            save_products(placeholder)
