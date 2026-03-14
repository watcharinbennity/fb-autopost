import os
import random
from datetime import datetime, timedelta, timezone

from utils import iter_csv_rows, load_posted, save_posted, log, image_key_from_url
from product_filter import build_product
from ai_caption import generate_caption
from facebook_post import post_product

TZ_TH = timezone(timedelta(hours=7))

CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

MAX_ROWS = 200000
TOP_PERCENT = 0.005


def score_product(product):

    sold = product["sold"]
    rating = product["rating"]

    sold_score = sold * 2
    rating_score = rating * 10

    trend_bonus = min(sold, 5000) * 0.05

    category_boost = 10 if product["group"] in [
        "lighting",
        "electrical",
        "tools"
    ] else 0

    recent_hot = 20 if sold > 1000 else 0

    return sold_score + rating_score + trend_bonus + category_boost + recent_hot


def rank_top_elite(products):

    ranked = sorted(products, key=score_product, reverse=True)

    keep = max(1, int(len(ranked) * TOP_PERCENT))

    return ranked[:keep]


def choose_product(csv_url, posted_data):

    posted_ids = set(posted_data.get("ids", []))
    posted_images = set(posted_data.get("image_keys", []))

    candidates = []

    stats = {
        "rows_seen": 0,
        "accepted": 0
    }

    for row in iter_csv_rows(csv_url, max_rows=MAX_ROWS):

        stats["rows_seen"] += 1

        product = build_product(row)

        if not product:
            continue

        if product["id"] in posted_ids:
            continue

        img_key = image_key_from_url(product["image"])

        if img_key in posted_images:
            continue

        product["image_key"] = img_key

        candidates.append(product)

        stats["accepted"] += 1

        candidates = sorted(
            candidates,
            key=score_product,
            reverse=True
        )[:1000]

    log(f"rows_seen={stats['rows_seen']}")
    log(f"accepted={stats['accepted']}")

    if not candidates:
        return None

    elite = rank_top_elite(candidates)

    if not elite:
        elite = candidates[:10]

    top_pool = elite[:20] if len(elite) >= 20 else elite

    chosen = random.choice(top_pool)

    log(
        f"CHOSEN => {chosen['title']} "
        f"| sold={chosen['sold']} "
        f"| rating={chosen['rating']} "
        f"| group={chosen['group']}"
    )

    return chosen


def run_engine():

    log("BEN AI ENGINE V70 START")

    posted_data = load_posted()

    product = choose_product(CSV_URL, posted_data)

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
