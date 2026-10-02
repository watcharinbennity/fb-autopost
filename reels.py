"""
สร้างคลิป Reels 9:16 อัตโนมัติจากสินค้า Shopee
- Claude เขียนข้อความบนจอ + เสียงพากย์ + แคปชัน
- Google Cloud Text-to-Speech พากย์เสียงไทย (ถ้ามี GOOGLE_TTS_API_KEY) ไม่มีก็เป็นคลิปเงียบ
- ffmpeg ตัดต่อ: พื้นหลังเบลอ, รูปสินค้า, ซูมช้า ๆ, ตัวหนังสือไทย, เฟดระหว่างฉาก
"""
import base64
import json
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Optional

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import engine

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(HERE, "assets", "fonts", "NotoSansThai.ttf")
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "").strip()
TTS_VOICE = os.getenv("TTS_VOICE", "").strip()  # ว่าง = เลือกเสียงไทยที่ดีที่สุดอัตโนมัติ

PAGE_STYLE = {
    "ben": {"name": "BEN Home & Electrical", "accent": (255, 176, 32)},
    "smart": {"name": "SmartHome Thailand", "accent": (56, 189, 248)},
}

EMOJI_RE = re.compile("[\U0001F000-\U0001FFFF☀-➿️‍]+")


# ---------------------------------------------------------------- script
def make_script(product: Dict, mode: str) -> Dict:
    page = PAGE_STYLE[mode]["name"]
    prompt = f"""
ทำสคริปต์คลิป Reels ภาษาไทย ยาวประมาณ 12-15 วินาที สำหรับเพจ {page}

สินค้า: {product['title']}
คะแนนรีวิว: {product['rating']:.1f}
ขายแล้ว: {int(product['sold']):,} ชิ้น

ตอบเป็น JSON อย่างเดียว ตามรูปแบบนี้:
{{"slides": ["...", "...", "...", "..."], "voiceover": "...", "caption": "..."}}

กติกา:
- slides = ข้อความบนจอ 4 ฉาก ฉากละไม่เกิน 28 ตัวอักษร ห้ามมีอีโมจิ
  ฉาก 1 hook ดึงความสนใจ / ฉาก 2-3 จุดเด่นจากชื่อสินค้า / ฉาก 4 ชวนกดลิงก์ในคอมเมนต์
- voiceover = บทพากย์ต่อเนื่อง 2-3 ประโยค อ่านจบใน 12 วินาที ภาษาพูดเป็นกันเอง ไม่มีอีโมจิ ไม่อ่านตัวเลขยาว ๆ
- caption = แคปชันโพสต์ 3-4 บรรทัด มีอีโมจิได้ ปิดด้วยแฮชแท็ก 2-3 อัน ห้ามใส่ลิงก์
- ห้ามแต่งสเปกหรือคุณสมบัติที่ไม่มีในชื่อสินค้า ห้ามใส่ราคา ห้ามเร่งให้รีบซื้อ ห้ามชวนทักแชท
- ภาษาไทยถูกต้อง เป็นธรรมชาติ
""".strip()
    raw = engine.ai_write(
        "คุณเป็นครีเอเตอร์ทำคลิปรีวิวสินค้าสั้น ๆ ภาษาไทย ตอบเป็น JSON ที่ถูกต้องเท่านั้น",
        prompt,
        temperature=0.8,
        max_tokens=1200,
    )
    data = None
    if raw:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception as e:
                print("REELS SCRIPT JSON ERROR:", e, flush=True)
    if not (isinstance(data, dict) and isinstance(data.get("slides"), list) and len(data["slides"]) >= 2):
        data = fallback_script(product, mode)
        data["source"] = "template"
    else:
        data["source"] = "claude"
    data["slides"] = [EMOJI_RE.sub("", str(s)).strip() for s in data["slides"][:5] if str(s).strip()]
    data["voiceover"] = EMOJI_RE.sub("", str(data.get("voiceover", ""))).strip()
    data["caption"] = str(data.get("caption", "")).strip()
    return data


def fallback_script(product: Dict, mode: str) -> Dict:
    short = product["title"][:40]
    return {
        "slides": [
            "ของดีที่ควรมีติดบ้าน" if mode == "ben" else "ของใช้สมาร์ทโฮมน่าใช้",
            short,
            f"รีวิว {product['rating']:.1f} ขายแล้ว {int(product['sold']):,} ชิ้น",
            "กดดูลิงก์ในคอมเมนต์",
        ],
        "voiceover": f"ตัวนี้คือ {short} รีวิวดี คนซื้อเยอะ สนใจกดดูลิงก์ในคอมเมนต์ได้เลย",
        "caption": f"{product['title']}\n⭐ รีวิว {product['rating']:.1f} | ขายแล้ว {int(product['sold']):,} ชิ้น",
    }


# ---------------------------------------------------------------- voice
def pick_voice() -> str:
    if TTS_VOICE:
        return TTS_VOICE
    try:
        res = requests.get(
            "https://texttospeech.googleapis.com/v1/voices",
            params={"languageCode": "th-TH", "key": GOOGLE_TTS_API_KEY},
            timeout=30,
        )
        names = [v["name"] for v in res.json().get("voices", [])]
    except Exception as e:
        print("TTS VOICES ERROR:", e, flush=True)
        names = []
    for kind in ("Chirp3-HD", "Neural2", "Standard"):
        for n in sorted(names):
            if kind in n:
                return n
    return names[0] if names else "th-TH-Standard-A"


def synthesize(text: str, out_path: str) -> Optional[str]:
    if not GOOGLE_TTS_API_KEY or not text:
        return None
    voice = pick_voice()
    try:
        res = requests.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            params={"key": GOOGLE_TTS_API_KEY},
            json={
                "input": {"text": text},
                "voice": {"languageCode": "th-TH", "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "sampleRateHertz": 44100},
            },
            timeout=60,
        )
        data = res.json()
        if res.status_code != 200 or "audioContent" not in data:
            msg = str((data.get("error") or {}).get("message"))[:200]
            print("TTS ERROR:", res.status_code, msg, flush=True)
            engine.annotate("warning", "TTS", f"{res.status_code} {msg}")
            return None
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(data["audioContent"]))
        print("TTS OK:", voice, flush=True)
        return out_path
    except Exception as e:
        print("TTS EXCEPTION:", e, flush=True)
        return None


def media_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- frames
def font(size: int, weight: bytes = b"Bold") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT_PATH, size, layout_engine=ImageFont.Layout.RAQM)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def wrap(draw: ImageDraw.ImageDraw, text: str, f, max_w: int) -> List[str]:
    """ตัดบรรทัดตามความกว้างจริง (ภาษาไทยไม่มีช่องว่าง จึงตัดเป็นตัวอักษร
    แต่ไม่แยกสระ/วรรณยุกต์ออกจากพยัญชนะ)"""
    lines, cur = [], ""
    tokens = re.findall(r"\S+\s*|\s+", text)
    for tok in tokens:
        if draw.textlength(cur + tok, font=f) <= max_w:
            cur += tok
            continue
        if cur.strip():
            lines.append(cur.rstrip())
            cur = ""
        if draw.textlength(tok, font=f) <= max_w:
            cur = tok
            continue
        for ch in tok:  # คำยาวเกิน: ตัดทีละตัว ไม่ตัดก่อนสระ/วรรณยุกต์ที่เป็น combining
            if cur and draw.textlength(cur + ch, font=f) > max_w and not is_thai_mark(ch):
                lines.append(cur.rstrip())
                cur = ""
            cur += ch
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


def is_thai_mark(ch: str) -> bool:
    o = ord(ch)
    return o == 0x0E31 or 0x0E33 <= o <= 0x0E3A or 0x0E47 <= o <= 0x0E4E


def fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    r = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * r) + 1, int(img.height * r) + 1), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def fit_contain(img: Image.Image, w: int, h: int) -> Image.Image:
    r = min(w / img.width, h / img.height)
    return img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.LANCZOS)


def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def base_frame(product_img: Image.Image, mode: str) -> Image.Image:
    accent = PAGE_STYLE[mode]["accent"]
    bg = fit_cover(product_img.convert("RGB"), W, H).filter(ImageFilter.GaussianBlur(45))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (10, 12, 18)), 0.55).convert("RGBA")

    card = fit_contain(product_img.convert("RGB"), 900, 900)
    pad = Image.new("RGB", (card.width + 40, card.height + 40), (255, 255, 255))
    pad.paste(card, (20, 20))
    pad = rounded(pad, 36)
    shadow = Image.new("RGBA", (pad.width + 60, pad.height + 60), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((30, 40, pad.width + 30, pad.height + 40), radius=40, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    cx, cy = (W - pad.width) // 2, 300 + (900 + 40 - pad.height) // 2
    bg.alpha_composite(shadow, (cx - 30, cy - 30))
    bg.alpha_composite(pad, (cx, cy))

    d = ImageDraw.Draw(bg)
    f = font(40, b"SemiBold")
    name = PAGE_STYLE[mode]["name"]
    tw = d.textlength(name, font=f)
    d.rounded_rectangle(((W - tw) / 2 - 34, 120, (W + tw) / 2 + 34, 200), radius=40, fill=(*accent, 255))
    d.text((W / 2, 160), name, font=f, fill=(15, 15, 15), anchor="mm")
    return bg


def slide_frame(base: Image.Image, text: str, mode: str, idx: int, total: int) -> Image.Image:
    accent = PAGE_STYLE[mode]["accent"]
    img = base.copy()
    d = ImageDraw.Draw(img)
    f = font(84 if len(text) <= 18 else 72)
    lines = wrap(d, text, f, W - 160)[:3]
    lh = int(f.size * 1.45)
    block_h = lh * len(lines) + 80
    top = 1330 + max(0, (420 - block_h) // 2)
    panel = Image.new("RGBA", (W - 80, block_h), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((0, 0, W - 80, block_h), radius=40, fill=(0, 0, 0, 165))
    img.alpha_composite(panel, (40, top))
    d.rounded_rectangle((40, top, 52, top + block_h), radius=6, fill=(*accent, 255))
    y = top + 40 + lh // 2
    for ln in lines:
        d.text((W / 2, y), ln, font=f, fill=(255, 255, 255), anchor="mm")
        y += lh
    # จุดบอกลำดับฉาก
    for i in range(total):
        x = W / 2 + (i - (total - 1) / 2) * 34
        d.ellipse((x - 8, 1820 - 8, x + 8, 1820 + 8), fill=(*accent, 255) if i == idx else (255, 255, 255, 110))
    return img.convert("RGB")


# ---------------------------------------------------------------- video
def build_video(frames: List[str], audio: Optional[str], out_path: str, total_sec: float) -> str:
    n = len(frames)
    fade = 0.4
    seg = (total_sec + fade * (n - 1)) / n
    frames_per = int(seg * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for fr in frames:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{seg:.3f}", "-i", fr]
    if audio:
        cmd += ["-i", audio]
    else:
        cmd += ["-f", "lavfi", "-t", f"{total_sec:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    filt = []
    for i in range(n):
        filt.append(
            f"[{i}:v]scale={W*2}:{H*2},zoompan=z='min(1+0.0009*on,1.08)':d={frames_per}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},setsar=1,format=yuv420p[v{i}]"
        )
    last = "v0"
    for i in range(1, n):
        offset = i * (seg - fade)
        filt.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={offset:.3f}[x{i}]")
        last = f"x{i}"
    a_idx = n
    filt.append(f"[{a_idx}:a]aresample=44100,apad[aout]")
    cmd += [
        "-filter_complex", ";".join(filt),
        "-map", f"[{last}]", "-map", "[aout]",
        "-t", f"{total_sec:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def download_image(url: str, path: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def make_reel(product: Dict, mode: str, out_dir: str, image_path: Optional[str] = None) -> Dict:
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix=f"reel_{mode}_")
    img_path = image_path or download_image(product["image"], os.path.join(work, "product.jpg"))
    script = make_script(product, mode)

    voice = synthesize(script["voiceover"], os.path.join(work, "voice.mp3"))
    voice_sec = media_duration(voice) if voice else 0.0
    total = min(30.0, max(12.0, voice_sec + 1.2))

    base = base_frame(Image.open(img_path), mode)
    frames = []
    for i, text in enumerate(script["slides"]):
        p = os.path.join(work, f"slide{i}.png")
        slide_frame(base, text, mode, i, len(script["slides"])).save(p)
        frames.append(p)

    out = os.path.join(out_dir, f"reel_{mode}_{product['itemid']}.mp4")
    build_video(frames, voice, out, total)
    print(f"REEL OK ({mode}): {out} {total:.1f}s voice={'yes' if voice else 'no'} script={script['source']}", flush=True)
    return {"path": out, "script": script, "seconds": total, "voice": bool(voice), "cover": frames[0]}
