import os
import textwrap
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1920


def download_image(url, out_path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path


def make_text_slide(text, out_path, title="BEN Home & Electrical"):
    img = Image.new("RGB", (WIDTH, HEIGHT), color=(12, 12, 12))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("DejaVuSans.ttf", 46)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 68)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 42)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    wrapped = textwrap.fill(text, width=18)

    draw.text((60, 100), title, fill=(255, 255, 255), font=title_font)
    draw.multiline_text((60, 520), wrapped, fill=(255, 255, 255), font=body_font, spacing=18)
    draw.text((60, 1650), "เช็กราคาล่าสุดที่ลิงก์ด้านล่าง", fill=(255, 220, 80), font=small_font)

    img.save(out_path)
    return out_path


def fit_product_image(in_path, out_path):
    img = Image.open(in_path).convert("RGB")
    bg = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))

    ratio = min(WIDTH / img.width, HEIGHT / img.height)
    new_size = (int(img.width * ratio), int(img.height * ratio))
    img = img.resize(new_size)

    x = (WIDTH - img.width) // 2
    y = (HEIGHT - img.height) // 2
    bg.paste(img, (x, y))
    bg.save(out_path)
    return out_path


def make_video_from_image(image_path, duration, out_path):
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-t", str(duration),
        "-vf", f"scale={WIDTH}:{HEIGHT},format=yuv420p",
        "-r", "24",
        "-pix_fmt", "yuv420p",
        out_path
    ]
    subprocess.run(cmd, check=True)
    return out_path


def concat_videos(video_list, out_path):
    list_file = "inputs.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for v in video_list:
            f.write(f"file '{os.path.abspath(v)}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        out_path
    ]
    subprocess.run(cmd, check=True)
    return out_path


def create_product_reel(image_url, product_name, out_path="reel.mp4"):
    raw_img = "product_raw.jpg"
    product_slide = "product_slide.jpg"
    intro_slide = "intro.jpg"
    outro_slide = "outro.jpg"

    intro_video = "intro.mp4"
    product_video = "product.mp4"
    outro_video = "outro.mp4"

    download_image(image_url, raw_img)
    fit_product_image(raw_img, product_slide)

    make_text_slide(product_name, intro_slide, title="BEN Home & Electrical")
    make_text_slide("ของน่าใช้สำหรับบ้านและงานไฟฟ้า", outro_slide, title="BEN Home & Electrical")

    make_video_from_image(intro_slide, 2, intro_video)
    make_video_from_image(product_slide, 4, product_video)
    make_video_from_image(outro_slide, 2, outro_video)

    concat_videos([intro_video, product_video, outro_video], out_path)

    for p in [
        raw_img, product_slide, intro_slide, outro_slide,
        intro_video, product_video, outro_video, "inputs.txt"
    ]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    return out_path
