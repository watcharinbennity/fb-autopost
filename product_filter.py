from utils import to_float

ALLOW_KEYWORDS = [
    "ไฟ", "หลอดไฟ", "โคมไฟ", "โคม", "lamp", "light", "led", "floodlight", "spotlight",
    "ไฟฉาย", "ไฟโซล่า", "ไฟสนาม", "ไฟถนน",
    "ไฟฟ้า", "electrical", "ปลั๊ก", "ปลั๊กไฟ", "ปลั๊กพ่วง", "socket", "power strip",
    "เต้ารับ", "เบรกเกอร์", "breaker", "mcb", "rcbo", "fuse", "สวิตช์", "switch",
    "สายไฟ", "wire", "cable", "ตู้ไฟ", "consumer unit",
    "tool", "tools", "เครื่องมือ", "เครื่องมือช่าง", "ช่าง", "ไขควง", "ไขควงวัดไฟ",
    "คีม", "คีมตัด", "คีมปอกสาย", "สว่าน", "drill", "มัลติมิเตอร์", "multimeter",
    "tester", "ประแจ", "ค้อน", "เลื่อย", "คัตเตอร์"
]

BLOCK_KEYWORDS = [
    "fashion", "bag", "tote bag", "beauty", "cosmetic", "makeup", "lip", "dress",
    "เสื้อ", "เสื้อผ้า", "กระเป๋า", "รองเท้า", "น้ำหอม", "ของเล่น", "toy",
    "ตุ๊กตา", "อาหาร", "snack", "เครื่องประดับ", "แม่และเด็ก", "baby"
]

MIN_RATING = 4.0
MIN_SOLD = 10.0


def normalize(text: str) -> str:
    return str(text).strip().lower()


def title_allowed(title: str) -> bool:
    t = normalize(title)

    for bad in BLOCK_KEYWORDS:
        if bad in t:
            return False

    for good in ALLOW_KEYWORDS:
        if good in t:
            return True

    return False


def pick_first(row, keys, default=""):
    lower_map = {k.lower(): k for k in row.keys()}
    for key in keys:
        real = lower_map.get(key.lower())
        if real:
            value = row.get(real, "")
            if str(value).strip():
                return str(value).strip()
    return default


def build_product(row):
    title = pick_first(row, ["product_name", "title", "name", "ชื่อสินค้า"], "")
    if not title:
        return None

    if not title_allowed(title):
        return None

    rating = to_float(pick_first(row, ["rating", "item_rating", "คะแนน"], "0"))
    sold = to_float(pick_first(row, ["sold", "historical_sold", "sales", "ขายแล้ว"], "0"))

    if rating < MIN_RATING:
        return None
    if sold < MIN_SOLD:
        return None

    pid = pick_first(row, ["itemid", "item_id", "product_id", "id"], title)
    image = pick_first(row, ["image", "image_url", "image_url_1", "picture"], "")
    link = pick_first(
        row,
        ["product_short link", "product_short_link", "short_link", "product_link", "product_url", "link"],
        "",
    )

    if not image or not link:
        return None

    return {
        "id": str(pid).strip(),
        "title": title.strip(),
        "image": image.strip(),
        "link": link.strip(),
        "rating": rating,
        "sold": sold,
    }


def score_product(product):
    sold_score = product["sold"] * 2
    rating_score = product["rating"] * 10
    return sold_score + rating_score
