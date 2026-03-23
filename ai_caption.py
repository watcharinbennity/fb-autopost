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


def fallback_caption(product, page_mode):
    title = product["title"]

    if page_mode == "ben":
        hooks = [
            "🔥 ของมันต้องมีสำหรับสายช่าง",
            "⚡ ตัวช่วยงานไฟฟ้าและงานช่าง",
            "🛠 ใช้งานจริง คุ้มค่า น่าใช้",
            "🚀 รุ่นนี้กำลังมาแรง",
        ]
        benefits = [
            "เหมาะมีติดบ้านติดร้าน",
            "ช่วยให้งานสะดวกขึ้น",
            "คัดมาให้จากสินค้าใช้งานจริง",
            "ของดีสำหรับเพจ BEN Home & Electrical",
        ]
    else:
        hooks = [
            "🏠 อัปเกรดบ้านให้อัจฉริยะขึ้น",
            "📶 ของใช้ Smart Home ที่น่าโดน",
            "🎯 ตัวช่วยให้บ้านสะดวกและปลอดภัยขึ้น",
            "🚀 สินค้า Smart Home กำลังมาแรง",
        ]
        benefits = [
            "ควบคุมง่าย ใช้งานได้จริง",
            "เหมาะกับบ้านยุคใหม่",
            "ช่วยให้บ้านสะดวกและปลอดภัยขึ้น",
            "คัดมาให้จากเพจ SmartHome Thailand",
        ]

    text = (
        f"{random.choice(hooks)}\n\n"
        f"{title}\n\n"
        f"✅ {random.choice(benefits)}\n"
        f"✅ กดดูรายละเอียดที่ลิงก์ด้านล่าง"
    )
    return append_link(text, product.get("link", ""))


def generate_caption(product, page_mode="ben"):
    if not USE_OPENAI or not OPENAI_API_KEY:
        return fallback_caption(product, page_mode)

    if page_mode == "ben":
        style = "เพจไฟฟ้าและเครื่องมือช่าง"
    else:
        style = "เพจบ้านอัจฉริยะ Smart Home"

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทยสำหรับขายสินค้า

สไตล์เพจ:
{style}

สินค้า:
{product['title']}
หมวด:
{product.get('group', '')}

เงื่อนไข:
- เขียน 10 แบบ
- แนวขายจริง อ่านง่าย
- ไม่ใส่ราคาตัวเลข
- ยาว 4-6 บรรทัด
- ไม่ต้องเวอร์เกินจริง
- ห้ามใส่ลิงก์เอง ระบบจะเติมให้ทีหลัง
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
                    {"role": "system", "content": "คุณเป็นนักเขียนแคปชันขายของภาษาไทย"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.95,
                "response_format": {"type": "json_object"},
            },
            timeout=45,
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"].strip()
        obj = json.loads(content)
        captions = [str(x).strip() for x in obj.get("captions", []) if str(x).strip()]
        if not captions:
            return fallback_caption(product, page_mode)
        return append_link(random.choice(captions[:10]), product.get("link", ""))
    except Exception as e:
        print(f"OpenAI fallback: {e}", flush=True)
        return fallback_caption(product, page_mode)


def generate_comment_text(product, page_mode="ben"):
    if page_mode == "ben":
        tail = "🔥 สนใจกดดูก่อนได้เลย"
    else:
        tail = "🏠 สนใจกดดูรายละเอียดได้เลย"

    return f"🛒 สั่งซื้อสินค้าตัวนี้\n{product['link']}\n\n{tail}"
