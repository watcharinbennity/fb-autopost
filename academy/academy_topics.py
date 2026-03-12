# academy/academy_topics.py

def build_curriculum():
    lessons = []

    def add(module, items):
        for item in items:
            lessons.append({
                "module": module,
                "title": item["title"],
                "type": item["type"],
            })

    add("พื้นฐานไฟฟ้า", [
        {"title": "ไฟฟ้าคืออะไร", "type": "concept"},
        {"title": "อิเล็กตรอนคืออะไร", "type": "concept"},
        {"title": "แรงดันไฟฟ้าคืออะไร", "type": "voltage"},
        {"title": "กระแสไฟฟ้าคืออะไร", "type": "current"},
        {"title": "กำลังไฟฟ้าคืออะไร", "type": "power"},
        {"title": "โวลต์ แอมป์ วัตต์ ต่างกันยังไง", "type": "vaw"},
        {"title": "ไฟ AC กับ DC ต่างกันยังไง", "type": "acdc"},
        {"title": "กฎของโอห์มคืออะไร", "type": "ohm"},
        {"title": "สูตร V = I × R ใช้ยังไง", "type": "ohm"},
        {"title": "สูตร P = V × I ใช้ยังไง", "type": "power"},
        {"title": "วงจรไฟฟ้าคืออะไร", "type": "circuit"},
        {"title": "วงจรเปิดกับวงจรปิด", "type": "circuit"},
        {"title": "วงจรอนุกรมคืออะไร", "type": "series"},
        {"title": "วงจรขนานคืออะไร", "type": "parallel"},
        {"title": "การไหลของกระแสไฟ", "type": "current_flow"},
        {"title": "แบตเตอรี่ทำงานยังไง", "type": "battery"},
        {"title": "ตัวต้านทานคืออะไร", "type": "resistor"},
        {"title": "ตัวเก็บประจุคืออะไร", "type": "capacitor"},
        {"title": "คอยล์หรืออินดักเตอร์คืออะไร", "type": "inductor"},
        {"title": "โหลดไฟฟ้าคืออะไร", "type": "load"},
    ])

    add("ไฟฟ้าในบ้าน", [
        {"title": "ระบบไฟฟ้าในบ้านคืออะไร", "type": "house"},
        {"title": "ไฟ 1 เฟสคืออะไร", "type": "house_phase"},
        {"title": "ไฟ 3 เฟสคืออะไร", "type": "three_phase"},
        {"title": "220V กับ 380V ต่างกันยังไง", "type": "three_phase"},
        {"title": "สายไฟแต่ละสีหมายถึงอะไร", "type": "wire_color"},
        {"title": "สายเฟส สายนิวทรัล สายดิน ต่างกันยังไง", "type": "wire_color"},
        {"title": "สายดินคืออะไร", "type": "ground"},
        {"title": "ปลั๊กไฟ 2 ขา กับ 3 ขา ต่างกันยังไง", "type": "plug"},
        {"title": "เต้ารับทำงานยังไง", "type": "plug"},
        {"title": "สวิตช์ไฟตัดอะไรในวงจร", "type": "switch"},
        {"title": "ปลั๊กพ่วงปลอดภัยไหม", "type": "plug"},
        {"title": "ฟิวส์คืออะไร", "type": "fuse"},
        {"title": "เบรกเกอร์คืออะไร", "type": "breaker"},
        {"title": "MCB คืออะไร", "type": "breaker"},
        {"title": "RCCB คืออะไร", "type": "breaker"},
        {"title": "RCBO คืออะไร", "type": "breaker"},
        {"title": "เบรกเกอร์ตัดเพราะอะไร", "type": "breaker"},
        {"title": "ไฟดูดเกิดจากอะไร", "type": "shock"},
        {"title": "ไฟรั่วคืออะไร", "type": "shock"},
        {"title": "เครื่องทำน้ำอุ่นต้องมีสายดินทำไม", "type": "ground"},
    ])

    add("เครื่องมือช่างไฟ", [
        {"title": "มัลติมิเตอร์คืออะไร", "type": "meter"},
        {"title": "วัดแรงดันด้วยมัลติมิเตอร์ยังไง", "type": "meter_voltage"},
        {"title": "วัดความต้านทานยังไง", "type": "meter_ohm"},
        {"title": "วัดกระแสยังไง", "type": "meter_current"},
        {"title": "แคลมป์มิเตอร์คืออะไร", "type": "meter_current"},
        {"title": "เช็กแบตเตอรี่ด้วยมิเตอร์ยังไง", "type": "battery"},
        {"title": "เช็กปลั๊กไฟด้วยมิเตอร์ยังไง", "type": "plug"},
        {"title": "ใช้มัลติมิเตอร์อย่างปลอดภัย", "type": "meter"},
        {"title": "ข้อผิดพลาดที่มือใหม่ชอบทำตอนวัดไฟ", "type": "meter"},
        {"title": "วิธีเลือกเครื่องมือช่างไฟพื้นฐาน", "type": "meter"},
    ])

    add("มอเตอร์และควบคุม", [
        {"title": "มอเตอร์ไฟฟ้าคืออะไร", "type": "motor"},
        {"title": "มอเตอร์ AC กับ DC ต่างกันยังไง", "type": "motor"},
        {"title": "มอเตอร์ 1 เฟสทำงานยังไง", "type": "motor"},
        {"title": "มอเตอร์ 3 เฟสทำงานยังไง", "type": "three_phase"},
        {"title": "คาปาซิเตอร์สตาร์ตคืออะไร", "type": "capacitor"},
        {"title": "ทำไมมอเตอร์กินกระแสสตาร์ตสูง", "type": "motor"},
        {"title": "มอเตอร์ร้อนเพราะอะไร", "type": "motor"},
        {"title": "รีเลย์คืออะไร", "type": "relay"},
        {"title": "คอนแทคเตอร์คืออะไร", "type": "relay"},
        {"title": "โอเวอร์โหลดคืออะไร", "type": "relay"},
        {"title": "ปุ่ม Start Stop ทำงานยังไง", "type": "relay"},
        {"title": "Timer Relay คืออะไร", "type": "relay"},
        {"title": "วงจรควบคุมกับวงจรกำลังต่างกันยังไง", "type": "relay"},
        {"title": "PLC คืออะไรแบบเข้าใจง่าย", "type": "plc"},
        {"title": "เซนเซอร์คืออะไร", "type": "plc"},
    ])

    add("โซลาร์และพลังงาน", [
        {"title": "โซลาร์เซลล์คืออะไร", "type": "solar"},
        {"title": "แผงโซลาร์ผลิตไฟได้ยังไง", "type": "solar"},
        {"title": "Solar Inverter คืออะไร", "type": "solar"},
        {"title": "On Grid คืออะไร", "type": "solar"},
        {"title": "Off Grid คืออะไร", "type": "solar"},
        {"title": "Hybrid Solar คืออะไร", "type": "solar"},
        {"title": "แบตเตอรี่โซลาร์ต่างจากแบตทั่วไปยังไง", "type": "solar"},
        {"title": "Solar คุ้มไหมสำหรับบ้าน", "type": "solar"},
        {"title": "คำนวณขนาดระบบโซลาร์เบื้องต้น", "type": "solar"},
        {"title": "ดูแลแผงโซลาร์ยังไง", "type": "solar"},
    ])

    add("ระดับวิศวกร", [
        {"title": "หม้อแปลงไฟฟ้าคืออะไร", "type": "transformer"},
        {"title": "Step Up กับ Step Down ต่างกันยังไง", "type": "transformer"},
        {"title": "ทำไมส่งไฟไกลต้องใช้แรงดันสูง", "type": "transformer"},
        {"title": "Power Factor คืออะไร", "type": "pf"},
        {"title": "ฮาร์มอนิกคืออะไร", "type": "pf"},
        {"title": "ระบบไฟฟ้าโรงงานคืออะไร", "type": "industrial"},
        {"title": "ระบบจำหน่ายไฟฟ้าคืออะไร", "type": "industrial"},
        {"title": "สถานีไฟฟ้าย่อยคืออะไร", "type": "industrial"},
        {"title": "Smart Grid คืออะไร", "type": "industrial"},
        {"title": "EV Charger ทำงานยังไง", "type": "industrial"},
    ])

    base = lessons[:]
    while len(lessons) < 365:
        for item in base:
            if len(lessons) >= 365:
                break
            lessons.append(item.copy())

    return lessons[:365]


CURRICULUM = build_curriculum()
