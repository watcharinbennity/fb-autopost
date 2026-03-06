import os
import io
import csv
import json
import time
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import requests

# =========================
# CONFIG
# =========================
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

STATE_FILE = os.getenv("STATE_FILE", "state.json")
MAX_STATE_ITEMS = int(os.getenv("MAX_STATE_ITEMS", "9000"))

# Page + CSV
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

# Shopee Affiliate
AFFILIATE_ID = os.getenv("SHOPEE_AFFILIATE_ID", "15328100363").strip()
AFF_UTM_SOURCE = os.getenv("AFF_UTM_SOURCE", "facebook").strip()
AFF_TAG = os.getenv("AFF_TAG", "BENHomeElectrical").strip()

# Schedule (Bangkok)
TZ_BKK = timezone(timedelta(hours=7))
SLOTS_BKK = os.getenv("SLOTS_BKK", "12:00,18:30").split(",")
SLOTS_BKK = [s.strip() for s in SLOTS_BKK if s.strip()]
SLOT_WINDOW_MIN = int(os.getenv("SLOT_WINDOW_MIN", "12"))  # ยอมให้คลาดเคลื่อน +/- กี่นาที

# Run behavior
POSTS_MAX_PER_RUN = int(os.getenv("POSTS_MAX_PER_RUN", "1"))
FORCE_POST = os.getenv("FORCE_POST", "0").strip().lower() in ("1", "true", "yes")
FIRST_RUN_POST_1 = os.getenv("FIRST_RUN_POST_1", "1").strip().lower() in ("1", "true", "yes")

# Selection filters
MIN_RATING = float(os.getenv("MIN_RATING", "4.7"))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "15"))
MIN_SOLD = int(os.getenv("MIN_SOLD", "50"))
PRICE_MIN = float(os.getenv("PRICE_MIN", "59"))
PRICE_MAX = float(os.getenv("PRICE_MAX", "4999"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "21"))

# Media
POST_IMAGES_COUNT = int(os.getenv("POST_IMAGES_COUNT", "3"))

# CSV streaming
STREAM_MAX_ROWS = int(os.getenv("STREAM_MAX_ROWS", "250000"))
TOPK_POOL = int(os.getenv("TOPK_POOL", "220"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "40"))

# Caption
BRAND = os.getenv("BRAND", "BEN Home & Electrical").strip()
HASHTAGS = os.getenv(
    "HASHTAGS",
    "#BENHomeElectrical #ของใช้ในบ้าน #อุปกรณ์ไฟฟ้า #เครื่องมือช่าง #งานช่าง #ซ่อมบ้าน #ShopeeAffiliate"
).strip()

# Targeting: ให้ “ตรงเพจ” มากขึ้น (กรองทั้ง title/description + category)
ALLOW_KEYWORDS = os.getenv(
    "ALLOW_KEYWORDS",
    r"(ไฟฟ้า|ปลั๊ก|รางปลั๊ก|สายไฟ|เบรกเกอร์|ตู้ไฟ|หลอดไฟ|โคม|สวิตช์|มิเตอร์|UPS|แบตเตอรี่|LiFePO4|อินเวอร์เตอร์|โซล่า|solar|ชาร์จ|charger|หัวชาร์จ|adapter|อะแดปเตอร์|พาวเวอร์แบงก์|เครื่องมือ|สว่าน|ค้อน|ประแจ|คีม|ไขควง|งานช่าง|บ้าน|ซ่อม|DIY|กาว|เทปพันสาย|ปลั๊กพ่วง|ปลั๊กกันไฟกระชาก)"
).strip()

BLOCK_KEYWORDS = os.getenv(
    "BLOCK_KEYWORDS",
    r"(เสื้อผ้า|บรา|กางเกง|เดรส|รองเท้าแฟชั่น|เครื่องสำอาง|สกินแคร์|น้ำหอม|ของเล่นเด็ก|ตุ๊กตา|อาหารเสริม|บุหรี่|แอลกอฮอล์|ย้อมผม|วิกผม|แฟลชกล้อง|กล้องถ่ายรูป|เลนส์)"
).strip()

# หมวดที่อยาก “อนุญาต” (ถ้ามีใน CSV)
ALLOW_CATEGORIES = os.getenv(
    "ALLOW_CATEGORIES",
    r"(Home\s*&\s*Living|Home Improvement|Tools|Hardware|Electrical|Lighting|Cables|Chargers|Converters|Power|Solar|Batteries|DIY)"
).strip()

BLOCK_CATEGORIES = os.getenv(
    "BLOCK_CATEGORIES",
    r"(Beauty|Fashion|Toys|Groceries|Food|Health|Baby|Women|Men|Camera|Photography)"
).strip()


def die(msg: str, code: int = 1):
    print("FATAL:", msg)
    raise SystemExit(code)


if not PAGE_ID:
    die("Missing env: PAGE_ID")
if not PAGE_ACCESS_TOKEN:
    die("Missing env: PAGE_ACCESS_TOKEN")
if not SHOPEE_CSV_URL:
    die("Missing env: SHOPEE_CSV_URL")


# =========================
# TIME / STATE
# =========================
def now_bkk() -> datetime:
    return datetime.now(TZ_BKK)


def load_state() -> dict:
    base = {"used_urls": [], "posted_slots": {}, "posted_at": {}, "first_run_done": False}
    if not os.path.exists(STATE_FILE):
        return base
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
        if not isinstance(s, dict):
            return base
        s.setdefault("used_urls", [])
        s.setdefault("posted_slots", {})
        s.setdefault("posted_at", {})
        s.setdefault("first_run_done", False)
        if not isinstance(s["used_urls"], list):
            s["used_urls"] = []
        if not isinstance(s["posted_slots"], dict):
            s["posted_slots"] = {}
        if not isinstance(s["posted_at"], dict):
            s["posted_at"] = {}
        if not isinstance(s["first_run_done"], bool):
            s["first_run_done"] = False
        return s
    except Exception:
        return base


def save_state(state: dict) -> None:
    used = state.get("used_urls", [])
    if len(used) > MAX_STATE_ITEMS:
        state["used_urls"] = used[-MAX_STATE_ITEMS:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def mark_slot_posted(state: dict, now: datetime, slot_hhmm: str) -> None:
    key = now.strftime("%Y-%m-%d")
    state.setdefault("posted_slots", {})
    state["posted_slots"].setdefault(key, [])
    if slot_hhmm not in state["posted_slots"][key]:
        state["posted_slots"][key].append(slot_hhmm)


def is_due_now(now: datetime, hhmm: str, window_min: int) -> bool:
    hh, mm = hhmm.split(":")
    t = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    delta = abs((now - t).total_seconds()) / 60.0
    return delta <= window_min


def due_slots_now(state: dict, now: datetime) -> List[str]:
    key = now.strftime("%Y-%m-%d")
    posted = set(state.get("posted_slots", {}).get(key, []))
    due = []
    for hhmm in SLOTS_BKK:
        if hhmm in posted:
            continue
        if is_due_now(now, hhmm, SLOT_WINDOW_MIN):
            due.append(hhmm)
    return due


# =========================
# HELPERS
# =========================
def safe_float(x: str, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        x = str(x).strip()
        if not x:
            return default
        return float(x)
    except Exception:
        return default


def safe_int(x: str, default: int = 0) -> int:
    try:
        if x is None:
            return default
        x = str(x).strip()
        if not x:
            return default
        # บางไฟล์เป็น "1,234"
        x = x.replace(",", "")
        return int(float(x))
    except Exception:
        return default


def norm_text(*parts: Optional[str]) -> str:
    s = " ".join([p for p in parts if p])
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compile_re(pat: str) -> re.Pattern:
    return re.compile(pat, re.IGNORECASE | re.UNICODE)


RE_ALLOW = compile_re(ALLOW_KEYWORDS)
RE_BLOCK = compile_re(BLOCK_KEYWORDS)
RE_ALLOW_CAT = compile_re(ALLOW_CATEGORIES)
RE_BLOCK_CAT = compile_re(BLOCK_CATEGORIES)


def pick_images(row: Dict[str, str], n: int) -> List[str]:
    # คีย์ที่พบบ่อย: image_link, image_link_2.., image_link_10, additional_image_link
    urls: List[str] = []

    # 1) image_link ตรงๆ
    for k in ["image_link", "image_link_2", "image_link_3", "image_link_4", "image_link_5",
              "image_link_6", "image_link_7", "image_link_8", "image_link_9", "image_link_10"]:
        v = (row.get(k) or "").strip()
        if v and v not in urls:
            urls.append(v)

    # 2) คีย์อื่นที่ขึ้นต้น image_link*
    for k, v in row.items():
        if len(urls) >= n:
            break
        if not k:
            continue
        if k.lower().startswith("image_link") and k not in ["image_link", "image_link_2", "image_link_3", "image_link_4",
                                                            "image_link_5", "image_link_6", "image_link_7", "image_link_8",
                                                            "image_link_9", "image_link_10"]:
            vv = (v or "").strip()
            if vv and vv not in urls:
                urls.append(vv)

    # 3) additional_image_link อาจมีหลายลิงก์คั่นด้วย | หรือ ,
    add = (row.get("additional_image_link") or "").strip()
    if add and len(urls) < n:
        parts = re.split(r"[|,]\s*", add)
        for p in parts:
            if len(urls) >= n:
                break
            p = p.strip()
            if p and p not in urls:
                urls.append(p)

    return urls[:n]


def build_affiliate_url(row: Dict[str, str]) -> str:
    # ใช้ product_short link ถ้ามี (มักเป็น shope.ee/an_redir)
    short_link = (row.get("product_short link") or row.get("product_short_link") or "").strip()
    product_link = (row.get("product_link") or "").strip()

    base = short_link or product_link
    if not base:
        return ""

    # เติมพารามิเตอร์นายหน้าให้ชัวร์
    u = urlparse(base)
    q = dict(parse_qsl(u.query, keep_blank_values=True))

    # ถ้าเป็น shope.ee/an_redir แล้วมี origin_link อยู่ ก็เติม affiliate params ที่ปลาย query ได้เลย
    q["affiliate_id"] = AFFILIATE_ID
    q["utm_source"] = AFF_UTM_SOURCE
    q["afftag"] = AFF_TAG

    new_q = urlencode(q, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))


def looks_relevant(row: Dict[str, str]) -> bool:
    title = (row.get("title") or "").strip()
    desc = (row.get("description") or "").strip()

    cat = norm_text(
        row.get("global_category1"),
        row.get("global_category2"),
        row.get("global_category3"),
    )

    blob = norm_text(title, desc, cat)

    # บล็อกก่อน
    if RE_BLOCK.search(blob):
        return False
    if cat and RE_BLOCK_CAT.search(cat):
        return False

    # ต้องผ่าน allow อย่างน้อย 1 อย่าง (keyword หรือ category)
    allow_hit = bool(RE_ALLOW.search(blob)) or (cat and bool(RE_ALLOW_CAT.search(cat)))
    return allow_hit


def score_row(row: Dict[str, str]) -> float:
    rating = safe_float(row.get("item_rating") or row.get("rating") or row.get("item_rating_score"), 0.0)
    sold = safe_int(row.get("item_sold") or row.get("sold") or row.get("historical_sold"), 0)
    discount = safe_float(row.get("discount_percentage") or row.get("discount") or "0", 0.0)
    price = safe_float(row.get("sale_price") or row.get("price") or "0", 0.0)
    like = safe_int(row.get("like") or "0", 0)

    # สกอร์เน้น: sold + rating + discount + like - ราคาแพงเกินไปเล็กน้อย
    s = (sold * 0.06) + (rating * 8.0) + (discount * 0.45) + (like * 0.01) - (price * 0.0006)
    return s


@dataclass
class Candidate:
    row: Dict[str, str]
    score: float
    url: str
    images: List[str]


def row_pass_numeric_filters(row: Dict[str, str]) -> bool:
    rating = safe_float(row.get("item_rating") or row.get("rating") or "0", 0.0)
    sold = safe_int(row.get("item_sold") or "0", 0)
    discount = safe_float(row.get("discount_percentage") or "0", 0.0)
    price = safe_float(row.get("sale_price") or row.get("price") or "0", 0.0)

    if rating < MIN_RATING:
        return False
    if sold < MIN_SOLD:
        return False
    if discount < MIN_DISCOUNT_PCT:
        return False
    if price < PRICE_MIN or price > PRICE_MAX:
        return False
    return True


def already_used(state: dict, url: str, now: datetime) -> bool:
    used_urls = set(state.get("used_urls", []))
    if url in used_urls:
        # ถ้าต้องการ repost ได้ ให้เช็ค posted_at
        posted_at = state.get("posted_at", {}).get(url)
        if posted_at:
            try:
                dt = datetime.fromisoformat(posted_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=TZ_BKK)
                if (now - dt).days >= REPOST_AFTER_DAYS:
                    return False
            except Exception:
                pass
        return True
    return False


# =========================
# FACEBOOK GRAPH API
# =========================
def fb_post_photos_and_feed(page_id: str, token: str, message: str, image_urls: List[str]) -> str:
    # 1) Upload photos unpublished
    media_fbs = []
    for idx, img_url in enumerate(image_urls):
        print(f"INFO: Upload photo {idx+1}/{len(image_urls)}")
        r = requests.post(
            f"{GRAPH_BASE}/{page_id}/photos",
            data={
                "url": img_url,
                "published": "false",
                "access_token": token,
            },
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Upload photo failed: {r.status_code} {r.text}")
        pid = r.json().get("id")
        if not pid:
            raise RuntimeError(f"Upload photo no id: {r.text}")
        media_fbs.append({"media_fbid": pid})

    # 2) Create feed post with attached_media
    payload = {
        "message": message,
        "access_token": token,
    }
    # attached_media[0], attached_media[1]...
    for i, m in enumerate(media_fbs):
        payload[f"attached_media[{i}]"] = json.dumps(m, ensure_ascii=False)

    r2 = requests.post(f"{GRAPH_BASE}/{page_id}/feed", data=payload, timeout=REQUEST_TIMEOUT)
    if r2.status_code >= 400:
        raise RuntimeError(f"Create feed failed: {r2.status_code} {r2.text}")

    post_id = r2.json().get("id", "")
    return post_id


# =========================
# CSV STREAM + PICK
# =========================
def iter_csv_rows(url: str):
    with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT) as r:
        r.raise_for_status()
        # พยายามเดา encoding แบบปลอดภัย
        content = r.content
        # ถ้าไฟล์ใหญ่มาก r.content อาจหนัก แต่ส่วนใหญ่ CSV affiliate ไม่ใหญ่ระดับนั้น
        # ถ้าใหญ่จริง: เปลี่ยนเป็น decode line-by-line ภายหลังได้
        try:
            text = content.decode("utf-8-sig", errors="replace")
        except Exception:
            text = content.decode("utf-8", errors="replace")

        f = io.StringIO(text)
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= STREAM_MAX_ROWS:
                break
            if not isinstance(row, dict):
                continue
            yield row


def pick_best_candidate(state: dict, now: datetime) -> Optional[Candidate]:
    pool: List[Candidate] = []
    seen = 0

    for row in iter_csv_rows(SHOPEE_CSV_URL):
        seen += 1

        if not looks_relevant(row):
            continue
        if not row_pass_numeric_filters(row):
            continue

        aff_url = build_affiliate_url(row)
        if not aff_url:
            continue

        if already_used(state, aff_url, now):
            continue

        images = pick_images(row, POST_IMAGES_COUNT)
        if len(images) < 1:
            continue  # เพจต้องมีรูปเท่านั้น

        s = score_row(row)
        pool.append(Candidate(row=row, score=s, url=aff_url, images=images))

        if len(pool) >= TOPK_POOL:
            break

    if not pool:
        print(f"INFO: No candidate found (scanned rows={seen}).")
        return None

    pool.sort(key=lambda x: x.score, reverse=True)
    # สุ่มเล็กน้อยจาก top เพื่อไม่ซ้ำจำเจ
    top = pool[: min(15, len(pool))]
    chosen = random.choice(top)
    return chosen


def build_caption(c: Candidate) -> str:
    row = c.row

    title = (row.get("title") or "").strip()
    price = safe_float(row.get("sale_price") or row.get("price") or "0", 0.0)
    normal_price = safe_float(row.get("price") or row.get("normal_price") or "0", 0.0)
    discount = safe_float(row.get("discount_percentage") or "0", 0.0)
    rating = safe_float(row.get("item_rating") or row.get("rating") or "0", 0.0)
    sold = safe_int(row.get("item_sold") or "0", 0)

    # ถ้าปกติไม่มี normal_price ให้แสดงแบบไม่งง
    if normal_price <= 0 or normal_price == price:
        promo_line = f"💸 ราคาโปร: {int(price):,} บาท"
    else:
        promo_line = f"💸 ราคาโปร: {int(price):,} บาท (ปกติ {int(normal_price):,} | ลด {int(discount)}%)"

    msg = []
    msg.append(f"🏠⚡ {BRAND}")
    msg.append("✅ คัดตัวฮิตรีวิวดี ราคาคุ้ม")
    msg.append("")
    msg.append(f"🛒 {title}")
    msg.append("")
    msg.append(promo_line)
    msg.append(f"⭐ เรตติ้ง: {rating:.1f}/5")
    msg.append(f"📦 ขายแล้ว: {sold:,} ชิ้น")
    msg.append("")
    msg.append("👉 ลิงก์นายหน้า (กดดูโปร/โค้ดส่วนลด):")
    msg.append(c.url)
    msg.append("")
    msg.append(HASHTAGS)

    return "\n".join(msg).strip()


# =========================
# MAIN
# =========================
def main():
    state = load_state()
    now = now_bkk()

    # === โหมด Force/First run ===
    force_post = FORCE_POST
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        force_post = True
        print("INFO: First run detected -> FORCE 1 post immediately")

    due = due_slots_now(state, now)

    if not force_post and not due:
        print(f"INFO: No due slot now. now={now.isoformat()} slots={SLOTS_BKK} window_min={SLOT_WINDOW_MIN}")
        return

    posts_target = POSTS_MAX_PER_RUN
    posts_done = 0

    # ถ้าเป็น force_post (manual/first_run) ไม่ต้องผูก slot
    run_slots = due if (not force_post) else ["FORCE"]

    for slot in run_slots:
        if posts_done >= posts_target:
            break

        c = pick_best_candidate(state, now)
        if not c:
            print("WARN: No candidate -> nothing posted.")
            break

        caption = build_caption(c)
        # โพสต์
        try:
            post_id = fb_post_photos_and_feed(PAGE_ID, PAGE_ACCESS_TOKEN, caption, c.images)
            print(f"INFO: Posted OK. post_id={post_id}")
        except Exception as e:
            print(f"ERROR: Post failed: {e}")
            raise

        # บันทึก state กันซ้ำ
        state.setdefault("used_urls", [])
        state.setdefault("posted_at", {})
        state["used_urls"].append(c.url)
        state["posted_at"][c.url] = now.isoformat()

        if slot != "FORCE":
            mark_slot_posted(state, now, slot)

        posts_done += 1

        # กันยิงถี่เกิน
        time.sleep(2)

    # ทำเครื่องหมาย first_run_done หลังจากพยายามโพสต์เสร็จ
    if FIRST_RUN_POST_1 and not state.get("first_run_done", False):
        if posts_done > 0:
            state["first_run_done"] = True
            print("INFO: first_run_done set to True")
        else:
            print("WARN: first_run posting produced 0 posts; keep first_run_done=False so it will try again next run")

    save_state(state)
    print(f"INFO: Done. posts_done={posts_done}")


if __name__ == "__main__":
    main()
