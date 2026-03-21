from utils import to_float

MIN_RATING = 4.0
MIN_SOLD = 10.0
MIN_COMMISSION = 50.0

MAX_PRICE_ELECTRICAL = 3000.0
MAX_PRICE_TOOLS = 50000.0

ELECTRICAL_KEYWORDS = [
    "หลอดไฟ", "โคมไฟ", "ไฟ led", "ไฟแอลอีดี", "led bulb",
    "downlight", "ไฟดาวน์ไลท์", "spotlight", "floodlight",
    "ไฟเพดาน", "ไฟติดผนัง", "ไฟสนาม", "ไฟถนน",
    "ปลั๊กไฟ", "ปลั๊กพ่วง", "เต้ารับ", "socket", "power strip",
    "เบรกเกอร์", "breaker", "mcb", "rcbo", "fuse",
    "สวิตช์ไฟ", "switch", "สายไฟ", "wire", "cable",
    "ตู้ไฟ", "consumer unit", "adapter", "อะแดปเตอร์",
    "usb plug", "ปลั๊ก usb", "ปลั๊กยูเอสบี",
    "voltage tester", "ไฟฉาย", "ไฟฉุกเฉิน", "electrical"
]

TOOLS_KEYWORDS = [
    "เครื่องมือช่าง", "tool", "tools",
    "ไขควง", "ไขควงแฉก", "ไขควงปากแบน", "ไขควงวัดไฟ",
    "คีม", "คีมตัด", "คีมปอกสาย", "คีมย้ำหางปลา",
    "ประแจ", "ประแจเลื่อน", "ประแจแหวน", "บล็อกขันน็อต",
    "ค้อน", "เลื่อย", "คัตเตอร์", "ตลับเมตร",
    "สว่าน", "drill", "สว่านไฟฟ้า", "สว่านไร้สาย",
    "multimeter", "มัลติมิเตอร์", "tester",
    "ลูกบล็อก", "บ๊อก", "ไขควงไฟฟ้า", "เครื่องเจียร", "ลูกหมู",
    "grinder", "ปืนกาว", "ปืนลม", "เครื่องเป่าลม",
    "สว่านกระแทก", "เลื่อยวงเดือน", "ตู้เชื่อม", "เครื่องเชื่อม",
    "ปั๊มน้ำ", "เครื่องฉีดน้ำ", "สกัดไฟฟ้า"
]

BLOCK_KEYWORDS = [
    # apple / gadget / mobile
    "apple", "iphone", "ipad", "apple watch", "watch series", "airpods",
    "macbook", "imac", "istudio", "copperwired", "โทรศัพท์", "สมาร์ทโฟน",
    "มือถือ", "แท็บเล็ต", "นาฬิกาอัจฉริยะ", "smartwatch", "smart watch",

    # beauty / skincare
    "beauty", "cosmetic", "makeup", "lip", "lipstick",
    "micellar", "cleansing", "garnier", "konvy", "serum", "skincare",
    "facial", "face", "หน้ากาก", "mask", "หน้า", "ผิว",
    "บำรุงผิว", "สกินแคร์", "ความงาม", "ครีม", "led mask", "nir",

    # fashion
    "fashion", "bag", "tote bag", "เสื้อ", "เสื้อผ้า", "กระเป๋า", "รองเท้า",
    "น้ำหอม", "เครื่องสำอาง",

    # food
    "oats", "rolled oats", "ข้าวโอ๊ต", "อาหาร", "snack", "ของกิน", "เวอรี่นาย",

    # camping / outdoor
    "tent", "เต็นท์", "camping", "แคมป์", "glamping",
    "เต็นท์สนาม", "เต็นท์กาง", "โต๊ะแคมป์", "เก้าอี้แคมป์",

    # unrelated
    "toy", "ของเล่น", "baby", "เด็ก", "เครื่องประดับ", "pet", "สัตว์เลี้ยง"
]


def normalize(text: str) -> str:
    return str(text).strip().lower()


def contains_any(text, keywords):
    return any(k in text for k in keywords)


def pick_first(row, keys, default=""):
    lower_map = {k.lower(): k for k in row.keys()}
    for key in keys:
        real = lower_map.get(key.lower())
        if real:
            val = row.get(real, "")
            if str(val).strip():
                return str(val).strip()
    return default


def get_price(row):
    lower_map = {k.lower(): k for k in row.keys()}

    def get_any(keys):
        for k in keys:
            real = lower_map.get(k.lower())
            if real:
                val = row.get(real, "")
                if str(val).strip():
                    return to_float(val)
        return 0.0

    return get_any([
        "price",
        "final_price",
        "sale_price",
        "product_price",
        "price_min",
        "price_max",
        "ราคาขาย"
    ])


def calc_commission(row):
    lower_map = {k.lower(): k for k in row.keys()}

    def get_any(keys):
        for k in keys:
            real = lower_map.get(k.lower())
            if real:
                val = row.get(real, "")
                if str(val).strip():
                    return to_float(val)
        return 0.0

    commission = get_any([
        "commission",
        "commission_value",
        "estimated_commission",
        "earning",
        "earn",
        "payout",
        "commission baht",
        "ค่าคอม",
        "ค่าคอมมิชชั่น"
    ])
    if commission > 0:
        return commission

    rate = get_any([
        "commission_rate",
        "commission %",
        "commission_percent",
        "rate",
        "commission rate",
        "เปอร์เซ็นต์ค่าคอม"
    ])

    price = get_price(row)

    if rate > 0 and price > 0:
        return (rate / 100.0) * price

    if price > 0:
        return price * 0.10

    return 0.0


def detect_group(title: str) -> str:
    t = normalize(title)

    if contains_any(t, BLOCK_KEYWORDS):
        return "blocked"

    if contains_any(t, ELECTRICAL_KEYWORDS):
        return "electrical"

    if contains_any(t, TOOLS_KEYWORDS):
        return "tools"

    return "other"


def build_product(row):
    title = pick_first(
        row,
        ["product_name", "title", "name", "item_name", "ชื่อสินค้า"],
        ""
    )
    if not title:
        return None

    group = detect_group(title)
    if group in ["blocked", "other"]:
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

    price = get_price(row)
    if price <= 0:
        return None

    if group == "electrical" and price > MAX_PRICE_ELECTRICAL:
        return None

    if group == "tools" and price > MAX_PRICE_TOOLS:
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
            "product_short link",
            "product_short_link",
            "short_link",
            "short link",
            "product_link",
            "product_url",
            "link",
            "affiliate_link",
            "product short link"
        ],
        ""
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
        "commission": commission,
        "price": price,
        "group": group,
    }
