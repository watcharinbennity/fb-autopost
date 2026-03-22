import os
import random
from utils import iter_csv_rows, load_posted, save_posted, log, image_key_from_url
from product_filter import build_product
from ai_caption import generate_caption, generate_comment_text
from facebook_post import post_product

CSV_URL = os.getenv("SHOPEE_CSV_URL", "").strip()

MAX_ROWS = 200000
TOP_PERCENT = 0.005


def score_product(product):
    sold = float(product["sold"])
    rating = float(product["rating"])
    commission = float(product.get("commission", 0.0))
    price = float(product.get("price", 0.0))
    group = product.get("group", "")

    sold_score = sold * 2.2
    rating_score = rating * 14.0
    commission_score = commission * 1.0

    hot_bonus = 40 if sold >= 1000 else 0
    social_bonus = 20 if sold >= 300 else 0

    # เน้นของราคากลางๆ ขายง่าย
    if group == "electrical":
        if 150 <= price <= 1500:
            price_bonus = 25
        elif 1500 < price <= 3000:
            price_bonus = 8
        else:
            price_bonus = 0
    elif group == "tools":
        if 300 <= price <= 5000:
            price_bonus = 25
        elif 5000 < price <= 15000:
            price_bonus = 10
        else:
            price_bonus = 0
    else:
        price_bonus = 0

    group_bonus = 15 if group in ["electrical", "tools"] else 0

    return (
        sold_score
        + rating_score
        + commission_score
        + hot_bonus
        + social_bonus
        + price_bonus
        + group_bonus
    )


def choose_product(csv_url, posted_data):
    posted_ids = set(posted_data.get("ids", []))
    posted_images = set(posted_data.get("image_keys", []))

    candidates = []
    rows_seen = 0
    build_none = 0
    dup_id = 0
    dup_image = 0
    accepted = 0

    for row in iter_csv_rows(csv_url, max_rows=MAX_ROWS):
        rows_seen += 1

        product = build_product(row)
        if not product:
            build_none += 1
            continue

        if product["id"] in posted_ids:
            dup_id += 1
            continue

        img_key = image_key_from_url(product["image"])
        if img_key in posted_images:
            dup_image += 1
            continue

        product["image_key"] = img_key
        product["score"] = score_product(product)
        candidates.append(product)
        accepted += 1

        # เก็บเฉพาะตัวเด่น ลดแรม
        candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)[:1200]

    log(f"rows_seen={rows_seen}")
    log(f"build_none={build_none}")
    log(f"dup_id={dup_id}")
    log(f"dup_image={dup_image}")
    log(f"accepted={accepted}")
    log(f"candidates={len(candidates)}")

    if not candidates:
        return None

    elite_size = max(1, int(len(candidates) * TOP_PERCENT))
    elite = sorted(candidates, key=lambda x: x["score"], reverse=True)[:elite_size]

    # สุ่มในกลุ่มท็อป เพื่อไม่ซ้ำแนวเกินไป
    top_pool = elite[:20] if len(elite) >= 20 else elite
    chosen = random.choice(top_pool)

    log(
        f"CHOSEN => {chosen['title']} "
        f"| sold={chosen['sold']} "
        f"| rating={chosen['rating']} "
        f"| price={chosen['price']:.2f} "
        f"| commission={chosen['commission']:.2f} "
        f"| group={chosen['group']} "
        f"| score={chosen['score']:.2f}"
    )

    return chosen


def run_engine():
    forced_mode = os.getenv("POST_MODE", "").strip().lower()
    log(f"BEN AI ENGINE V200 START | POST_MODE={forced_mode or 'auto'}")

    posted_data = load_posted()
    product = choose_product(CSV_URL, posted_data)

    if not product:
        log("NO PRODUCT FOUND")
        return

    log("READY TO POST PRODUCT NOW")

    caption = generate_caption(product)
    comment_text = generate_comment_text(product)
    post_id = post_product(product, caption, comment_text=comment_text)

    if post_id:
        posted_data["ids"].append(product["id"])
        posted_data["image_keys"].append(product["image_key"])

        posted_data["ids"] = posted_data["ids"][-5000:]
        posted_data["image_keys"] = posted_data["image_keys"][-5000:]

        save_posted(posted_data)
        log(f"POSTED SUCCESS => {product['title']}")
    else:
        log("POST FAILED")
