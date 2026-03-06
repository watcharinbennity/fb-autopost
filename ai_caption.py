import random

OPENERS=[
"🔥 ของมันต้องมีติดบ้าน",
"⚡ สินค้าขายดีใน Shopee",
"🏠 อุปกรณ์ไฟฟ้าที่ควรมี"
]

CTA=[
"กดดูรายละเอียด",
"เช็กราคาล่าสุด",
"กดดูสินค้า"
]

def build_caption(p,link):

    opener=random.choice(OPENERS)
    cta=random.choice(CTA)

    return f"""
{opener}

{p['name']}

⭐ รีวิว {p['rating']}/5
📦 ขายแล้ว {p['sold']}

💰 ราคา {p['price']} บาท

{cta}
{link}

#BENHomeElectrical
#ShopeeAffiliate
"""
