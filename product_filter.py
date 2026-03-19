from utils import to_float

MIN_RATING = 4.0
MIN_SOLD = 10.0
MIN_COMMISSION = 50.0

# ต้องตรงอย่างน้อย 1 กลุ่มแบบแรง ๆ
LIGHTING_KEYWORDS = [
    "โคมไฟ", "หลอดไฟ", "ไฟ led", "ไฟแอลอีดี", "led", "ไฟฉาย", "ไฟโซล่า",
    "solar light", "floodlight", "spotlight", "ไฟติดผนัง", "ไฟเพดาน",
    "ไฟเซ็นเซอร์", "sensor light", "motion light", "ไฟสนาม", "ไฟถนน"
]

ELECTRICAL_KEYWORDS = [
    "ปลั๊กไฟ", "ปลั๊กพ่วง", "socket", "power strip", "เต้ารับ", "เบรกเกอร์",
    "breaker", "mcb", "rcbo", "fuse", "สวิตช์ไฟ", "switch", "สายไฟ",
    "wire", "cable", "ตู้ไฟ", "consumer unit", "อะแดปเตอร์", "adapter",
    "voltage tester", "ปลั๊ก usb", "usb plug"
]

TOOLS_KEYWORDS = [
    "ไขควง", "ไขควงวัดไฟ", "คีม", "คีมตัด", "คีมปอกสาย", "สว่าน", "drill",
    "มัลติมิเตอร์", "multimeter", "tester", "ประแจ", "ประแจเลื่อน",
    "ค้อน", "เลื่อย", "คัตเตอร์", "ตลับเมตร", "เครื่องมือช่าง", "tool", "tools"
]

# บล็อกหมวดที่ไม่เกี่ยวข้อง
BLOCK_KEYWORDS = [
    # fashion / beauty
    "fashion", "bag", "tote bag", "beauty", "cosmetic", "makeup", "lip", "lipstick",
    "micellar", "cleansing", "garnier", "konvy", "serum", "skincare",
    "เสื้อ", "เสื้อผ้า", "กระเป๋า", "รองเท้า", "น้ำหอม", "เครื่องสำอาง",

    # food
    "oats", "rolled oats", "ข้าวโอ๊ต", "อาหาร", "snack", "ของกิน", "เวอรี่นาย",

    # other unrelated
    "ของเล่น", "toy", "ตุ๊กตา", "แม่และเด็ก", "baby", "เครื่องประดับ"
]


def normalize(text: str) -> str:
    return str(text).strip().lower()


def pick_first(row, keys, default=""):
    lower_map = {k.lower(): k for k in row.keys()}
    for key in keys:
        real = lower_map.get(key.lower())
        if real:
            value = row.get(real, "")
            if str(value).strip():
                return str(value).strip()
    return default


def contains_any(text: str, keywords):
    return any(k in text for k in keywords)


def detect_group(title: str) -> str:
    t = normalize(title)

    if contains_any(t, LIGHTING_KEYWORDS):
        return "lighting"
    if contains_any(t, ELECTRICAL_KEYWORDS):
        return "electrical"
    if contains_any(t, TOOLS_KEYWORDS):
        return "tools"
    return "other"


def title_allowed(title: str) -> bool:
    t = normalize(title)

    # เจอคำต้องห้าม = ตัดทิ้งทันที
    if contains_any(t, BLOCK_KEYWORDS):
        return False

    # ต้องเข้า whitelist แบบชัดเจนเท่านั้น
    if contains_any(t, LIGHTING_KEYWORDS):
        return True
    if contains_any(t, ELECTRICAL_KEYWORDS):
        return True
    if contains_any(t, TOOLS_KEYWORDS):
        return True

    return False


def calc_commission(row):
    """
    พยายามอ่านค่าคอมจากหลายชื่อคอลัมน์
    ถ้าไม่มีค่าคอมตรง จะลองคำนวณจาก commission_rate * price
    """

    commission = to_float(pick_first(row, [
        "commission",
        "commission_value",
        "estimated_commission",
        "earn",
        "earning",
        "commission baht",
        "ค่าคอม",
        "ค่าคอมมิชชั่น"
    ], "0"))

    if commission > 0:
        return commission

    commission_rate = to_float(pick_first(row, [
        "commission_rate",
        "commission %",
        "commission_percent",
        "rate",
        "เปอร์เซ็นต์ค่าคอม"
    ], "0"))

    price = to_float(pick_first(row, [
        "price",
        "final_price",
        "sale_price",
        "product_price",
        "ราคาขาย"
    ], "0"))

    if commission_rate > 0 and price > 0:
        return (commission_rate / 100.0) * price

    return 0.0


def build_product(row):
    title = pick_first(
        row,
        ["product_name", "product name", "title", "name", "ชื่อสินค้า", "item_name"],
        ""
    )
    if not title:
        return None

    if not title_allowed(title):
        return None

    rating = to_float(pick_first(
        row,
        ["rating", "item_rating", "คะแนน", "product_rating", "avg_rating"],
        "0"
    ))
    sold = to_float(pick_first(
        row,
        ["sold", "historical_sold", "sales", "ขายแล้ว", "sold_count", "item_sold"],
        "0"
    ))

    if rating < MIN_RATING:
        return None
    if sold < MIN_SOLD:
        return None

    commission = calc_commission(row)
    if commission < MIN_COMMISSION:
        return None

    pid = pick_first(
        row,
        ["itemid", "item_id", "product_id", "id", "itemid ", "product id"],
        title
    )
    image = pick_first(
        row,
        ["image", "image_url", "image_url_1", "picture", "image link", "image_link", "img_url"],
        ""
    )
    link = pick_first(
        row,
        [
            "product_short link", "product_short_link", "short_link", "short link",
            "product_link", "product_url", "link", "affiliate_link", "product short link"
        ],
        ""
    )

    if not image or not link:
        return None

    group = detect_group(title)
    if group == "other":
        return None

    return {
        "id": str(pid).strip(),
        "title": title.strip(),
        "image": image.strip(),
        "link": link.strip(),
        "rating": rating,
        "sold": sold,
        "commission": commission,
        "group": group,
        }
