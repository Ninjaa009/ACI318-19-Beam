"""🚧 INCOMING — ทดสอบระบบตรวจ sway / non-sway (incoming/sway.py) ยังไม่เปิดใช้"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sway as C  # noqa: E402

ROWS = []


def check(case, item, got, exp, tol, unit=""):
    ok = abs(got - exp) <= tol
    ROWS.append((case, item, f"{got:,.4g}", f"{exp:,.4g}", "ผ่าน" if ok else "ไม่ผ่าน"))


def check_true(case, item, cond, note=""):
    ROWS.append((case, item, note, "True", "ผ่าน" if cond else "ไม่ผ่าน"))


def run():
    Q, _ = C.stability_index(1083.58e3, 0.75, 49.11e3, 1500)
    check("C3", "Q ชั้นใต้ดิน ทิศ X (RCDC)", Q, 0.01103, 1e-5)
    Q, _ = C.stability_index(24000e3, 3.2, 900e3, 5000)
    check("C8", "Q ตัวอย่าง S1", Q, 24000 * 3.2 / (900 * 5000), 1e-12)
    # ---------------- C9 จำแนก sway / non-sway (ตาราง Q ของรายงาน RCDC) ----------------
    rcdc = [("-1.5–0", "x", "13", 1083.58, 0.75, 49.11, 1.5), ("0–3", "x", "13", 630.46, 1.16, 36.92, 3),
            ("3–6", "x", "13", 177.34, 0.52, 12.52, 3), ("-1.5–0", "y", "15", 1083.58, 0.63, 36.84, 1.5),
            ("0–3", "y", "15", 630.46, 0.97, 27.69, 3), ("3–6", "y", "15", 177.34, 0.45, 9.39, 3)]
    rows = [dict(story=st, direction=d, combo=cb, sumPu=P * 1e3, delta_o=do, Vus=V * 1e3,
                 lc=lc * 1e3, reduced=True) for st, d, cb, P, do, V, lc in rcdc]
    cls = {(c.story, c.direction): c for c in C.classify_stories(rows)}
    for (st, d), exp in ((("-1.5–0", "x"), 0.011), (("0–3", "x"), 0.007), (("3–6", "x"), 0.002),
                         (("-1.5–0", "y"), 0.012), (("0–3", "y"), 0.007), (("3–6", "y"), 0.003)):
        check("C9", f"Q ชั้น {st} ทิศ {d} เทียบ RCDC", cls[(st, d)].Q_max, exp, 0.0006)
    check_true("C9", "ทุกชั้นเป็น non-sway", all(c.status == "non-sway" for c in cls.values()))
    # ใช้ Q สูงสุดจากหลาย combo
    multi = rows[:1] + [dict(rows[0], combo="W2", delta_o=1.6)] + [dict(rows[0], combo="G", Vus=0)]
    c2 = C.classify_stories(multi)[0]
    check("C9", "Q สูงสุดจากหลาย combo (ข้าม combo ที่ Vus = 0)", c2.Q_max,
          1083.58 * 1.6 / (49.11 * 1500), 1e-12)
    check_true("C9", "combo วิกฤตคือ W2", c2.combo == "W2")
    # ยังไม่ลด stiffness
    nr = [dict(rows[0], reduced=False)]
    check_true("C9", "ไม่ลด stiffness แต่ Q/0.35 ≤ 0.05 → non-sway",
               C.classify_stories(nr)[0].status == "non-sway")
    nr2 = [dict(rows[0], reduced=False, delta_o=2.5)]
    c3 = C.classify_stories(nr2)[0]
    check_true("C9", "ไม่ลด stiffness และ Q ≤ 0.05 < Q/0.35 → ต้องยืนยัน", c3.status == "ต้องยืนยัน",
               f"Q = {c3.Q_max:.4f}, Q/0.35 = {c3.Q_upper:.4f}")
    sw = C.classify_stories([dict(rows[0], delta_o=4.0)])[0]
    check_true("C9", "Q > 0.05 → sway", sw.status == "sway", f"Q = {sw.Q_max:.4f}")
    check_true("C9", "Mx ใช้ผลการเซทิศ y", C.sway_dir_for_axis("x") == "y")

    # ---------------- C10 ด่านบังคับ non-sway ก่อนออกแบบ ----------------
    allc = C.classify_stories(rows)
    ok, _ = C.nonsway_gate(allc, "0–3")
    check_true("C10", "ชั้นที่ non-sway ทั้งสองทิศ → ผ่านด่าน", ok)
    ok, msg = C.nonsway_gate(C.classify_stories([r for r in rows if r["direction"] == "x"]), "0–3")
    check_true("C10", "ขาดข้อมูลทิศ y → ไม่ผ่านด่าน", (not ok) and "ทิศ y" in msg[0], msg[0][:40])
    ok, msg = C.nonsway_gate(C.classify_stories(rows), "ไม่มีชั้นนี้")
    check_true("C10", "ไม่มีข้อมูลชั้น → ไม่ผ่านด่าน", (not ok) and len(msg) == 2)
    sw_rows = [dict(r, delta_o=4.0) if (r["story"], r["direction"]) == ("-1.5–0", "x") else r
               for r in rows]
    ok, msg = C.nonsway_gate(C.classify_stories(sw_rows), "-1.5–0")
    check_true("C10", "sway → ไม่ผ่านด่าน (ปิดปรับปรุง)", (not ok) and "ปิดปรับปรุง" in msg[0])
    cf_rows = [dict(r, delta_o=2.5, reduced=False) if (r["story"], r["direction"]) == ("-1.5–0", "y")
               else r for r in rows]
    ok, msg = C.nonsway_gate(C.classify_stories(cf_rows), "-1.5–0")
    check_true("C10", "ต้องยืนยัน → ไม่ผ่านด่าน", (not ok) and "ต้องยืนยัน" in msg[0])
    ok, msg = C.nonsway_gate(C.classify_stories(cf_rows), "-1.5–0", "มีผนังรับแรงเฉือนสองทิศ")
    check_true("C10", "bypass + เหตุผล (กรณีต้องยืนยัน) → ผ่าน และบันทึกเหตุผล",
               ok and msg[0].startswith(C.BYPASS_LABEL) and "ผนัง" in msg[0])
    ok, msg = C.nonsway_gate([], "1", "โครงค้ำยัน")
    check_true("C10", "bypass เมื่อไม่มีข้อมูลชั้น → ผ่าน", ok)
    ok, msg = C.nonsway_gate(C.classify_stories(sw_rows), "-1.5–0", "ผู้ใช้ยืนยัน")
    check_true("C10", "bypass เมื่อข้อมูลแสดง sway → ไม่ยอม", (not ok) and "ไม่ได้" in msg[0])
    ok, _ = C.nonsway_gate([], "1", "   ")
    check_true("C10", "เหตุผลว่าง → ไม่ถือว่า bypass", not ok)

    check_true("C11", "ทิศการเซ (beta 0): X → Mz (ภายใน y), Z → My (ภายใน x)",
               (C.staad_sway_dir("X"), C.staad_sway_dir("z")) == ("y", "x"))
    check_true("C11", "beta 90°: สลับการจับคู่ทิศการเซ",
               (C.staad_sway_dir("X", True), C.staad_sway_dir("Z", True)) == ("x", "y"))
    return ROWS


if __name__ == "__main__":
    rows = run()
    bad = [r for r in rows if r[4] != "ผ่าน"]
    for r in rows:
        print(" | ".join(r))
    print(f"\nผ่าน {len(rows) - len(bad)}/{len(rows)}")
    sys.exit(1 if bad else 0)
