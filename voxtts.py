"""
เสียงพากย์แบบเดียวกับคลิปสอนไฟฟ้าบน TikTok: VoxCPM (โคลนเสียงจาก assets/voice/ben_ref.ogg)
ผ่าน Hugging Face Space สาธารณะ แล้วตรวจคำที่พูดด้วย Whisper ภาษาไทย (ถอดเสียงกลับเป็นข้อความ)
- สร้างทีละท่อน ท่อนไหนถอดเสียงแล้วไม่ตรงบท จะสร้างใหม่ (สูงสุด VOX_TRIES ครั้ง) แล้วเลือกตัวที่ตรงที่สุด
- ถ้าท่อนไหนยังไม่ผ่านเกณฑ์ หรือเว็บล่ม คืน None ให้ระบบไปใช้เสียงสำรอง
"""
import json
import os
import re
import subprocess
import tempfile
import time
from typing import List, Optional, Tuple

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
VOX = os.getenv("VOX_SPACE", "https://openbmb-voxcpm-demo.hf.space").rstrip("/")
ASR = os.getenv("ASR_SPACE", "https://biodatlab-whisper-thai-demo.hf.space").rstrip("/")
REF_PATH = os.getenv("VOX_REF", os.path.join(HERE, "assets", "voice", "ben_ref.ogg"))
TRIES = int(os.getenv("VOX_TRIES", "4"))
MAX_CER = float(os.getenv("VOX_MAX_CER", "0"))  # 0 = ถอดเสียงแล้วต้องตรงบททุกคำ (หลังปรับรูปแบบการเขียน)
TEMPO = os.getenv("VOX_TEMPO", "1.0")
TIMEOUT = 240
BUDGET = int(os.getenv("VOX_BUDGET_SEC", "600"))  # ใช้เวลาเกินนี้ต่อคลิป = เลิกแล้วใช้เสียงสำรอง

# คำที่ VoxCPM อ่านไม่ชัด (เรียนรู้จากคลิป TikTok ตอน 1-01/1-02): เขียนบทเสียงให้อ่านถูก
SPEAK_FIX = [
    (re.compile(r"สรุป"), "สะหรุบ"),
    (re.compile(r"เหมือน(?!กับ)"), "เหมือนกับ"),
]
# คำที่เขียนแทนแล้ว ต้องแปลงกลับตอนเทียบผลถอดเสียง
CHECK_FIX = [("สะหรุบ", "สรุป"), ("WiFi", "ไวไฟ"), ("Wi-Fi", "ไวไฟ"), ("wifi", "ไวไฟ"), ("USB", "ยูเอสบี"),
             ("ลิงค์", "ลิงก์"), ("โซลาร์", "โซล่า")]


def log(*a):
    print("VOX:", *a, flush=True)


def _annotate(level: str, title: str, msg: str):
    try:
        import engine
        engine.annotate(level, title, msg)
    except Exception:
        pass


def speak_text(text: str) -> str:
    for rx, rep in SPEAK_FIX:
        text = rx.sub(rep, text)
    return text


THAI_DIGITS = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]


LETTERS = {"A": "เอ", "B": "บี", "C": "ซี", "D": "ดี", "E": "อี", "F": "เอฟ", "G": "จี", "H": "เอช", "I": "ไอ",
           "J": "เจ", "K": "เค", "L": "แอล", "M": "เอ็ม", "N": "เอ็น", "O": "โอ", "P": "พี", "Q": "คิว", "R": "อาร์",
           "S": "เอส", "T": "ที", "U": "ยู", "V": "วี", "W": "ดับเบิลยู", "X": "เอ็กซ์", "Y": "วาย", "Z": "แซด"}
WORDS = {"solar cell": "โซล่าเซลล์", "solar": "โซล่า", "wifi": "ไวไฟ", "wi-fi": "ไวไฟ", "usb": "ยูเอสบี",
         "led": "แอลอีดี", "cctv": "ซีซีทีวี", "bluetooth": "บลูทูธ", "app": "แอป", "smart": "สมาร์ท",
         "online": "ออนไลน์", "battery": "แบตเตอรี่", "ok": "โอเค"}


def thai_number(num: str) -> str:
    """อ่านจำนวนเต็มเป็นคำไทย เช่น 30000 -> สามหมื่น, 21 -> ยี่สิบเอ็ด (เลขขึ้นต้นด้วย 0 อ่านทีละหลัก)"""
    if not num.isdigit():
        return num
    if len(num) > 1 and num.startswith("0") or len(num) > 12:
        return "".join(THAI_DIGITS[int(c)] for c in num)
    n = int(num)
    if n == 0:
        return "ศูนย์"
    units = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน"]

    def below_million(x: int) -> str:
        out, digits = "", str(x)
        for i, ch in enumerate(digits):
            d, pos = int(ch), len(digits) - i - 1
            if d == 0:
                continue
            if pos == 1 and d == 1:
                w = "สิบ"
            elif pos == 1 and d == 2:
                w = "ยี่สิบ"
            elif pos == 0 and d == 1 and len(digits) > 1:
                w = "เอ็ด"
            else:
                w = THAI_DIGITS[d] + units[pos]
            out += w
        return out

    if n >= 1_000_000:
        return below_million(n // 1_000_000) + "ล้าน" + (below_million(n % 1_000_000) if n % 1_000_000 else "")
    return below_million(n)


def thai_only(s: str) -> str:
    # ระบบถอดเสียงชอบเขียนคำทับศัพท์เป็นภาษาอังกฤษ แปลงกลับเป็นคำไทยก่อนเทียบ
    low = s.lower()
    for en, th in WORDS.items():
        low = re.sub(rf"(?<![a-z]){re.escape(en)}(?![a-z])", th, low)
    s = re.sub(r"(?<![A-Za-z])([A-Za-z]{1,3})(?![A-Za-z])",
               lambda m: "".join(LETTERS.get(c.upper(), c) for c in m.group(1)), low)
    s = s.replace("โซล่าร์", "โซล่า").replace("โซลาร์", "โซล่า").replace("ลิงค์", "ลิงก์")
    # ระบบถอดเสียงมักเขียนตัวเลขเป็นเลขอารบิก: แปลงทีละหลักเป็นคำไทย ทั้งบทและที่ได้ยิน
    s = re.sub(r"\d[\d,]*", lambda m: thai_number(m.group().replace(",", "")), s)
    for a, b in CHECK_FIX:
        s = s.replace(a, b)
    s = re.sub(r"[^฀-๿]", "", s)
    # ตัวการันต์ไม่ออกเสียง (เลนส์ = เลน, ลิงก์ = ลิง) ตัดทิ้งทั้งตัวอักษรและเครื่องหมาย
    s = re.sub("[ก-ฮ][ัิุ]?์", "", s)
    return s.replace("ๆ", "")


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[len(b)]


def cer(expected: str, heard: str) -> float:
    e, h = thai_only(expected), thai_only(heard)
    if not e:
        return 0.0
    return lev(e, h) / len(e)


def split_lines(text: str, min_len: int = 18, max_len: int = 70) -> List[str]:
    """ตัดบทเป็นท่อนตามช่องว่าง (ภาษาไทยเว้นวรรคระหว่างประโยค) รวมท่อนสั้นเข้าด้วยกัน"""
    parts = [p for p in re.split(r"\s+", text.strip()) if p]
    out: List[str] = []
    for p in parts:
        if out and (len(out[-1]) < min_len or len(p) < 6) and len(out[-1]) + len(p) + 1 <= max_len:
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def call(base: str, api: str, data: list) -> list:
    r = requests.post(f"{base}/gradio_api/call/{api}", json={"data": data}, timeout=60)
    r.raise_for_status()
    eid = r.json()["event_id"]
    t = requests.get(f"{base}/gradio_api/call/{api}/{eid}", timeout=TIMEOUT).text
    if "event: complete" not in t:
        raise RuntimeError(t[-300:].replace("\n", " "))
    return json.loads(t.split("data: ")[-1])


def upload_ref() -> dict:
    with open(REF_PATH, "rb") as f:
        r = requests.post(f"{VOX}/gradio_api/upload", files={"files": ("ref.ogg", f, "audio/ogg")}, timeout=60)
    r.raise_for_status()
    return {"path": r.json()[0], "meta": {"_type": "gradio.FileData"}, "orig_name": "ref.ogg"}


def upload_asr(path: str) -> str:
    with open(path, "rb") as f:
        r = requests.post(f"{ASR}/gradio_api/upload", files={"files": (os.path.basename(path), f, "audio/mpeg")},
                          timeout=60)
    r.raise_for_status()
    return r.json()[0]


def transcribe(url: str = "", path: str = "") -> str:
    """ถอดเสียงเป็นข้อความ (url = ไฟล์ที่อยู่บนเว็บแล้ว, path = ไฟล์ในเครื่อง จะอัปโหลดให้)"""
    for attempt in range(2):
        try:
            if url:
                fd = {"path": url, "url": url, "meta": {"_type": "gradio.FileData"}, "orig_name": "a.mp3"}
            else:
                fd = {"path": upload_asr(path), "meta": {"_type": "gradio.FileData"}, "orig_name": "a.mp3"}
            res = call(ASR, "transcribe", [None, fd])
            return str(res[0])
        except Exception as e:
            log("ASR error:", str(e)[:200])
            time.sleep(5)
    return ""


# ---------------------------------------------------------------- ตัวสร้างเสียงแต่ละแบบ (ทีละท่อน)
EDGE_VOICES = {"ben": os.getenv("EDGE_VOICE_BEN", "th-TH-NiwatNeural"),
               "smart": os.getenv("EDGE_VOICE_SMART", "th-TH-PremwadeeNeural")}
ENGINE_TRIES = {"vox": TRIES, "edge": 3, "gtts": 1}
ENGINE_TEMPO = {"vox": TEMPO, "edge": "1.0", "gtts": os.getenv("GTTS_TEMPO", "1.35")}


def make_vox(ref: dict):
    settings = [(2, False), (2.5, True), (3, False)]

    def gen(line: str, k: int, path: str) -> str:
        cfg, norm = settings[k % len(settings)]
        g = call(VOX, "generate", [speak_text(line), "", ref, False, "", cfg, norm, False])
        url = g[0]["url"]
        with open(path, "wb") as f:
            f.write(requests.get(url, timeout=120).content)
        return url
    return gen


def make_edge(mode: str):
    import asyncio
    import edge_tts
    voice = EDGE_VOICES.get(mode, EDGE_VOICES["ben"])
    rates = ["+0%", "-8%", "-15%"]

    def gen(line: str, k: int, path: str) -> str:
        async def run():
            await edge_tts.Communicate(line, voice, rate=rates[k % len(rates)]).save(path)
        asyncio.run(run())
        if os.path.getsize(path) < 1000:
            raise RuntimeError("edge empty")
        return ""
    return gen


def make_gtts():
    from gtts import gTTS

    def gen(line: str, k: int, path: str) -> str:
        gTTS(text=line, lang="th").save(path)
        return ""
    return gen


def gen_line(gen, line: str, work: str, idx: int, name: str) -> Tuple[Optional[str], float, str]:
    """สร้างเสียงท่อนเดียว แล้วถอดเสียงตรวจ คืน (ไฟล์, ค่าคลาดเคลื่อน, ข้อความที่ได้ยิน) ของตัวที่ดีที่สุด"""
    best: Tuple[Optional[str], float, str] = (None, 9.0, "")
    for k in range(ENGINE_TRIES.get(name, 1)):
        path = os.path.join(work, f"{name}_{idx}_{k}.mp3")
        try:
            url = gen(line, k, path)
        except Exception as e:
            log(f"{name} gen error line {idx} try {k}:", str(e)[:200])
            time.sleep(3)
            continue
        heard = transcribe(url=url) if url else transcribe(path=path)
        score = cer(line, heard) if heard else 9.0  # ถอดเสียงไม่ได้ = ตรวจไม่ได้ = ไม่ผ่าน
        log(f"{name} line {idx} try {k}: cer={score:.2f} | บท: {line} | ได้ยิน: {heard}")
        if score < best[1]:
            best = (path, score, heard)
        if score <= MAX_CER:
            break
    return best


def asr_bias(line: str, heard: str, work: str, idx: int, mode: str, name: str) -> bool:
    """ท่อนที่คลาดเล็กน้อย: ลองให้เสียงอื่นอีก 2 แบบพูดประโยคเดียวกัน ถ้าระบบถอดเสียงได้คำเดียวกันเป๊ะทุกตัว
    แปลว่าระบบถอดเสียงฟังผิดเอง (เช่น "ความจุ สาม" -> "ความจุดสาม") ไม่ใช่เสียงพูดผิด"""
    if not heard or lev(thai_only(line), thai_only(heard)) > 2:
        return False
    others = [n for n in ("vox", "edge", "gtts") if n != name][:2]
    target = thai_only(heard)
    for other in others:
        try:
            gen = make_edge(mode) if other == "edge" else make_gtts() if other == "gtts" else make_vox(upload_ref())
            path = os.path.join(work, f"bias_{other}_{idx}.mp3")
            url = gen(line, 0, path)
            h2 = transcribe(url=url) if url else transcribe(path=path)
        except Exception as e:
            log("bias check error:", other, str(e)[:150])
            return False
        log(f"bias check {other}: {h2}")
        if thai_only(h2) != target:
            return False
    return True


def synthesize(text: str, out_path: str, name: str = "vox", mode: str = "ben") -> Optional[str]:
    """สร้างเสียงทั้งบทด้วยเครื่องยนต์ name ทุกท่อนต้องผ่านการถอดเสียงตรวจ ไม่งั้นคืน None"""
    lines = split_lines(text)
    if not lines:
        return None
    work = tempfile.mkdtemp(prefix=f"{name}_")
    try:
        if name == "vox":
            if not os.path.exists(REF_PATH):
                return None
            gen = make_vox(upload_ref())
        elif name == "edge":
            gen = make_edge(mode)
        else:
            gen = make_gtts()
    except Exception as e:
        _annotate("warning", f"VOICE fail {name}", f"เริ่มไม่ได้: {str(e)[:200]}")
        return None
    files, report = [], []
    t0 = time.time()
    for i, line in enumerate(lines):
        if time.time() - t0 > BUDGET:
            _annotate("warning", f"VOICE fail {name}", "\n".join(report) + "\n(ใช้เวลานานเกิน)")
            return None
        path, score, heard = gen_line(gen, line, work, i, name)
        report.append(f"{score:.2f} | บท: {line} | ได้ยิน: {heard}")
        if path and score > MAX_CER and asr_bias(line, heard, work, i, mode, name):
            report[-1] += " | ✓ เสียงอื่นอีก 2 แบบถูกถอดเป็นคำเดียวกันทุกตัว = ระบบถอดเสียงฟังผิดเอง ไม่ใช่เสียงพูดผิด"
            score = 0.0
        if not path or score > MAX_CER:
            _annotate("warning", f"VOICE fail {name}",
                      "\n".join(report) + ("" if path else "\n(สร้างเสียงไม่สำเร็จ)"))
            return None
        files.append(path)
    # ต่อท่อนด้วยช่วงเงียบ 0.2 วินาที
    inputs, filt = [], []
    for i, p in enumerate(files):
        inputs += ["-i", p]
        filt.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=mono,silenceremove=start_periods=1:"
                    f"start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,"
                    f"areverse,apad=pad_dur=0.2[a{i}]")
    tempo = ENGINE_TEMPO.get(name, "1.0")
    filt.append("".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1,atempo={tempo}[out]")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt),
                        "-map", "[out]", "-ar", "44100", "-b:a", "160k", out_path], check=True)
    except Exception as e:
        log("concat error:", e)
        return None
    _annotate("notice", f"VOICE check {name}", "\n".join(report))
    return out_path if os.path.getsize(out_path) > 1000 else None
