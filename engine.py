import os
import random
from datetime import datetime, timedelta, timezone

from utils import iter_csv_rows, load_posted, save_posted, log, image_key_from_url
from product_filter import build_product, score_product
from product_ranker import rank_top_one_percent
from ai_caption import generate_caption
from facebook_post import post_product

TZ_TH = timezone(timedelta(hours=7))
CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()
MAX_ROWS = 100000


def get_mode() -> str:
    now = datetime.now(TZ_TH)
    hm = now.strftime("%H:%M")

    if hm == "09:00":
        return "viral"
    if hm == "12:00":
        return "product"
    if hm == "18:30":
        return "product"
    if hm == "21:00":
        return "engage"

    return "product"


def choose_best_product_stream(csv_url, posted_data, max_rows=100000):
    posted_ids = set(str(x) for x in posted_data.get("ids", []))
    posted_images = set(str(x) for x in posted_data.get("image_keys", []))

    candidates = []

    for row in iter_csv_rows(csv_url, max_rows=max_rows):
        product = build_product(row)
        if not product:
            continue

        if product["id"] in posted_ids:
            continue

        img_key = image_key_from_url(product["image"])
        if img_key in posted_images:
            continue

        product["image_key"] = img_key

        # เก็บ candidate ระหว่างอ่าน ไม่กินแรมเกิน
        candidates.append(product)
        candidates = sorted(candidates, key=score_product, reverse=True)[:500]

    if not candidates:
        return None

    # เอา top 1%
    elite = rank_top_one_percent(candidates)
    if not elite:
        elite = candidates[:10]

    # เลือกจากกลุ่มบนสุด เพื่อให้ยังมีความหลากหลาย
    top_pool = elite[:20] if len(elite) >= 20 else elite
    return random.choice(top_pool)


def run_engine():
    mode = get_mode()
    log(f"BEN AI ENGINE START | mode={mode}")

    if mode != "product":
        log("รอบนี้ยังเปิดใช้เฉพาะ product mode เป็นหลัก")
        mode = "product"

    posted_data = load_posted()
    product = choose_best_product_stream(CSV_URL, posted_data, max_rows=MAX_ROWS)

    if not product:
        log("NO PRODUCT FOUND")
        return

    caption = generate_caption(product)
    post_id = post_product(product, caption)

    if post_id:
        posted_data["ids"].append(product["id"])
        posted_data["image_keys"].append(product["image_key"])

        posted_data["ids"] = posted_data["ids"][-5000:]
        posted_data["image_keys"] = posted_data["image_keys"][-5000:]

        save_posted(posted_data)
        log(f"POSTED SUCCESS => {product['title']}")
    else:
        log("POST FAILED")
