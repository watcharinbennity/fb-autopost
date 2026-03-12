# academy_topics.py

def generate_curriculum():

    topics = []

    # LEVEL 1 BASIC (1-60)
    basic = [
        "ไฟฟ้าคืออะไร","โวลต์คืออะไร","แอมป์คืออะไร","วัตต์คืออะไร","โอห์มคืออะไร",
        "กฎของโอห์ม","ไฟ AC คืออะไร","ไฟ DC คืออะไร","อิเล็กตรอนคืออะไร",
        "แรงดันไฟฟ้า","กระแสไฟฟ้า","กำลังไฟฟ้า",
        "วงจรไฟฟ้าคืออะไร","วงจรอนุกรม","วงจรขนาน",
        "การไหลของกระแสไฟ","ทิศทางกระแสไฟ","แหล่งกำเนิดไฟฟ้า",
        "แบตเตอรี่ทำงานยังไง","สายไฟคืออะไร",
        "ตัวต้านทาน","ตัวเก็บประจุ","ตัวเหนี่ยวนำ"
    ]

    for i in range(60):
        topics.append({
            "title": basic[i % len(basic)],
            "type": "basic"
        })

    # LEVEL 2 HOME ELECTRIC (61-140)
    home = [
        "ระบบไฟฟ้าในบ้าน","ไฟฟ้า 1 เฟส","เบรกเกอร์คืออะไร",
        "ฟิวส์คืออะไร","สายดินคืออะไร","ไฟดูดเกิดจากอะไร",
        "ปลั๊กไฟทำงานยังไง","โหลดไฟฟ้า","ตู้ไฟบ้าน",
        "RCD คืออะไร","RCBO คืออะไร","MCB คืออะไร"
    ]

    for i in range(80):
        topics.append({
            "title": home[i % len(home)],
            "type": "home"
        })

    # LEVEL 3 TECHNICIAN (141-240)
    tech = [
        "มัลติมิเตอร์คืออะไร",
        "การวัดแรงดัน",
        "การวัดกระแส",
        "การวัดความต้านทาน",
        "แคลมป์มิเตอร์",
        "เครื่องทดสอบไฟ",
        "การเช็คไฟรั่ว"
    ]

    for i in range(100):
        topics.append({
            "title": tech[i % len(tech)],
            "type": "tool"
        })

    # LEVEL 4 ENGINEER (241-365)
    engineer = [
        "Power Factor",
        "Transformer",
        "ระบบไฟฟ้าโรงงาน",
        "มอเตอร์ 3 เฟส",
        "อินเวอร์เตอร์",
        "PLC คืออะไร",
        "SCADA คืออะไร"
    ]

    for i in range(125):
        topics.append({
            "title": engineer[i % len(engineer)],
            "type": "engineer"
        })

    return topics


CURRICULUM = generate_curriculum()
