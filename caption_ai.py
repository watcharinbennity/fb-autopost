import random

OPENERS=[
"⚡ ของมันควรมีติดบ้าน",
"🔥 ตัวนี้ขายดีใน Shopee",
"🏠 ของใช้ไฟฟ้าที่น่าสนใจ",
"🛠️ สายช่างต้องดู",
"💡 ของดีสายไฟฟ้า"
]

CTA=[
"กดดูรายละเอียด",
"เช็กราคาได้ที่ลิงก์",
"ดูโปรล่าสุด",
"กดดูสินค้า"
]

def build_caption(p):

    opener=random.choice(OPENERS)
    cta=random.choice(CTA)

    return f"""
{opener}

{p['name']}

⭐ รีวิว {p['rating']}/5
📦 ขายแล้ว {p['sold']}

💰 ราคา {p['price']} บาท

{cta}
{p['aff_link']}

#BENHomeElectrical
#ShopeeAffiliate
"""
