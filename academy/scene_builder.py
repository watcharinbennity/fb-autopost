from PIL import Image,ImageDraw

W=1080
H=1920

def canvas(title):

    img=Image.new("RGB",(W,H),(8,18,35))
    draw=ImageDraw.Draw(img)

    draw.text((80,120),title,(255,220,60))

    draw.rectangle((80,380,1000,1500),outline="white",width=6)

    return img,draw


def series(title):

    img,draw=canvas(title)

    y=1000

    draw.line((200,y,400,y),fill="yellow",width=10)

    draw.rectangle((400,920,480,1080),outline="white",width=6)

    draw.line((480,y,650,y),fill="yellow",width=10)

    draw.rectangle((650,920,730,1080),outline="white",width=6)

    draw.line((730,y,900,y),fill="yellow",width=10)

    return img


def parallel(title):

    img,draw=canvas(title)

    draw.line((200,820,200,1320),fill="yellow",width=10)
    draw.line((900,820,900,1320),fill="yellow",width=10)

    draw.line((200,900,500,900),fill="yellow",width=10)
    draw.rectangle((500,850,580,950),outline="white",width=6)
    draw.line((580,900,900,900),fill="yellow",width=10)

    draw.line((200,1150,700,1150),fill="yellow",width=10)
    draw.rectangle((700,1100,780,1200),outline="white",width=6)
    draw.line((780,1150,900,1150),fill="yellow",width=10)

    return img


def flow(title):

    img,draw=canvas(title)

    y=1000

    draw.line((200,y,900,y),fill="yellow",width=10)

    for x in [350,500,650,800]:

        draw.polygon([(x,y-30),(x+60,y),(x,y+30)],fill="red")

    return img
