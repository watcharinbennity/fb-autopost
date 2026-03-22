import os
import json
import random
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
USE_OPENAI = os.getenv("USE_OPENAI", "true").lower() == "true"


def append_link(text: str, link: str) -> str:
    text = str(text).strip()
    link = str(link).strip()

    if not link:
        return text

    if link in text:
        return text

    return f"{text}\n\n🛒 สั่งซื้อสินค้า\n{link}"


def fallback_caption(product):
    hooks = [
        "🔥 ของมันต้องมี",
        "⚡ สายช่างห้ามพลาด",
        "💡 ของดีใช้งานจริง",
        "🛠 ตัวช่วยงานบ้านงานช่าง",
        "🚀 รุ่นนี้กำลังมาแรง",
    ]

    benefits = [
        "ใช้งานง่าย",
        "คุ้มค่า น่าใช้",
        "เหมาะมีติดบ้านติดร้าน",
        "ช่วยให้งานสะดวกขึ้น",
        "ของแท้ คุณภาพดี",
    ]

    close = [
        "กดดูรายละเอียดที่ลิงก์ด้านล่าง",
        "ดูข้อมูลเพิ่มเติมได้ที่ลิงก์ด้านล่าง",
        "สนใจกดดูรายละเอียดได้เลย",
    ]

    text = (
        f"{random.choice(hooks)}\n\n"
        f"{product['title']}\n\n"
        f"✅ {random.choice(benefits)}\n"
        f"✅ เราคัดมาให้สำหรับเพจ BEN Home & Electrical\n"
        f"{random.choice(close)}"
    )
    return append_link(text, product.get("link", ""))


def generate_caption(product):
    if not USE_OPENAI or not OPENAI_API_KEY:
        return fallback_caption(product)

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทยสำหรับขายสินค้าแนวไฟฟ้า/เครื่องมือช่าง

สินค้า:
{product['title']}
หมวด:
{product.get('group', 'tools')}
ราคา:
{product.get('price', 0)}
ค่าคอม:
{product.get('commission', 0)}

เงื่อนไข:
- เขียน 10 แบบ
- สายขาย แต่ไม่เวอร์เกินจริง
- ไม่ใส่ราคาตัวเลข
- ความยาว 4-6 บรรทัด
- เหมาะกับเพจ BEN Home & Electrical
- ปิดท้ายชวนกดดูรายละเอียด
- ห้ามใส่ลิงก์เอง ระบบจะเติมลิงก์ภายหลัง
- ตอบ JSON เท่านั้น รูปแบบ:
{{"captions":["...","..."]}}
""".strip()

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "คุณเป็นนักเขียนแคปชันขายสินค้าไฟฟ้าและเครื่องมือช่างภาษาไทย"
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.95,
                "response_format": {"type": "json_object"},
            },
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"].strip()
        obj = json.loads(content)

        captions = obj.get("captions", [])
        captions = [str(x).strip() for x in captions if str(x).strip()]

        if not captions:
            return fallback_caption(product)

        caption = random.choice(captions[:10])
        return append_link(caption, product.get("link", ""))
    except Exception:
        return fallback_caption(product)


def generate_comment_text(product):
    lines = [
        "🛒 สั่งซื้อสินค้าตัวนี้",
        product["link"],
        "",
        "🔥 ของกำลังมาแรง สนใจกดดูก่อนได้เลย",
    ]
    return "\n".join(lines)
