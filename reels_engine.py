from ai_engine import ask_ai

def reels_script(product):

    prompt=f"""
เขียน script video reel 15 วินาที

สินค้า {product['name']}

Hook
โชว์สินค้า
ปิดการขาย
"""

    return ask_ai(prompt)
