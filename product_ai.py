import json


def load_products() -> list[dict]:
    try:
        with open("products.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def load_posted_products() -> list[str]:
    try:
        with open("posted_products.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_posted_products(posted: list[str]) -> None:
    with open("posted_products.json", "w", encoding="utf-8") as f:
        json.dump(posted, f, ensure_ascii=False, indent=2)


def score_product(product: dict) -> float:
    rating = float(product.get("rating", 0))
    sold = int(product.get("sold", 0))
    price = float(product.get("price", 0))

    score = 0.0
    score += rating * 25
    score += min(sold, 5000) * 0.08

    if 20 <= price <= 399:
        score += 20
    elif 400 <= price <= 800:
        score += 8

    return round(score, 2)


def pick_product() -> dict | None:
    products = load_products()
    posted = set(load_posted_products())

    candidates = []
    for p in products:
        link = p.get("link")
        if not link:
            continue
        if link in posted:
            continue

        rating = float(p.get("rating", 0))
        sold = int(p.get("sold", 0))

        if rating < 4.0:
            continue
        if sold < 10:
            continue

        item = dict(p)
        item["score"] = score_product(item)
        candidates.append(item)

    if not candidates:
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[0]


def mark_product_posted(product: dict) -> None:
    posted = load_posted_products()
    link = product.get("link")
    if link and link not in posted:
        posted.append(link)
        save_posted_products(posted)
