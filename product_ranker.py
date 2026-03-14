from product_filter import score_product, top_one_percent


def rank_products(products):
    return sorted(products, key=score_product, reverse=True)


def rank_top_one_percent(products):
    return top_one_percent(products)
