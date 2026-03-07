from datetime import datetime, timedelta, timezone

from caption_ai import (
    generate_product_caption,
    generate_viral_caption,
    generate_engagement_caption,
)
from image_ai import get_image_by_topic, get_image_by_category
from product_ai import pick_product, mark_product_posted, load_posted_products
from fb_publisher import publish_post, comment_product
from analytics_engine import log_post
from reel_ai import create_reel_script, save_reel_script

TH = timezone(timedelta(hours=7))

TOPICS = [
    "ไฟโซล่าดีไหม",
    "ปลั๊กไฟแบบไหนปลอดภัย",
    "เครื่องมือช่างที่ควรมีติดบ้าน",
    "5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน",
    "หลอดไฟ LED ประหยัดไฟจริงไหม",
]


def get_mode() -> str | None:
    now = datetime.now(TH)
    minute_of_day = now.hour * 60 + now.minute

    if 8 * 60 <= minute_of_day <= 10 * 60:
        return "viral"
    if 11 * 60 <= minute_of_day <= 13 * 60:
        return "product"
    if 18 * 60 <= minute_of_day <= 19 * 60:
        return "product"
    if 20 * 60 <= minute_of_day <= 22 * 60:
        return "engagement"

    return None


def get_first_run() -> bool:
    posted = load_posted_products()
    return len(posted) == 0


def run_viral() -> None:
    topic = TOPICS[datetime.now(TH).day % len(TOPICS)]
    image_path = get_image_by_topic(topic)
    caption = generate_viral_caption(topic)

    post_id = publish_post(caption, image_path)
    reel_script = create_reel_script(topic=topic)
    save_reel_script(reel_script)
    log_post(mode="viral", topic=topic, image=image_path, post_id=post_id)


def run_engagement() -> None:
    topic = "5 อุปกรณ์ไฟฟ้าที่ควรมีติดบ้าน"
    image_path = get_image_by_topic(topic)
    caption = generate_engagement_caption()

    post_id = publish_post(caption, image_path)
    reel_script = create_reel_script(topic=topic)
    save_reel_script(reel_script)
    log_post(mode="engagement", topic=topic, image=image_path, post_id=post_id)


def run_product() -> None:
    product = pick_product()
    if not product:
        print("NO PRODUCT", flush=True)
        return

    image_path = get_image_by_category(product.get("category", ""))
    caption = generate_product_caption(product)
    caption = f"{caption}\n\n🛒 สั่งซื้อ\n{product['link']}"

    post_id = publish_post(caption, image_path)

    if post_id:
        comment_product(post_id, product["link"])
        mark_product_posted(product)

    reel_script = create_reel_script(topic=product["name"], product=product)
    save_reel_script(reel_script)
    log_post(
        mode="product",
        topic=product["name"],
        image=image_path,
        product=product,
        post_id=post_id,
    )


def main() -> None:
    if get_first_run():
        print("FIRST RUN -> FORCE PRODUCT", flush=True)
        run_product()
        return

    mode = get_mode()
    if not mode:
        print("SKIP TIME", flush=True)
        return

    if mode == "viral":
        run_viral()
        return

    if mode == "engagement":
        run_engagement()
        return

    run_product()


if __name__ == "__main__":
    main()
