import os
import random

RAW_BASE = os.getenv(
    "RAW_BASE_URL",
    "https://raw.githubusercontent.com/watcharinbootprasan/fb-autopost/main/assets"
)

DEFAULT_IMAGE = f"{RAW_BASE}/home_electrical_5.jpg"

TOPIC_IMAGE_MAP = {
    "ไฟโซล่าดีไหม": f"{RAW_BASE}/solar.jpg",
    "ปลั๊กไฟแบบไหนปลอดภัย": f"{RAW_BASE}/safe_plug.jpg",
    "เครื่องมือช่างที่ควรมีติดบ้าน": f"{RAW_BASE}/tools.jpg",
    "5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน": f"{RAW_BASE}/home_electrical_5.jpg",
    "หลอดไฟ LED ประหยัดไฟจริงไหม": f"{RAW_BASE}/led_save_power.jpg",
}

TOPICS = list(TOPIC_IMAGE_MAP.keys())

ENGAGEMENT_POSTS = [
    {
        "text": "💬 บ้านคุณใช้ปลั๊กไฟกี่ตัว ?\n\nคอมเมนต์หน่อย",
        "image": f"{RAW_BASE}/safe_plug.jpg"
    },
    {
        "text": "💬 คุณใช้เครื่องมือช่างอะไรบ่อยที่สุด ?\n\nคอมเมนต์หน่อย",
        "image": f"{RAW_BASE}/tools.jpg"
    },
    {
        "text": "💬 บ้านคุณมีอุปกรณ์ไฟฟ้ากี่อย่างที่ใช้ทุกวัน ?\n\nคอมเมนต์หน่อย",
        "image": f"{RAW_BASE}/home_electrical_5.jpg"
    }
]


def choose_topic():
    return random.choice(TOPICS)


def get_image_by_topic(topic: str):
    return TOPIC_IMAGE_MAP.get(topic, DEFAULT_IMAGE)


def generate_viral_fallback():
    topic = choose_topic()
    caption = f"⚡ {topic}\n\nบ้านคุณคิดว่ายังไง ?\n\nคอมเมนต์บอกหน่อย"
    image = get_image_by_topic(topic)
    return caption, image, topic


def generate_engagement_fallback():
    post = random.choice(ENGAGEMENT_POSTS)
    return post["text"], post["image"]
