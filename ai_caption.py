import os
import json
import random
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
USE_OPENAI = os.getenv("USE_OPENAI", "true").lower() == "true"

FALLBACK_CAPTIONS = [
    "งานไฟ งานช่าง งานติดตั้ง ต้องมีตัวช่วยดี ๆ 👨‍🔧⚡\n{title}\n\nเหมาะกับสายช่างและคนที่ชอบทำงานเองที่บ้าน\nเช็กรายละเอียดล่าสุดที่ลิงก์ด้านล่าง",
    "ไอเท็มสายไฟฟ้า/เครื่องมือที่น่าใช้ 🔧⚡\n{title}\n\nใช้งานสะดวก เหมาะทั้งงานบ้านและงานช่าง\nเช็กรายละเอียดล่าสุดที่ลิงก์ด้านล่าง",
    "ของดีสาย BEN Home & Electrical ⚡\n{title}\n\nคัดมาให้แล้วสำหรับสายไฟ สายช่าง สายติดตั้ง\nเช็กรายละเอียดล่าสุดที่ลิงก์ด้านล่าง",
    "ตัวช่วยงานช่างที่น่าสนใจ 👷‍♂️\n{title}\n\nดูใช้งานง่าย น่ามีติดบ้านติดร้านไว้\nเช็กรายละเอียดล่าสุดที่ลิงก์ด้านล่าง",
]


def fallback_caption(product):
    return random.choice(FALLBACK_CAPTIONS).format(title=product["title"])


def generate_caption_choices(product):
    if not USE_OPENAI or not OPENAI_API_KEY:
        base = fallback_caption(product)
        return [base, base, base]

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทย สำหรับเพจ BEN Home & Electrical

สินค้า:
{product['title']}
หมวด:
{product.get('group', 'electrical')}

เงื่อนไข:
- เขียน 3 แบบ
- ไม่ใส่ราคาตัวเลข
- ความยาว 3-5 บรรทัดต่อแบบ
- โทนมืออาชีพ อ่านง่าย
- เหมาะกับสายไฟฟ้า เครื่องมือช่าง งานติดตั้ง
- ปิดท้ายให้ชวนกดดูรายละเอียดที่ลิงก์ด้านล่าง
- ตอบกลับเป็น JSON เท่านั้น
- รูปแบบ:
{{"captions":["แบบที่1","แบบที่2","แบบที่3"]}}
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
                    {"role": "system", "content": "คุณเป็นนักเขียนแคปชันขายของภาษาไทยเก่งด้านสินค้าไฟฟ้าและเครื่องมือช่าง"},
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

        if len(captions) >= 3:
            return captions[:3]

        base = fallback_caption(product)
        return captions + [base] * (3 - len(captions))
    except Exception:
        base = fallback_caption(product)
        return [base, base, base]


def generate_caption(product):
    choices = generate_caption_choices(product)
    return random.choice(choices)
