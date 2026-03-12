import os
import textwrap
import subprocess
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1920


def _find_font():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


FONT_PATH = _find_font()


def _font(size: int):
    if FONT_PATH:
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_text(text: str, width_chars: int = 18):
    return textwrap.fill(text, width=width_chars)


def make_slide(out_path: str, title: str, body: str, mascot_path: str):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (8, 18, 34))
    draw = ImageDraw.Draw(canvas)

    title_font = _font(56)
    body_font = _font(64)
    brand_font = _font(40)
    footer_font = _font(34)

    # กรอบบน
    draw.rounded_rectangle((40, 40, 1040, 180), radius=28, fill=(18, 34, 58))
    draw.text((70, 78), "BEN Home & Electrical", fill=(255, 255, 255), font=brand_font)

    # รูปช่างเบน
    if os.path.exists(mascot_path):
        mascot = Image.open(mascot_path).convert("RGBA")
        mascot.thumbnail((520, 520))
        mx = (WIDTH - mascot.width) // 2
        my = 210
        canvas.paste(mascot, (mx, my), mascot)
    else:
        draw.text((80, 250), "ไม่พบไฟล์ chang_ben.png", fill=(255, 120, 120), font=_font(32))

    # หัวข้อ
    draw.text((70, 760), title, fill=(255, 210, 70), font=title_font)

    # เนื้อหา
    wrapped = _fit_text(body, width_chars=16)
    draw.multiline_text(
        (70, 900),
        wrapped,
        fill=(255, 255, 255),
        font=body_font,
        spacing=16,
    )

    # footer
    draw.rounded_rectangle((40, 1760, 1040, 1860), radius=22, fill=(18, 34, 58))
    draw.text((70, 1790), "ช่างเบนสอนไฟฟ้า", fill=(180, 210, 255), font=footer_font)

    canvas.save(out_path)
    return out_path


def image_to_video(image_path: str, duration: float, out_path: str):
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path,
        "-t", str(duration),
        "-vf", f"scale={WIDTH}:{HEIGHT},format=yuv420p",
        "-r", "24",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def concat_videos(video_paths, out_path: str):
    list_file = "academy_concat.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for path in video_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def merge_audio(video_path: str, audio_path: str, out_path: str):
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def probe_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def build_intro_reel(
    mascot_path: str,
    audio_path: str,
    out_path: str = "academy_intro_final.mp4",
):
    total_duration = max(probe_duration(audio_path), 18.0)

    d1 = max(4.0, total_duration * 0.34)
    d2 = max(6.0, total_duration * 0.38)
    d3 = max(4.0, total_duration - d1 - d2)

    make_slide("intro1.png", "สวัสดีครับ", "ผมช่างเบน\nจาก BEN Home & Electrical", mascot_path)
    make_slide("intro2.png", "เราจะเรียนไฟฟ้า", "ตั้งแต่พื้นฐาน\nจนถึงระดับวิศวกร", mascot_path)
    make_slide("intro3.png", "เรียนไปด้วยกัน", "เข้าใจง่าย\nใช้ได้จริง", mascot_path)

    image_to_video("intro1.png", d1, "intro_v1.mp4")
    image_to_video("intro2.png", d2, "intro_v2.mp4")
    image_to_video("intro3.png", d3, "intro_v3.mp4")

    concat_videos(["intro_v1.mp4", "intro_v2.mp4", "intro_v3.mp4"], "academy_intro_silent.mp4")
    merge_audio("academy_intro_silent.mp4", audio_path, out_path)

    for p in [
        "intro1.png", "intro2.png", "intro3.png",
        "intro_v1.mp4", "intro_v2.mp4", "intro_v3.mp4",
        "academy_intro_silent.mp4", "academy_concat.txt"
    ]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    return out_path
