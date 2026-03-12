from PIL import Image, ImageDraw

WIDTH=1080
HEIGHT=1920


def create_circuit(path):

    img=Image.new("RGB",(WIDTH,HEIGHT),(10,20,40))
    draw=ImageDraw.Draw(img)

    y=900

    draw.line((200,y,800,y),fill="yellow",width=10)

    draw.rectangle((450,850,520,950),outline="white",width=6)

    draw.text((350,750),"ตัวอย่างวงจรไฟฟ้า",fill="yellow")

    draw.polygon([(600,900),(650,880),(650,920)],fill="red")

    img.save(path)
