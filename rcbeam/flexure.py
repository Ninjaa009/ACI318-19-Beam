"""แรงดัดคานสี่เหลี่ยม singly / doubly ตาม ACI 318M-19 (หน่วย MPa–mm–N)

ทุกระยะ y วัดลงจากผิวรับแรงอัด แรงในเหล็ก: บวก = อัด, ลบ = ดึง
"""
from dataclasses import dataclass, field
import math

ES = 200_000.0   # MPa §20.2.2.2
ECU = 0.003      # §22.2.2.1
PHI_TC = 0.90


def bar_area(db):
    return math.pi * db ** 2 / 4.0


def beta1(fc):
    """§22.2.2.4.3"""
    if fc <= 28.0:
        return 0.85
    return max(0.65, 0.85 - 0.05 * (fc - 28.0) / 7.0)


def eps_ty(fy, grade420_exception=False):
    """εty = fy/Es (§21.2.2.1) หรือ 0.002 สำหรับ Grade 420 (ข้อยกเว้น)"""
    if grade420_exception:
        if abs(fy - 420.0) > 0.5:
            raise ValueError("ข้อยกเว้น εty = 0.002 ใช้ได้เฉพาะ fy = 420 MPa")
        return 0.002
    return fy / ES


def eps_t_limit(ety):
    """§9.3.3.1: εt ≥ εty + 0.003"""
    return ety + 0.003


def c_max(dt, ety):
    return ECU * dt / (ECU + eps_t_limit(ety))


def phi_flexure(et, ety):
    """Table 21.2.2 (ปลอกธรรมดา)"""
    if et >= ety + 0.003:
        return 0.90
    if et <= ety:
        return 0.65
    return 0.65 + 0.25 * (et - ety) / 0.003


def as_min(fc, fy, bw, d):
    """§9.6.1.2 (fy ในสูตรไม่เกิน 550 MPa)"""
    fy_ = min(fy, 550.0)
    return max(0.25 * math.sqrt(fc) / fy_, 1.4 / fy_) * bw * d


def bars_per_layer(b, cover, ds, db, dagg=20.0):
    """จำนวนเหล็กสูงสุดต่อชั้นตามระยะช่องว่าง §25.2.1"""
    s_clear = max(25.0, db, 4.0 / 3.0 * dagg)
    avail = b - 2.0 * (cover + ds)
    return max(1, int(math.floor((avail + s_clear) / (db + s_clear) + 1e-9)))


@dataclass
class Layer:
    n: int
    db: float
    y: float            # ระยะจากผิวรับแรงอัด (mm)
    role: str           # "tension" | "compression"

    @property
    def area(self):
        return self.n * bar_area(self.db)


def tension_layers(h, cover, ds, db, counts, clear_v=25.0):
    """ชั้นเหล็กดึง: ชั้นแรกอยู่นอกสุด ช่องว่างระหว่างชั้น ≥ 25 mm (§25.2.2)"""
    layers, y = [], h - cover - ds - db / 2.0
    for n in counts:
        if n > 0:
            layers.append(Layer(n, db, y, "tension"))
        y -= db + clear_v
    return layers


def compression_layer(cover, ds, n, db):
    return Layer(n, db, cover + ds + db / 2.0, "compression") if n > 0 else None


def split_layers(n, n_max):
    counts = []
    while n > 0:
        counts.append(min(n, n_max))
        n -= n_max
    return counts


@dataclass
class SteelResult:
    layer: Layer
    eps: float
    fs: float
    force: float        # N (+ อัด)
    in_block: bool


@dataclass
class FlexureResult:
    b: float
    h: float
    fc: float
    fy: float
    ety: float
    c: float
    a: float
    beta1: float
    Cc: float
    steel: list
    Mn: float
    phi: float
    phiMn: float
    d: float
    dt: float
    et: float
    et_limit: float
    cmax: float
    As: float
    As_comp: float
    As_min: float

    @property
    def strain_ok(self):
        return self.et >= self.et_limit - 1e-12

    @property
    def as_min_ok(self):
        return self.As >= self.As_min - 1e-9


def _forces(c, b, h, fc, fy, layers):
    b1 = beta1(fc)
    a = min(b1 * c, h)
    Cc = 0.85 * fc * b * a
    steel = []
    for L in layers:
        eps = ECU * (c - L.y) / c
        fs = max(-fy, min(fy, ES * eps))
        in_block = fs > 0 and L.y <= a
        # เหล็กอัดใน stress block หักคอนกรีตที่ถูกแทนที่, ถ้า a < d′ < c ไม่หัก
        F = L.area * (fs - 0.85 * fc) if in_block else L.area * fs
        steel.append(SteelResult(L, eps, fs, F, in_block))
    return a, Cc, steel


def analyze(b, h, fc, fy, layers, ety=None):
    """หาค่า c จาก ΣF(c) = 0 ด้วย bisection แล้วคำนวณ Mn, εt, φ"""
    if ety is None:
        ety = eps_ty(fy)
    tens = [L for L in layers if L.role == "tension"]
    if not tens:
        raise ValueError("ต้องมีเหล็กรับแรงดึงอย่างน้อยหนึ่งชั้น")

    def sumF(c):
        _, Cc, st = _forces(c, b, h, fc, fy, layers)
        return Cc + sum(s.force for s in st)

    lo, hi = 1e-6, 10.0 * h
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if sumF(mid) > 0:
            hi = mid
        else:
            lo = mid
    c = 0.5 * (lo + hi)
    a, Cc, steel = _forces(c, b, h, fc, fy, layers)
    Mn = -(Cc * a / 2.0 + sum(s.force * s.layer.y for s in steel))

    As_t = sum(L.area for L in tens)
    d = sum(L.area * L.y for L in tens) / As_t
    dt = max(L.y for L in tens)
    et = ECU * (dt - c) / c
    phi = phi_flexure(et, ety)
    return FlexureResult(
        b=b, h=h, fc=fc, fy=fy, ety=ety, c=c, a=a, beta1=beta1(fc), Cc=Cc,
        steel=steel, Mn=Mn, phi=phi, phiMn=phi * Mn, d=d, dt=dt, et=et,
        et_limit=eps_t_limit(ety), cmax=c_max(dt, ety), As=As_t,
        As_comp=sum(L.area for L in layers if L.role == "compression"),
        As_min=as_min(fc, fy, b, d),
    )


@dataclass
class FlexureDesign:
    kind: str                       # "singly" | "doubly" | "fail"
    n_t: int
    db: float
    counts: list
    n_c: int
    db_c: float
    As_req: float
    Asc_req: float
    result: FlexureResult = None
    notes: list = field(default_factory=list)


def _singly_As(Mu, fc, fy, b, d, phi=PHI_TC):
    """a = d − √(d² − 2Mu/(φ·0.85f′c·b)), As = 0.85f′c·b·a/fy (อนุมานจากสมดุล)"""
    disc = d ** 2 - 2.0 * Mu / (phi * 0.85 * fc * b)
    if disc < 0:
        return None
    a = d - math.sqrt(disc)
    return 0.85 * fc * b * a / fy


def design_flexure(b, h, fc, fy, Mu, cover, ds, db, db_c, dagg=20.0, ety=None,
                   max_iter=40):
    """ออกแบบ: ลอง singly ก่อน ถ้าไม่ผ่านใช้ doubly (Mu เป็นค่าบวก N·mm)"""
    if ety is None:
        ety = eps_ty(fy)
    Mu = abs(Mu)
    Ab, Abc = bar_area(db), bar_area(db_c)
    n_max = bars_per_layer(b, cover, ds, db, dagg)
    notes = []

    # --- singly ---
    d = h - cover - ds - db / 2.0
    n_t, As_req = None, None
    for _ in range(max_iter):
        As_req = _singly_As(Mu, fc, fy, b, d)
        if As_req is None:
            break
        As_req = max(As_req, as_min(fc, fy, b, d))
        n_new = max(2, math.ceil(As_req / Ab - 1e-9))
        layers = tension_layers(h, cover, ds, db, split_layers(n_new, n_max))
        d_new = sum(L.area * L.y for L in layers) / sum(L.area for L in layers)
        if n_new == n_t and abs(d_new - d) < 1e-6:
            break
        n_t, d = n_new, d_new
    if As_req is not None:
        for _ in range(max_iter):
            counts = split_layers(n_t, n_max)
            layers = tension_layers(h, cover, ds, db, counts)
            r = analyze(b, h, fc, fy, layers, ety)
            if not r.strain_ok:
                break
            if r.phiMn >= Mu:
                return FlexureDesign("singly", n_t, db, counts, 0, db_c,
                                     As_req, 0.0, r, notes)
            n_t += 1
        notes.append("singly ไม่ผ่าน strain limit (§9.3.3.1) → ใช้ doubly")
    else:
        notes.append("singly: หน้าตัดเล็กเกินไป (d² < 2Mu/φ0.85f′cb) → ใช้ doubly")

    # --- doubly: ประมาณค่าเริ่มต้นที่ c = cmax แล้ววนปรับให้สอดคล้องกับเหล็กจริง ---
    comp = compression_layer(cover, ds, 2, db_c)
    dp = comp.y
    b1 = beta1(fc)
    n_t = n_t or 2
    n_c = 2
    As_req = Asc_req = 0.0
    for _ in range(max_iter):
        layers = tension_layers(h, cover, ds, db, split_layers(n_t, n_max))
        As_t = sum(L.area for L in layers)
        d = sum(L.area * L.y for L in layers) / As_t
        dt = max(L.y for L in layers)
        c = c_max(dt, ety)
        a = b1 * c
        Cc = 0.85 * fc * b * a
        Mn1 = Cc * (d - a / 2.0)
        Mn2 = Mu / PHI_TC - Mn1
        fsp = max(-fy, min(fy, ES * ECU * (c - dp) / c))
        coeff = fsp - 0.85 * fc if dp <= a else fsp
        if Mn2 <= 0 or coeff <= 0:
            Asc_req = 0.0
        else:
            Asc_req = Mn2 / (coeff * (d - dp))
        As_req = (Cc + Asc_req * coeff) / fy
        nt_new = max(2, math.ceil(As_req / Ab - 1e-9))
        nc_new = max(2, math.ceil(Asc_req / Abc - 1e-9))
        if nt_new == n_t and nc_new == n_c:
            break
        n_t, n_c = nt_new, nc_new

    nc_max = bars_per_layer(b, cover, ds, db_c, dagg)
    if n_c > nc_max:
        notes.append(f"ต้องการเหล็กอัด {n_c} เส้น เกิน {nc_max} เส้นต่อชั้น "
                     "→ ควรเพิ่มขนาดหน้าตัดหรือขนาดเหล็กอัด")
        n_c = nc_max
    for _ in range(max_iter):
        counts = split_layers(n_t, n_max)
        layers = tension_layers(h, cover, ds, db, counts)
        layers.append(compression_layer(cover, ds, n_c, db_c))
        r = analyze(b, h, fc, fy, layers, ety)
        if r.strain_ok and r.phiMn >= Mu:
            return FlexureDesign("doubly", n_t, db, counts, n_c, db_c,
                                 As_req, Asc_req, r, notes)
        if not r.strain_ok:
            if n_c >= nc_max:
                notes.append(f"เหล็กอัดเต็มชั้น ({nc_max} เส้น) แต่ยังไม่ผ่าน strain "
                             "limit → ควรเพิ่มขนาดหน้าตัด")
                break
            n_c += 1
        else:
            nxt = tension_layers(h, cover, ds, db, split_layers(n_t + 1, n_max))
            if nxt[-1].y - db / 2 - (dp + db_c / 2) < 25.0:
                notes.append("ไม่มีที่วางเหล็กดึงเพิ่ม (ชนเหล็กอัด) → ควรเพิ่มขนาดหน้าตัด")
                break
            n_t += 1
    return FlexureDesign("fail", n_t, db, counts, n_c, db_c,
                         As_req, Asc_req, r, notes)


def crack_spacing(fy, cc):
    """Table 24.3.2, fs = 2fy/3 (§24.3.2.1)"""
    fs = 2.0 * fy / 3.0
    return min(380.0 * (280.0 / fs) - 2.5 * cc, 300.0 * (280.0 / fs))


def bar_spacing(b, cover, ds, n, db):
    """ระยะศูนย์กลางเหล็กในชั้นนอกสุด"""
    if n < 2:
        return 0.0
    return (b - 2.0 * (cover + ds) - db) / (n - 1)
