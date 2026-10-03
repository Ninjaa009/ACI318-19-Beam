"""ออกแบบ/ตรวจสอบเสา คสล. หน้าตัดสี่เหลี่ยม ปลอกเดี่ยว (tied) โครง non-sway ตาม ACI 318M-19

หน่วยภายใน: MPa, mm, N, N·mm   (ใช้ฟังก์ชัน kn/knm/kgf/kgfm แปลงจากหน่วยผู้ใช้)

แกนและเครื่องหมาย
- แกน x ขนานด้าน b, แกน y ขนานด้าน h, จุดกำเนิดที่ศูนย์ถ่วงหน้าตัด
- Mx = โมเมนต์รอบแกน x (ใช้ความลึก h รับ), My = โมเมนต์รอบแกน y (ใช้ความลึก b รับ)
- P > 0 = แรงอัด, แรงในเหล็ก > 0 = แรงอัด
- Mx > 0 ทำให้ผิว +y รับแรงอัด, My > 0 ทำให้ผิว +x รับแรงอัด

ฟังก์ชันหลัก
- Section / rect_bars                : หน้าตัดและเหล็กยืนรอบรูป
- point(sec, theta, c)              : strain compatibility ที่มุมแกนสะเทิน theta และความลึก c
- capacity_at(sec, Pu, Mux, Muy)    : φMcap ที่ระดับ Pu ตามทิศของโมเมนต์ (3D interaction)
- surface(sec)                      : จุดบน interaction surface (φPn, φMnx, φMny) สำหรับพล็อต
- curvature_ratio, slenderness      : ความชะลูดและการขยายโมเมนต์ (non-sway)
  (ระบบตรวจ sway / non-sway ย้ายไป incoming/sway.py — ยังไม่เปิดใช้)
- shear_check, omf_shear, biaxial_shear          : แรงเฉือน
- longitudinal_checks, tie_checks                : รายละเอียดเหล็ก
"""
from dataclasses import dataclass, field
import math
import re

ES = 200_000.0      # §20.2.2.2
ECU = 0.003         # §22.2.2.1
PHI_V = 0.75        # Table 21.2.1
PHI_C_TIED = 0.65   # Table 21.2.2
PHI_T = 0.90

# ---------------------------------------------------------------- หน่วย
G = 9.80665


def kn(x):
    return x * 1e3


def knm(x):
    return x * 1e6


def kgf(x):
    return x * G


def kgfm(x):
    return x * G * 1e3


def ksc(x):
    return x * 0.0980665


def bar_area(db):
    return math.pi * db ** 2 / 4.0


# ---------------------------------------------------------------- วัสดุ
def beta1(fc):
    """§22.2.2.4.3"""
    if fc <= 28.0:
        return 0.85
    return max(0.65, 0.85 - 0.05 * (fc - 28.0) / 7.0)


def eps_ty(fy, grade420=False):
    """§21.2.2.1 — ข้อยกเว้น Grade 420 ใช้ εty = 0.002 ได้เฉพาะ fy = 420 MPa"""
    if grade420:
        if abs(fy - 420.0) > 0.5:
            raise ValueError("ข้อยกเว้น εty = 0.002 ใช้ได้เฉพาะ fy = 420 MPa")
        return 0.002
    return fy / ES


def phi_axial_flexure(et, ety):
    """Table 21.2.2 สำหรับปลอกเดี่ยว: 0.65 → 0.90 ตาม εt"""
    if et >= ety + 0.003:
        return PHI_T
    if et <= ety:
        return PHI_C_TIED
    return PHI_C_TIED + 0.25 * (et - ety) / 0.003


def Ec(fc):
    """§19.2.2.1(b) คอนกรีตน้ำหนักปกติ"""
    return 4700.0 * math.sqrt(fc)


# ---------------------------------------------------------------- หน้าตัด
@dataclass
class Bar:
    x: float
    y: float
    db: float

    @property
    def area(self):
        return bar_area(self.db)


@dataclass
class Section:
    b: float                 # ขนาดตามแกน x (mm)
    h: float                 # ขนาดตามแกน y (mm)
    fc: float
    fy: float
    fyt: float
    bars: list
    cover: float             # clear cover ถึงผิวปลอก (mm)
    ds: float                # ขนาดปลอก (mm)
    dagg: float = 20.0
    lam: float = 1.0
    grade420: bool = False

    @property
    def Ag(self):
        return self.b * self.h

    @property
    def Ast(self):
        return sum(br.area for br in self.bars)

    @property
    def rho(self):
        return self.Ast / self.Ag

    @property
    def ety(self):
        return eps_ty(self.fy, self.grade420)

    @property
    def Po(self):
        """§22.4.2.2 (fy ไม่เกิน 550 MPa ตาม §20.2.2.4)"""
        fy = min(self.fy, 550.0)
        return 0.85 * self.fc * (self.Ag - self.Ast) + fy * self.Ast

    @property
    def Pn_max(self):
        """Table 22.4.2.1 ปลอกเดี่ยว: 0.80Po"""
        return 0.80 * self.Po

    @property
    def phiPn_max(self):
        return PHI_C_TIED * self.Pn_max


def rect_bars(b, h, cover, ds, db, nx, ny, cover_to="tie"):
    """เหล็กยืนรอบรูป: nx เส้นต่อด้าน b (รวมมุม), ny เส้นต่อด้าน h (รวมมุม)

    cover_to = "tie"  : cover วัดถึงผิวปลอก (นิยาม ACI)
             = "long" : cover วัดถึงผิวเหล็กยืน (นิยามของ RCDC)
    คืน (bars, clear cover ถึงผิวปลอก)
    """
    if nx < 2 or ny < 2:
        raise ValueError("ต้องมีเหล็กอย่างน้อย 2 เส้นต่อด้าน")
    off = cover + (ds if cover_to == "tie" else 0.0) + db / 2.0
    tie_cover = cover if cover_to == "tie" else cover - ds
    xs = [-b / 2 + off + i * (b - 2 * off) / (nx - 1) for i in range(nx)]
    ys = [-h / 2 + off + j * (h - 2 * off) / (ny - 1) for j in range(ny)]
    bars = [Bar(x, ys[0], db) for x in xs] + [Bar(x, ys[-1], db) for x in xs]
    bars += [Bar(xs[0], y, db) for y in ys[1:-1]] + [Bar(xs[-1], y, db) for y in ys[1:-1]]
    return bars, tie_cover


# ---------------------------------------------------------------- strain compatibility
def _clip(poly, u, t):
    """ตัดรูปหลายเหลี่ยมเก็บส่วนที่ p·u ≥ t"""
    out = []
    n = len(poly)
    for i in range(n):
        P, Q = poly[i], poly[(i + 1) % n]
        fp = P[0] * u[0] + P[1] * u[1] - t
        fq = Q[0] * u[0] + Q[1] * u[1] - t
        if fp >= 0:
            out.append(P)
        if (fp >= 0) != (fq >= 0):
            s = fp / (fp - fq)
            out.append((P[0] + s * (Q[0] - P[0]), P[1] + s * (Q[1] - P[1])))
    return out


def _area_centroid(poly):
    if len(poly) < 3:
        return 0.0, 0.0, 0.0
    A = cx = cy = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        cr = x0 * y1 - x1 * y0
        A += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
    A *= 0.5
    if abs(A) < 1e-12:
        return 0.0, 0.0, 0.0
    return abs(A), cx / (6 * A), cy / (6 * A)


@dataclass
class SectionPoint:
    theta: float
    c: float
    a: float
    Pn: float
    Mnx: float
    Mny: float
    et: float
    phi: float

    @property
    def phiPn(self):
        return self.phi * self.Pn

    @property
    def phiMnx(self):
        return self.phi * self.Mnx

    @property
    def phiMny(self):
        return self.phi * self.Mny


def point(sec, theta, c):
    """จุดบน interaction surface: u = (cos θ, sin θ) ชี้ไปด้านรับแรงอัด, c วัดตั้งฉากแกนสะเทิน

    §22.2.1 สมดุล + strain compatibility, §22.2.2 εcu = 0.003, stress block 0.85f′c ลึก a = β1c,
    §20.2.2.1 fs = Esεs ≤ fy, เหล็กอัดที่อยู่ใน block หักคอนกรีตที่ถูกแทนที่
    """
    ux, uy = math.cos(theta), math.sin(theta)
    b, h = sec.b, sec.h
    corners = [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
    proj = [p[0] * ux + p[1] * uy for p in corners]
    dmax, dmin = max(proj), min(proj)
    a = min(beta1(sec.fc) * c, dmax - dmin)
    A, cx, cy = _area_centroid(_clip(corners, (ux, uy), dmax - a))
    Cc = 0.85 * sec.fc * A
    P, Mx, My = Cc, Cc * cy, Cc * cx
    fy = sec.fy
    et = -1.0
    for br in sec.bars:
        y = dmax - (br.x * ux + br.y * uy)          # ระยะจากผิวรับแรงอัดสุด
        eps = ECU * (c - y) / c
        fs = max(-fy, min(fy, ES * eps))
        F = br.area * (fs - 0.85 * sec.fc) if (fs > 0 and y <= a) else br.area * fs
        P += F
        Mx += F * br.y
        My += F * br.x
        et = max(et, -eps)
    return SectionPoint(theta, c, a, P, Mx, My, et, phi_axial_flexure(et, sec.ety))


def _c_for_P(sec, theta, P_target, factored=True):
    """หา c ที่ φPn (หรือ Pn) = P_target ด้วย bisection"""
    lo, hi = 1e-3, 50.0 * max(sec.b, sec.h)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        pt = point(sec, theta, mid)
        val = pt.phiPn if factored else pt.Pn
        if val > P_target:
            hi = mid
        else:
            lo = mid
    return point(sec, theta, 0.5 * (lo + hi))


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


@dataclass
class Capacity:
    Pu: float
    Mux: float
    Muy: float
    Mres: float
    load_angle: float          # องศา, atan2(Mux, Muy)
    phiMcap: float
    ratio: float
    pt: SectionPoint = None
    ok_axial: bool = True
    note: str = ""

    @property
    def ok(self):
        return self.ok_axial and self.ratio <= 1.0 + 1e-9


def capacity_at(sec, Pu, Mux, Muy, factored=True):
    """φMcap ที่ระดับ Pu ตามทิศของโมเมนต์ลัพธ์ (load contour ของ 3D interaction surface)

    หามุมแกนสะเทิน θ ที่ทำให้ทิศ (φMnx, φMny) ตรงกับทิศ (Mux, Muy) — มุมแกนสะเทินไม่จำเป็นต้อง
    เท่ากับมุมโหลด จากนั้น ratio = Mres/φMcap
    factored=False คืน Mn (ไม่คูณ φ) ที่ Pn = Pu ใช้กับ §18.3.3
    """
    Mres = math.hypot(Mux, Muy)
    alpha = math.atan2(Mux, Muy)
    Pmax = sec.phiPn_max if factored else sec.Pn_max
    Pmin = -(PHI_T if factored else 1.0) * min(sec.fy, 550.0) * sec.Ast
    if Pu > Pmax + 1e-6:
        return Capacity(Pu, Mux, Muy, Mres, math.degrees(alpha), 0.0, math.inf, None, False,
                        "Pu > φPn,max (§22.4.2)")
    if Pu < Pmin:
        return Capacity(Pu, Mux, Muy, Mres, math.degrees(alpha), 0.0, math.inf, None, False,
                        "แรงดึงเกินกำลังเหล็ก")
    if Mres < 1e-6:
        alpha = math.pi / 2          # ไม่มีโมเมนต์: รายงานกำลังรอบแกน x

    def mdir(th):
        pt = _c_for_P(sec, th, Pu, factored)
        return _wrap(math.atan2(pt.Mnx, pt.Mny) - alpha), pt

    # หาช่วงที่ทิศโมเมนต์ตัดผ่านทิศโหลด (θ ≈ alpha ในหน้าตัดทั่วไป)
    steps = [alpha + math.radians(d) for d in range(-90, 91, 6)]
    vals = [mdir(t) for t in steps]
    lo = hi = None
    for (t0, (g0, _)), (t1, (g1, _)) in zip(zip(steps, vals), zip(steps[1:], vals[1:])):
        if abs(g0) < math.pi / 2 and abs(g1) < math.pi / 2 and (g0 <= 0 <= g1 or g1 <= 0 <= g0):
            lo, hi, glo = t0, t1, g0
            break
    if lo is None:
        best = min(zip(steps, vals), key=lambda z: abs(z[1][0]))
        pt = best[1][1]
    else:
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            g, pt = mdir(mid)
            if (g <= 0) == (glo <= 0):
                lo, glo = mid, g
            else:
                hi = mid
        pt = mdir(0.5 * (lo + hi))[1]
    f = pt.phi if factored else 1.0
    Mcap = f * math.hypot(pt.Mnx, pt.Mny)
    ratio = Mres / Mcap if Mcap > 0 else math.inf
    return Capacity(Pu, Mux, Muy, Mres, math.degrees(math.atan2(Mux, Muy)), Mcap, ratio, pt)


def contour_at(sec, Pu, n=72):
    """เส้นตัด surface ที่ φPn = Pu: list ของ (φMnx, φMny) ใช้วาดกราฟ Mx–My (ว่างถ้า Pu เกินช่วง)"""
    if Pu > sec.phiPn_max or Pu < -PHI_T * min(sec.fy, 550.0) * sec.Ast:
        return []
    pts = []
    for i in range(n + 1):
        pt = _c_for_P(sec, 2 * math.pi * i / n, Pu)
        pts.append((pt.phiMnx, pt.phiMny))
    return pts


def surface(sec, n_theta=36, n_c=30):
    """จุดบน φ-surface สำหรับพล็อต: list ของ (φPn, φMnx, φMny) ตัดที่ φPn,max"""
    pts = []
    cmax = 3.0 * max(sec.b, sec.h)
    for i in range(n_theta):
        th = 2 * math.pi * i / n_theta
        row = []
        for j in range(1, n_c + 1):
            c = cmax * (j / n_c) ** 2
            pt = point(sec, th, c)
            row.append((min(pt.phiPn, sec.phiPn_max), pt.phiMnx, pt.phiMny))
        pts.append(row)
    return pts


# ---------------------------------------------------------------- ความชะลูด (non-sway)
CURV_TOL = 0.10     # ความคลาดเคลื่อนที่ยอมให้ในการตรวจทิศการดัดด้วย |V|·L


def curvature_ratio(M_top, M_bot, V=None, L=None, curvature=None):
    """คืน (M1/M2 ตาม ACI, คำอธิบาย) — ลบ = โค้งทางเดียว, บวก = โค้งสองทาง (§6.2.5.1)

    เครื่องหมายโมเมนต์จากแต่ละโปรแกรมไม่เหมือนกัน จึงตัดสินจาก
    1) curvature = "single" / "double" ถ้าผู้ใช้ระบุ หรือ
    2) สมดุลแรงเฉือนของเสาที่ไม่มีแรงกระทำระหว่างช่วง: |V|·L ≈ |Mt| + |Mb| → โค้งสองทาง,
       |V|·L ≈ ||Mt| − |Mb|| → โค้งทางเดียว (L = ความยาวชิ้นส่วนในการวิเคราะห์)
    กรณี M1 = M2 = 0 ใช้ −1 (กติกาของสกิล: อนุรักษ์นิยม สอดคล้องกับ Cm = 1.0)
    """
    a, b = abs(M_top), abs(M_bot)
    if a < 1e-9 and b < 1e-9:
        return -1.0, "M1 = M2 = 0 → ใช้ M1/M2 = −1 (กติกาของสกิล)"
    M1, M2 = min(a, b), max(a, b)
    if M1 < 1e-9:
        return 0.0, "โมเมนต์ปลายหนึ่งเป็นศูนย์ → M1/M2 = 0"
    r = M1 / M2
    if curvature in ("single", "double"):
        return (r if curvature == "double" else -r), f"ผู้ใช้ระบุ {curvature} curvature"
    if V is None or not L:
        raise ValueError("ระบุ curvature หรือส่ง V และ L เพื่อตรวจทิศการดัดจากสมดุลแรงเฉือน")
    vd, vs = (a + b) / L, abs(a - b) / L
    double = abs(abs(V) - vd) <= abs(abs(V) - vs)
    # ต้องตรงกับแบบใดแบบหนึ่งพอสมควร ไม่เช่นนั้นแกนอาจจับคู่ผิด (V ไม่ได้มาจากโมเมนต์แกนเดียวกัน)
    # หรือมีแรงกระทำระหว่างช่วงเสา → ให้ผู้ใช้ระบุทิศการดัดเอง
    err = min(abs(abs(V) - vd), abs(abs(V) - vs))
    if err > CURV_TOL * vd + 1.0:
        raise ValueError(
            f"ทิศการดัดตรวจจากแรงเฉือนไม่ได้: |V| = {abs(V) / 1e3:.2f} kN ไม่ตรงทั้ง "
            f"(|Mt|+|Mb|)/L = {vd / 1e3:.2f} และ ||Mt|−|Mb||/L = {vs / 1e3:.2f} kN "
            f"(ต่างเกิน {CURV_TOL:.0%}) — ตรวจการจับคู่แกน V↔M หรือแรงกระทำระหว่างช่วง "
            "แล้วระบุ single/double เอง")
    txt = (f"สมดุลแรงเฉือน: |V| = {abs(V) / 1e3:.2f} kN, (|Mt|+|Mb|)/L = {vd / 1e3:.2f} kN, "
           f"||Mt|−|Mb||/L = {vs / 1e3:.2f} kN → {'โค้งสองทาง' if double else 'โค้งทางเดียว'}")
    return (r if double else -r), txt


@dataclass
class Slenderness:
    axis: str
    k: float
    lu: float
    r: float
    klu_r: float
    ratio_M1M2: float
    ratio_note: str
    limit: float
    slender: bool
    M2: float = 0.0           # |M2| ลำดับหนึ่ง
    M2min: float = 0.0
    EIeff: float = 0.0
    Pc: float = 0.0
    Cm: float = 1.0
    delta: float = 1.0
    Mc: float = 0.0
    stable: bool = True
    ok_14: bool = True
    notes: list = field(default_factory=list)


def slenderness(sec, axis, lu, Pu, M_top, M_bot, k=1.0, V=None, L=None, curvature=None,
                beta_dns=0.6, transverse_load=False, r_method="exact", EI_method="a"):
    """ความชะลูดและการขยายโมเมนต์แบบ non-sway ของแกนหนึ่ง

    axis = "x" : ดัดรอบแกน x (ความลึก h), axis = "y" : ดัดรอบแกน y (ความลึก b)
    §6.2.5.1 kl_u/r ≤ min(34 + 12 M1/M2, 40)
    §6.6.4.4.2 Pc = π²(EI)eff/(k l_u)², §6.6.4.4.4 (EI)eff
    §6.6.4.5.2 δ = Cm/(1 − Pu/0.75Pc) ≥ 1, §6.6.4.5.3 Cm, §6.6.4.5.4 M2,min = Pu(15 + 0.03h)
    §6.2.6 โมเมนต์รวมลำดับสอง ≤ 1.4 × ลำดับหนึ่ง
    """
    depth, width = (sec.h, sec.b) if axis == "x" else (sec.b, sec.h)
    Ig = width * depth ** 3 / 12.0
    r = 0.3 * depth if r_method == "0.3h" else math.sqrt(Ig / sec.Ag)
    klu_r = k * lu / r
    ratio, note = curvature_ratio(M_top, M_bot, V, L, curvature)
    limit = min(34.0 + 12.0 * ratio, 40.0)
    S = Slenderness(axis, k, lu, r, klu_r, ratio, note, limit, klu_r > limit)
    M2 = max(abs(M_top), abs(M_bot))
    S.M2 = M2
    S.Mc = M2
    if not S.slender:
        return S
    S.M2min = Pu * (15.0 + 0.03 * depth)
    E = Ec(sec.fc)
    if EI_method == "b":
        Ise = sum(br.area * (br.y if axis == "x" else br.x) ** 2 for br in sec.bars)
        S.EIeff = (0.2 * E * Ig + ES * Ise) / (1.0 + beta_dns)
    else:
        S.EIeff = 0.4 * E * Ig / (1.0 + beta_dns)
    S.Pc = math.pi ** 2 * S.EIeff / (k * lu) ** 2
    Cm = 1.0 if transverse_load else 0.6 - 0.4 * ratio
    M2d = M2
    if M2 < S.M2min:
        M2d = S.M2min
        Cm = 1.0
        S.notes.append("M2 < M2,min → ใช้ M2,min และ Cm = 1.0 (§6.6.4.5.4)")
    S.Cm = Cm
    if Pu >= 0.75 * S.Pc:
        S.stable = False
        S.delta = math.inf
        S.Mc = math.inf
        S.notes.append("Pu ≥ 0.75Pc → เสาไม่เสถียร ต้องเพิ่มหน้าตัด")
        return S
    S.delta = max(1.0, Cm / (1.0 - Pu / (0.75 * S.Pc)))
    S.Mc = S.delta * M2d
    S.ok_14 = S.Mc <= 1.4 * M2d + 1e-9
    if not S.ok_14:
        S.notes.append("โมเมนต์ลำดับสองเกิน 1.4 เท่าของลำดับหนึ่ง (§6.2.6)")
    return S


# ---------------------------------------------------------------- นำเข้าแรงจาก STAAD.Pro
# ชื่อแกนแบบ STAAD.Pro (หน้าต่าง Prismatic): ZD แนวนอน = b (แกน x ภายใน ↔ local z),
# YD แนวตั้ง = h (แกน y ภายใน ↔ local y) → Mx ภายใน = Mz, My = My, Vuy = Fy, Vux = Fz
STAAD_AXIS = {"x": "z", "y": "y"}


def from_staad(fx_s, fy_s, fz_s, my_s, mz_s, my_e, mz_e, flip_axial=False):
    """แปลง member end forces ของ STAAD (แกน local, ค่าที่ start และ end node) เป็นแรงของสกิล

    YD/ZD ของหน้าตัดกับแรงในตาราง member end forces อยู่ในแกน local ชุดเดียวกัน จึงจับคู่ตรง
    ไม่ขึ้นกับ beta angle: Mz (ดัดรอบ local z ใช้ความลึก YD = h) → Mx ภายใน, Fy → Vuy;
    My (ใช้ความลึก ZD = b) → My, Fz → Vux  (beta มีผลเฉพาะการจับคู่ทิศการเซของชั้น — incoming/sway.py)
    P = Fx ที่ start node (ใน member end forces ของ STAAD ค่าบวกที่ start = แรงอัด) —
    flip_axial กลับเครื่องหมายถ้าข้อมูลมาจากแหล่งที่ใช้ convention ต่างกัน
    โมเมนต์ใช้ขนาด (หน้าตัดเหล็กสมมาตร) ทิศการดัดตัดสินภายหลังจากสมดุลแรงเฉือน
    คืน dict: Pu, Mxt, Mxb, Myt, Myb, Vuy, Vux (หน่วยเดียวกับที่ป้อน)
    """
    return {"Pu": -fx_s if flip_axial else fx_s,
            "Mxt": abs(mz_e), "Mxb": abs(mz_s), "Myt": abs(my_e), "Myb": abs(my_s),
            "Vuy": abs(fy_s), "Vux": abs(fz_s)}


# หน่วยที่ STAAD แสดงในหัวตาราง → ตัวคูณเป็น N และ N·mm
STAAD_FORCE_UNITS = {"kN": 1e3, "kg": 9.80665, "kgf": 9.80665, "ton": 9806.65, "MTon": 9806.65,
                     "N": 1.0, "kip": 4448.222}
STAAD_MOMENT_UNITS = {"kN-m": 1e6, "kg-m": 9806.65, "kgf-m": 9806.65, "ton-m": 9.80665e6,
                      "MTon-m": 9.80665e6, "N-m": 1e3, "N-mm": 1.0, "kip-ft": 1.3558179e6}


def _num(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def parse_staad_end_forces(text):
    """แยกตาราง Beam End Force ที่คัดลอกจาก STAAD (Ctrl+C แล้ววาง)

    แต่ละแถว: Beam, L/C, Node, Axial Force, Shear-Y, Shear-Z, Torsion, Moment-Y, Moment-Z
    (L/C อาจมีชื่อต่อท้ายได้) — แถวหัวตารางถูกข้าม แต่ถ้ามีหน่วย (เช่น kg, kN-m) จะอ่านไว้
    คืน (rows, force_unit หรือ None, moment_unit หรือ None)
    rows: list ของ dict beam, lc, node, fx, fy, fz, mx, my, mz (หน่วยตามตาราง)
    """
    rows, fu, mu = [], None, None
    flo = {k.lower(): k for k in STAAD_FORCE_UNITS}
    mlo = {k.lower(): k for k in STAAD_MOMENT_UNITS}
    for line in str(text).splitlines():
        tok = [t for t in re.split(r"\t|\s{2,}|\s(?=-?\d)", line.strip()) if t.strip()]
        tok = [t.strip() for t in tok]
        if not tok:
            continue
        nums = [_num(t) for t in tok]
        if len(tok) >= 9 and all(v is not None for v in nums[-7:]) and nums[0] is not None:
            rows.append(dict(beam=str(tok[0]).split(".")[0], lc=" ".join(tok[1:-7]),
                             node=str(tok[-7]).split(".")[0], fx=nums[-6], fy=nums[-5], fz=nums[-4],
                             mx=nums[-3], my=nums[-2], mz=nums[-1]))
            continue
        for t in line.split():                      # แถวหัวตาราง: เก็บหน่วยตัวแรกที่เจอ
            t = t.strip().lower()
            if fu is None and t in flo:
                fu = flo[t]
            elif mu is None and t in mlo:
                mu = mlo[t]
    return rows, fu, mu


def guess_start_node(rows):
    """เดา start node ของ member: ที่ start node ของ STAAD Fx บวก = อัด ส่วน end node กลับเครื่องหมาย
    เสาที่รับแรงอัดเป็นหลักจึงมี Fx > 0 ที่ start node เกือบทุก L/C → เลือก node ที่ Fx > 0 บ่อยที่สุด
    คืน (node, มั่นใจหรือไม่) — ไม่มั่นใจเมื่อคะแนนเท่ากัน (ให้ผู้ใช้เลือกเอง)
    """
    score = {}
    for r in rows:
        score[r["node"]] = score.get(r["node"], 0) + (1 if r["fx"] > 0 else -1)
    if not score:
        return None, False
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    sure = len(ranked) == 2 and ranked[0][1] > ranked[1][1]
    return ranked[0][0], sure


def pair_staad_rows(rows, start_node, flip_axial=False):
    """จับคู่แถว start/end ของแต่ละ L/C (member เดียว) แล้วแปลงด้วย from_staad
    คืน (list ของ (lc, forces), ข้อความผิดพลาด) — L/C ที่ไม่มีครบ 2 node ถูกตัดออกพร้อมแจ้ง
    """
    by_lc, order, errs = {}, [], []
    for r in rows:
        if r["lc"] not in by_lc:
            by_lc[r["lc"]] = {}
            order.append(r["lc"])
        by_lc[r["lc"]][r["node"]] = r
    out = []
    for lc in order:
        d = by_lc[lc]
        if start_node not in d or len(d) != 2:
            errs.append(f"L/C {lc}: ต้องมี 2 แถว (start node {start_node} และ end node) — พบ node "
                        f"{', '.join(d)}")
            continue
        s = d[start_node]
        e = next(v for k, v in d.items() if k != start_node)
        out.append((lc, from_staad(s["fx"], s["fy"], s["fz"], s["my"], s["mz"], e["my"], e["mz"],
                                   flip_axial)))
    return out, errs


# คู่หน่วยที่ STAAD ใช้บ่อย (แรง, โมเมนต์) — ใช้เดาหน่วยเมื่อคัดลอกมาไม่มีหัวตาราง
STAAD_UNIT_PAIRS = [("kN", "kN-m"), ("kg", "kN-m"), ("kg", "kg-m"), ("ton", "ton-m"), ("ton", "kN-m"),
                    ("kN", "kg-m"), ("N", "N-m"), ("N", "N-mm"), ("N", "kN-m")]


def staad_units_from_statics(pairs, L):
    """หาคู่หน่วย (แรง, โมเมนต์) ที่ทำให้สมดุลของเสาเป็นจริงทุก L/C: |F|·L ≈ |Mt| ± |Mb|

    pairs: ผลจาก pair_staad_rows (ค่าดิบตามตาราง), L: ความยาวชิ้นส่วน (mm)
    สมดุลบอกได้แค่ "อัตราส่วน" หน่วยแรงต่อหน่วยโมเมนต์ (เช่น kg กับ kN-m ไม่เข้ากันกับ kN กับ kN-m)
    แต่แยก kN/kN-m กับ kg/kg-m ไม่ได้ → ถ้าได้หลายคู่ ผู้ใช้ต้องเลือกเอง
    คืน list ของคู่หน่วยที่ผ่าน (ว่าง = ไม่มีคู่ไหนผ่าน: ตรวจ L หรือมีแรงกระทำกลางเสา)
    """
    return [(fu, mu) for fu, mu in STAAD_UNIT_PAIRS if not staad_statics_errors(pairs, fu, mu, L)]


def staad_statics_errors(pairs, fu, mu, L):
    """L/C ที่สมดุล |F|·L ≈ |Mt| ± |Mb| ไม่เป็นจริงเมื่อใช้หน่วย (fu, mu) และความยาว L (mm)
    ข้ามแกนที่โมเมนต์ < 5% ของค่าสูงสุดในชุดข้อมูล — คืน list ของ (L/C, แกน, |F| kN, (|Mt|+|Mb|)/L kN)
    """
    kf, km = STAAD_FORCE_UNITS[fu], STAAD_MOMENT_UNITS[mu]
    axes = [(lc, ax, Mt, Mb, V) for lc, f in pairs
            for ax, Mt, Mb, V in (("Mz/Fy", f["Mxt"], f["Mxb"], f["Vuy"]), ("My/Fz", f["Myt"], f["Myb"], f["Vux"]))]
    big = max((Mt + Mb for *_, Mt, Mb, V in axes), default=0.0)
    if big <= 0:
        return []
    bad = []
    for lc, ax, Mt, Mb, V in axes:
            if Mt + Mb >= 0.05 * big:          # ข้ามแกนที่โมเมนต์เล็กมากเทียบกับข้อมูลชุดนี้ (เศษตัวเลข)
                try:
                    curvature_ratio(Mt * km, Mb * km, V=V * kf, L=L)
                except ValueError:
                    bad.append((lc, ax, V * kf / 1e3, (Mt + Mb) * km / L / 1e3))
    return bad


def staad_member_length(pairs, fu, mu, tol=CURV_TOL):
    """ความยาวเสา (mm) ที่ทำให้ |F|·L = |Mt| + |Mb| (โค้งสองทาง ซึ่งเป็นกรณีปกติของเสาในโครงข้อแข็ง)
    ตรงกันทุก L/C เมื่อใช้หน่วย (fu, mu) — ใช้แนะนำผู้ใช้เมื่อ L หรือหน่วยไม่เข้ากับข้อมูล
    แต่ละ L/C ใช้แกนที่โมเมนต์ใหญ่กว่า คืน L (mm) หรือ None ถ้าไม่ตรงกันทุก L/C
    """
    kf, km = STAAD_FORCE_UNITS[fu], STAAD_MOMENT_UNITS[mu]
    Ls = []
    for _, f in pairs:
        Mt, Mb, V = max(((f["Mxt"], f["Mxb"], f["Vuy"]), (f["Myt"], f["Myb"], f["Vux"])),
                        key=lambda t: t[0] + t[1])
        if V > 0 and Mt + Mb > 0:
            Ls.append((Mt + Mb) * km / (V * kf))
    if not Ls:
        return None
    Lm = sorted(Ls)[len(Ls) // 2]
    return Lm if all(abs(x - Lm) <= tol * Lm for x in Ls) else None


def staad_suggest(pairs, L_range=(1500.0, 15000.0)):
    """คู่หน่วยที่ทำให้เสามีความยาวสมจริง (โค้งสองทาง) → list ของ (fu, mu, L_mm) ใช้เป็นคำแนะนำ"""
    out = []
    for fu, mu in STAAD_UNIT_PAIRS:
        Ls = staad_member_length(pairs, fu, mu)
        if Ls and L_range[0] <= Ls <= L_range[1]:
            out.append((fu, mu, Ls))
    return out


def check_axial_sign(rows):
    """ตรวจเครื่องหมายแรงตามแกนจาก combo ที่มีแต่แรงแนวดิ่ง (D, L): ต้องเป็นแรงอัด (Pu > 0)

    rows: list ของ (ชื่อ combo, Pu, เป็น combo แนวดิ่งล้วนหรือไม่)
    คืน (ผ่านหรือไม่, ข้อความ) — ไม่มี combo แนวดิ่งให้ตรวจ → ผ่านแต่เตือน
    """
    grav = [(n, P) for n, P, g in rows if g]
    if not grav:
        return True, ["ไม่มี combo แนวดิ่งล้วน (D, L) ให้ตรวจเครื่องหมาย P — ทำเครื่องหมายอย่างน้อย 1 combo"]
    bad = [n for n, P in grav if P <= 0]
    if bad:
        return False, [f"combo แนวดิ่งล้วน {', '.join(map(str, bad))} ได้ P ≤ 0 (แรงดึง) — เครื่องหมาย P "
                       "น่าจะกลับด้าน (เช่น อ่าน Fx จาก end node แทน start node) ตรวจก่อนออกแบบ"]
    return True, []


# ---------------------------------------------------------------- แรงเฉือน
def sqrt_fc(fc):
    return min(math.sqrt(fc), 8.3)     # §22.5.3.1


def av_min_per_s(fc, bw, fyt):
    """Table 10.6.2.2"""
    return max(0.062 * math.sqrt(fc) * bw / fyt, 0.35 * bw / fyt)


@dataclass
class ShearResult:
    direction: str
    Vu: float
    Nu: float
    bw: float
    d: float
    rho_w: float
    Av: float
    s: float
    Av_min_s: float
    axial_term: float
    Vc: float
    vc_eq: str
    Vc_max: float
    Vs: float
    phiVn: float
    section_limit: float
    s_max: float
    min_required: bool
    notes: list = field(default_factory=list)

    @property
    def strength_ok(self):
        return self.phiVn >= self.Vu - 1e-9

    @property
    def section_ok(self):
        return self.Vu <= self.section_limit + 1e-9

    @property
    def av_min_ok(self):
        return (not self.min_required) or (self.s > 0 and self.Av / self.s >= self.Av_min_s - 1e-12)

    @property
    def spacing_ok(self):
        """§10.7.6.5.2 ใช้เมื่อต้องมีเหล็กรับแรงเฉือน (Vu > 0.5φVc) — ไม่เช่นนั้นระยะปลอกคุมด้วย §25.7.2.1"""
        if not self.min_required:
            return True
        return self.s == 0 or self.s <= self.s_max + 1e-9

    @property
    def ratio(self):
        return abs(self.Vu) / self.phiVn if self.phiVn > 0 else math.inf

    @property
    def ok(self):
        return self.strength_ok and self.section_ok and self.av_min_ok and self.spacing_ok


def shear_check(sec, direction, Vu, Nu, s, legs):
    """แรงเฉือนทิศ direction ("y": แรงขนานด้าน h, bw = b / "x": แรงขนานด้าน b, bw = h)

    Nu > 0 = แรงอัด (เกิดพร้อม Vu)
    Table 22.5.5.1: (a) [0.17λ√f′c + Nu/(6Ag)]bw·d เมื่อ Av ≥ Av,min
                    (c) [0.66λsλρw^(1/3)√f′c + Nu/(6Ag)]bw·d เมื่อ Av < Av,min
    Nu/(6Ag) ≤ 0.05f′c, Vc ≤ 0.42λ√f′c·bw·d, Vc ≥ 0
    §10.6.2.1 ต้องมีปลอกขั้นต่ำเมื่อ Vu > 0.5φVc
    """
    if direction == "y":
        bw = sec.b
        d = sec.h / 2 + max(-br.y for br in sec.bars)
        tension = [br for br in sec.bars if br.y < -1e-6]
        mid = [br for br in sec.bars if abs(br.y) <= 1e-6]
    else:
        bw = sec.h
        d = sec.b / 2 + max(-br.x for br in sec.bars)
        tension = [br for br in sec.bars if br.x < -1e-6]
        mid = [br for br in sec.bars if abs(br.x) <= 1e-6]
    As = sum(br.area for br in tension) + 0.5 * sum(br.area for br in mid)
    rho_w = As / (bw * d)
    rf, lam = sqrt_fc(sec.fc), sec.lam
    axial = min(Nu / (6.0 * sec.Ag), 0.05 * sec.fc)
    Av = legs * bar_area(sec.ds) if s > 0 else 0.0
    Avmin_s = av_min_per_s(sec.fc, bw, sec.fyt)
    Vc_max = 0.42 * lam * rf * bw * d
    if s > 0 and Av / s >= Avmin_s - 1e-12:
        eq, Vc = "a", (0.17 * lam * rf + axial) * bw * d
    else:
        ls = min(1.0, math.sqrt(2.0 / (1.0 + d / 250.0)))
        eq, Vc = "c", (0.66 * ls * lam * rho_w ** (1 / 3) * rf + axial) * bw * d
    Vc = max(0.0, min(Vc, Vc_max))
    Vs = Av * sec.fyt * d / s if s > 0 else 0.0
    Vs_req = max(0.0, abs(Vu) / PHI_V - Vc)
    s_max = min(d / 2, 600.0) if Vs_req <= 0.33 * rf * bw * d else min(d / 4, 300.0)
    return ShearResult(direction, abs(Vu), Nu, bw, d, rho_w, Av, s, Avmin_s, axial, Vc, eq,
                       Vc_max, Vs, PHI_V * (Vc + Vs), PHI_V * (Vc + 0.66 * rf * bw * d), s_max,
                       abs(Vu) > 0.5 * PHI_V * Vc)


def omf_shear(sec, direction, Pu_top, Pu_bot, lu, Vu_analysis, Vu_omega=None):
    """§18.3.3 เสา OMF ใน SDC B ที่ l_u ≤ 5c1

    φVn ≥ น้อยกว่าของ (a) แรงเฉือนจาก **Mn** (ไม่คูณ φ) ที่ปลายเสาภายใต้ Pu และ
    (b) แรงเฉือนจาก load combination ที่คูณแรงแผ่นดินไหวด้วย Ω0
    คืน (Vu ออกแบบ, รายละเอียด) — ถ้าไม่มี (b) ใช้ (a) และหมายเหตุ
    """
    c1 = sec.h if direction == "y" else sec.b
    if lu > 5 * c1:
        return abs(Vu_analysis), {"applies": False, "note": f"l_u = {lu:.0f} > 5c1 = {5 * c1:.0f} mm"}
    Mux, Muy = (1.0, 0.0) if direction == "y" else (0.0, 1.0)
    Mnt = capacity_at(sec, Pu_top, Mux, Muy, factored=False).phiMcap
    Mnb = capacity_at(sec, Pu_bot, Mux, Muy, factored=False).phiMcap
    Vu1 = (Mnt + Mnb) / lu
    if Vu_omega is None:
        Vuc, note = Vu1, "ไม่มี load case ที่คูณ Ω0 → ใช้ (a)"
    else:
        Vuc, note = min(Vu1, abs(Vu_omega)), "min[(a), (b)]"
    return max(Vuc, abs(Vu_analysis)), {"applies": True, "Mnt": Mnt, "Mnb": Mnb, "Vu1": Vu1,
                                         "Vu_omega": Vu_omega, "note": note}


def biaxial_shear(rx, ry):
    """§22.5.1.11: ถ้าทั้งสองอัตราส่วน > 0.5 ต้องได้ผลรวม ≤ 1.5"""
    if rx > 0.5 and ry > 0.5:
        return rx + ry <= 1.5, rx + ry
    return True, rx + ry


# ---------------------------------------------------------------- รายละเอียดเหล็ก
def longitudinal_checks(sec):
    """§10.6.1.1 (0.01–0.08Ag), §10.7.3.1 (≥ 4 เส้น), §25.2.3 ช่องว่าง ≥ max(40, 1.5db, 4/3 dagg)"""
    out = []
    out.append(("ρg ≥ 0.01", sec.rho >= 0.01 - 1e-12, f"{sec.rho * 100:.2f}%", "10.6.1.1"))
    out.append(("ρg ≤ 0.08", sec.rho <= 0.08 + 1e-12, f"{sec.rho * 100:.2f}%", "10.6.1.1"))
    out.append(("จำนวนเหล็ก ≥ 4", len(sec.bars) >= 4, f"{len(sec.bars)} เส้น", "10.7.3.1"))
    db = max(br.db for br in sec.bars)
    need = max(40.0, 1.5 * db, 4.0 / 3.0 * sec.dagg)
    clear = min(math.hypot(p.x - q.x, p.y - q.y) - (p.db + q.db) / 2
                for i, p in enumerate(sec.bars) for q in sec.bars[i + 1:])
    out.append(("ช่องว่างเหล็กยืน", clear >= need - 1e-6, f"{clear:.0f} ≥ {need:.0f} mm", "25.2.3"))
    return out


def tie_checks(sec, s, legs_x, legs_y, cover_min=40.0, bundled=False):
    """§25.7.2.1 ระยะปลอก, §25.7.2.2 ขนาดปลอก, §25.7.2.3 การยึดเหล็ก, Table 20.5.1.3.1 cover"""
    out = []
    db = max(br.db for br in sec.bars)
    smax = min(16 * db, 48 * sec.ds, min(sec.b, sec.h))
    out.append(("ระยะปลอก s ≤ min(16db, 48dbt, ด้านแคบ)", s <= smax + 1e-6,
                f"{s:.0f} ≤ {smax:.0f} mm", "25.7.2.1"))
    need = 12.7 if (db > 32.3 or bundled) else 9.5
    out.append(("ขนาดปลอก", sec.ds >= need - 1e-6,
                f"{sec.ds:g} ≥ {need} mm ({'No.13' if need > 10 else 'No.10'})", "25.7.2.2"))
    # เหล็กต่อด้าน (รวมมุม)
    xs = sorted({round(br.x, 3) for br in sec.bars})
    ys = sorted({round(br.y, 3) for br in sec.bars})
    nx = sum(1 for br in sec.bars if abs(br.y - ys[-1]) < 1e-3)
    ny = sum(1 for br in sec.bars if abs(br.x - xs[-1]) < 1e-3)
    status, val = None, ""
    if legs_x > 2 or legs_y > 2:
        status, val = None, "มี crosstie → ตรวจตามแบบ"
    else:
        ok = True
        msgs = []
        for n, L in ((nx, sec.b), (ny, sec.h)):
            if n > 3:
                ok = False
                msgs.append(f"{n} เส้น/ด้าน ต้องมี crosstie")
            elif n == 3:
                gap = (L - 2 * (sec.cover + sec.ds) - db) / 2 - db
                ok &= gap <= 150 + 1e-6
                msgs.append(f"ช่องว่างถึงเหล็กมุม {gap:.0f} ≤ 150 mm")
        status, val = ok, "; ".join(msgs) or "มีเฉพาะเหล็กมุม"
    out.append(("เหล็กยืนทุกเส้นถูกยึดด้านข้าง", status, val, "25.7.2.3"))
    out.append(("ระยะหุ้มถึงปลอก", sec.cover >= cover_min - 1e-6,
                f"{sec.cover:.1f} ≥ {cover_min:.0f} mm", "Table 20.5.1.3.1"))
    return out
