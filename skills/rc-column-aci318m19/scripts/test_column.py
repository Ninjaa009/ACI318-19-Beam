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

    # ---------------- C11 sign convention / นำเข้าจาก STAAD ----------------
    f = C.from_staad(fx_s=1600, fy_s=-6, fz_s=10, my_s=-20, mz_s=60, my_e=-30, mz_e=-90)
    check_true("C11", "STAAD: Mz→Mx, Fy→Vuy, My→My, Fz→Vux, P = Fx(start)",
               (f["Pu"], f["Mxt"], f["Mxb"], f["Vuy"], f["Myt"], f["Myb"], f["Vux"])
               == (1600, 90, 60, 6, 30, 20, 10))
    check_true("C11", "ชื่อแกน STAAD: x ภายใน = z, y = y", C.STAAD_AXIS == {"x": "z", "y": "y"})
    ok, m = C.check_axial_sign([("1.2D+1.6L", -1500e3, True), ("W", 300e3, False)])
    check_true("C11", "combo แนวดิ่งได้แรงดึง → หยุด (เครื่องหมาย P กลับด้าน)", (not ok) and "กลับด้าน" in m[0])
    ok, m = C.check_axial_sign([("1.2D+1.6L", 1500e3, True), ("0.9D+W", -50e3, False)])
    check_true("C11", "แรงดึงใน combo ลม (ไม่ใช่แนวดิ่ง) → ผ่าน", ok and not m)
    ok, m = C.check_axial_sign([("W", 1e3, False)])
    check_true("C11", "ไม่มี combo แนวดิ่ง → ผ่านแต่เตือน", ok and len(m) == 1)
    # แกนจับคู่ผิด: ใช้ V ของอีกแกน (10 kN) กับ Mx 90/60 (สมดุลต้อง 6 หรือ 30 kN)
    try:
        C.curvature_ratio(90e6, 60e6, V=10e3, L=5000)
        bad = False
    except ValueError as e:
        bad = "จับคู่แกน" in str(e)
    check_true("C11", "V ไม่สอดคล้องกับโมเมนต์ (จับคู่แกนผิด) → แจ้งให้ระบุเอง", bad)
    r, _ = C.curvature_ratio(90e6, 60e6, V=6.3e3, L=5000)
    check_true("C11", "คลาดเคลื่อน 5% ยังตัดสินได้ (โค้งทางเดียว)", r < 0)

    # ---------------- C12 วางตาราง Beam End Force ของ STAAD ทั้งก้อน ----------------
    txt = ("Beam\tL/C\tNode\tAxial Force\tShear-Y\tShear-Z\tTorsion\tMoment-Y\tMoment-Z\n"
           "\t\t\tkg\tkg\tkg\tkN-m\tkN-m\tkN-m\n"
           "12\t102\t24\t-5708.917\t-890.992\t753.547\t0.009\t17.505\t20.958\n"
           "12\t102\t12\t7764.665\t890.992\t-753.547\t-0.009\t8.359\t9.624\n"
           "12\t2\t24\t-1619.806\t-277.428\t235.279\t0.004\t5.466\t6.526\n"
           "12\t2\t12\t1619.806\t277.428\t-235.279\t-0.004\t2.610\t2.996\n")
    rows, fu, mu = C.parse_staad_end_forces(txt)
    check_true("C12", "อ่าน 4 แถว + หน่วยจากหัวตาราง (kg, kN-m)", (len(rows), fu, mu) == (4, "kg", "kN-m"))
    r12 = {(r["lc"], r["node"]): r for r in rows}
    check_true("C12", "L/C 102 node 12: Fx 7764.665 kg, Mz 9.624, My 8.359 kN·m",
               (r12[("102", "12")]["fx"], r12[("102", "12")]["mz"], r12[("102", "12")]["my"])
               == (7764.665, 9.624, 8.359))
    Fy = 890.992 * C.STAAD_FORCE_UNITS["kg"]                 # N
    r, _ = C.curvature_ratio(20.958e6, 9.624e6, V=Fy, L=3500)
    check_true("C12", "หน่วยผสม kg / kN-m แปลงแล้วสมดุลได้ (โค้งสองทาง, L = 3.5 m)", r > 0)
    grp, fu2, mu2 = C.parse_staad_end_forces("Beam\tL/C\tNode\tAxial Force kg\tShear-Y kg\tShear-Z kg\t"
                                             "Torsion kN-m\tMoment-Y kN-m\tMoment-Z kN-m\n"
                                             "1\t1\t1\t 3379.927\t-213.153\t 179.037\t 0.000\t-1.986\t-2.303\n"
                                             "\t\t13\t-1666.803\t 213.153\t-179.037\t-0.000\t-4.159\t-5.014\n"
                                             "\t2\t1\t 1619.806\t-277.428\t 235.279\t-0.004\t-2.610\t-2.996\n")
    check_true("C12", "ตารางแบบกลุ่ม (Beam / L/C เว้นว่าง) เติมจากแถวบน + หน่วยในหัวคอลัมน์",
               [(r["beam"], r["lc"], r["node"]) for r in grp] == [("1", "1", "1"), ("1", "1", "13"), ("1", "2", "1")]
               and (fu2, mu2) == ("kg", "kN-m"))
    rows3, _, _ = C.parse_staad_end_forces("5   101 1.2D+1.6L   3   100   1   2   0   3   4")
    check_true("C12", "L/C มีชื่อต่อท้าย", rows3 and rows3[0]["lc"] == "101 1.2D+1.6L" and rows3[0]["node"] == "3")

    # ---------------- C13 อ่านไฟล์ STAAD .std + ตาราง Beam End Force ----------------
    import staad_io as SIO
    ex = Path(__file__).resolve().parent.parent / "references" / "staad_example"
    Mo = SIO.parse_std((ex / "frame_3x2.std").read_text())
    check_true("C13", ".std: 24 joint, 29 member, เสา 1–12", (len(Mo.joints), len(Mo.members), Mo.columns())
               == (24, 29, list(range(1, 13))))
    check_true("C13", "PRIS เสา YD 500 ZD 400 mm, คาน YD 500 ZD 300 mm, L เสา 3,500 mm",
               Mo.prism[12] == (500.0, 400.0) and Mo.prism[20] == (500.0, 300.0) and abs(Mo.length(12) - 3500) < 1e-9)
    check_true("C13", "start node ของเสา 12 = N12 (ล่าง)", Mo.members[12] == (12, 24) and Mo.bottom_top(12) == (12, 24))
    check_true("C13", "FLOOR LOAD 2.88 kN/m² (หน่วย METER KN → N/mm²)",
               abs(Mo.loads[2].items[0]["w"] + 0.00288) < 1e-12)
    check_true("C13", "COMB 101, 102 = กำลัง; 103 (ตัวคูณ 1.0, SERVICE) = ใช้งาน", Mo.strength_combos() == [101, 102]
               and Mo.is_service(103))
    check_true("C13", "ไม่มีแรงด้านข้างในทุก combo", not any(Mo.is_lateral(c) for c in (101, 102, 103)))
    check_true("C13", "FCU 25 MPa อ่านเป็น MPa", abs(Mo.material["CONC_C25"]["STRENGTH FCU"] - 25) < 1e-9)
    check_true("C13", "ids: '1 TO 7 BY 3 10' → [1, 4, 7, 10]", SIO.ids("1 TO 7 BY 3 10") == [1, 4, 7, 10])
    for lid, exp in ((1, -507.60), (2, -432.00), (3, -294.20)):     # ΣFy ที่ STAAD.Pro 2025 พิมพ์ของโมเดลนี้
        check("C13", f"LOAD {lid}: ΣFy ที่คำนวณจาก .std (kN) เทียบ STAAD", Mo.vertical_total(lid)[0] / 1e3, exp, 0.01)
    Ft = SIO.forces_from_table((ex / "frame_3x2_beam_end_force.txt").read_text(), C.parse_staad_end_forces,
                               C.STAAD_FORCE_UNITS, C.STAAD_MOMENT_UNITS)
    check_true("C13", "ตาราง Beam End Force จริง (Beam/L/C เว้นว่าง, kg + kN-m): เสา 1–12 + คาน 13, 14, 17, 24, load 1–3, 101–103",
               Ft.members() == list(range(1, 15)) + [17, 24] and Ft.loads() == [1, 2, 3, 101, 102, 103])
    check_true("C13", "ตารางจริง: สมดุลเสาทั้ง 12 ต้น × 6 load ด้วย L จาก geometry",
               all(SIO.check_equilibrium(Mo, Ft, m, lc)[0] for m in Mo.columns() for lc in Ft.loads()))
    for lid, exp in ((1, 507.60), (2, 432.00), (3, 294.20), (101, 1315.44), (102, 1598.24)):
        check("C13", f"ตารางจริง: Σ แรงอัดฐานเสา 12 ต้น load {lid} = น้ำหนักรวม (kN)",
              SIO.base_reactions(Mo, Ft, lid)[0] / 1e3, exp, 0.02)
    fc = SIO.column_forces(Mo, Ft, 12, 102, C.from_staad)
    check_true("C13", "เสา 12 COMB 102: Mz 9.624/20.958 เครื่องหมายเดียวกัน → โค้งสองทาง ทั้งสองแกน (ตรงกับ |F|·L)",
               (fc["curv_x"], fc["curv_y"]) == ("double", "double"))
    check_true("C13", "เสา 5: My = 0 ทั้งสองปลาย → auto (กติกา M1 = M2 = 0)",
               SIO.column_forces(Mo, Ft, 5, 102, C.from_staad)["curv_y"] == "auto")
    check_true("C13", "end_curvature: เครื่องหมายต่างกัน → single", SIO.end_curvature(5e6, -7e6) == "single")
    # เสาวาดจากบนลงล่าง (start = joint บน): ป้ายบน/ล่างต้องตาม geometry และ Pu = แรงอัดที่ตีนเสา
    Mr = SIO.Model(joints={1: (0.0, 0.0, 0.0), 2: (0.0, 3500.0, 0.0)}, members={1: (2, 1)}, prism={1: (500.0, 400.0)})
    Fr = SIO.Forces(data={(1, 9): {2: (90e3, 1e3, 2e3, 0.0, 3e6, 20e6), 1: (-100e3, -1e3, -2e3, 0.0, 4e6, 10e6)}})
    fr = SIO.column_forces(Mr, Fr, 1, 9, C.from_staad)
    check_true("C13", "start อยู่บน: Mz บน = ค่าที่ joint บน (20), ล่าง = 10; Pu ตีนเสา = −Fx(end) = 100 kN",
               (fr["Mxt"], fr["Mxb"], fr["Myt"], fr["Myb"], fr["Pu"]) == (20e6, 10e6, 3e6, 4e6, 100e3))
    d = Ft.data[(12, 1)]
    check("C13", "น้ำหนักเสาเอง = Fx(N12) + Fx(N24) = 0.5×0.4×3.5×24 (kN)", (d[12][0] + d[24][0]) / 1e3, 16.8, 0.02)
    # ---------------- C14 คาน: FLOOR LOAD 45° จาก .std + M(x), V(x) จากแรงปลาย ----------------
    fl2 = [it for it in Mo.loads[2].items if it["type"] == "floor"][0]
    FL, npan = SIO.floor_beam_loads(Mo, fl2)
    tot = lambda m: sum((w0 + w1) / 2 * (b - a) for _, w0, w1, a, b in FL[m])            # noqa: E731
    mom = lambda m: sum((w0 + w1) / 2 * (b - a) * (a + (b - a) * (w0 + 2 * w1) / (3 * (w0 + w1)))  # noqa: E731
                        for _, w0, w1, a, b in FL[m])
    check_true("C14", "FLOOR LOAD 2: พบแผ่นพื้น 6 แผ่น (5×5 m) ส่งแรงลงคานทั้ง 17 ตัว", npan == 6 and sorted(FL) == list(range(13, 30)))
    # ค่าที่ STAAD.Pro 2025 แปลง floor load เป็น member load (16 แรงคานริม / 32 แรงคานใน) ของโมเดลเดียวกัน
    check("C14", "คานริม 13: ΣP = 2.88 × สามเหลี่ยม 6.25 m² เทียบ STAAD (kN)", -tot(13) / 1e3, 18.0, 1e-6)
    check("C14", "คานใน 24 (สองแผ่น) เทียบ STAAD (kN)", -tot(24) / 1e3, 36.0, 1e-6)
    check("C14", "คาน 13: ΣP·x รอบ start เทียบ STAAD (kN·m)", -mom(13) / 1e6, 45.0, 1e-6)
    m2 = sum(sum((w0 + (w1 - w0) * (t + 0.5) / 400) * ((a + (b - a) * (t + 0.5) / 400) ** 2) * (b - a) / 400
                 for t in range(400)) for _, w0, w1, a, b in FL[13])
    check("C14", "คาน 13: ΣP·x² (รูปสามเหลี่ยม 45°) เทียบ STAAD 131.11 (kN·m²)", -m2 / 1e9, 131.11, 0.2)
    worst = max(max(SIO.beam_diagram(Mo, Ft, m, lc)["close_M"], SIO.beam_diagram(Mo, Ft, m, lc)["close_V"])
                for m in (13, 14, 17, 24) for lc in Ft.loads())
    check_true("C14", "สมดุลปิด: คาน 13, 14, 17, 24 × 6 load — M(L) = Mz_e และ V(L) = −Fy_e (คลาดเคลื่อน < 0.1%)",
               worst < 1e-3, f"สูงสุด {worst:.1e}")
    Rb = SIO.beam_design_values(Mo, Ft, 13, [101, 102], d_eff=440)
    check_true("C14", "ผิวเสาคาน 13 = YD/2 ของเสา 1 และเสา 2 (YD ขนานแกน X) = 250 mm", Rb["faces"] == (250.0, 250.0))
    # STAAD ใช้แรงจุด 16 แรงแทนสามเหลี่ยม → M+ จากรายการแรงจุดใน .anl = 21.07; สามเหลี่ยมต่อเนื่อง = 20.86 (ต่าง 1%)
    check("C14", "คาน 13 M+ สูงสุด COMB 102 — floor load สามเหลี่ยม 45° (kN·m)", Rb["env"]["mid"][0] / 1e6, 20.86, 0.01)
    check("C14", "… เทียบ 21.07 ที่คิดจากแรงจุดของ STAAD (ต่างไม่เกิน 1.5%)", Rb["env"]["mid"][0] / 1e6, 21.07, 0.32)
    check_true("C14", "คาน 13 M− ที่ผิวเสาทั้งสองข้างเป็นลบ (ดึงบน) และปลาย end มากกว่า (ต่อเนื่อง)",
               Rb["env"]["left"][0] < 0 and Rb["env"]["right"][0] < Rb["env"]["left"][0])
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
