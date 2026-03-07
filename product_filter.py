KEYWORDS = [
    "ไฟ", "led", "โคม", "solar",
    "ปลั๊ก", "สวิตช์", "สายไฟ",
    "เครื่องมือ", "ช่าง", "ไขควง",
    "สว่าน", "diy", "hardware"
]


def match_category(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in KEYWORDS)


def filter_products(rows, state):
    products = []
    posted = set(state.get("posted", []))

    for r in rows:
        try:
            title = (r.get("title") or "").strip()
            link = (r.get("product_link") or "").strip()
            image = (r.get("image_link") or "").strip()

            if not title or not link or not image:
                continue

            if link in posted:
                continue

            if not match_category(title):
                continue

            rating = float(r.get("item_rating") or 0)
            sold = int(float(r.get("item_sold") or 0))
            price = float(r.get("sale_price") or r.get("price") or 0)

            if rating < 4.5:
                continue
            if sold < 100:
                continue
            if price < 20 or price > 300:
                continue

            products.append({
                "name": title,
                "link": link,
                "image": image,
                "price": price,
                "rating": rating,
                "sold": sold
            })
        except Exception:
            continue

    return products
