import os
import json
import random
import time
import csv
import io
import re
import calendar
from datetime import datetime
from dateutil import tz
import requests

GRAPH_VERSION = "v25.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = "state.json"
MAX_STATE_ITEMS = 5000
REQ_TIMEOUT = 60  # Graph timeout

# ---- ENV ----
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL")

POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
END_MONTH_BOOST_DAYS = int(os.getenv("END_MONTH_BOOST_DAYS", "5"))
DOUBLE_DAY_BOOST = os.getenv("DOUBLE_DAY_BOOST", "1") == "1"
COMMENT_LINK = os.getenv("COMMENT_LINK", "1") == "1"
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

CSV_TIMEOUT = int(os.getenv("CSV_TIMEOUT", "25"))
CSV_RETRIES = int(os.getenv("CSV_RETRIES", "5"))
CSV_RETRY_SLEEP = int(os.getenv("CSV_RETRY_SLEEP", "4"))

HASHTAGS = [
    "#BENHomeElectrical",
    "#ของใช้ในบ้าน",
    "#อุปกรณ์ไฟฟ้า",
    "#เครื่องมือช่าง",
    "#งานช่าง",
    "#ซ่อมบ้าน",
    "#ของดีบอกต่อ",
]

SELLING_HOOKS = [
    "🔧 งานช่างต้องมีติดบ้าน! ใช้งานง่าย คุณภาพคุ้มราคา 💯",
    "⚡ ของมันต้องมี! ช่วยให้บ้านคุณพร้อมใช้งานทุกวัน 🏡",
    "🛠️ เลือกของดีไว้ก่อน ซ่อม/ติดตั้งได้สบาย ๆ",
    "🔥 ราคาดี + ใช้จริงคุ้มจริง เหมาะกับสายช่างและเจ้าของบ้าน",
    "✅ รีวิวดี ส่งไว ใช้งานได้หลากหลาย เหมาะมากสำหรับบ้านคุณ",
]

CTA_LINES = [
    "📌 สนใจทักแชทได้เลย เดี๋ยวแนะนำให้ตรงงานครับ",
    "💬 คอมเมนต์คำว่า ‘สนใจ’ เดี๋ยวส่งลิงก์ให้",
    "🚚 พร้อมส่ง เช็คโปรก่อนหมดได้เลย",
    "⭐ กดติดตามเพจไว้ มีของดีมาอัปเดตทุกวัน",
]

MONTHLY_PROMO_LINES = [
    "🎉 โปรประจำเดือน! ของดีราคาพิเศษ รีบเก็บก่อนหมดโปร",
    "🏷️ ช่วงโปรแรงของเดือนนี้ ลดคุ้ม ๆ ต้องรีบจัด",
    "🔥 โปรเดือนนี้มาแล้ว! ราคาดีหายาก",
]

END_MONTH_LINES = [
    "🔥 โค้งสุดท้ายปลายเดือน! โปรแรง เคลียร์สต็อก รีบจัดก่อนหมด",
    "💥 ปลายเดือนโปรเดือด! ราคาพิเศษเฉพาะช่วงนี้",
]

DOUBLE_DAY_LINES = [
    "🎯 วันเลขเบิ้ล โปรพิเศษ! เก็บคูปอง/ลดเพิ่มได้อีก",
    "⚡ วันนี้เลขเบิ้ล! ของดีต้องรีบจัด",
]

def die(msg: str):
    raise SystemExit(msg)

def now_th():
    return datetime.now(tz=tz.gettz("Asia/Bangkok"))

def is_end_month_boost(dt: datetime) -> bool:
    last_day = calendar.monthrange(dt.year, dt.month)[1]
    return dt.day >= (last_day - END_MONTH_BOOST_DAYS + 1)

def is_double_day(dt: datetime) -> bool:
    return dt.day == dt.month

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted_keys": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted_keys": []}

def save_state(state):
    keys = state.get("posted_keys", [])
    if len(keys) > MAX_STATE_ITEMS:
        state["posted_keys"] = keys[-MAX_STATE_ITEMS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_csv_with_retry(url: str) -> list[dict]:
    print("INFO: Fetching CSV...")
    last_err = None

    for attempt in range(1, CSV_RETRIES + 1):
        try:
            print(f"INFO: CSV fetch attempt {attempt}/{CSV_RETRIES} (timeout={CSV_TIMEOUT}s)")
            r = requests.get(url, timeout=CSV_TIMEOUT, allow_redirects=True)
            r.raise_for_status()

            content = r.content.decode("utf-8", errors="replace")
            if content.startswith("\ufeff"):
                content = content.lstrip("\ufeff")

            # debug small preview
            preview = content[:300].replace("\n", "\\n")
            print(f"INFO: CSV preview(300): {preview}")

            f = io.StringIO(content)
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                if not row:
                    continue
                rows.append({(k.strip() if k else k): (v.strip() if isinstance(v, str) else v) for k, v in row.items()})
            return rows

        except Exception as e:
            last_err = e
            print(f"WARN: CSV fetch failed: {e}")
            if attempt < CSV_RETRIES:
                time.sleep(CSV_RETRY_SLEEP)

    die(f"ERROR: Fetch CSV failed after {CSV_RETRIES} attempts. Last error: {last_err}")

def pick_best_url(row: dict) -> str:
    for k in ["url", "product_link", "link", "product_url", "item_link"]:
        v = row.get(k)
        if v and str(v).startswith("http"):
            return str(v).strip()
    return ""

def pick_best_name(row: dict) -> str:
    for k in ["name", "title", "product_name", "item_name"]:
        v = row.get(k)
        if v:
            return clean_text(v)
    return ""

def pick_image_candidates(row: dict) -> list[str]:
    candidates = []
    keys_priority = [
        "image", "image_url", "image_link",
        "image_link_1","image_link_2","image_link_3","image_link_4","image_link_5",
        "image_link_6","image_link_7","image_link_8","image_link_9","image_link_10",
        "additional_image_link",
    ]
    for k in keys_priority:
        v = row.get(k)
        if not v:
            continue
        v = str(v).strip()
        if v.startswith("http"):
            candidates.append(v)

    extra = row.get("additional_image_link")
    if extra and isinstance(extra, str) and "," in extra:
        for part in extra.split(","):
            part = part.strip()
            if part.startswith("http"):
                candidates.append(part)

    seen = set()
    uniq = []
    for u in candidates:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    return uniq

def row_key(row: dict) -> str:
    for k in ["itemid", "item_id", "model_id", "modelid", "product_id", "url", "product_link"]:
        v = row.get(k)
        if v:
            return f"{k}:{str(v).strip()}"
    return f"nu:{pick_best_name(row)}|{pick_best_url(row)}"

def build_caption(name: str, url: str) -> str:
    dt = now_th()
    lines = []
    lines.append(random.choice(SELLING_HOOKS))
    if name:
        lines.append(f"✅ {name}")

    lines.append(random.choice(MONTHLY_PROMO_LINES))
    if is_end_month_boost(dt):
        lines.append(random.choice(END_MONTH_LINES))
    if DOUBLE_DAY_BOOST and is_double_day(dt):
        lines.append(random.choice(DOUBLE_DAY_LINES))

    lines.append(random.choice(CTA_LINES))
    lines.append("")
    lines.append(" ".join(HASHTAGS))

    if (not COMMENT_LINK) and url:
        lines.append(f"👉 {url}")
    return "\n".join(lines).strip()

def graph_post(path: str, data: dict) -> dict:
    url = f"{GRAPH_BASE}/{path.lstrip('/')}"
    payload = dict(data)
    payload["access_token"] = PAGE_ACCESS_TOKEN
    r = requests.post(url, data=payload, timeout=REQ_TIMEOUT)
    j = r.json() if r.headers.get("content-type","").startswith("application/json") else {"raw": r.text}
    if r.status_code >= 400 or ("error" in j):
        raise RuntimeError(f"Graph API error {r.status_code}: {j}")
    return j

def upload_photo_unpublished(image_url: str) -> str:
    j = graph_post(f"{PAGE_ID}/photos", {"url": image_url, "published": "false"})
    return j["id"]

def create_feed_post(attached_media_ids: list[str], message: str) -> str:
    attached_media = [json.dumps({"media_fbid": pid}) for pid in attached_media_ids]
    j = graph_post(f"{PAGE_ID}/feed", {"message": message, "attached_media": attached_media})
    return j["id"]

def comment_on_post(post_id: str, comment: str):
    graph_post(f"{post_id}/comments", {"message": comment})

def main():
    if not PAGE_ID:
        die("ERROR: Missing env: PAGE_ID")
    if not PAGE_ACCESS_TOKEN:
        die("ERROR: Missing env: PAGE_ACCESS_TOKEN")
    if not SHOPEE_CSV_URL:
        die("ERROR: Missing env: SHOPEE_CSV_URL")

    state = load_state()
    posted = set(state.get("posted_keys", []))

    rows = fetch_csv_with_retry(SHOPEE_CSV_URL)
    if not rows:
        die("ERROR: CSV is empty.")

    candidates = []
    for row in rows:
        url = pick_best_url(row)
        name = pick_best_name(row)
        imgs = pick_image_candidates(row)
        if not url or not name or not imgs:
            continue
        candidates.append({"key": row_key(row), "name": name, "url": url, "images": imgs})

    if not candidates:
        cols = list(rows[0].keys()) if rows else []
        die(f"ERROR: No usable rows in CSV. Found columns: {cols}")

    fresh = [c for c in candidates if c["key"] not in posted]
    pool = fresh if fresh else candidates

    product = random.choice(pool)
    images = product["images"][:]
    random.shuffle(images)
    images = images[: max(1, POST_IMAGES_COUNT)]

    caption = build_caption(product["name"], product["url"])

    print("INFO: Selected product")
    print(f" - key: {product['key']}")
    print(f" - name: {product['name']}")
    print(f" - url: {product['url']}")
    print(f" - images: {len(images)}")

    if DRY_RUN:
        print("DRY_RUN=1 -> Not posting.")
        print("CAPTION:\n" + caption)
        return

    media_ids = []
    for i, img_url in enumerate(images, start=1):
        print(f"INFO: Uploading image {i}/{len(images)}...")
        pid = upload_photo_unpublished(img_url)
        media_ids.append(pid)
        time.sleep(1)

    print("INFO: Creating feed post...")
    post_id = create_feed_post(media_ids, caption)
    print(f"INFO: Posted -> {post_id}")

    if COMMENT_LINK and product["url"]:
        print("INFO: Commenting link for reach...")
        comment_on_post(post_id, f"👉 ลิงก์สินค้า: {product['url']}")
        print("INFO: Comment done.")

    state.setdefault("posted_keys", [])
    state["posted_keys"].append(product["key"])
    save_state(state)
    print("INFO: state.json updated")

if __name__ == "__main__":
    main()
