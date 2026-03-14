import os
import random
from utils import iter_csv_rows, load_posted, save_posted, log, image_key_from_url
from product_filter import build_product
from ai_caption import generate_caption
from facebook_post import post_product

CSV_URL = os.getenv("SHOPEE_CSV_URL")

MAX_ROWS = 200000
TOP_PERCENT = 0.005


def score_product(product):

    sold = product["sold"]
    rating = product["rating"]

    sold_score = sold * 2
    rating_score = rating * 10

    trend_bonus = min(sold, 5000) * 0.05
    hot_bonus = 20 if sold > 1000 else 0

    category_boost = 10 if product["group"] in [
        "lighting",
        "electrical",
        "tools"
    ] else 0

    return sold_score + rating_score + trend_bonus + hot_bonus + category_boost


def choose_product(csv_url, posted_data):

    posted_ids = set(posted_data.get("ids", []))
    posted_images = set(posted_data.get("image_keys", []))

    candidates = []

    rows_seen = 0

    for row in iter_csv_rows(csv_url, max_rows=MAX_ROWS):

        rows_seen += 1

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

        candidates = sorted(
            candidates,
            key=score_product,
            reverse=True
        )[:1000]

    log(f"rows_seen={rows_seen}")
    log(f"candidates={len(candidates)}")

    if not candidates:
        return None

    elite_size = max(1, int(len(candidates) * TOP_PERCENT))

    elite = sorted(
        candidates,
        key=score_product,
        reverse=True
    )[:elite_size]

    top_pool = elite[:20] if len(elite) >= 20 else elite

    chosen = random.choice(top_pool)

    log(
        f"CHOSEN => {chosen['title']} "
        f"| sold={chosen['sold']} "
        f"| rating={chosen['rating']}"
    )

    return chosen


def run_engine():

    log("BEN AI ENGINE V80 START")

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
