import json
import random

PRODUCT_FILE = "products.json"
POSTED_FILE = "posted_products.json"


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_trending_products():
    products = load_json(PRODUCT_FILE)
    posted = set(load_json(POSTED_FILE))

    trending = [
        p for p in products
        if p.get("link")
        and p["link"] not in posted
        and float(p.get("rating", 0)) >= 4.0
        and int(p.get("sold", 0)) >= 10
    ]

    if not trending:
        return None

    # เน้น sold + rating
    trending.sort(
        key=lambda x: (
            int(x.get("sold", 0)),
            float(x.get("rating", 0))
        ),
        reverse=True
    )

    top = trending[:20] if len(trending) >= 20 else trending
    product = random.choice(top)

    posted.add(product["link"])
    save_json(POSTED_FILE, list(posted))

    return product
