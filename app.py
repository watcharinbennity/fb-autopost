import os
import io
import json
import random
import time
import csv
from datetime import datetime, timedelta, timezone
import requests

GRAPH_VERSION = os.getenv("GRAPH_VERSION", "25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/v{GRAPH_VERSION}"

POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))
END_MONTH_BOOST_DAYS = int(os.getenv("END_MONTH_BOOST_DAYS", "3"))
POSTS = int(os.getenv("POSTS", "1"))

STATE_FILE = "state.json"
MAX_STATE_ITEMS = 8000

# BEN Home & Electrical hashtags (ปรับได้)
HASHTAGS = [
    "#BENHomeElectrical",
    "#ของใช้ในบ้าน",
    "#อุปกรณ์ไฟฟ้า",
    "#เครื่องมือช่าง",
    "#งานช่าง",
    "#ซ่อมบ้าน",
    "#ติดตั้ง",
    "#ของดีบอกต่อ",
    "#ของใช้จำเป็น",
]

SELLING_HOOKS = [
    "ของมันต้องมีติดบ้าน 🏠✨",
    "ของดีราคาคุ้ม ใช้ได้นาน ✅",
    "งานช่าง/งานไฟ จบในตัวเดียว 🔧⚡",
    "จัดโปรวันนี้ รีบกดก่อนหมด 🔥",
    "ของเข้าใหม่ พร้อมส่ง 🚚",
]

CTAS = [
    "สนใจทักแชทได้เลยครับ 📩",
    "กดลิงก์ดูรายละเอียด/สั่งซื้อได้เลย ✅",
    "ถามสเปค/การใช้งานได้ครับ ยินดีแนะนำ 👍",
]

# แคมเปญรายเดือน (เพิ่ม Reach ด้วยคีย์เวิร์ดโปร)
MONTH_CAMPAIGNS = {
    3:  "🔥 โปร 3.3 ลดแรงของเข้าใหม่!",
    4:  "🔥 โปร 4.4 ของใช้ในบ้านคุ้มๆ!",
    5:  "🔥 โปร 5.5 ช่างต้องมี!",
    6:  "🔥 โปร 6.6 ลดคุ้ม จัดเต็ม!",
    7:  "🔥 โปร 7.7 สายช่างห้ามพลาด!",
    8:  "🔥 โปร 8.8 ดีลแรงประจำเดือน!",
    9:  "🔥 โปร 9.9 ช้อปคุ้มๆ!",
    10: "🔥 โปร 10.10 ดีลใหญ่!",
    11: "🔥 โปร 11.11 ลดหนักมาก!",
    12: "🔥 โปร 12.12 ปิดปี ดีลโหด!",
    1:  "🔥 โปรต้นปี ของใช้จำเป็น!",
    2:  "🔥 โปร 2.2 คุ้มจัด!",
}

def bkk_now():
    return datetime.now(timezone(timedelta(hours=7)))

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"posted_ids": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted_ids": []}

def save_state(state):
    posted = state.get("posted_ids", [])
    if len(posted) > MAX_STATE_ITEMS:
        state["posted_ids"] = posted[-MAX_STATE_ITEMS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def must_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SystemExit(f"ERROR: Missing env: {name}")
    return v.strip()

def http_get_stream(url, timeout=60):
    # stream download + retry
    headers = {
        "User-Agent": "fb-autopost/3 (GitHub Actions)",
        "Accept": "*/*",
    }
    last_err = None
    for attempt in range(1, 6):
        try:
            print(f"INFO: CSV fetch attempt {attempt}/5 (timeout={timeout}s)")
            r = requests.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
            r.raise_for_status()
            content = r.content
            if not content or len(content) < 50:
                raise RuntimeError(f"CSV content too small ({len(content)} bytes)")
            return content, dict(r.headers)
        except Exception as e:
            last_err = e
            time.sleep(2 * attempt)
    raise RuntimeError(f"CSV fetch failed after retries: {last_err}")

def normalize_header(h: str) -> str:
    return (h or "").strip().lower()

def pick_best_images(row: dict, want=3):
    # รองรับทั้ง image_link, image_link_2.. และ image_link_3.. รวมถึง image_link_4..10 ที่คุณมี
    keys = []
    for k in row.keys():
        lk = normalize_header(k)
        if lk.startswith("image_link"):
            keys.append(k)
    # เรียงลำดับ image_link, image_link_2, image_link_3 ... ตามเลขท้าย
    def key_order(k):
        lk = normalize_header(k)
        if lk == "image_link":
            return 0
        parts = lk.split("_")
        try:
            return int(parts[-1])
        except:
            return 999
    keys = sorted(keys, key=key_order)

    urls = []
    for k in keys:
        v = (row.get(k) or "").strip()
        if v.startswith("http"):
            urls.append(v)

    # กันซ้ำ
    uniq = []
    seen = set()
    for u in urls:
        if u not in seen:
            uniq.append(u)
            seen.add(u)

    return uniq[:want]

def extract_product(row: dict):
    # Shopee CSV มักมี title กับ product_link
    title = (row.get("title") or row.get("name") or row.get("product_name") or "").strip()
    url = (row.get("product_link") or row.get("url") or row.get("link") or "").strip()

    # บางไฟล์อาจใส่ product_link เป็น short link หรือว่าง
    if not url.startswith("http"):
        # เผื่อมีคอลัมน์อื่น
        for k in row.keys():
            lk = normalize_header(k)
            if "link" in lk or lk == "url":
                cand = (row.get(k) or "").strip()
                if cand.startswith("http"):
                    url = cand
                    break

    images = pick_best_images(row, want=POST_IMAGES_COUNT)
    return title, url, images

def build_caption(title: str, url: str, boost: bool, campaign_line: str):
    hook = random.choice(SELLING_HOOKS)
    cta = random.choice(CTAS)
    tags = " ".join(HASHTAGS)

    lines = []
    if campaign_line:
        lines.append(campaign_line)
    lines.append(hook)
    if title:
        lines.append(f"🛒 {title}")
    if boost:
        lines.append("📈 โหมดเพิ่ม Reach: ของฮิต/ของจำเป็นรีบจัดก่อนโปรหมด!")
    if url:
        lines.append(f"🔗 {url}")
    lines.append(cta)
    lines.append(tags)
    return "\n".join(lines).strip()

def is_end_month_boost(now_bkk: datetime) -> bool:
    # ถ้าเหลือ END_MONTH_BOOST_DAYS วันสุดท้ายของเดือน -> boost
    # เช่น END_MONTH_BOOST_DAYS=3 => 29-31 (หรือ 28-31) แล้วแต่เดือน
    # หา last day
    next_month = (now_bkk.replace(day=28) + timedelta(days=4)).replace(day=1)
    last_day = next_month - timedelta(days=1)
    return (last_day.date() - now_bkk.date()).days < END_MONTH_BOOST_DAYS

def campaign_for_month(m: int) -> str:
    return MONTH_CAMPAIGNS.get(m, "")

def parse_csv_bytes(csv_bytes: bytes):
    # พยายาม decode หลายแบบ
    for enc in ("utf-8-sig", "utf-8", "cp874", "latin-1"):
        try:
            text = csv_bytes.decode(enc)
            return text
        except Exception:
            continue
    # fallback
    return csv_bytes.decode("utf-8", errors="replace")

def read_rows_from_csv(text: str):
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        raise RuntimeError("CSV has no header row")

    # normalize keys to lower (ง่ายต่อการดึง)
    rows = []
    for r in reader:
        nr = {}
        for k, v in r.items():
            if k is None:
                continue
            nr[normalize_header(k)] = (v or "").strip()
        rows.append(nr)

    return rows

def upload_photo_unpublished(page_id: str, access_token: str, image_url: str):
    url = f"{GRAPH_BASE}/{page_id}/photos"
    data = {
        "url": image_url,
        "published": "false",
        "access_token": access_token,
    }
    r = requests.post(url, data=data, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Upload photo failed: {r.status_code} {r.text[:300]}")
    j = r.json()
    # ได้ id ของ photo
    return j.get("id")

def create_feed_post_with_attached_media(page_id: str, access_token: str, message: str, media_ids: list[str]):
    url = f"{GRAPH_BASE}/{page_id}/feed"
    data = {
        "message": message,
        "access_token": access_token,
    }
    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})

    r = requests.post(url, data=data, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Create post failed: {r.status_code} {r.text[:300]}")
    return r.json()

def main():
    page_id = must_env("PAGE_ID")
    token = must_env("PAGE_ACCESS_TOKEN")
    csv_url = must_env("SHOPEE_CSV_URL")

    now = bkk_now()
    boost = is_end_month_boost(now)
    campaign_line = campaign_for_month(now.month)

    print(f"INFO: Now (BKK) = {now.isoformat()}")
    print(f"INFO: End-month boost = {boost} (END_MONTH_BOOST_DAYS={END_MONTH_BOOST_DAYS})")
    print(f"INFO: Campaign line = {bool(campaign_line)}")
    print(f"INFO: POST_IMAGES_COUNT = {POST_IMAGES_COUNT}")
    print("INFO: Fetching CSV...")

    csv_bytes, headers = http_get_stream(csv_url, timeout=60)
    print(f"INFO: CSV bytes = {len(csv_bytes)}; content-type={headers.get('content-type','')}")
    text = parse_csv_bytes(csv_bytes)
    rows = read_rows_from_csv(text)
    print(f"INFO: CSV rows loaded = {len(rows)}")

    # ทำ list สินค้าที่ usable
    usable = []
    for r in rows:
        title, url, images = extract_product(r)
        if title and url and len(images) >= 1:
            # เอา key กันซ้ำ: ใช้ itemid ถ้ามี ไม่งั้นใช้ url
            key = r.get("itemid") or r.get("modelid") or url
            usable.append((key, title, url, images))

    if not usable:
        # แสดง header ช่วย debug
        sample_keys = list(rows[0].keys()) if rows else []
        raise SystemExit(
            "ERROR: No usable rows in CSV. Need title/name + product_link/url + at least 1 image_link.\n"
            f"Found keys sample: {sample_keys[:40]}"
        )

    state = load_state()
    posted_ids = set(state.get("posted_ids", []))

    # กันซ้ำ: เลือกจากของที่ยังไม่เคยโพสต์
    pool = [x for x in usable if x[0] not in posted_ids]
    if not pool:
        # รีเซ็ตถ้าใช้หมด
        posted_ids = set()
        state["posted_ids"] = []
        pool = usable[:]

    random.shuffle(pool)

    posts_done = 0
    for _ in range(POSTS):
        if not pool:
            break

        key, title, url, images = pool.pop()
        # เลือก 3 รูปแรก (หรือเท่าที่มี)
        images = images[:POST_IMAGES_COUNT]

        caption = build_caption(title=title, url=url, boost=boost, campaign_line=campaign_line)

        print(f"INFO: Picked product key={key}")
        print(f"INFO: Title={title[:80]}")
        print(f"INFO: Images={len(images)}")

        # Upload images unpublished → แล้ว attach ไปโพสต์เดียว
        media_ids = []
        for img in images:
            mid = upload_photo_unpublished(page_id, token, img)
            media_ids.append(mid)
            time.sleep(1.2)  # กัน rate limit

        res = create_feed_post_with_attached_media(page_id, token, caption, media_ids)
        post_id = res.get("id", "")
        print(f"INFO: Posted OK: {post_id}")

        state.setdefault("posted_ids", []).append(key)
        posts_done += 1

        # พักนิด
        time.sleep(2)

    save_state(state)
    print(f"INFO: Done. posts_done={posts_done}")

if __name__ == "__main__":
    main()
