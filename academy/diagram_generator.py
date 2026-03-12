from PIL import Image, ImageDraw

WIDTH=1080
HEIGHT=1920


def create_series_circuit(path):

    img=Image.new("RGB",(WIDTH,HEIGHT),(10,20,40))
    draw=ImageDraw.Draw(img)

    y=900

    draw.line((200,y,400,y),fill="yellow",width=8)
    draw.line((400,y,600,y),fill="yellow",width=8)
    draw.line((600,y,800,y),fill="yellow",width=8)

    draw.rectangle((400,850,450,950),outline="white",width=5)
    draw.rectangle((600,850,650,950),outline="white",width=5)

    draw.text((400,980),"หลอดไฟ",fill="white")
    draw.text((600,980),"หลอดไฟ",fill="white")

    draw.text((200,750),"วงจรอนุกรม",fill="yellow")

    img.save(path)



def create_parallel_circuit(path):

    img=Image.new("RGB",(WIDTH,HEIGHT),(10,20,40))
    draw=ImageDraw.Draw(img)

    draw.line((200,900,800,900),fill="yellow",width=8)

    draw.line((400,900,400,700),fill="yellow",width=8)
    draw.line((600,900,600,700),fill="yellow",width=8)

    draw.rectangle((380,650,420,750),outline="white",width=5)
    draw.rectangle((580,650,620,750),outline="white",width=5)

    draw.text((350,600),"วงจรขนาน",fill="yellow")

    img.save(path)
