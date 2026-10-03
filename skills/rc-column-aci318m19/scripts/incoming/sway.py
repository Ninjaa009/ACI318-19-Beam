"""🚧 INCOMING — ระบบตรวจ sway / non-sway (ACI 318M-19 §6.6.4.3) ยังไม่เปิดใช้ในแอปและ workflow

เก็บไว้เพื่อพัฒนาต่อ: Stability index Q, จำแนกชั้นทุกชั้นทุกทิศ, ด่านบังคับ non-sway (+ bypass),
การจับคู่ทิศการเซแกนโลก STAAD (X/Z) กับ Mz/My ตาม beta angle
ปัจจุบันสกิลและแอปถือว่าเสาอยู่ในโครง non-sway — ผู้ออกแบบยืนยันเอง

ทดสอบ: python3 incoming/test_sway.py
"""
from dataclasses import dataclass, field
import math


def stability_index(sum_Pu, delta_o, Vus, lc):
    """§6.6.4.3(b): Q = ΣPuΔo/(Vus·lc) — Q ≤ 0.05 ถือเป็น non-sway (หน่วย N, mm)"""
    Q = sum_Pu * delta_o / (Vus * lc)
    return Q, Q <= 0.05


@dataclass
class StoryClass:
    story: str
    direction: str             # ทิศการเซ "x" | "y"
    Q_max: float
    combo: str                 # combo ที่ให้ Q สูงสุด
    nonsway: bool              # ผลจำแนก (ใช้ Q ที่ป้อน)
    Q_upper: float = None      # Q/0.35 เมื่อโมเดลยังไม่ลด stiffness (ประมาณขอบบน)
    status: str = ""           # "non-sway" | "sway" | "ต้องยืนยัน" | "ไม่มีข้อมูล"
    notes: list = field(default_factory=list)
    rows: list = field(default_factory=list)   # (combo, ΣPu, Vus, Δo, lc, Q)


def classify_stories(rows):
    """จำแนก sway / non-sway ทุกชั้นทุกทิศ (§6.6.4.3(b), Q ตาม §6.6.4.4.1)

    rows: list ของ dict {story, direction ("x"|"y"), combo, sumPu (N), Vus (N), delta_o (mm),
                         lc (mm), reduced (bool: Δo จากโมเดลที่ลด stiffness ตาม §6.6.3.1.1 แล้ว)}
    กติกาของสกิล:
    - ใช้ Q สูงสุดของ (ชั้น, ทิศ) จากทุก combo ที่มีแรงด้านข้าง (Vus > 0)
    - combo ที่มีแต่แรงแนวดิ่งใช้ผลจำแนกของชั้น/ทิศนั้น (เป็นคุณสมบัติของโครง)
    - ถ้าโมเดลยังไม่ลด stiffness: Δo จริงอาจมากขึ้นถึง 1/0.35 เท่า → ถ้า Q/0.35 ≤ 0.05 ยืนยัน
      non-sway ได้, ถ้า Q ≤ 0.05 < Q/0.35 → "ต้องยืนยัน" (รันโมเดลลด stiffness)
    - Q อยู่ระหว่าง 0.04–0.05 → เตือนว่าใกล้เกณฑ์
    """
    groups = {}
    for r in rows:
        groups.setdefault((str(r["story"]), r["direction"]), []).append(r)
    out = []
    for (story, d), rs in groups.items():
        data = []
        for r in rs:
            if not r.get("Vus") or not r.get("lc"):
                continue
            Q = r["sumPu"] * r["delta_o"] / (r["Vus"] * r["lc"])
            data.append((str(r.get("combo", "")), r["sumPu"], r["Vus"], r["delta_o"], r["lc"], Q,
                         bool(r.get("reduced", False))))
        if not data:
            out.append(StoryClass(story, d, math.nan, "", False, status="ไม่มีข้อมูล",
                                  notes=["ไม่มี combo ที่มีแรงด้านข้าง (Vus > 0)"]))
            continue
        g = max(data, key=lambda t: t[5])
        Q = g[5]
        S = StoryClass(story, d, Q, g[0], Q <= 0.05, rows=[t[:6] for t in data])
        all_reduced = all(t[6] for t in data)
        if Q > 0.05:
            S.status = "sway"
        elif all_reduced:
            S.status = "non-sway"
        else:
            S.Q_upper = Q / 0.35
            if S.Q_upper <= 0.05:
                S.status = "non-sway"
                S.notes.append(f"โมเดลยังไม่ลด stiffness แต่ Q/0.35 = {S.Q_upper:.4f} ≤ 0.05 "
                               "จึงยังเป็น non-sway")
            else:
                S.status = "ต้องยืนยัน"
                S.notes.append(f"โมเดลยังไม่ลด stiffness: Q/0.35 = {S.Q_upper:.4f} > 0.05 → "
                               "รันโมเดลที่ลด stiffness (คาน 0.35Ig, เสา 0.70Ig) เพื่อยืนยัน")
        if 0.04 <= Q <= 0.05:
            S.notes.append("Q ใกล้เกณฑ์ 0.05")
        out.append(S)
    return out


SWAY_CLOSED = "การออกแบบเสาในโครง sway ปิดปรับปรุง (ยังไม่รองรับ δs)"


BYPASS_LABEL = "ผู้ใช้ยืนยัน"


def nonsway_gate(classes, story, bypass_reason="", labels=None):
    """ด่านบังคับก่อนออกแบบ: ชั้นของเสาต้องมีผลจำแนกครบทั้งทิศ x และ y และเป็น non-sway ทั้งคู่

    คืน (ผ่านหรือไม่, รายการข้อความ) — ไม่ผ่านเมื่อ: ไม่มีข้อมูลชั้น/ทิศ, ไม่มี combo ที่มีแรงด้านข้าง,
    "ต้องยืนยัน" (โมเดลยังไม่ลด stiffness และ Q/0.35 > 0.05) หรือ sway (ปิดปรับปรุง)

    bypass_reason: วิศวกรยืนยันเองว่าเป็น non-sway (เช่น มีผนังรับแรงเฉือน/โครงค้ำยัน) ต้องมีเหตุผล
    — ข้ามได้เฉพาะกรณีไม่มีข้อมูลหรือ "ต้องยืนยัน" **ข้ามไม่ได้เมื่อข้อมูลที่ป้อนแสดงว่า sway**
    (ออกแบบแบบ non-sway จะได้โมเมนต์ต่ำกว่าจริง) ข้อความแรกขึ้นต้นด้วย BYPASS_LABEL เมื่อข้าม
    """
    mine = {c.direction: c for c in classes if c.story == str(story)}
    lab = labels or {"x": "x", "y": "y"}          # ชื่อทิศที่ใช้ในข้อความ
    reason = (bypass_reason or "").strip()
    if reason:
        sway = [d for d, c in mine.items() if c.status == "sway"]
        if sway:
            return False, [f"ข้ามการตรวจ sway ไม่ได้: ข้อมูลชั้น {story} ทิศ "
                           f"{', '.join(lab.get(d, d) for d in sway)} "
                           f"แสดงว่าเป็น sway (Q > 0.05) — {SWAY_CLOSED}"]
        return True, [f"{BYPASS_LABEL}: ข้ามการตรวจ sway ชั้น {story} โดยวิศวกรยืนยันว่าเป็น "
                      f"non-sway — เหตุผล: {reason}"]
    msgs = []
    for d in ("x", "y"):
        c = mine.get(d)
        n = lab.get(d, d)
        if c is None:
            msgs.append(f"ชั้น {story} ไม่มีข้อมูลทิศ {n} — ต้องตรวจ sway ทั้งสองทิศก่อนออกแบบ")
        elif c.status == "sway":
            msgs.append(f"ชั้น {story} ทิศ {n}: Q = {c.Q_max:.4f} > 0.05 → sway — {SWAY_CLOSED}")
        elif c.status == "ต้องยืนยัน":
            msgs.append(f"ชั้น {story} ทิศ {n}: ต้องยืนยัน — Q/0.35 = {c.Q_upper:.4f} > 0.05 "
                        "รันโมเดลที่ลด stiffness แล้วป้อน Δo ใหม่")
        elif c.status != "non-sway":
            msgs.append(f"ชั้น {story} ทิศ {n}: {c.status} — {'; '.join(c.notes)}")
    return not msgs, msgs


def sway_dir_for_axis(axis):
    """เสาดัดรอบแกน x (Mx) เกิดจากการเซในทิศ y และกลับกัน"""
    return "y" if axis == "x" else "x"



def staad_sway_dir(global_dir, beta90=False):
    """ทิศการเซของชั้นในแกนโลก STAAD (X หรือ Z; Y คือแนวดิ่ง) → ทิศภายในที่ใช้ใน classify/gate

    เสาตั้ง beta = 0: local z ขนานโลก Z → การเซทิศ X ทำให้เกิด Mz (Mx ภายใน → ทิศภายใน "y"),
    การเซทิศ Z ทำให้เกิด My (ทิศภายใน "x"); beta = 90° สลับกัน  ⚠️ ยืนยันกับโมเดลจริง
    """
    g = str(global_dir).strip().upper()
    if g not in ("X", "Z"):
        raise ValueError("ทิศการเซของชั้นต้องเป็น X หรือ Z (แกนโลก STAAD)")
    if beta90:
        g = "Z" if g == "X" else "X"
    return "y" if g == "X" else "x"
