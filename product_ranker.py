def score_product(product):
    sold_score = product["sold"] * 2
    rating_score = product["rating"] * 10
    return sold_score + rating_score


def rank_products(products):
    return sorted(products, key=score_product, reverse=True)
