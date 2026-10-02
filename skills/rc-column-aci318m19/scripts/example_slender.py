"""ตัวอย่างเสาชะลูด S1 — รายการคำนวณมือ (อิสระจาก column.py) ใช้เป็นเคสทดสอบ C8

เสา 400×400 มม. 8-DB20 (3 เส้นต่อด้าน) ปลอก DB10 @ 250 มม. cover 40 มม. ถึงปลอก
f′c = 28 MPa, fy = fyt = 420 MPa, l_u = 4.5 ม., ความยาวชิ้นส่วน (c/c) 5.0 ม., โครง non-sway, k = 1.0
Pu = 1,600 kN, βdns = 0.6
แกน x: Mt = 90, Mb = 60 kN·m, Vu = 6 kN (โค้งทางเดียว)
แกน y: Mt = 30, Mb = 20 kN·m, Vu = 10 kN (โค้งสองทาง)
ข้อมูลชั้น: ΣPu = 24,000 kN, Δo = 3.2 มม., Vus = 900 kN, lc = 5,000 มม.

รัน: python3 example_slender.py → เขียน ../references/example-slender-column.md
ฟังก์ชันในไฟล์นี้เขียนแยกจาก solver เพื่อให้การเทียบผลมีความหมาย
"""
import math
from pathlib import Path

# ---------------- ข้อมูล ----------------
b = h = 400.0
fc, fy, fyt, Es = 28.0, 420.0, 420.0, 200000.0
cover, ds, db = 40.0, 10.0, 20.0
lu, Lmem, k = 4500.0, 5000.0, 1.0
Pu = 1600e3
beta_dns = 0.6
Mx_t, Mx_b, Vx = 90e6, 60e6, 6e3       # ดัดรอบแกน x (Vu ทิศ y)
My_t, My_b, Vy = 30e6, 20e6, 10e3      # ดัดรอบแกน y (Vu ทิศ x)
sumPu, delta_o, Vus, lc = 24000e3, 3.2, 900e3, 5000.0
s_tie, legs = 250.0, 2

Ab = math.pi * db ** 2 / 4
n_bars = 8
Ast = n_bars * Ab
e = cover + ds + db / 2                  # ระยะศูนย์กลางเหล็กจากผิว = 60
rows_x = [(3 * Ab, e), (2 * Ab, h / 2), (3 * Ab, h - e)]   # (พื้นที่, ระยะจากผิวอัด) ดัดรอบแกนใดก็ได้ (สมมาตร)
b1 = 0.85                                # f′c = 28 ≤ 28
ety = fy / Es


def phi_of(et):
    if et >= ety + 0.003:
        return 0.90
    if et <= ety:
        return 0.65
    return 0.65 + 0.25 * (et - ety) / 0.003


def section_at(c):
    """ดัดแกนเดียว เหล็ก 3 แถว: คืน (Pn, Mn รอบศูนย์ถ่วง, εt, ตารางแรง)"""
    a = b1 * c
    Cc = 0.85 * fc * b * min(a, h)
    P, M = Cc, Cc * (h / 2 - min(a, h) / 2)
    tab = [("คอนกรีต", min(a, h) / 2, None, None, Cc)]
    for A, y in rows_x:
        eps = 0.003 * (c - y) / c
        fs = max(-fy, min(fy, Es * eps))
        F = A * (fs - 0.85 * fc) if (fs > 0 and y <= a) else A * fs
        P += F
        M += F * (h / 2 - y)
        tab.append((f"{A / Ab:.0f}-DB20", y, eps, fs, F))
    et = 0.003 * (h - e - c) / c
    return P, M, et, tab


def c_at_phiP(Pt):
    lo, hi = 1.0, 5 * h
    for _ in range(200):
        c = (lo + hi) / 2
        P, M, et, _ = section_at(c)
        if phi_of(et) * P > Pt:
            hi = c
        else:
            lo = c
    return c


def c_at_ecc(ecc):
    """c ที่ Mn/Pn = ecc (ใช้กับ Bresler)"""
    lo, hi = 1.0, 5 * h
    for _ in range(200):
        c = (lo + hi) / 2
        P, M, et, _ = section_at(c)
        if M - ecc * P > 0:
            lo = c
        else:
            hi = c
    return c


def fiber_point(theta, c, n=200):
    """จุดบน surface ด้วยการแบ่ง fiber (อิสระจากวิธีรูปหลายเหลี่ยมของ solver)"""
    ux, uy = math.cos(theta), math.sin(theta)
    dmax = (b / 2) * abs(ux) + (h / 2) * abs(uy)
    a = b1 * c
    dx, dy = b / n, h / n
    P = Mx = My = 0.0
    for i in range(n):
        x = -b / 2 + (i + 0.5) * dx
        for j in range(n):
            y = -h / 2 + (j + 0.5) * dy
            if dmax - (x * ux + y * uy) <= a:
                f = 0.85 * fc * dx * dy
                P += f
                Mx += f * y
                My += f * x
    off = b / 2 - e
    bars = [(sx * off, sy * off) for sx in (-1, 0, 1) for sy in (-1, 0, 1) if (sx, sy) != (0, 0)]
    et = -1.0
    for x, y in bars:
        yy = dmax - (x * ux + y * uy)
        eps = 0.003 * (c - yy) / c
        fs = max(-fy, min(fy, Es * eps))
        F = Ab * (fs - 0.85 * fc) if (fs > 0 and yy <= a) else Ab * fs
        P += F
        Mx += F * y
        My += F * x
        et = max(et, -eps)
    return P, Mx, My, et


def hand_calc():
    R = {}
    Ag = b * h
    Ig = b * h ** 3 / 12
    r = math.sqrt(Ig / Ag)
    R.update(Ag=Ag, Ig=Ig, r=r, Ast=Ast, rho=Ast / Ag)
    R["Q"] = sumPu * delta_o / (Vus * lc)
    # เครื่องหมายจากสมดุลแรงเฉือน
    R["x_double"] = abs(Vx * Lmem - (Mx_t + Mx_b)) < abs(Vx * Lmem - abs(Mx_t - Mx_b))
    R["y_double"] = abs(Vy * Lmem - (My_t + My_b)) < abs(Vy * Lmem - abs(My_t - My_b))
    R["rx"] = (1 if R["x_double"] else -1) * min(Mx_t, Mx_b) / max(Mx_t, Mx_b)
    R["ry"] = (1 if R["y_double"] else -1) * min(My_t, My_b) / max(My_t, My_b)
    R["klu_r"] = k * lu / r
    R["lim_x"] = min(34 + 12 * R["rx"], 40)
    R["lim_y"] = min(34 + 12 * R["ry"], 40)
    R["Ec"] = 4700 * math.sqrt(fc)
    R["EI"] = 0.4 * R["Ec"] * Ig / (1 + beta_dns)
    R["Pc"] = math.pi ** 2 * R["EI"] / (k * lu) ** 2
    R["M2min"] = Pu * (15 + 0.03 * h)
    R["Cm"] = 0.6 - 0.4 * R["rx"]
    R["delta"] = max(1.0, R["Cm"] / (1 - Pu / (0.75 * R["Pc"])))
    R["Mcx"] = R["delta"] * max(Mx_t, R["M2min"])
    Po = 0.85 * fc * (Ag - Ast) + fy * Ast
    R.update(Po=Po, phiPnmax=0.65 * 0.80 * Po)
    # ดัดแกนเดียว (Mcx) ด้วยเหล็ก 3 แถว
    c = c_at_phiP(Pu)
    P, M, et, tab = section_at(c)
    R.update(c_u=c, a_u=b1 * c, et_u=et, phi_u=phi_of(et), Mn_u=M, phiMn_u=phi_of(et) * M,
             tab_u=tab, Pn_u=P)
    # Bresler (ค่าเทียบประกอบ): Pnx ที่ ey = Mcx/Pu, Pny ที่ ex = My/Pu
    Pnx = section_at(c_at_ecc(R["Mcx"] / Pu))[0]
    Pny = section_at(c_at_ecc(My_t / Pu))[0]
    Pn_b = 1 / (1 / Pnx + 1 / Pny - 1 / Po)
    R.update(Pnx=Pnx, Pny=Pny, Pn_bresler=Pn_b, ratio_bresler=Pu / (0.65 * Pn_b))
    # แรงเฉือน
    d = h - e
    rf = math.sqrt(fc)
    axial = min(Pu / (6 * Ag), 0.05 * fc)
    Av = legs * math.pi * ds ** 2 / 4
    Avmin_s = max(0.062 * rf * b / fyt, 0.35 * b / fyt)
    Vc = min((0.17 * rf + axial) * b * d, 0.42 * rf * b * d)
    R.update(d=d, axial=axial, axial_raw=Pu / (6 * Ag), Av=Av, Avs=Av / s_tie, Avmin_s=Avmin_s,
             Vc_a=(0.17 * rf + axial) * b * d, Vc_max=0.42 * rf * b * d, Vc=Vc,
             Vs=Av * fyt * d / s_tie)
    R["phiVn"] = 0.75 * (Vc + R["Vs"])
    R["s_max_tie"] = min(16 * db, 48 * ds, min(b, h))
    R["clear_mid"] = (b / 2 - e) - db
    return R


def markdown(R, solver=None):
    """รายการคำนวณ (Markdown) — solver = dict ผลจาก column.py สำหรับเทียบ (ถ้ามี)"""
    f = lambda x, n=2: f"{x:,.{n}f}"  # noqa: E731
    L = []
    A = L.append
    A("# ตัวอย่างรายการคำนวณ: เสาชะลูด S1 (ACI 318M-19)")
    A("")
    A("> ตัวอย่างสร้างขึ้นเพื่อทดสอบสกิล (ไม่ใช่งานจริง) ตัวเลขทุกบรรทัดคำนวณด้วยสคริปต์มือ "
      "`example_slender.py` ซึ่งเขียนแยกจาก solver แล้วนำไปเทียบกับ `column.py` ในเคสทดสอบ C8")
    A("")
    A("## 1. ข้อมูล")
    A("")
    A("| รายการ | ค่า |")
    A("|---|---|")
    A(f"| หน้าตัด b × h | {b:.0f} × {h:.0f} mm |")
    A(f"| เหล็กยืน | 8-DB20 (3 เส้นต่อด้าน), Ast = 8 × π(20)²/4 = {f(Ast, 1)} mm², "
      f"ρg = {f(R['rho'] * 100)}% |")
    A(f"| ปลอก | DB10 @ {s_tie:.0f} mm, {legs} ขาต่อทิศ, cover ถึงปลอก {cover:.0f} mm |")
    A(f"| วัสดุ | f′c = {fc:.0f} MPa, fy = fyt = {fy:.0f} MPa, Es = 200,000 MPa |")
    A(f"| ความยาว | l_u = {lu / 1000:.1f} m (ทั้งสองแกน), ความยาวชิ้นส่วน c/c = {Lmem / 1000:.1f} m, "
      "k = 1.0 (non-sway) |")
    A(f"| แรงอัด | Pu = {Pu / 1e3:,.0f} kN, βdns = {beta_dns} |")
    A("| ดัดรอบแกน x | Mt = 90, Mb = 60 kN·m, Vu = 6 kN |")
    A("| ดัดรอบแกน y | Mt = 30, Mb = 20 kN·m, Vu = 10 kN |")
    A("| ข้อมูลชั้น | ΣPu = 24,000 kN, Δo = 3.2 mm, Vus = 900 kN, lc = 5,000 mm |")
    A("")
    A("## 2. Sway หรือ non-sway (§6.6.4.3)")
    A("")
    A(f"Q = ΣPu·Δo/(Vus·lc) = 24,000 × 3.2 / (900 × 5,000) = **{R['Q']:.4f} ≤ 0.05 → non-sway**")
    A("")
    A("## 3. ความชะลูด (§6.2.5.1)")
    A("")
    A(f"r = √(Ig/Ag) = h/√12 = {f(R['r'])} mm → kl_u/r = 1.0 × {lu:.0f} / {f(R['r'])} = "
      f"**{f(R['klu_r'])}**")
    A("")
    A("**ทิศการดัดจากสมดุลแรงเฉือน** (เสาไม่มีแรงกระทำระหว่างช่วง):")
    A("")
    A(f"- แกน x: |V|·L = 6 × 5.0 = 30 kN·m เท่ากับ |Mt − Mb| = 30 → **โค้งทางเดียว** → "
      f"M1/M2 = −60/90 = {R['rx']:.4f}")
    A(f"- แกน y: |V|·L = 10 × 5.0 = 50 kN·m เท่ากับ |Mt| + |Mb| = 50 → **โค้งสองทาง** → "
      f"M1/M2 = +20/30 = {R['ry']:.4f}")
    A("")
    A(f"- แกน x: เกณฑ์ = min(34 + 12({R['rx']:.4f}), 40) = **{f(R['lim_x'])}** → "
      f"{f(R['klu_r'])} > {f(R['lim_x'])} → **ชะลูด**")
    A(f"- แกน y: เกณฑ์ = min(34 + 12({R['ry']:.4f}), 40) = **{f(R['lim_y'])}** → "
      f"{f(R['klu_r'])} < {f(R['lim_y'])} → **ไม่ชะลูด**")
    A("")
    A("## 4. การขยายโมเมนต์แกน x (§6.6.4.4–6.6.4.5)")
    A("")
    A(f"- Ec = 4700√f′c = 4700√28 = {f(R['Ec'], 0)} MPa")
    A(f"- Ig = bh³/12 = 400 × 400³/12 = {R['Ig']:.4e} mm⁴")
    A(f"- (EI)eff = 0.4EcIg/(1 + βdns) = 0.4 × {f(R['Ec'], 0)} × {R['Ig']:.4e} / 1.6 = "
      f"{R['EI']:.4e} N·mm²")
    A(f"- Pc = π²(EI)eff/(kl_u)² = π² × {R['EI']:.4e} / 4,500² = **{f(R['Pc'] / 1e3, 1)} kN**")
    A(f"- Cm = 0.6 − 0.4(M1/M2) = 0.6 − 0.4({R['rx']:.4f}) = {R['Cm']:.4f}")
    A(f"- δ = Cm/(1 − Pu/0.75Pc) = {R['Cm']:.4f}/(1 − 1,600/(0.75 × {f(R['Pc'] / 1e3, 1)})) = "
      f"**{R['delta']:.4f}** ≥ 1.0")
    A(f"- M2,min = Pu(15 + 0.03h) = 1,600 × (15 + 12) = {f(R['M2min'] / 1e6, 1)} kN·m < M2 = 90 "
      "→ ใช้ M2 = 90 kN·m")
    A(f"- **Mcx = δM2 = {R['delta']:.4f} × 90 = {f(R['Mcx'] / 1e6)} kN·m**")
    A(f"- §6.2.6: Mc/M2 = δ = {R['delta']:.3f} ≤ 1.4 → **ผ่าน**")
    A("- แกน y ไม่ชะลูด → ใช้โมเมนต์ลำดับหนึ่ง Muy = 30 kN·m")
    A("")
    A("## 5. แรงอัดสูงสุด (§22.4.2)")
    A("")
    A(f"Po = 0.85f′c(Ag − Ast) + fyAst = 0.85 × 28 × (160,000 − {f(Ast, 1)}) + 420 × {f(Ast, 1)} = "
      f"{f(R['Po'] / 1e3, 1)} kN")
    A(f"φPn,max = 0.65 × 0.80 × Po = **{f(R['phiPnmax'] / 1e3, 1)} kN ≥ Pu = 1,600 kN → ผ่าน**")
    A("")
    A("## 6. กำลังดัดแกน x ที่ Pu (ตรวจมือด้วย strain compatibility)")
    A("")
    A(f"ลองค่า c จน φPn = Pu ได้ **c = {f(R['c_u'], 1)} mm**, a = 0.85c = {f(R['a_u'], 1)} mm")
    A("")
    A("| ส่วน | y จากผิวอัด (mm) | εs | fs (MPa) | F (kN) |")
    A("|---|---|---|---|---|")
    for name, y, eps, fs, F in R["tab_u"]:
        if eps is None:
            A(f"| {name} 0.85f′c·b·a | {f(y, 1)} (a/2) | – | – | {F / 1e3:+,.1f} |")
        else:
            A(f"| {name} | {f(y, 1)} | {eps:+.5f} | {fs:+.1f} | {F / 1e3:+,.1f} |")
    A("")
    A(f"- Pn = ΣF = {f(R['Pn_u'] / 1e3, 1)} kN, εt = {R['et_u']:.5f} ≤ εty = {ety:.5f} → "
      f"φ = {R['phi_u']:.2f} (compression-controlled) → φPn = {f(R['phi_u'] * R['Pn_u'] / 1e3, 1)} kN = Pu ✓")
    A(f"- Mn = ΣF·(h/2 − y) = {f(R['Mn_u'] / 1e6, 1)} kN·m → **φMnx = {f(R['phiMn_u'] / 1e6, 1)} kN·m**")
    A("")
    A("## 7. แรงอัดร่วมดัดสองแกน (3D interaction)")
    A("")
    A("ตรวจที่ Pu = 1,600 kN สามจุด: ปลายบน (ลำดับหนึ่ง), กลางเสา (Mcx ขยาย + Muy) และกรณีแกน x อย่างเดียว")
    A("")
    if solver:
        A("| จุด | Mux (kN·m) | Muy (kN·m) | มุมโหลด | Mres | φMcap | ratio |")
        A("|---|---|---|---|---|---|---|")
        for row in solver["checks"]:
            A("| " + " | ".join(row) + " |")
        A("")
        A(f"- ตรวจจุดความจุของ solver ด้วย **fiber model อิสระ** (200 × 200 ช่อง) ที่ θ, c เดียวกัน: "
          f"φPn ต่างกัน {solver['fiber_dP']:.3f}%, φMcap ต่างกัน {solver['fiber_dM']:.3f}%")
    A(f"- ค่าเทียบประกอบ Bresler (§R22.4, ใช้ได้เมื่อ Pu ≥ 0.1f′cAg = 448 kN): "
      f"Pnx = {f(R['Pnx'] / 1e3, 0)}, Pny = {f(R['Pny'] / 1e3, 0)}, Po = {f(R['Po'] / 1e3, 0)} kN → "
      f"Pn = {f(R['Pn_bresler'] / 1e3, 0)} kN → Pu/φPn = **{R['ratio_bresler']:.3f}** "
      "(อัตราส่วนเชิงแรงอัด จึงไม่เท่ากับ ratio เชิงโมเมนต์ แต่ต้องสรุปผ่าน/ไม่ผ่านตรงกัน)")
    A("")
    A("**ข้อสังเกต:** ถ้าไม่คิดการขยายโมเมนต์ ratio ที่กลางเสาจะต่ำกว่าความจริงประมาณ 20% "
      "เป็นเหตุผลที่ต้องตรวจความชะลูดก่อนเช็ค interaction")
    A("")
    A("## 8. แรงเฉือน (Table 22.5.5.1, §10.6.2)")
    A("")
    A(f"- d = h − 60 = {f(R['d'], 0)} mm, Av = 2 × π(10)²/4 = {f(R['Av'], 1)} mm², "
      f"Av/s = {R['Avs']:.4f} ≥ Av,min/s = max(0.062√28 × 400/420, 0.35 × 400/420) = "
      f"{R['Avmin_s']:.4f} → ใช้สมการ (a)")
    A(f"- Nu/(6Ag) = 1,600,000/(6 × 160,000) = {R['axial_raw']:.3f} MPa > 0.05f′c = 1.40 → "
      f"**ใช้ {R['axial']:.2f} MPa**")
    A(f"- Vc(a) = (0.17√28 + 1.40) × 400 × 340 = {f(R['Vc_a'] / 1e3, 1)} kN > "
      f"Vc,max = 0.42√28 × 400 × 340 = {f(R['Vc_max'] / 1e3, 1)} kN → **Vc = {f(R['Vc'] / 1e3, 1)} kN**")
    A(f"- Vs = Av·fyt·d/s = {f(R['Av'], 1)} × 420 × 340/250 = {f(R['Vs'] / 1e3, 1)} kN → "
      f"φVn = 0.75(Vc + Vs) = **{f(R['phiVn'] / 1e3, 1)} kN ≫ Vu = 6, 10 kN → ผ่าน**")
    A(f"- Vu ≤ 0.5φVc = {f(0.375 * R['Vc'] / 1e3, 1)} kN → ไม่บังคับปลอกขั้นต่ำ (§10.6.2.1) "
      "แต่ปลอกที่ใส่ก็เกินขั้นต่ำ")
    A("- แรงเฉือนสองทิศ (§22.5.1.11): อัตราส่วนทั้งสองทิศ < 0.5 → ไม่ต้องตรวจผลรวม")
    A("")
    A("## 9. รายละเอียดเหล็ก")
    A("")
    A(f"- ρg = {f(R['rho'] * 100)}% อยู่ระหว่าง 1–8% (§10.6.1.1) ✓, 8 เส้น ≥ 4 ✓")
    A("- ช่องว่างเหล็กยืน = 140 − 20 = 120 mm ≥ max(40, 1.5 × 20, 4/3 × 20) = 40 mm (§25.2.3) ✓")
    A(f"- ระยะปลอก 250 ≤ min(16 × 20, 48 × 10, 400) = {f(R['s_max_tie'], 0)} mm (§25.7.2.1) ✓")
    A("- ขนาดปลอก DB10 = 10 ≥ 9.5 mm (No.10) สำหรับเหล็กยืน ≤ 32 mm (§25.7.2.2) ✓")
    A(f"- เหล็กกลางด้านห่างจากเหล็กมุม (ช่องว่าง) {f(R['clear_mid'], 0)} mm ≤ 150 mm และเป็นเหล็ก"
      "เว้นเส้น → ปลอกรอบรูปพอ (§25.7.2.3) ✓")
    A("- ระยะหุ้มถึงปลอก 40 mm ตาม Table 20.5.1.3.1 (เสาภายใน) ✓")
    A("")
    A("## 10. สรุป")
    A("")
    A("| รายการ | ผล |")
    A("|---|---|")
    A(f"| Sway | non-sway (Q = {R['Q']:.4f}) |")
    A(f"| ความชะลูด | แกน x ชะลูด (δ = {R['delta']:.3f}), แกน y ไม่ชะลูด |")
    A("| φPn,max | ผ่าน |")
    if solver:
        A(f"| 3D interaction | ratio สูงสุด {solver['ratio_max']:.3f} (กลางเสา) → ผ่าน |")
    A("| แรงเฉือน | ผ่าน (Vc ถูกจำกัดที่ Vc,max) |")
    A("| รายละเอียดเหล็ก | ผ่าน |")
    A("| ระยะทาบ/ฝังยึด, รอยต่อ | ยังไม่ตรวจ |")
    A("")
    return "\n".join(L)


def solver_compare(R):
    """เรียก column.py แล้วสรุปผลสำหรับตาราง §7 (ใช้ทั้งในเอกสารและเคสทดสอบ)"""
    import column as C
    bars, tc = C.rect_bars(b, h, cover, ds, db, 3, 3)
    S = C.Section(b, h, fc, fy, fyt, bars, tc, ds)
    pts = [("ปลายบน (ลำดับหนึ่ง)", Mx_t, My_t), ("กลางเสา (Mcx ขยาย + Muy)", R["Mcx"], My_t),
           ("แกน x อย่างเดียว (Mcx)", R["Mcx"], 0.0)]
    rows, caps = [], []
    for name, mx, my in pts:
        cap = C.capacity_at(S, Pu, mx, my)
        caps.append(cap)
        ang = math.degrees(math.atan2(my, mx))
        rows.append((name, f"{mx / 1e6:.1f}", f"{my / 1e6:.1f}", f"{ang:.1f}°",
                     f"{cap.Mres / 1e6:.1f}", f"{cap.phiMcap / 1e6:.1f}", f"{cap.ratio:.3f}"))
    mid = caps[1].pt
    P, Mx, My, et = fiber_point(mid.theta, mid.c)
    phi = phi_of(et)
    dP = abs(phi * P - mid.phiPn) / mid.phiPn * 100
    dM = abs(phi * math.hypot(Mx, My) - caps[1].phiMcap) / caps[1].phiMcap * 100
    return {"checks": rows, "caps": caps, "S": S, "fiber_dP": dP, "fiber_dM": dM,
            "ratio_max": max(c.ratio for c in caps[:2])}


if __name__ == "__main__":
    R = hand_calc()
    sol = solver_compare(R)
    out = Path(__file__).parent.parent / "references" / "example-slender-column.md"
    out.write_text(markdown(R, sol), encoding="utf-8")
    print(out)
