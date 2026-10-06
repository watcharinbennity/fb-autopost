import csv
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Generator, Optional
from urllib.parse import quote

import requests

MAX_ROWS = 250000
TIMEOUT = 30
POSTED_FILE = "posted.json"
REPLIED_FILE = "replied_comments.json"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()

PAGE_ID_2 = os.getenv("PAGE_ID_2", "").strip()
PAGE_ACCESS_TOKEN_2 = os.getenv("PAGE_ACCESS_TOKEN_2", "").strip()

SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()
SHOPEE_AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "").strip()
SHOPEE_SUB_ID_PREFIX = os.getenv("SHOPEE_SUB_ID_PREFIX", "fbbot").strip()


# Claude (Anthropic) — ใช้เขียนแคปชันและตอบคอมเมนต์ (ไม่มี key = ใช้แคปชันแม่แบบ)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5").strip()            # เขียนแคปชัน
CLAUDE_REPLY_MODEL = os.getenv("CLAUDE_REPLY_MODEL", "claude-haiku-4-5-20251001").strip()  # ตอบคอมเมนต์



def claude_once(use_model: str, system: str, prompt: str, temperature: float, max_tokens: int) -> str:
    body = {
        "model": use_model,
        # เผื่อ token ให้รุ่นที่คิดก่อนตอบ (thinking) ไม่ให้ใช้หมดก่อนได้ข้อความ
        "max_tokens": max(max_tokens, 4000),
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    if "-4-" in use_model:
        body["temperature"] = temperature
    for attempt in range(2):
        try:
            res = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
                timeout=90,
            )
            data = res.json()
        except Exception as e:
            print("CLAUDE EXCEPTION:", e, flush=True)
            annotate("warning", "Claude", f"{use_model}: {str(e)[:200]}")
            return ""

        if res.status_code == 200:
            blocks = data.get("content", []) or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
            if text:
                print(f"AI: claude ({use_model})", flush=True)
                return text
            info = f"{use_model}: empty text stop_reason={data.get('stop_reason')} blocks={[b.get('type') for b in blocks]}"
            print("CLAUDE EMPTY:", info, flush=True)
            annotate("warning", "Claude", info)
            return ""

        err = (data.get("error") or {}) if isinstance(data, dict) else {}
        msg = str(err.get("message"))
        if attempt == 0 and "temperature" in msg and "temperature" in body:
            body.pop("temperature")
            continue
        print(f"CLAUDE ERROR: {use_model} {res.status_code} {err.get('type')} {msg[:200]}", flush=True)
        annotate("warning", "Claude", f"{use_model} {res.status_code} {err.get('type')} {msg[:200]}")
        return ""
    return ""

def ai_write(system: str, prompt: str, temperature: float, max_tokens: int = 600, model: str = "") -> str:
    """ให้ Claude เขียนข้อความ; คืน "" ถ้าใช้ไม่ได้ (จะใช้ข้อความแม่แบบแทน)"""
    if ANTHROPIC_API_KEY:
        first = model or CLAUDE_MODEL
        chain = [first] + ([CLAUDE_REPLY_MODEL] if CLAUDE_REPLY_MODEL and CLAUDE_REPLY_MODEL != first else [])
        for use_model in chain:
            text = claude_once(use_model, system, prompt, temperature, max_tokens)
            if text:
                return text
    return ""

SHORTENER_BASE_URL = os.getenv(
    "SHORTENER_BASE_URL",
    "https://ben-shortener.bennity.workers.dev"
).strip()

AUTO_REPLY_COMMENTS = os.getenv("AUTO_REPLY_COMMENTS", "true").lower() == "true"
COMMENT_SCAN_LIMIT = int(os.getenv("COMMENT_SCAN_LIMIT", "20"))
MAX_REPLY_PER_RUN = int(os.getenv("MAX_REPLY_PER_RUN", "5"))

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
MIN_RATING = float(os.getenv("MIN_RATING", "4.0"))
MIN_SOLD = float(os.getenv("MIN_SOLD", "20"))
GRAPH = "https://graph.facebook.com/v25.0"
STATUS_FILE = "run_status.json"
IN_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"


def annotate(level: str, title: str, msg: str) -> None:
    """แสดงผลสรุปบนหน้า Actions (annotation) — ไม่ใส่ token/ลิงก์ยาว"""
    if not IN_ACTIONS:
        return
    msg = str(msg)[:900].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    title = title.replace(",", " ").replace("::", ":")
    print(f"::{level} title={title}::{msg}", flush=True)

PAGES = [
    {"mode": "ben", "name": "BEN Home & Electrical", "id": PAGE_ID, "token": PAGE_ACCESS_TOKEN},
    {"mode": "smart", "name": "SmartHome Thailand", "id": PAGE_ID_2, "token": PAGE_ACCESS_TOKEN_2},
]

# คอลัมน์ลิงก์ Affiliate ที่ feed อาจให้มาเอง (ถ้ามี จะใช้ก่อนการประกอบลิงก์เอง)
AFF_LINK_COLUMNS = ["product_short link", "product_short_link", "short_link", "offer_link", "affiliate_link"]


def graph_error(data) -> str:
    """คืนข้อความ error ของ Graph API (ไม่มี token) หรือ "" ถ้าไม่มี error"""
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        e = data["error"]
        return f"code={e.get('code')} sub={e.get('error_subcode')} type={e.get('type')} msg={str(e.get('message'))[:200]}"
    return ""


def safe_json(res) -> Dict:
    try:
        return res.json()
    except Exception:
        return {"error": {"code": res.status_code, "message": res.text[:200]}}


def check_page_token(page: Dict) -> bool:
    """ตรวจว่า token ยังใช้ได้และเป็นของเพจที่ถูกต้อง"""
    try:
        res = requests.get(f"{GRAPH}/me", params={"fields": "id,name", "access_token": page["token"]}, timeout=TIMEOUT)
        data = safe_json(res)
    except Exception as e:
        print(f"TOKEN CHECK EXCEPTION ({page['mode']}): {e}", flush=True)
        return False

    err = graph_error(data)
    if err:
        print(f"❌ TOKEN INVALID ({page['mode']}): {err}", flush=True)
        annotate("error", f"Token {page['mode']}", err)
        if "code=190" in err:
            print("   → Page Access Token หมดอายุ/ถูกยกเลิก ต้องสร้าง token ใหม่แล้วอัปเดต GitHub Secret", flush=True)
        return False

    if str(data.get("id")) != str(page["id"]):
        print(f"❌ TOKEN/PAGE MISMATCH ({page['mode']}): token เป็นของ '{data.get('name')}' ไม่ใช่ PAGE_ID ที่ตั้งไว้", flush=True)
        annotate("error", f"Token {page['mode']}", f"token เป็นของเพจ {data.get('name')} ไม่ตรง PAGE_ID")
        return False

    print(f"✅ TOKEN OK ({page['mode']}): {data.get('name')}", flush=True)
    annotate("notice", f"Token {page['mode']}", f"OK: {data.get('name')}")
    return True


def load_posted() -> Dict:
    default_data = {
        "ben": {"items": [], "images": [], "titles": []},
        "smart": {"items": [], "images": [], "titles": []},
    }

    if not os.path.exists(POSTED_FILE):
        return default_data

    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if not isinstance(raw, dict):
            return default_data

        for mode in ["ben", "smart"]:
            raw.setdefault(mode, {})
            raw[mode].setdefault("items", [])
            raw[mode].setdefault("images", [])
            raw[mode].setdefault("titles", [])

        return raw
    except Exception:
        return default_data


def save_posted(data: Dict) -> None:
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_replied() -> Dict:
    default_data = {"comments": []}

    if not os.path.exists(REPLIED_FILE):
        return default_data

    try:
        with open(REPLIED_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if not isinstance(raw, dict):
            return default_data

        raw.setdefault("comments", [])
        return raw
    except Exception:
        return default_data


def save_replied(data: Dict) -> None:
    with open(REPLIED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def mark_comment_replied(comment_id: str) -> None:
    data = load_replied()
    if comment_id not in data["comments"]:
        data["comments"].append(comment_id)
    save_replied(data)


def was_comment_replied(comment_id: str) -> bool:
    data = load_replied()
    return comment_id in data["comments"]


def normalize_image_key(image_url: str) -> str:
    if not image_url:
        return ""
    return image_url.strip().split("/")[-1].split("?")[0].lower()


def is_duplicate(posted_page_data: Dict, product_id: str, image_key: str, title: str) -> bool:
    if product_id in posted_page_data["items"]:
        return True

    if image_key and image_key in posted_page_data["images"]:
        return True

    head = title[:60].strip().lower()
    for old_title in posted_page_data["titles"]:
        if head and head == old_title[:60].strip().lower():
            return True

    return False


def mark_as_posted(page_mode: str, itemid: str, image_key: str, title: str) -> None:
    posted = load_posted()

    if itemid and itemid not in posted[page_mode]["items"]:
        posted[page_mode]["items"].append(itemid)

    if image_key and image_key not in posted[page_mode]["images"]:
        posted[page_mode]["images"].append(image_key)

    short_title = title[:100].strip()
    if short_title and short_title not in posted[page_mode]["titles"]:
        posted[page_mode]["titles"].append(short_title)

    save_posted(posted)


def to_float(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def norm_text(v) -> str:
    return str(v or "").strip()


def iter_csv_rows(url: str) -> Generator[Dict, None, None]:
    print("Streaming CSV...", flush=True)

    res = None
    for attempt, wait in enumerate((0, 45, 120)):
        if wait:
            print(f"CSV retry in {wait}s (attempt {attempt + 1})", flush=True)
            time.sleep(wait)
        res = requests.get(url, stream=True, timeout=(20, 120))
        if res.status_code in (429, 500, 502, 503, 504):
            print("CSV HTTP", res.status_code, flush=True)
            res.close()
            continue
        break
    with res:
        res.raise_for_status()

        lines = (
            line.decode("utf-8-sig", errors="ignore")
            for line in res.iter_lines()
            if line
        )

        reader = csv.DictReader(lines)

        for i, row in enumerate(reader, start=1):
            if i % 5000 == 0:
                print(f"streamed_rows={i}", flush=True)

            if i >= MAX_ROWS:
                print("Reached MAX_ROWS", flush=True)
                break

            yield row


def create_real_short_link(long_url: str, slug: str) -> str:
    if not long_url:
        return ""

    if not SHORTENER_BASE_URL:
        return long_url

    base = SHORTENER_BASE_URL.rstrip("/")
    create_url = f"{base}/create?target={quote(long_url, safe='')}&slug={quote(slug, safe='')}"

    try:
        res = requests.get(create_url, timeout=20)

        if res.status_code == 200:
            data = res.json()
            if data.get("ok") and data.get("short_url"):
                return data["short_url"]

        if res.status_code == 409:
            return f"{base}/{slug}"

        print("SHORTENER ERROR:", res.status_code, res.text[:300], flush=True)
        return long_url
    except Exception as e:
        print("SHORTENER EXCEPTION:", e, flush=True)
        return long_url


def build_shopee_affiliate_link(row: Dict, page_mode: str) -> str:
    landing_page = norm_text(row.get("product_link"))
    itemid = norm_text(row.get("itemid"))

    if not landing_page or not itemid or not SHOPEE_AFFILIATE_ID:
        return ""

    encoded = quote(landing_page, safe="")
    sub_id = f"{SHOPEE_SUB_ID_PREFIX}-{page_mode}-{itemid}"

    return (
        f"https://s.shopee.co.th/an_redir?"
        f"origin_link={encoded}"
        f"&affiliate_id={SHOPEE_AFFILIATE_ID}"
        f"&sub_id={sub_id}"
    )


def has_link_data(row: Dict) -> bool:
    if "affiliate_id=" in feed_affiliate_link(row):
        return True
    landing_page = norm_text(row.get("product_link"))
    itemid = norm_text(row.get("itemid"))
    return bool(landing_page and itemid and SHOPEE_AFFILIATE_ID)


def feed_affiliate_link(row: Dict) -> str:
    for col in AFF_LINK_COLUMNS:
        v = norm_text(row.get(col))
        if v.startswith("http"):
            return v
    return ""


def aff_ok(link: str) -> bool:
    """ลิงก์มี affiliate id หรือเป็นลิงก์ย่อของเรา (ซึ่งชี้ไปลิงก์ที่มี affiliate id)"""
    if not link:
        return False
    if "affiliate_id=" in link:
        return True
    return bool(SHORTENER_BASE_URL) and link.startswith(SHORTENER_BASE_URL.rstrip("/"))


def build_final_link(row: Dict, page_mode: str) -> tuple[str, str]:
    itemid = norm_text(row.get("itemid"))
    # ใช้ลิงก์จาก feed เฉพาะเมื่อมี affiliate_id อยู่แล้ว ไม่งั้นจะไม่ได้ค่าคอม
    feed_link = feed_affiliate_link(row)
    if feed_link and "affiliate_id=" in feed_link:
        return feed_link, "feed_column"
    long_aff_link = build_shopee_affiliate_link(row, page_mode)

    if not long_aff_link:
        return "", "none"

    if SHORTENER_BASE_URL:
        slug = f"{page_mode}-{itemid}".lower()
        short_link = create_real_short_link(long_aff_link, slug)
        if short_link and short_link != long_aff_link:
            return short_link, "worker_short"
        if short_link:
            return short_link, "affiliate_long"

    return long_aff_link, "affiliate_long"


def is_ben_target(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    text = f"{title} {cat1} {cat2} {cat3}".lower()

    allow_keywords = [
        "electrical", "electric", "ไฟฟ้า", "อุปกรณ์ไฟฟ้า",
        "ปลั๊ก", "ปลั๊กไฟ", "รางปลั๊ก", "ปลั๊กพ่วง", "เต้ารับ", "เต้าเสียบ",
        "power socket", "socket", "power strip", "extension", "extension cord",
        "สายไฟ", "cable", "wire", "usb", "usb-c", "type-c", "lightning", "สายชาร์จ", "หัวชาร์จ",
        "adapter", "charger", "fast charge", "gan", "power adapter",
        "converter", "transformer", "เบรกเกอร์", "breaker", "switch", "สวิตช์",
        "หลอดไฟ", "led", "โคมไฟ", "ไฟฉาย",
        "tools", "tool", "เครื่องมือ", "เครื่องมือช่าง",
        "drill", "สว่าน", "ไขควง", "คีม", "ประแจ", "ค้อน", "เลื่อย",
        "multimeter", "tester", "เทสเตอร์", "มิเตอร์ไฟ",
        "กาว", "กาวร้อน", "กาวแห้งเร็ว", "ซิลิโคน", "sealant",
        "ตะขอ", "พุก", "พุกตะกั่ว", "anchor", "น็อต", "สกรู", "ตะปู",
        "เทปพันสายไฟ", "insulation tape", "เคเบิ้ลไทร์", "cable tie",
        "filter", "air purifier filter"
    ]

    block_keywords = [
        "bra", "bra pad", "บรา", "บราทรง", "เสื้อใน", "ชั้นใน",
        "fashion", "beauty", "cosmetic", "skincare", "สบู่", "soap", "ครีม",
        "lip", "ลิป", "เสื้อ", "กางเกง", "รองเท้า", "กระเป๋า", "หมวก",
        "iphone", "ipad", "macbook", "airpods", "apple watch",
        "case", "เคส", "lens protection", "full lens", "watch strap",
        "smart home", "camera", "cctv", "ip camera", "security camera",
        "กล้อง", "กล้องติดรถ", "dash cam", "smart plug", "smart bulb",
        "smart switch", "router", "mesh", "wifi", "sensor", "doorbell",
        "robot vacuum", "หุ่นยนต์ดูดฝุ่น",
        "food", "อาหาร", "ขนม", "ของเล่น", "toy",
        "ผ้าใบ", "กันฝน", "tarp", "tarpaulin", "canvas", "cover", "คลุมรถ",
        "ที่นอน", "หมอน", "ผ้าห่ม", "ตกแต่งบ้าน", "ของแต่งบ้าน",
        "ถุง", "ซอง", "ฝากาว", "แพ็ก", "แพค", "บรรจุภัณฑ์", "สติ๊กเกอร์",
        "เทปใส", "ซองใส", "ถุงแก้ว", "opp", "packing", "package", "poly bag",
        "กระทะ", "หม้อ", "เครื่องครัว", "ครัว", "ทำอาหาร", "ทอด",
        "frying pan", "pan", "cookware", "kitchenware", "kitchen"
    ]

    if any(k in text for k in block_keywords):
        return False

    return any(k in text for k in allow_keywords)


def is_hard_block_for_ben(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    text = f"{title} {cat1} {cat2} {cat3}".lower()
    hard_blocks = [
        "bra", "bra pad", "บรา", "บราทรง", "เสื้อใน", "ชั้นใน",
        "fashion", "beauty", "cosmetic", "skincare", "สบู่", "ครีม",
        "เสื้อ", "กางเกง", "รองเท้า", "กระเป๋า",
        "iphone case", "ipad case", "เคสมือถือ", "watch strap",
        "smart home", "camera", "cctv", "ip camera", "security camera",
        "กล้อง", "กล้องติดรถ", "dash cam", "smart plug", "smart bulb",
        "router", "mesh", "wifi", "sensor", "doorbell",
        "food", "อาหาร", "ขนม", "ของเล่น", "toy",
        "ผ้าใบ", "กันฝน", "ตัดเย็บ", "แฟชั่น",
        "ถุง", "ซอง", "ฝากาว", "แพ็ก", "แพค", "บรรจุภัณฑ์", "สติ๊กเกอร์",
        "เทปใส", "ซองใส", "ถุงแก้ว", "opp", "packing", "package", "poly bag",
        "กระทะ", "หม้อ", "เครื่องครัว", "ครัว", "ทำอาหาร", "ทอด",
        "frying pan", "pan", "cookware", "kitchenware", "kitchen",
        # อุปกรณ์เสริมมือถือที่ไม่ใช่งานไฟฟ้า/เครื่องมือช่าง
        "ฟิล์ม", "film", "กระจกนิรภัย", "tempered", "screen protector", "กันรอย",
        "เคส", "ที่วางมือถือ", "ขาตั้งมือถือ", "สายคล้อง"
    ]
    return any(k in text for k in hard_blocks)


def is_smarthome_target(title: str, cat1: str, cat2: str, cat3: str) -> bool:
    text = f"{title} {cat1} {cat2} {cat3}".lower()

    # เฉพาะคำที่เป็น "อุปกรณ์" สมาร์ทโฮมจริง (ไม่ใช้คำกว้าง ๆ อย่าง smart / camera / กล้อง)
    allow_keywords = [
        "smart home", "smart plug", "wifi plug", "ปลั๊กอัจฉริยะ", "ปลั๊กไวไฟ",
        "smart bulb", "smart light", "หลอดไฟอัจฉริยะ", "smart switch", "สวิตช์อัจฉริยะ",
        "cctv", "ip camera", "security camera", "กล้องวงจรปิด", "wifi camera", "กล้อง wifi",
        "dash cam", "กล้องติดรถ", "doorbell", "กริ่งประตู", "smart lock", "กลอนดิจิตอล",
        "robot vacuum", "หุ่นยนต์ดูดฝุ่น", "air purifier", "เครื่องฟอกอากาศ",
        "router", "เราเตอร์", "mesh wifi", "access point", "motion sensor", "เซ็นเซอร์",
        "tuya", "google home", "alexa", "homekit", "zigbee",
    ]

    block_keywords = [
        "power socket", "รางปลั๊ก", "ปลั๊กพ่วง", "สายไฟ", "extension cord",
        "drill", "ไขควง", "สว่าน", "คีม", "tester", "multimeter",
        "beauty", "สบู่", "soap", "fashion", "เสื้อ", "รองเท้า",
        "food", "อาหาร", "ผ้าใบ", "กันฝน", "tarp", "tarpaulin", "canvas",
        "ถุง", "ซอง", "ฝากาว", "แพ็ก", "แพค", "บรรจุภัณฑ์",
        "กระทะ", "หม้อ", "เครื่องครัว", "ครัว", "ทำอาหาร",
        "frying pan", "pan", "cookware", "kitchenware", "kitchen",
        "ผ้า", "microfiber", "ไมโครไฟเบอร์", "lens cloth", "ฟิล์ม", "film",
        "เคส", "case", "strap", "สายนาฬิกา", "ที่วางมือถือ",
        "แฟชั่น", "fashion", "เครื่องประดับ", "jewelry", "ห่วงโซ่", "สายคล้อง", "พวงกุญแจ"
    ]

    if any(k in text for k in block_keywords):
        return False

    return any(k in text for k in allow_keywords)


def score_product(row: Dict, page_mode: str) -> float:
    sold = to_float(row.get("item_sold"))
    rating = to_float(row.get("item_rating"))
    price = to_float(row.get("sale_price"))
    title = norm_text(row.get("title")).lower()

    score = (sold * 3.0) + (rating * 120.0)

    if 80 <= price <= 3000:
        score += 25
    if sold >= 500:
        score += 80
    if sold >= 1000:
        score += 120
    if rating >= 4.8:
        score += 50

    hot_words = [
        "usb", "gan", "power bank", "adapter", "ปลั๊ก",
        "switch", "led", "พุก", "กาว", "ตะขอ", "filter"
    ]
    if any(k in title for k in hot_words):
        score += 35

    if page_mode == "smart" and any(k in title for k in ["camera", "smart", "wifi", "led", "filter"]):
        score += 25

    if page_mode == "ben" and any(k in title for k in ["ปลั๊ก", "adapter", "gan", "กาว", "พุก", "น็อต", "สกรู", "กาวร้อน"]):
        score += 25

    return score


def row_matches_page(row: Dict, page_mode: str) -> bool:
    title = norm_text(row.get("title"))
    cat1 = norm_text(row.get("global_category1"))
    cat2 = norm_text(row.get("global_category2"))
    cat3 = norm_text(row.get("global_category3"))

    if page_mode == "ben":
        if is_hard_block_for_ben(title, cat1, cat2, cat3):
            return False
        ben_required_keywords = [
            "ปลั๊ก", "ปลั๊กไฟ", "รางปลั๊ก", "ปลั๊กพ่วง",
            "สายไฟ", "สายชาร์จ", "charger", "adapter", "gan",
            "ไฟฟ้า", "electrical", "breaker", "เบรกเกอร์", "switch", "สวิตช์",
            "หลอดไฟ", "led", "โคมไฟ",
            "เครื่องมือ", "tool", "drill", "สว่าน", "ไขควง", "คีม", "ประแจ",
            "กาว", "พุก", "น็อต", "สกรู", "anchor", "เทปพันสายไฟ"
        ]
        raw_text = f"{title} {cat1} {cat2} {cat3}".lower()
        if not any(k in raw_text for k in ben_required_keywords):
            return False
        return is_ben_target(title, cat1, cat2, cat3)

    return is_smarthome_target(title, cat1, cat2, cat3)



IMAGE_COLUMNS = ["image_link", "additional_image_link"] + [f"image_link_{i}" for i in range(2, 11)]
MAX_POST_IMAGES = int(os.getenv("MAX_POST_IMAGES", "4"))


def product_images(row: Dict, limit: int = 10) -> list:
    """รวมรูปสินค้าทุกคอลัมน์ (ไม่ซ้ำ) รูปหลักมาก่อนเสมอ"""
    out, seen = [], set()
    for col in IMAGE_COLUMNS:
        for url in re.split(r"[,|\s]+", norm_text(row.get(col))):
            url = url.strip()
            key = normalize_image_key(url)
            if url.startswith("http") and key and key not in seen:
                seen.add(key)
                out.append(url)
    return out[:limit]

def choose_products(page_modes: list, history: Optional[Dict] = None) -> Dict[str, Optional[Dict]]:
    """อ่าน CSV รอบเดียว แล้วเลือกสินค้าที่ดีที่สุดให้ทุกเพจพร้อมกัน
    history: ประวัติกันซ้ำต่อเพจ (ค่าเริ่มต้น = ประวัติโพสต์รูป)"""
    posted = history if history is not None else load_posted()
    best = {m: (None, -1.0) for m in page_modes}
    count = 0
    no_link_count = 0
    headers_logged = False
    diag = {"cb": {}, "samples": []}

    for row in iter_csv_rows(SHOPEE_CSV_URL):
        if not headers_logged:
            print("CSV COLUMNS:", ", ".join(list(row.keys())[:40]), flush=True)
            img_cols = [k for k in row.keys() if k and "image" in k.lower()]
            annotate("notice", "CSV columns", ", ".join(list(row.keys())[:60]) + f"\nimage columns: {img_cols}\nsample: " +
                     " | ".join(f"{k}={str(row.get(k))[:120]}" for k in img_cols))
            headers_logged = True
        count += 1
        if os.getenv("FEED_DIAG") == "true":
            cb = norm_text(row.get("cb_option"))[:40]
            diag["cb"][cb] = diag["cb"].get(cb, 0) + 1
            if len(diag["samples"]) < 6 and cb:
                diag["samples"].append({k: norm_text(row.get(k))[:60] for k in ("cb_option", "price", "sale_price", "discount_percentage", "is_official_shop", "global_category1")})
        try:
            title = norm_text(row.get("title"))
            image = norm_text(row.get("image_link"))
            itemid = norm_text(row.get("itemid"))
            if not title or not image or not itemid:
                continue
            if not has_link_data(row):
                no_link_count += 1
                continue
            if to_float(row.get("item_rating")) < MIN_RATING:
                continue
            if to_float(row.get("item_sold")) < MIN_SOLD:
                continue

            image_key = normalize_image_key(image)
            for mode in page_modes:
                if is_duplicate(posted[mode], itemid, image_key, title):
                    continue
                if not row_matches_page(row, mode):
                    continue
                score = score_product(row, mode)
                if score > best[mode][1]:
                    best[mode] = (row, score)
        except Exception as e:
            if count < 5:
                print("ROW ERROR:", e, flush=True)
            continue

    print(f"SCAN DONE: {count} rows | no_link={no_link_count}", flush=True)
    if os.getenv("FEED_DIAG") == "true":
        annotate("notice", "Feed diag", json.dumps(diag, ensure_ascii=False)[:900])
    if count == 0:
        print("❌ CSV ว่างหรืออ่านไม่ได้ — ตรวจ SHOPEE_CSV_URL", flush=True)

    result: Dict[str, Optional[Dict]] = {}
    for mode in page_modes:
        row = best[mode][0]
        if not row:
            print(f"❌ No product found ({mode})", flush=True)
            annotate("error", f"Product {mode}", "ไม่พบสินค้าที่ผ่านเงื่อนไข")
            result[mode] = None
            continue

        final_link, link_source = build_final_link(row, mode)
        product = {
            "itemid": norm_text(row.get("itemid")),
            "title": norm_text(row.get("title")),
            "image": norm_text(row.get("image_link")),
            "images": product_images(row),
            "image_key": normalize_image_key(norm_text(row.get("image_link"))),
            "sold": to_float(row.get("item_sold")),
            "rating": to_float(row.get("item_rating")),
            "price": to_float(row.get("sale_price")),
            "link": final_link,
            "link_source": link_source,
            "cat1": norm_text(row.get("global_category1")),
            "cat2": norm_text(row.get("global_category2")),
            "cat3": norm_text(row.get("global_category3")),
        }
        print(
            f"✅ CHOSEN ({mode}): {product['title']} | sold={product['sold']} | "
            f"rating={product['rating']} | price={product['price']} | link={link_source}",
            flush=True,
        )
        result[mode] = product

    return result


def make_hook(page_mode: str) -> str:
    ben_hooks = [
        "⚡ ของแนวนี้กำลังขายดี กดดูตัวนี้ก่อน",
        "🔥 สายช่างและสายบ้านน่าดูตัวนี้มาก",
        "👀 รีวิวดี คนซื้อเยอะ ใช้งานจริง",
        "🛠 ของใช้คุ้ม ๆ ตัวนี้กำลังมาแรง",
    ]

    smart_hooks = [
        "📱 ของชิ้นนี้กำลังฮิต คนกดดูเยอะมาก",
        "🏠 ของแนว Smart Home ตัวนี้น่าสนใจมาก",
        "🔥 รีวิวพุ่ง คนซื้อเยอะ ใช้งานคุ้ม",
        "⚡ ของใช้งานง่าย ตัวนี้กำลังมาแรง",
    ]

    return random.choice(smart_hooks if page_mode == "smart" else ben_hooks)


def fallback_caption(product: Dict, page_mode: str) -> str:
    hook = make_hook(page_mode)
    sold_text = f"{int(product['sold']):,}"
    rating_text = f"{product['rating']:.2f}"

    return "\n".join([
        hook,
        "",
        product["title"],
        "",
        f"⭐ รีวิว {rating_text}",
        f"🛒 ขายแล้ว {sold_text} ชิ้น",
        "📌 ของกำลังมาแรง คนสนใจเยอะ",
        "",
        "👉 กดดูรายละเอียดและราคาล่าสุดตรงนี้",
        product["link"],
    ])


def generate_caption(product: Dict, page_mode: str) -> str:
    sold_text = f"{int(product['sold']):,}"
    if page_mode == "smart":
        page_desc = "เพจ SmartHome Thailand (อุปกรณ์สมาร์ทโฮม กล้อง ปลั๊กอัจฉริยะ ของใช้ไฮเทคในบ้าน)"
    else:
        page_desc = "เพจ BEN Home & Electrical (อุปกรณ์ไฟฟ้า ของใช้ในบ้าน เครื่องมือช่าง)"

    prompt = f"""
เขียนแคปชัน Facebook ภาษาไทยสำหรับ {page_desc}

สินค้า: {product['title']}
คะแนนรีวิว: {product['rating']:.1f}
ขายแล้ว: {sold_text} ชิ้น
หมวด: {product['cat1']} / {product['cat2']} / {product['cat3']}

เงื่อนไข:
- บรรทัดแรกเป็น hook สั้น ดึงความสนใจ
- รวม 5-7 บรรทัด อ่านง่าย ใช้อีโมจิพอประมาณ
- บอกว่าสินค้านี้ช่วยแก้ปัญหาอะไร/เหมาะกับใคร โดยอิงจากชื่อสินค้าเท่านั้น
- ห้ามแต่งสเปก คุณสมบัติ หรือคำรับรองที่ไม่มีในชื่อสินค้า (เช่น ทนทาน ไม่ทิ้งรอย ปลอดภัย ของแท้)
- ห้ามเร่งให้รีบซื้อ เช่น ก่อนหมด ด่วน สต๊อกจำกัด โปรวันนี้เท่านั้น
- ใช้ภาษาไทยที่ถูกต้องและเป็นธรรมชาติ ทุกคำต้องเป็นคำไทยที่มีความหมาย ตรวจทานก่อนตอบ
- ห้ามพูดถึงคำสั่งหรือที่มาของข้อมูล (เช่น "ตามชื่อสินค้า", "ระบุว่า")
- ห้ามชวนทักแชทหรือส่งข้อความหาเพจ ให้ชวนกดลิงก์ด้านล่างแทน
- ห้ามใส่ราคา ห้ามใส่ลิงก์ ห้ามพูดถึงค่าคอมมิชชัน
- ปิดท้ายด้วยแฮชแท็ก 2-3 อัน
- ตอบเฉพาะตัวแคปชัน ไม่ต้องมีคำอธิบายอื่น
""".strip()

    content = ai_write(
        "คุณเป็นแอดมินเพจขายของออนไลน์ชาวไทย เขียนแคปชันกระชับ เป็นกันเอง และซื่อสัตย์ต่อข้อมูลสินค้า",
        prompt,
        temperature=0.9,
    )
    if not content:
        return fallback_caption(product, page_mode)

    return f"{content}\n\n👉 กดดูรายละเอียดและราคาล่าสุดตรงนี้\n{product['link']}"


def get_page_posts(page_id: str, access_token: str, limit: int = 5) -> list:
    try:
        res = requests.get(
            f"{GRAPH}/{page_id}/posts",
            params={
                "access_token": access_token,
                "fields": "id,message,created_time",
                "limit": limit,
            },
            timeout=TIMEOUT,
        )
        data = safe_json(res)
        err = graph_error(data)
        if err:
            print("GET PAGE POSTS ERROR:", err, flush=True)
        return data.get("data", [])
    except Exception as e:
        print("GET PAGE POSTS EXCEPTION:", e, flush=True)
        return []


def get_post_comments(post_id: str, access_token: str, limit: int = 20) -> list:
    try:
        res = requests.get(
            f"{GRAPH}/{post_id}/comments",
            params={
                "access_token": access_token,
                "fields": "id,message,from,created_time,parent",
                "filter": "stream",
                "limit": limit,
            },
            timeout=TIMEOUT,
        )
        data = safe_json(res)
        err = graph_error(data)
        if err:
            print("GET COMMENTS ERROR:", err, flush=True)
        return data.get("data", [])
    except Exception as e:
        print("GET COMMENTS EXCEPTION:", e, flush=True)
        return []


def generate_comment_reply(comment_text: str, page_mode: str) -> str:
    fallback_map = {
        "ben": "ขอบคุณมากครับ สนใจรายละเอียดเพิ่มเติมกดลิงก์ใต้โพสต์ได้เลย 🙏",
        "smart": "ขอบคุณมากครับ ถ้าสนใจรายละเอียดเพิ่มเติมกดลิงก์ใต้โพสต์ได้เลย 🙏",
    }

    page_desc = "เพจเครื่องมือช่างและงานไฟฟ้า" if page_mode == "ben" else "เพจ Smart Home"

    prompt = f"""
คุณเป็นแอดมินเพจ {page_desc}
ช่วยตอบคอมเมนต์ลูกค้าแบบสั้น สุภาพ เป็นกันเอง ภาษาไทย

คอมเมนต์ลูกค้า:
{comment_text}

เงื่อนไข:
- ตอบสั้น 1-2 ประโยค
- สุภาพ
- ไม่เวอร์
- ไม่ใส่ราคา
- ไม่ใส่ข้อมูลที่ไม่รู้จริง
- ถ้าเป็นแนวสนใจซื้อ ให้ชวนกดลิงก์ใต้โพสต์
- ถ้าเป็นแนวชม ให้ขอบคุณ
- ถ้าเป็นแนวถามทั่วไป ให้ตอบกลาง ๆ และชวนดูรายละเอียดที่ลิงก์ใต้โพสต์
""".strip()

    content = ai_write(
        "คุณเป็นแอดมินเพจขายของ ตอบคอมเมนต์สั้น สุภาพ และน่าเชื่อถือ",
        prompt,
        temperature=0.7,
        max_tokens=200,
        model=CLAUDE_REPLY_MODEL,
    )
    return content or fallback_map.get(page_mode, "ขอบคุณมากครับ 🙏")


def reply_to_comment(comment_id: str, access_token: str, message: str) -> bool:
    if DRY_RUN:
        print(f"[DRY_RUN] would reply to {comment_id}: {message[:80]}", flush=True)
        return False
    try:
        res = requests.post(
            f"{GRAPH}/{comment_id}/comments",
            data={"message": message, "access_token": access_token},
            timeout=TIMEOUT,
        )
        data = safe_json(res)
        err = graph_error(data)
        if err:
            print("REPLY COMMENT ERROR:", err, flush=True)
            return False
        return "id" in data
    except Exception as e:
        print("REPLY COMMENT EXCEPTION:", e, flush=True)
        return False


def auto_reply_recent_comments(page_mode: str, page_id: str, access_token: str, page_name: str) -> None:
    if not AUTO_REPLY_COMMENTS:
        return

    posts = get_page_posts(page_id, access_token, limit=5)
    total_replied = 0

    for post in posts:
        post_id = norm_text(post.get("id"))
        if not post_id:
            continue

        comments = get_post_comments(post_id, access_token, COMMENT_SCAN_LIMIT)

        for c in comments:
            if total_replied >= MAX_REPLY_PER_RUN:
                break

            comment_id = norm_text(c.get("id"))
            message = norm_text(c.get("message"))
            from_obj = c.get("from") or {}
            from_name = norm_text(from_obj.get("name"))
            from_id = norm_text(from_obj.get("id"))

            if not comment_id or not message:
                continue

            if was_comment_replied(comment_id):
                continue

            if from_id and from_id == page_id:
                continue
            if from_name and from_name.lower() == page_name.lower():
                continue

            reply_text = generate_comment_reply(message, page_mode)
            ok = reply_to_comment(comment_id, access_token, reply_text)

            if ok:
                mark_comment_replied(comment_id)
                total_replied += 1
                time.sleep(2)

        if total_replied >= MAX_REPLY_PER_RUN:
            break

    print(f"AUTO REPLY DONE ({page_mode}): {total_replied}", flush=True)


def post_images(page_id: str, access_token: str, image_urls: list, caption: str) -> Optional[str]:
    """โพสต์หลายรูปในโพสต์เดียว; ถ้ามีรูปเดียวหรือทำไม่สำเร็จ ใช้โพสต์รูปเดียวแทน"""
    urls = [u for u in image_urls if u][:MAX_POST_IMAGES]
    if len(urls) < 2:
        return post_image(page_id, access_token, urls[0] if urls else "", caption)
    if DRY_RUN:
        print(f"[DRY_RUN] would post {len(urls)} images", flush=True)
        print("[DRY_RUN] caption:\n" + caption, flush=True)
        return None

    media_ids = []
    for u in urls:
        try:
            res = requests.post(
                f"{GRAPH}/{page_id}/photos",
                data={"url": u, "published": "false", "access_token": access_token},
                timeout=TIMEOUT,
            )
            data = safe_json(res)
            if graph_error(data) or "id" not in data:
                print("PHOTO UPLOAD SKIP:", graph_error(data), flush=True)
                continue
            media_ids.append(data["id"])
        except Exception as e:
            print("PHOTO UPLOAD EXCEPTION:", e, flush=True)

    if len(media_ids) < 2:
        print("MULTI PHOTO → fallback single", flush=True)
        return post_image(page_id, access_token, urls[0], caption)

    payload = {"message": caption, "access_token": access_token}
    for n, mid in enumerate(media_ids):
        payload[f"attached_media[{n}]"] = json.dumps({"media_fbid": mid})
    try:
        res = requests.post(f"{GRAPH}/{page_id}/feed", data=payload, timeout=TIMEOUT)
        data = safe_json(res)
    except Exception as e:
        print("MULTI POST EXCEPTION:", e, flush=True)
        data = {"error": {"message": str(e)}}
    err = graph_error(data)
    if err or "id" not in data:
        print("❌ MULTI POST ERROR:", err, "→ fallback single", flush=True)
        annotate("warning", "Post", f"multi-photo failed ({err}) → single photo")
        return post_image(page_id, access_token, urls[0], caption)
    print(f"✅ POSTED ({len(media_ids)} photos):", data["id"], flush=True)
    annotate("notice", "Posted", f"{data['id']} ({len(media_ids)} photos)")
    return data["id"]


def post_image(page_id: str, access_token: str, image_url: str, caption: str) -> Optional[str]:
    if DRY_RUN:
        print("[DRY_RUN] would post image:", image_url, flush=True)
        print("[DRY_RUN] caption:\n" + caption, flush=True)
        return None
    try:
        res = requests.post(
            f"{GRAPH}/{page_id}/photos",
            data={"url": image_url, "caption": caption, "access_token": access_token},
            timeout=TIMEOUT,
        )
        data = safe_json(res)
        err = graph_error(data)
        if err:
            print("❌ POST IMAGE ERROR:", err, flush=True)
            annotate("error", "Post", err)
            return None
        post_id = data.get("post_id") or data.get("id")
        print("✅ POSTED:", post_id, flush=True)
        annotate("notice", "Posted", str(post_id))
        return post_id
    except Exception as e:
        print("POST IMAGE EXCEPTION:", e, flush=True)
        return None


def comment_link(post_id: str, access_token: str, link: str) -> None:
    try:
        res = requests.post(
            f"{GRAPH}/{post_id}/comments",
            data={"message": f"🛒 ลิงก์สั่งซื้ออยู่ตรงนี้\n{link}", "access_token": access_token},
            timeout=TIMEOUT,
        )
        err = graph_error(safe_json(res))
        print("COMMENT LINK:", err or "ok", flush=True)
        annotate("warning" if err else "notice", "Comment link", err or f"ok on {post_id}")
    except Exception as e:
        print("COMMENT LINK EXCEPTION:", e, flush=True)


def save_status(results: Dict[str, str]) -> None:
    """บันทึกผลรอบล่าสุดแบบรายวัน (ทำให้ repo มี activity และดูสถานะได้ง่าย)"""
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    data = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    for mode, result in results.items():
        data[mode] = {"date": today, "result": result}
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_all_pages() -> None:
    if DRY_RUN:
        print("===== DRY_RUN: อ่านและเลือกสินค้าเท่านั้น ไม่โพสต์/ไม่ตอบคอมเมนต์ =====", flush=True)

    if not SHOPEE_CSV_URL:
        print("❌ Missing SHOPEE_CSV_URL", flush=True)
        sys.exit(1)

    results: Dict[str, str] = {}
    active = []
    for page in PAGES:
        if not page["id"] or not page["token"]:
            print(f"SKIP PAGE ({page['mode']}) missing PAGE_ID/TOKEN secret", flush=True)
            continue
        if not check_page_token(page):
            results[page["mode"]] = "token_error"
            continue
        active.append(page)

    products: Dict[str, Optional[Dict]] = {}
    if active:
        try:
            products = choose_products([p["mode"] for p in active])
        except Exception as e:
            print("❌ CSV ERROR:", e, flush=True)
            annotate("error", "CSV", str(e)[:300])
            for p in active:
                results[p["mode"]] = "csv_error"
            active = []

    for page in active:
        mode = page["mode"]
        try:
            product = products.get(mode)
            if not product:
                results[mode] = "no_product"
            else:
                caption = generate_caption(product, mode)
                annotate(
                    "notice",
                    f"Caption {mode}",
                    f"{product['title'][:80]} | rating {product['rating']} | sold {int(product['sold'])} | images {len(product.get('images') or [])} | link {product['link_source']} | aff_id={'yes' if aff_ok(product['link']) else 'NO'}\n---\n{caption}",
                )
                post_id = post_images(page["id"], page["token"], product.get("images") or [product["image"]], caption)
                if post_id:
                    mark_as_posted(mode, product["itemid"], product["image_key"], product["title"])
                    time.sleep(3)
                    comment_link(post_id, page["token"], product["link"])
                    results[mode] = "posted"
                else:
                    results[mode] = "dry_run" if DRY_RUN else "post_error"

            time.sleep(3)
            auto_reply_recent_comments(mode, page["id"], page["token"], page["name"])
        except Exception as e:
            print(f"❌ PAGE ERROR ({mode}):", e, flush=True)
            results[mode] = "page_error"

    print("===== SUMMARY =====", flush=True)
    for mode, r in results.items():
        print(f"{mode}: {r}", flush=True)
    annotate("notice", "Summary", " | ".join(f"{m}: {r}" for m, r in results.items()) + (" (DRY_RUN)" if DRY_RUN else ""))

    if not DRY_RUN:
        save_status(results)

    failed = [m for m, r in results.items() if r not in ("posted", "dry_run")]
    if failed or not results:
        print("❌ Run มีปัญหา:", failed or "ไม่มีเพจที่ตั้งค่าไว้", flush=True)
        sys.exit(1)
