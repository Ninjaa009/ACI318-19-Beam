# ตัวอย่างโมเดล STAAD (โครง 1 ชั้น 3×2 ช่วง)

- `frame_3x2.std` — ไฟล์ input จริงจากผู้ใช้: เสา 1–12 PRIS YD 0.5 × ZD 0.4 m สูง 3.5 m, คาน YD 0.5 × ZD 0.3 m,
  LOAD 1–3 (DL, slab DL, LL), COMB 101 (1.4D), 102 (1.2D+1.6L), 103 (D+L service)
- `frame_3x2_cols11_12.anl` — **จำลอง**รูปแบบตาราง MEMBER END FORCES ของ STAAD (`ALL UNITS ARE -- KN METE`)
  จากตาราง Beam End Force ที่ผู้ใช้คัดลอกจาก STAAD สำหรับเสา 11 และ 12 (แรง kg × 0.00980665 → kN, โมเมนต์ kN·m)
  ⚠️ ยังไม่ใช่ไฟล์ .anl จริง — ต้องทดสอบ `parse_anl` กับไฟล์จริงของผู้ใช้
- `frame_3x2_real_noforces.anl` — ไฟล์ .anl **จริง** จาก STAAD.Pro 2025 ของโมเดลเดียวกัน (ตัดรายการ member load และ
  joint load ที่ซ้ำ ๆ ให้สั้นลง ส่วนอื่นคงเดิม) — ใช้ `PERFORM ANALYSIS PRINT ALL` อย่างเดียวจึง**ไม่มีตาราง MEMBER END FORCES**
  ต้องเพิ่ม `PRINT MEMBER FORCES` แล้วรันใหม่ · ใช้ทดสอบ `extract_input_echo` (สำเนา input ต้นไฟล์) และ `applied_totals`
  (ΣFy: LOAD 1 = −507.60, LOAD 2 = −432.00, LOAD 3 = −294.20 kN ตรงกับ `Model.vertical_total`)
- `frame_3x2_beam_end_force.txt` — ตาราง **Beam End Force จริง** ที่คัดลอกจากหน้าจอ STAAD (แรง kg, โมเมนต์ kN-m;
  Beam และ L/C พิมพ์เฉพาะแถวแรกของกลุ่ม) — เสา 1–12 ครบทุก load + คาน 13 (load 1 และ 102) เป็นตัวอย่าง
  (คาน 14–29 ตัดออก) · Σ แรงอัดฐานเสา = 507.60 / 432.00 / 294.20 kN ตรงกับ .anl
- `frame_3x2_cols11_12.anl` (ด้านบน) ใช้ทดสอบ `parse_anl` เท่านั้น — รูปแบบตาราง MEMBER END FORCES ใน .anl ยังไม่ได้ยืนยันกับไฟล์จริง
