import os
import random
from datetime import datetime, timedelta, timezone

from utils import load_csv, load_posted, save_posted, log
from product_filter import filter_products
from product_ranker import rank_products
from ai_caption import generate_caption
from facebook_post import post_product

TZ_TH = timezone(timedelta(hours=7))
CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()
MAX_ROWS = 100000


def get_mode() -> str:
    now = datetime.now(TZ_TH)
    hm = now.strftime("%H:%M")

    # เวลาไทย
    if hm == "09:00":
        return "viral"
    if hm == "12:00":
        return "product"
    if hm == "18:30":
        return "product"
    if hm == "21:00":
        return "engage"

    # manual run หรือ fallback
    return "product"


def run_engine():
    mode = get_mode()
    log(f"BEN AI ENGINE START | mode={mode}")

    if mode != "product":
        log("รอบนี้ยังเปิดใช้เฉพาะ product mode เป็นหลัก")
        mode = "product"

    rows = load_csv(CSV_URL, MAX_ROWS)
    posted_ids = load_posted()

    products = filter_products(rows, posted_ids)
    ranked = rank_products(products)

    if not ranked:
        log("NO PRODUCT FOUND")
        return

    pool = ranked[:20] if len(ranked) >= 20 else ranked
    product = random.choice(pool)

    caption = generate_caption(product)
    post_id = post_product(product, caption)

    if post_id:
        posted_ids.append(product["id"])
        save_posted(posted_ids)
        log(f"POSTED SUCCESS => {product['title']}")
    else:
        log("POST FAILED")
