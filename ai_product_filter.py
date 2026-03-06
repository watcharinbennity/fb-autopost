KEYWORDS = [
"ปลั๊ก","สายไฟ","หลอดไฟ","โคมไฟ",
"ไขควง","คีม","สว่าน","multimeter",
"plug","socket","power strip","led",
"lamp","wire","cable","tool"
]

def allow_product(name):

    name=name.lower()

    for k in KEYWORDS:
        if k in name:
            return True

    return False
