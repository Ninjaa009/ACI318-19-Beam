"""เคสทดสอบ rc-column-aci318m19

- C1–C4: ตัวเลขจากรายงาน RCDC (ACI 318M-19) เสา 300×300 4-DB19.1 f′c 25 fy 420
- C5–C7: เสาชะลูด / แรงดัดสองแกนสูง ตรวจกับสูตรปิดที่เขียนแยกในไฟล์นี้ (ไม่เรียก solver ซ้ำ)
รัน: python3 test_column.py  → พิมพ์ผลและเขียน ../references/test-cases.md
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import column as C  # noqa: E402

ROWS = []


def check(case, item, got, exp, tol, unit=""):
    ok = abs(got - exp) <= tol
    ROWS.append((case, item, f"{got:,.4g} {unit}".strip(), f"{exp:,.4g} {unit}".strip(),
                 "ผ่าน" if ok else "ไม่ผ่าน"))
    return ok


def check_true(case, item, cond, note=""):
    ROWS.append((case, item, note, "True", "ผ่าน" if cond else "ไม่ผ่าน"))
    return cond


def rcdc_section():
    bars, tc = C.rect_bars(300, 300, 50, 9.5, 19.1, 2, 2, cover_to="long")
    return C.Section(300, 300, 25, 420, 420, bars, tc, 9.5)


# ---------- สูตรปิดอิสระ (หน้าตัดสมมาตร ดัดแกนเดียว เหล็ก 2 แถว) ----------
def uniaxial_closed(fc, fy, b, h, As_face, dp, Pu):
    """φMn ที่ φPn = Pu สำหรับเหล็ก 2 แถว (As_face ที่ระยะ dp จากแต่ละผิว)"""
    b1 = 0.85 if fc <= 28 else max(0.65, 0.85 - 0.05 * (fc - 28) / 7)
    ety = fy / 200000.0

    def at(c):
        a = b1 * c
        Cc = 0.85 * fc * b * a
        P, M = Cc, Cc * (h / 2 - a / 2)
        for y in (dp, h - dp):
            e = 0.003 * (c - y) / c
            fs = max(-fy, min(fy, 200000.0 * e))
            F = As_face * (fs - 0.85 * fc) if (fs > 0 and y <= a) else As_face * fs
            P += F
            M += F * (h / 2 - y)
        et = 0.003 * (h - dp - c) / c
        phi = 0.9 if et >= ety + 0.003 else (0.65 if et <= ety else 0.65 + 0.25 * (et - ety) / 0.003)
        return P, M, phi

    lo, hi = 1.0, 10 * h
    for _ in range(200):
        c = (lo + hi) / 2
        P, M, phi = at(c)
        if phi * P > Pu:
            hi = c
        else:
            lo = c
    P, M, phi = at(c)
    return phi * M, M, phi


def magnifier_closed(fc, b, h, lu, k, Pu, M1, M2, beta_dns, single):
    """δ ตาม §6.6.4: EIeff = 0.4EcIg/(1+βdns)"""
    Ig = b * h ** 3 / 12
    EI = 0.4 * 4700 * math.sqrt(fc) * Ig / (1 + beta_dns)
    Pc = math.pi ** 2 * EI / (k * lu) ** 2
    r = (-1 if single else 1) * abs(M1) / abs(M2)
    M2min = Pu * (15 + 0.03 * h)
    Cm = 0.6 - 0.4 * r
    M2d = abs(M2)
    if M2d < M2min:
        M2d, Cm = M2min, 1.0
    delta = max(1.0, Cm / (1 - Pu / (0.75 * Pc)))
    return delta, delta * M2d, Pc, Cm


def run():
    S = rcdc_section()
    Ab = C.bar_area(19.1)
    # ---------------- C1 แรงอัดสูงสุด + ดัดแกนเดียว ----------------
    Po = 0.85 * 25 * (90000 - 4 * Ab) + 420 * 4 * Ab
    check("C1", "Ast (mm²)", S.Ast, 1146.08, 0.01)
    check("C1", "φPn,max = 0.65·0.80·Po (kN)", S.phiPn_max / 1e3, 0.52 * Po / 1e3, 1e-6)
    check("C1", "φPn,max เทียบ RCDC (kN)", S.phiPn_max / 1e3, 1232.14, 0.01)
    cap = C.capacity_at(S, C.kn(57.08), C.knm(-11.9), 0)
    phiM, _, _ = uniaxial_closed(25, 420, 300, 300, 2 * Ab, 50 + 9.55, 57.08e3)
    check("C1", "φMcap (Pu = 57.08) เทียบสูตรปิด (kN·m)", cap.phiMcap / 1e6, phiM / 1e6, 0.01)
    check("C1", "φMcap เทียบ RCDC 54.16 (kN·m, ±0.5%)", cap.phiMcap / 1e6, 54.16, 0.27)
    check("C1", "capacity ratio เทียบ RCDC 0.22", cap.ratio, 0.22, 0.005)
    c3 = C.capacity_at(S, C.kn(27.9), 0, C.knm(-7.6))
    check("C1", "φMcap ระดับ 3–6 m เทียบ RCDC 51.35 (±0.5%)", c3.phiMcap / 1e6, 51.35, 0.26)

    # ---------------- C2 แรงเฉือนที่มีแรงอัด ----------------
    for dirn, Nu, exp in (("y", 47.96, 50.79), ("x", 62.83, 52.28)):
        r = C.shear_check(S, dirn, C.kn(3.34), C.kn(Nu), 100, 2)
        vc = 0.75 * (0.17 * 5 + min(Nu * 1e3 / (6 * 90000), 1.25)) * 300 * 240.45
        check("C2", f"φVc ทิศ {dirn} สูตรปิด (kN)", 0.75 * r.Vc / 1e3, vc / 1e3, 1e-6)
        check("C2", f"φVc ทิศ {dirn} เทียบ RCDC (kN)", 0.75 * r.Vc / 1e3, exp, 0.01)
    check("C2", "d (mm)", r.d, 240.45, 1e-6)
    check("C2", "Vc,max = 0.42√f′c·bw·d (kN) [RCDC ติดป้าย φ ผิด]", r.Vc_max / 1e3, 151.48, 0.01)
    check("C2", "Av,min/s (mm²/m)", r.Av_min_s * 1000, 250.0, 1e-6)
    check("C2", "φVs (kN)", 0.75 * r.Vs / 1e3, 107.37, 0.01)
    check_true("C2", "ใช้สมการ (a) เพราะ Av ≥ Av,min", r.vc_eq == "a")

    # ---------------- C3 ความชะลูด เครื่องหมายจากแรงเฉือน ----------------
    Q, nonsway = C.stability_index(C.kn(1083.58), 0.75, C.kn(49.11), 1500)
    check("C3", "Q ชั้นใต้ดิน ทิศ X", Q, 0.01103, 1e-5)
    s = C.slenderness(S, "x", 2600, C.kn(59.37), C.knm(-8.13), C.knm(7.08), V=C.kn(5.07), L=3000)
    check("C3", "M1/M2 (โค้งสองทาง ตรวจจาก V·L)", s.ratio_M1M2, 7.08 / 8.13, 1e-9)
    check("C3", "เกณฑ์ min(34 + 12M1/M2, 40)", s.limit, 40.0, 1e-9)
    check("C3", "klu/r", s.klu_r, 30.02, 0.01)
    check_true("C3", "ไม่ชะลูด", not s.slender)
    s0 = C.slenderness(S, "y", 1100, C.kn(57.08), 0, 0)
    check("C3", "M1 = M2 = 0 → เกณฑ์ 22 (กติกาสกิล)", s0.limit, 22.0, 1e-9)
    check("C3", "§18.3.3 Mn ที่ Pn = Pu = 195.47 (kN·m, RCDC ใช้ φMn = 66.98)",
          C.capacity_at(S, C.kn(195.47), 1, 0, factored=False).phiMcap / 1e6, 72.51, 0.01)
    check("C3", "φMn ที่ Pu = 195.47 ตรงค่า Mnt ของ RCDC (kN·m)",
          C.capacity_at(S, C.kn(195.47), 1, 0).phiMcap / 1e6, 66.98, 0.05)

    # ---------------- C4 แรงดัดสองแกน (ระดับ 0–3 m) ----------------
    c4 = C.capacity_at(S, C.kn(59.37), C.knm(-8.13), C.knm(-5.3))
    check("C4", "MRes (kN·m)", c4.Mres / 1e6, 9.705, 0.001)
    check("C4", "φMcap เทียบ RCDC 53.66 (±1.5% — ยังไม่ทราบสาเหตุส่วนต่าง)",
          c4.phiMcap / 1e6, 53.66, 0.81)
    pt = c4.pt
    check("C4", "จุดที่ได้อยู่บน surface: φPn = Pu (kN)", pt.phiPn / 1e3, 59.37, 0.01)
    check("C4", "ทิศโมเมนต์ความจุ = ทิศโหลด (องศา)",
          math.degrees(math.atan2(abs(pt.Mnx), abs(pt.Mny))), math.degrees(math.atan2(8.13, 5.3)),
          0.05)
    sym = C.capacity_at(S, C.kn(59.37), C.knm(-5.3), C.knm(-8.13))
    check("C4", "สมมาตร: φMcap(α) = φMcap(90°−α)", sym.phiMcap / 1e6, c4.phiMcap / 1e6, 0.01)

    # ---------------- C5 เสาชะลูด (non-sway) ----------------
    bars, tc = C.rect_bars(300, 300, 40, 10, 20, 2, 2)
    S5 = C.Section(300, 300, 28, 420, 420, bars, tc, 10)
    Pu, M1, M2 = 400e3, 20e6, 30e6
    s5 = C.slenderness(S5, "x", 4500, Pu, M2, M1, curvature="single", beta_dns=0.6)
    d_exp, Mc_exp, Pc_exp, Cm_exp = magnifier_closed(28, 300, 300, 4500, 1.0, Pu, M1, M2, 0.6, True)
    check("C5", "klu/r", s5.klu_r, 4500 / (300 / math.sqrt(12)), 1e-9)
    check("C5", "เกณฑ์ 34 + 12(−2/3)", s5.limit, 26.0, 1e-9)
    check_true("C5", "ชะลูด", s5.slender)
    check("C5", "Pc (kN)", s5.Pc / 1e3, Pc_exp / 1e3, 1e-6)
    check("C5", "Cm = 0.6 − 0.4(−2/3)", s5.Cm, Cm_exp, 1e-9)
    check("C5", "δ", s5.delta, d_exp, 1e-9)
    check("C5", "Mc (kN·m)", s5.Mc / 1e6, Mc_exp / 1e6, 1e-9)
    check_true("C5", "δ ≤ 1.4 (§6.2.6)", s5.ok_14 == (s5.delta <= 1.4), f"δ = {s5.delta:.3f}")

    # ---------------- C6 M2 < M2,min และ ไม่เสถียร ----------------
    s6 = C.slenderness(S5, "x", 4500, Pu, 2e6, 1e6, curvature="double")
    check("C6", "M2,min = Pu(15 + 0.03h) (kN·m)", s6.M2min / 1e6, 400 * (15 + 9) / 1e3, 1e-9)
    check("C6", "Cm = 1.0 เมื่อใช้ M2,min", s6.Cm, 1.0, 1e-12)
    s7 = C.slenderness(S5, "x", 9000, 1500e3, 30e6, 20e6, curvature="single")
    check_true("C6", "Pu ≥ 0.75Pc → ไม่เสถียร", not s7.stable)

    # ---------------- C7 แรงดัดสองแกนสูง (ratio ≈ 1) ----------------
    bars, tc = C.rect_bars(400, 600, 40, 10, 25, 3, 2)        # เหล็ก 2 แถว แถวละ 3 เส้น
    S7 = C.Section(400, 600, 32, 420, 420, bars, tc, 10)
    Pu7 = 1500e3
    full = C.capacity_at(S7, Pu7, 1.0, 1.0)              # หา φMcap ที่ 45° ใน (Mx, My)
    m = full.phiMcap / math.sqrt(2)
    on = C.capacity_at(S7, Pu7, m, m)
    check("C7", "จุดบน surface ให้ ratio = 1.000", on.ratio, 1.0, 1e-6)
    check("C7", "φPn ของจุดความจุ = Pu (kN)", on.pt.phiPn / 1e3, 1500.0, 0.01)
    ux = C.capacity_at(S7, Pu7, 1.0, 0.0).phiMcap
    uy = C.capacity_at(S7, Pu7, 0.0, 1.0).phiMcap
    phx, _, _ = uniaxial_closed(32, 420, 400, 600, 3 * C.bar_area(25), 40 + 10 + 12.5, Pu7)
    check("C7", "φMnx แกนเดียว เทียบสูตรปิด (kN·m)", ux / 1e6, phx / 1e6, 0.01)
    # load contour ที่ 45° ต้องอยู่ระหว่างเส้นตรง Mx/φMnx + My/φMny = 1 กับมุมสี่เหลี่ยม (φMnx, φMny)
    m45 = full.phiMcap / math.sqrt(2)
    lin = 1.0 / (1.0 / ux + 1.0 / uy)
    check_true("C7", "contour อยู่ระหว่างเส้นตรงกับมุมสี่เหลี่ยม (ไม่ใช่การเทียบแกนเดียว)",
               lin <= m45 <= min(ux, uy),
               f"{lin / 1e6:.1f} ≤ {m45 / 1e6:.1f} ≤ {min(ux, uy) / 1e6:.1f} kN·m ต่อแกน")
    # ---------------- C8 ตัวอย่างเสาชะลูด S1 (รายการคำนวณมือ example_slender.py) ----------------
    import example_slender as E
    R = E.hand_calc()
    sol = E.solver_compare(R)
    S8 = sol["S"]
    sx = C.slenderness(S8, "x", E.lu, E.Pu, E.Mx_t, E.Mx_b, V=E.Vx, L=E.Lmem, beta_dns=E.beta_dns)
    sy = C.slenderness(S8, "y", E.lu, E.Pu, E.My_t, E.My_b, V=E.Vy, L=E.Lmem, beta_dns=E.beta_dns)
    check("C8", "Q", C.stability_index(E.sumPu, E.delta_o, E.Vus, E.lc)[0], R["Q"], 1e-12)
    check("C8", "M1/M2 แกน x (โค้งทางเดียวจาก V·L)", sx.ratio_M1M2, R["rx"], 1e-12)
    check("C8", "M1/M2 แกน y (โค้งสองทางจาก V·L)", sy.ratio_M1M2, R["ry"], 1e-12)
    check_true("C8", "แกน x ชะลูด / แกน y ไม่ชะลูด", sx.slender and not sy.slender,
               f"{sx.klu_r:.2f} > {sx.limit:.0f}, {sy.klu_r:.2f} < {sy.limit:.0f}")
    check("C8", "Pc (kN)", sx.Pc / 1e3, R["Pc"] / 1e3, 1e-6)
    check("C8", "δ", sx.delta, R["delta"], 1e-12)
    check("C8", "Mcx (kN·m)", sx.Mc / 1e6, R["Mcx"] / 1e6, 1e-9)
    check("C8", "φPn,max (kN)", S8.phiPn_max / 1e3, R["phiPnmax"] / 1e3, 1e-6)
    check("C8", "φMnx แกนเดียวที่ Pu เทียบมือ 3 แถว (kN·m)", sol["caps"][2].phiMcap / 1e6,
          R["phiMn_u"] / 1e6, 0.01)
    check("C8", "จุดความจุกลางเสา: fiber อิสระต่างจาก solver (%)", sol["fiber_dM"], 0.0, 0.05)
    check("C8", "ratio กลางเสา (Mcx + Muy)", sol["caps"][1].ratio, 0.750, 0.002)
    check_true("C8", "Bresler สรุปผ่านตรงกับ 3D (ทั้งคู่ < 1)",
               (R["ratio_bresler"] < 1) == (sol["caps"][1].ratio < 1),
               f"Bresler {R['ratio_bresler']:.3f}, 3D {sol['caps'][1].ratio:.3f}")
    for dirn, V in (("y", E.Vx), ("x", E.Vy)):
        r = C.shear_check(S8, dirn, V, E.Pu, E.s_tie, E.legs)
        check("C8", f"Vc ทิศ {dirn} ถูกจำกัดที่ Vc,max (kN)", r.Vc / 1e3, R["Vc"] / 1e3, 1e-6)
        check("C8", f"φVn ทิศ {dirn} (kN)", r.phiVn / 1e3, R["phiVn"] / 1e3, 1e-6)
        check_true("C8", f"ทิศ {dirn}: Vu ≤ 0.5φVc → ไม่คุมระยะ d/2 (§10.7.6.5.2) ผ่านทั้งหมด",
                   (not r.min_required) and r.ok, f"s = 250 > d/2 = {r.d / 2:.0f} mm แต่ไม่บังคับ")
    tie = {x[0]: x[1] for x in C.tie_checks(S8, E.s_tie, 2, 2)}
    check_true("C8", "รายละเอียดปลอกผ่านทุกข้อ", all(v for v in tie.values()))

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
    return ROWS


def main():
    rows = run()
    n_fail = sum(r[4] != "ผ่าน" for r in rows)
    lines = ["# เคสทดสอบ rc-column-aci318m19 (สร้างโดย scripts/test_column.py)", "",
             "| เคส | รายการ | ได้ | คาดหมาย | ผล |", "|---|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows]
    lines += ["", f"**สรุป:** ผ่าน {len(rows) - n_fail}/{len(rows)}"]
    out = Path(__file__).parent.parent / "references" / "test-cases.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for r in rows:
        print(" | ".join(r))
    print(f"\nผ่าน {len(rows) - n_fail}/{len(rows)}")
    return n_fail


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
