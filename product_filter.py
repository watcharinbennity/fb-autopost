KEYWORDS_STRONG = [
    "ไฟ", "led", "โคม", "โคมไฟ", "หลอดไฟ", "ไฟฉาย", "ไฟฉุกเฉิน",
    "solar", "โซล่า", "โซลาร์เซลล์",
    "ปลั๊ก", "ปลั๊กไฟ", "สวิตช์", "เต้ารับ", "สายไฟ", "เบรกเกอร์",
    "เครื่องมือ", "เครื่องมือช่าง", "ช่าง", "ไขควง", "สว่าน", "คีม", "ประแจ",
    "diy", "hardware", "ฮาร์ดแวร์",
    "พัดลม", "ปั๊ม", "ปั๊มน้ำ", "มิเตอร์", "มัลติมิเตอร์",
    "adapter", "อะแดปเตอร์"
]

KEYWORDS_WEAK = [
    "home", "บ้าน", "ซ่อม", "อุปกรณ์", "อเนกประสงค์", "ติดผนัง", "ติดบ้าน"
]

BAD_KEYWORDS = [
    "สุนัข", "แมว", "สัตว์เลี้ยง", "ปลาร้า", "อาหาร", "ขนม", "เสื้อ", "กางเกง",
    "รองเท้า", "เครื่องสำอาง", "ลิป", "ครีม", "น้ำหอม", "ตุ๊กตา", "ของเล่น",
    "เคสมือถือ", "เสื้อผ้า", "แฟชั่น", "กระเป๋า"
]


def score_title(title: str) -> int:
    t = (title or "").lower()

    for bad in BAD_KEYWORDS:
        if bad in t:
            return -999

    score = 0

    for k in KEYWORDS_STRONG:
        if k.lower() in t:
            score += 3

    for k in KEYWORDS_WEAK:
        if k.lower() in t:
            score += 1

    return score


def score_product(title_score: int, rating: float, sold: int, price: float) -> float:
    score = 0.0

    score += title_score * 10
    score += rating * 20
    score += min(sold, 5000) * 0.08

    if 20 <= price <= 199:
        score += 20
    elif 200 <= price <= 399:
        score += 10
    elif 400 <= price <= 800:
        score += 4

    return round(score, 2)


def filter_products(rows: list[dict], state: dict):
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

            title_score = score_title(title)
            if title_score < 3:
                continue

            rating = float(r.get("item_rating") or 0)
            sold = int(float(r.get("item_sold") or 0))
            price = float(r.get("sale_price") or r.get("price") or 0)

            if rating < 4.0:
                continue
            if sold < 10:
                continue
            if price < 10 or price > 800:
                continue

            final_score = score_product(title_score, rating, sold, price)

            products.append({
                "name": title,
                "link": link,
                "image": image,
                "price": price,
                "rating": rating,
                "sold": sold,
                "title_score": title_score,
                "final_score": final_score,
            })
        except Exception:
            continue

    products.sort(
        key=lambda x: (x["final_score"], x["title_score"], x["rating"], x["sold"]),
        reverse=True,
    )
    return products
