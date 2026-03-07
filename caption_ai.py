from ai_engine import ask_ai


def generate_product_caption(product: dict) -> str:
    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทยสำหรับเพจ BEN Home & Electrical

สินค้า: {product['name']}
ราคา: {product['price']} บาท
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

กติกา:
- ไม่เกิน 5 บรรทัด
- มี emoji พอดี
- กระตุ้นให้น่าซื้อ
- ยังไม่ต้องใส่ลิงก์
""".strip()

    text = ask_ai(prompt)
    if text:
        return text

    return (
        f"⚡ {product['name']}\n\n"
        f"⭐ รีวิว {product['rating']}\n"
        f"🔥 ขายแล้ว {product['sold']}\n"
        f"💰 ราคา {product['price']} บาท"
    )


def generate_viral_caption(topic: str) -> str:
    prompt = f"""
เขียนโพสต์ Facebook ภาษาไทยแบบไวรัล

หัวข้อ: {topic}

กติกา:
- ไม่เกิน 4 บรรทัด
- มี emoji
- ชวนคอมเมนต์
- อ่านง่าย
""".strip()

    text = ask_ai(prompt)
    if text:
        return text

    return f"⚡ {topic}\n\nบ้านคุณคิดว่ายังไง ?\n\nคอมเมนต์บอกหน่อย"


def generate_engagement_caption() -> str:
    prompt = """
เขียนโพสต์ Facebook ภาษาไทยสำหรับถามคำถามเกี่ยวกับ
ของใช้ในบ้าน อุปกรณ์ไฟฟ้า หรือเครื่องมือช่าง

กติกา:
- ไม่เกิน 3 บรรทัด
- ชวนคอมเมนต์
- มี emoji เล็กน้อย
""".strip()

    text = ask_ai(prompt)
    if text:
        return text

    return "💬 บ้านคุณใช้ปลั๊กไฟกี่ตัว ?\n\nคอมเมนต์หน่อย"
