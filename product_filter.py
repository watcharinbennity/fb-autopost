ALLOWED = [
"ปลั๊ก","สายไฟ","หลอด","โคม","สวิตช์",
"ไขควง","คีม","สว่าน","มัลติมิเตอร์",
"ups","อินเวอร์เตอร์","โซล่า","แบตเตอรี่"
]

BLOCK = [
"เสื้อ","รองเท้า","กระเป๋า","ลิป","ครีม",
"อาหาร","ขนม","ของเล่น"
]

def allow_product(name):

    name=name.lower()

    for b in BLOCK:
        if b in name:
            return False

    for a in ALLOWED:
        if a in name:
            return True

    return False
