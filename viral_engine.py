import random

RAW_BASE="https://raw.githubusercontent.com/watcharinbootprasan/fb-autopost/main/assets"

TOPICS={
"ไฟโซล่าดีไหม":f"{RAW_BASE}/solar.jpg",
"ปลั๊กไฟแบบไหนปลอดภัย":f"{RAW_BASE}/safe_plug.jpg",
"เครื่องมือช่างที่ควรมีติดบ้าน":f"{RAW_BASE}/tools.jpg",
"5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน":f"{RAW_BASE}/home_electrical_5.jpg",
"หลอดไฟ LED ประหยัดไฟจริงไหม":f"{RAW_BASE}/led_save_power.jpg"
}

def generate():

 topic=random.choice(list(TOPICS.keys()))

 caption=f"""
⚡ {topic}

บ้านคุณคิดว่ายังไง ?

คอมเมนต์บอกหน่อย 👇
"""

 image=TOPICS[topic]

 return caption,image
