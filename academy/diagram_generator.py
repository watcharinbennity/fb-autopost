# academy/diagram_generator.py

from PIL import Image, ImageDraw, ImageFont
import os

WIDTH = 1080
HEIGHT = 1920
BASE_DIR = os.path.dirname(__file__)
MASCOT_PATH = os.path.join(BASE_DIR, "assets", "chang_ben.png")


def _find_font():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


FONT_PATH = _find_font()


def _font(size: int):
    if FONT_PATH:
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _remove_white_bg(img):
    img = img.convert("RGBA")
    data = []
    for r, g, b, a in img.getdata():
        if r > 245 and g > 245 and b > 245:
            data.append((255, 255, 255, 0))
        else:
            data.append((r, g, b, a))
    img.putdata(data)
    return img


def _base_canvas(title):
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 18, 34))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((40, 40, 1040, 170), radius=28, fill=(18, 34, 58))
    draw.text((70, 78), "BEN Home & Electrical", fill="white", font=_font(40))
    draw.text((70, 220), title, fill=(255, 220, 70), font=_font(50))
    return img, draw


def _footer(draw):
    draw.rounded_rectangle((40, 1760, 1040, 1860), radius=22, fill=(18, 34, 58))
    draw.text((70, 1790), "ช่างเบนสอนไฟฟ้า", fill=(180, 210, 255), font=_font(34))


def _draw_mascot(img):
    if not os.path.exists(MASCOT_PATH):
        return
    mascot = Image.open(MASCOT_PATH)
    mascot = _remove_white_bg(mascot)
    mascot.thumbnail((280, 280))
    img.paste(mascot, (740, 360), mascot)


def draw_intro(path, title):
    img, draw = _base_canvas(title)

    draw.rounded_rectangle((80, 460, 1000, 1540), radius=46, outline="white", width=6)

    draw.text((140, 620), "สวัสดีครับ ผมช่างเบน", fill="white", font=_font(52))
    draw.text((140, 740), "เราจะเรียนไฟฟ้าตั้งแต่", fill=(255, 220, 70), font=_font(48))
    draw.text((140, 820), "พื้นฐาน จนถึงระดับวิศวกร", fill=(255, 220, 70), font=_font(48))

    draw.text((140, 1010), "เข้าใจง่าย", fill="white", font=_font(44))
    draw.text((140, 1080), "ใช้ได้จริง", fill="white", font=_font(44))
    draw.text((140, 1150), "ค่อย ๆ ไต่ระดับไปด้วยกัน", fill="white", font=_font(44))

    draw.line((160, 1380, 820, 1380), fill="yellow", width=8)
    draw.polygon([(760, 1345), (840, 1380), (760, 1415)], fill="red")
    draw.text((160, 1450), "BEN Home & Electrical Academy", fill=(180, 210, 255), font=_font(32))

    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_generic(path, title, subtitle="อธิบายพื้นฐานแบบเข้าใจง่าย"):
    img, draw = _base_canvas(title)
    draw.rounded_rectangle((110, 520, 970, 1480), radius=40, outline="white", width=6)
    draw.text((180, 950), subtitle, fill="white", font=_font(48))
    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_series(path, title):
    img, draw = _base_canvas(title)
    y = 980
    draw.line((150, y, 350, y), fill="yellow", width=10)
    draw.rectangle((350, 920, 430, 1040), outline="white", width=6)
    draw.line((430, y, 620, y), fill="yellow", width=10)
    draw.rectangle((620, 920, 700, 1040), outline="white", width=6)
    draw.line((700, y, 900, y), fill="yellow", width=10)
    draw.text((330, 1060), "โหลด 1", fill="white", font=_font(34))
    draw.text((600, 1060), "โหลด 2", fill="white", font=_font(34))
    draw.polygon([(510, 930), (560, 980), (510, 1030)], fill="red")
    draw.text((130, 800), "กระแสไหลผ่านทีละตัว", fill=(255, 220, 70), font=_font(40))
    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_parallel(path, title):
    img, draw = _base_canvas(title)
    draw.line((220, 820, 220, 1320), fill="yellow", width=10)
    draw.line((820, 820, 820, 1320), fill="yellow", width=10)

    draw.line((220, 900, 420, 900), fill="yellow", width=10)
    draw.rectangle((420, 850, 500, 950), outline="white", width=6)
    draw.line((500, 900, 820, 900), fill="yellow", width=10)

    draw.line((220, 1150, 620, 1150), fill="yellow", width=10)
    draw.rectangle((620, 1100, 700, 1200), outline="white", width=6)
    draw.line((700, 1150, 820, 1150), fill="yellow", width=10)

    draw.polygon([(320, 860), (370, 900), (320, 940)], fill="red")
    draw.polygon([(320, 1110), (370, 1150), (320, 1190)], fill="red")
    draw.text((140, 760), "กระแสแยกได้หลายทาง", fill=(255, 220, 70), font=_font(40))
    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_current_flow(path, title):
    img, draw = _base_canvas(title)
    y = 980
    draw.line((150, y, 900, y), fill="yellow", width=10)
    for x in [280, 430, 580, 730]:
        draw.polygon([(x, y - 35), (x + 55, y), (x, y + 35)], fill="red")
    draw.text((140, 830), "ลูกศรแสดงทิศทางการไหลของกระแส", fill=(255, 220, 70), font=_font(40))
    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_voltage(path, title):
    img, draw = _base_canvas(title)
    draw.rectangle((260, 760, 420, 1180), outline="white", width=6)
    draw.text((285, 1200), "แหล่งจ่าย", fill="white", font=_font(34))
    draw.line((420, 970, 840, 970), fill="yellow", width=10)
    draw.polygon([(700, 930), (760, 970), (700, 1010)], fill="red")
    draw.text((470, 860), "แรงดันผลักให้กระแสไหล", fill=(255, 220, 70), font=_font(40))
    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_meter(path, title):
    img, draw = _base_canvas(title)
    draw.rounded_rectangle((320, 700, 760, 1260), radius=40, outline="white", width=6)
    draw.rectangle((390, 800, 690, 980), outline=(100, 255, 100), width=6)
    draw.text((450, 860), "220V", fill=(100, 255, 100), font=_font(60))
    draw.text((380, 1060), "มัลติมิเตอร์", fill="white", font=_font(44))
    draw.line((300, 1320, 450, 1500), fill="red", width=8)
    draw.line((780, 1320, 630, 1500), fill="black", width=8)
    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_breaker(path, title):
    img, draw = _base_canvas(title)
    draw.line((160, 980, 420, 980), fill="yellow", width=10)
    draw.rectangle((420, 860, 620, 1100), outline="white", width=6)
    draw.line((620, 980, 900, 980), fill="yellow", width=10)
    draw.line((500, 920, 560, 860), fill="red", width=8)
    draw.text((400, 1140), "เบรกเกอร์", fill="white", font=_font(40))
    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_transformer(path, title):
    img, draw = _base_canvas(title)
    draw.arc((260, 760, 420, 1160), start=90, end=270, fill="white", width=6)
    draw.arc((360, 760, 520, 1160), start=90, end=270, fill="white", width=6)
    draw.arc((560, 760, 720, 1160), start=-90, end=90, fill="white", width=6)
    draw.arc((660, 760, 820, 1160), start=-90, end=90, fill="white", width=6)
    draw.line((540, 720, 540, 1200), fill=(255, 220, 70), width=8)
    draw.text((350, 1280), "หม้อแปลงไฟฟ้า", fill="white", font=_font(44))
    _draw_mascot(img)
    _footer(draw)
    img.save(path)


def draw_for_topic(topic_type, path, title):
    if title.startswith("เปิดตัว"):
        return draw_intro(path, title)
    if topic_type == "series":
        return draw_series(path, title)
    if topic_type == "parallel":
        return draw_parallel(path, title)
    if topic_type == "current_flow":
        return draw_current_flow(path, title)
    if topic_type in ["voltage", "vaw", "power", "ohm", "acdc"]:
        return draw_voltage(path, title)
    if topic_type in ["meter", "meter_voltage", "meter_ohm", "meter_current"]:
        return draw_meter(path, title)
    if topic_type in ["breaker", "fuse", "ground", "shock", "plug", "switch"]:
        return draw_breaker(path, title)
    if topic_type in ["transformer", "pf", "industrial", "three_phase"]:
        return draw_transformer(path, title)
    return draw_generic(path, title)
