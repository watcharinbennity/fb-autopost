import os
import io
import json
import time
import random
import hashlib
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import pandas as pd


# -----------------------------
# ENV
# -----------------------------
PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
SHOPEE_CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

TZ_NAME = os.getenv("TZ", "Asia/Bangkok")
TZ = ZoneInfo(TZ_NAME)

POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "1"))
TOP_POOL = int(os.getenv("TOP_POOL", "200"))
REPOST_AFTER_DAYS = int(os.getenv("REPOST_AFTER_DAYS", "14"))

CAPTION_STYLE = os.getenv("CAPTION_STYLE", "short").strip().lower()  # short|full
HASHTAGS = os.getenv("HASHTAGS", "").strip()

FB_PRIVACY = os.getenv("FB_PRIVACY", "public").strip().lower()  # public|friends|... (page ปกติใช้ public)
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "25"))
FB_API_VERSION = os.getenv("FB_API_VERSION", "v20.0")

STATE_FILE = os.getenv("STATE_FILE", "state.json")


def die(msg: str, code: int = 1):
    print(f"[FATAL] {msg}")
    raise SystemExit(code)


def now_th() -> dt.datetime:
    return dt.datetime.now(tz=TZ)


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted_keys": {}, "last_run": ""}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted_keys": {}, "last_run": ""}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def http_get(url: str) -> bytes:
    headers = {"User-Agent": "fb-autopost/1.0"}
    r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.content


def http_post(url: str, data=None, files=None) -> dict:
    r = requests.post(url, data=data, files=files, timeout=HTTP_TIMEOUT)
    # Facebook บางทีตอบ 200 แต่มี error ใน JSON -> ต้องเช็คด้วย
    try:
        js = r.json()
    except Exception:
        die(f"Facebook response not JSON. status={r.status_code}, text={r.text[:200]}")
    if r.status_code >= 400 or ("error" in js):
        die(f"Facebook API error: {js}")
    return js


def parse_shopee_csv(content: bytes) -> pd.DataFrame:
    # พยายามอ่านแบบ utf-8 ก่อน ถ้าไม่ได้ fallback latin1
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            text = content.decode(enc)
            df = pd.read_csv(io.StringIO(text))
            return df
        except Exception:
            continue
    die("อ่าน CSV ไม่ได้ (encoding/format ไม่ถูกต้อง)")


def pick_candidates(df: pd.DataFrame) -> pd.DataFrame:
    # รองรับหลายชื่อคอลัมน์ (เพื่อให้ใช้ได้กับ CSV หลายแบบ)
    colmap = {c.lower(): c for c in df.columns}

    def col(*names):
        for n in names:
            if n in colmap:
                return colmap[n]
        return None

    title_c = col("title", "name", "product_name", "สินค้า", "ชื่อสินค้า")
    url_c = col("url", "link", "product_url", "ลิงก์", "ลิ้ง", "link_url")
    image_c = col("image", "image_url", "img", "img_url", "รูป", "รูปภาพ", "image_link")
    price_c = col("price", "price_sale", "sale_price", "ราคา", "ราคาขาย", "promotion_price")

    # ต้องมีอย่างน้อย title + url
    if not title_c or not url_c:
        die(f"CSV ต้องมีคอลัมน์อย่างน้อย title/name และ url/link (ตอนนี้มี: {list(df.columns)})")

    # สร้างคอลัมน์มาตรฐาน
    out = pd.DataFrame()
    out["title"] = df[title_c].astype(str).fillna("").str.strip()
    out["url"] = df[url_c].astype(str).fillna("").str.strip()

    out["image"] = ""
    if image_c:
        out["image"] = df[image_c].astype(str).fillna("").str.strip()

    out["price"] = ""
    if price_c:
        out["price"] = df[price_c].astype(str).fillna("").str.strip()

    # กรองแถวที่จำเป็นต้องมี
    out = out[(out["title"] != "") & (out["url"] != "")]
    if len(out) == 0:
        die("CSV ไม่มีแถวที่ใช้งานได้ (title/url ว่างหมด)")

    # เลือก top pool
    if TOP_POOL > 0 and len(out) > TOP_POOL:
        out = out.head(TOP_POOL)

    return out.reset_index(drop=True)


def is_repost_allowed(state: dict, key: str) -> bool:
    posted_keys = state.get("posted_keys", {})
    last = posted_keys.get(key)
    if not last:
        return True
    try:
        last_dt = dt.datetime.fromisoformat(last)
    except Exception:
        return True
    delta = now_th() - last_dt.astimezone(TZ)
    return delta.days >= REPOST_AFTER_DAYS


def build_caption(row: dict) -> str:
    title = row.get("title", "").strip()
    url = row.get("url", "").strip()
    price = row.get("price", "").strip()

    # ไม่ใช้คำว่า “เพจนายหน้า”
    # โทน: รวมดีลของใช้ในบ้าน & อุปกรณ์ไฟฟ้า
    if CAPTION_STYLE == "full":
        lines = [
            "🛒 รวมดีลของใช้ในบ้าน & อุปกรณ์ไฟฟ้า",
            f"✅ {title}",
        ]
        if price:
            lines.append(f"💰 ราคา: {price}")
        lines += [
            f"🔗 สั่งซื้อ/ดูรายละเอียด: {url}",
            "📩 ทักแชทสอบถามได้เลย",
        ]
    else:
        # short
        lines = [
            "🛒 ดีลของใช้ในบ้าน & อุปกรณ์ไฟฟ้า",
            f"✅ {title}",
        ]
        if price:
            lines.append(f"💰 {price}")
        lines.append(f"🔗 {url}")
        lines.append("📩 สอบถามได้เลย")

    caption = "\n".join(lines).strip()
    if HASHTAGS:
        caption = f"{caption}\n\n{HASHTAGS}".strip()
    return caption


def fb_upload_photo_unpublished(image_url: str) -> str:
    """
    อัปโหลดรูปแบบ unpublished เพื่อใช้แนบในโพสต์ feed
    return photo_id
    """
    api = f"https://graph.facebook.com/{FB_API_VERSION}/{PAGE_ID}/photos"
    img_bytes = http_get(image_url)
    files = {"source": ("image.jpg", img_bytes, "image/jpeg")}
    data = {
        "published": "false",
        "access_token": PAGE_ACCESS_TOKEN,
    }
    js = http_post(api, data=data, files=files)
    photo_id = js.get("id")
    if not photo_id:
        die(f"upload photo failed: {js}")
    return photo_id


def fb_create_post(message: str, photo_id: str | None = None) -> str:
    api = f"https://graph.facebook.com/{FB_API_VERSION}/{PAGE_ID}/feed"
    data = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN,
    }

    # privacy (page ส่วนใหญ่จะ public)
    if FB_PRIVACY == "public":
        # ไม่ต้องส่งก็ได้ แต่ส่งไปก็ไม่ผิดในหลายเคส
        pass

    if photo_id:
        # แนบรูปเป็น attached_media
        data["attached_media[0]"] = json.dumps({"media_fbid": photo_id})

    js = http_post(api, data=data)
    post_id = js.get("id")
    if not post_id:
        die(f"create post failed: {js}")
    return post_id


def main():
    print("[INFO] fb-autopost start")
    print(f"[INFO] now_th={now_th().isoformat()}")
    print(f"[INFO] TZ={TZ_NAME}")
    print(f"[INFO] POSTS_PER_RUN={POSTS_PER_RUN}, TOP_POOL={TOP_POOL}, REPOST_AFTER_DAYS={REPOST_AFTER_DAYS}")
    print(f"[INFO] CAPTION_STYLE={CAPTION_STYLE}")
    print(f"[INFO] HASHTAGS={HASHTAGS}")

    if not PAGE_ID:
        die("Missing env: PAGE_ID")
    if not PAGE_ACCESS_TOKEN:
        die("Missing env: PAGE_ACCESS_TOKEN")
    if not SHOPEE_CSV_URL:
        die("Missing env: SHOPEE_CSV_URL")

    state = load_state()

    # โหลด CSV
    print("[INFO] downloading CSV...")
    csv_bytes = http_get(SHOPEE_CSV_URL)
    df_raw = parse_shopee_csv(csv_bytes)
    df = pick_candidates(df_raw)

    # สุ่ม candidate ที่ยังไม่ติด repost window
    print(f"[INFO] candidates={len(df)}")
    rows = df.to_dict(orient="records")

    # ทำ list ของที่ “โพสต์ได้”
    usable = []
    for r in rows:
        key = sha1((r.get("title", "") + "|" + r.get("url", "")).strip())
        if is_repost_allowed(state, key):
            r["_key"] = key
            usable.append(r)

    if not usable:
        print("[WARN] ไม่มีรายการที่โพสต์ได้ (ติด REPOST_AFTER_DAYS ทั้งหมด) -> ออกปกติ")
        state["last_run"] = now_th().isoformat()
        save_state(state)
        return

    random.shuffle(usable)
    to_post = usable[: max(1, POSTS_PER_RUN)]

    posted = 0
    for r in to_post:
        caption = build_caption(r)
        image_url = (r.get("image") or "").strip()

        print("--------------------------------------------------")
        print("[INFO] Posting preview:")
        print(caption[:800])

        photo_id = None
        if image_url:
            try:
                print(f"[INFO] uploading image: {image_url}")
                photo_id = fb_upload_photo_unpublished(image_url)
                print(f"[INFO] photo_id={photo_id}")
            except Exception as e:
                # ถ้าอัปโหลดรูปไม่ได้ ยังโพสต์เป็นข้อความได้
                print(f"[WARN] upload image failed -> post text only. err={e}")

        print("[INFO] creating post...")
        post_id = fb_create_post(caption, photo_id=photo_id)
        print(f"[OK] posted post_id={post_id}")

        # update state
        state.setdefault("posted_keys", {})
        state["posted_keys"][r["_key"]] = now_th().isoformat()
        posted += 1

        # กันยิงถี่เกิน
        time.sleep(2)

    state["last_run"] = now_th().isoformat()
    save_state(state)
    print(f"[INFO] done. posted={posted}")


if __name__ == "__main__":
    main()
