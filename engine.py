import os
import random
from datetime import datetime, timedelta, timezone

from utils import iter_csv_rows, load_posted, save_posted, log
from product_filter import build_product, score_product
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


def choose_best_product_stream(csv_url, posted_ids, max_rows=100000):
    posted_set = set(str(x) for x in posted_ids)
    candidates = []

    for row in iter_csv_rows(csv_url, max_rows=max_rows):
        product = build_product(row)
        if not product:
            continue

        if product["id"] in posted_set:
            continue

        candidates.append(product)
        candidates = sorted(candidates, key=score_product, reverse=True)[:50]

    if not candidates:
        return None

    top_pool = candidates[:20] if len(candidates) >= 20 else candidates
    return random.choice(top_pool)


def run_engine():
    mode = get_mode()
    log(f"BEN AI ENGINE START | mode={mode}")

    if mode != "product":
        log("รอบนี้ยังเปิดใช้เฉพาะ product mode เป็นหลัก")
        mode = "product"

    posted_ids = load_posted()
    product = choose_best_product_stream(CSV_URL, posted_ids, max_rows=MAX_ROWS)

    if not product:
        log("NO PRODUCT FOUND")
        return

    caption = generate_caption(product)
    post_id = post_product(product, caption)

    if post_id:
        posted_ids.append(product["id"])
        save_posted(posted_ids)
        log(f"POSTED SUCCESS => {product['title']}")
    else:
        log("POST FAILED")
