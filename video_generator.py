import os
import textwrap
import requests
from moviepy.editor import ImageClip, ColorClip, CompositeVideoClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1920
FPS = 24


def _download_image(url: str, path: str) -> str:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def _make_text_image(text: str, path: str, width: int = WIDTH, height: int = HEIGHT) -> str:
    img = Image.new("RGB", (width, height), color=(12, 12, 12))
    draw = ImageDraw.Draw(img)

    # ใช้ default font ถ้าไม่มีฟอนต์ไทยใน runner
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 62)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 42)
    except Exception:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    title = "BEN Home & Electrical"
    body = textwrap.fill(text, width=18)
    footer = "เช็กราคาล่าสุดที่ลิงก์ด้านล่าง"

    draw.text((60, 120), title, fill=(255, 255, 255), font=small_font)
    draw.multiline_text((60, 520), body, fill=(255, 255, 255), font=font, spacing=18)
    draw.text((60, 1600), footer, fill=(255, 220, 80), font=small_font)

    img.save(path)
    return path


def create_product_reel(image_url: str, product_name: str, output_path: str = "reel.mp4") -> str:
    product_img = "tmp_product.jpg"
    intro_img = "tmp_intro.jpg"
    outro_img = "tmp_outro.jpg"

    _download_image(image_url, product_img)
    _make_text_image(product_name, intro_img)
    _make_text_image("ของน่าใช้สำหรับบ้านและงานไฟฟ้า", outro_img)

    intro = ImageClip(intro_img).set_duration(2.2)
    product = ImageClip(product_img).resize(height=HEIGHT).set_position("center")
    bg = ColorClip(size=(WIDTH, HEIGHT), color=(0, 0, 0), duration=4.6)
    product_scene = CompositeVideoClip([bg, product.set_duration(4.6)], size=(WIDTH, HEIGHT))
    outro = ImageClip(outro_img).set_duration(2.2)

    video = concatenate_videoclips([intro, product_scene, outro], method="compose")
    video.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio=False,
        preset="medium",
        threads=2,
        logger=None
    )

    for p in [product_img, intro_img, outro_img]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    return output_path
