from ai_engine import ask_ai


def create_reel_script(topic: str, product: dict | None = None) -> str:
    if product:
        prompt = f"""
เขียนสคริปต์ Reels ภาษาไทย 15 วินาที

สินค้า: {product['name']}
ราคา: {product['price']}
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

โครงสร้าง:
- Hook
- โชว์สินค้า
- Call to action
""".strip()
    else:
        prompt = f"""
เขียนสคริปต์ Reels ภาษาไทย 15 วินาที

หัวข้อ: {topic}

โครงสร้าง:
- Hook
- เนื้อหาสั้น
- Call to action
""".strip()

    text = ask_ai(prompt)
    if text:
        return text

    if product:
        return f"ของดีน่าใช้ {product['name']} ราคา {product['price']} บาท ดูลิงก์ใต้โพสต์เลย"
    return f"{topic} ใครเคยใช้บ้าง คอมเมนต์บอกหน่อย"


def save_reel_script(text: str) -> None:
    with open("reels_script.txt", "w", encoding="utf-8") as f:
        f.write(text)from ai_engine import ask_ai


def create_reel_script(topic: str, product: dict | None = None) -> str:
    if product:
        prompt = f"""
เขียนสคริปต์ Reels ภาษาไทย 15 วินาที

สินค้า: {product['name']}
ราคา: {product['price']}
รีวิว: {product['rating']}
ขายแล้ว: {product['sold']}

โครงสร้าง:
- Hook
- โชว์สินค้า
- Call to action
""".strip()
    else:
        prompt = f"""
เขียนสคริปต์ Reels ภาษาไทย 15 วินาที

หัวข้อ: {topic}

โครงสร้าง:
- Hook
- เนื้อหาสั้น
- Call to action
""".strip()

    text = ask_ai(prompt)
    if text:
        return text

    if product:
        return f"ของดีน่าใช้ {product['name']} ราคา {product['price']} บาท ดูลิงก์ใต้โพสต์เลย"
    return f"{topic} ใครเคยใช้บ้าง คอมเมนต์บอกหน่อย"


def save_reel_script(text: str) -> None:
    with open("reels_script.txt", "w", encoding="utf-8") as f:
        f.write(text)
