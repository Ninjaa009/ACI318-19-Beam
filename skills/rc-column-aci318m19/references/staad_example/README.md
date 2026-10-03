# ตัวอย่างโมเดล STAAD (โครง 1 ชั้น 3×2 ช่วง)

- `frame_3x2.std` — ไฟล์ input จริงจากผู้ใช้: เสา 1–12 PRIS YD 0.5 × ZD 0.4 m สูง 3.5 m, คาน YD 0.5 × ZD 0.3 m,
  LOAD 1–3 (DL, slab DL, LL), COMB 101 (1.4D), 102 (1.2D+1.6L), 103 (D+L service)
- `frame_3x2_cols11_12.anl` — **จำลอง**รูปแบบตาราง MEMBER END FORCES ของ STAAD (`ALL UNITS ARE -- KN METE`)
  จากตาราง Beam End Force ที่ผู้ใช้คัดลอกจาก STAAD สำหรับเสา 11 และ 12 (แรง kg × 0.00980665 → kN, โมเมนต์ kN·m)
  ⚠️ ยังไม่ใช่ไฟล์ .anl จริง — ต้องทดสอบ `parse_anl` กับไฟล์จริงของผู้ใช้
