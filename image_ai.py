ASSET_BY_TOPIC = {
    "ไฟโซล่าดีไหม": "assets/solar.jpg",
    "ปลั๊กไฟแบบไหนปลอดภัย": "assets/safe_plug.jpg",
    "เครื่องมือช่างที่ควรมีติดบ้าน": "assets/tools.jpg",
    "5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน": "assets/home_electrical_5.jpg",
    "หลอดไฟ LED ประหยัดไฟจริงไหม": "assets/led_save_power.jpg",
}

DEFAULT_IMAGE = "assets/home_electrical_5.jpg"


def get_image_by_topic(topic: str) -> str:
    return ASSET_BY_TOPIC.get(topic, DEFAULT_IMAGE)


def get_image_by_category(category: str) -> str:
    c = (category or "").lower()

    if c == "solar":
        return "assets/solar.jpg"
    if c == "plug":
        return "assets/safe_plug.jpg"
    if c == "tools":
        return "assets/tools.jpg"
    if c == "led":
        return "assets/led_save_power.jpg"

    return DEFAULT_IMAGE
