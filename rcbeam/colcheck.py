"""ตรวจเสาครบทุก load combination โดยใช้ solver ของ skill rc-column-aci318m19

หน่วยภายใน MPa–mm–N เหมือน solver — หน้าแอปเป็นผู้แปลงหน่วยผู้ใช้
"""
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent / "skills" / "rc-column-aci318m19" / "scripts"
if str(_SKILL) not in sys.path:
    sys.path.insert(0, str(_SKILL))
import column as C  # noqa: E402

PASS, FAIL, NOT_CHECKED, NA = "ผ่าน", "ไม่ผ่าน", "ยังไม่ตรวจ", "ไม่มีข้อมูล"
NONSWAY_NOTE = ("สมมติเป็นโครง non-sway — ผู้ออกแบบต้องยืนยันเอง (Q ≤ 0.05 ตาม ACI 6.6.4.3) · "
                "ระบบตรวจ sway: incoming")


@dataclass
class ColumnInput:
    b: float
    h: float
    fc: float
    fy: float
    fyt: float
    cover: float
    db: float
    nx: int
    ny: int
    ds: float
    s: float
    legs_x: int = 2
    legs_y: int = 2
    cover_to: str = "tie"        # "tie" | "long"
    dagg: float = 20.0
    grade420: bool = False
    lu_x: float = 3000.0         # ดัดรอบแกน x
    lu_y: float = 3000.0         # ดัดรอบแกน y
    k_x: float = 1.0
    k_y: float = 1.0
    L: float = 3000.0            # ความยาวชิ้นส่วน (c/c) ใช้ตรวจทิศการดัดจากแรงเฉือน
    beta_dns: float = 0.6
    r_method: str = "exact"
    EI_method: str = "a"
    omf: bool = False            # §18.3.3 (OMF ใน SDC B)
    cover_min: float = 40.0

    def section(self):
        bars, tie_cover = C.rect_bars(self.b, self.h, self.cover, self.ds, self.db, self.nx,
                                      self.ny, self.cover_to)
        return C.Section(self.b, self.h, self.fc, self.fy, self.fyt, bars, tie_cover, self.ds,
                         self.dagg, grade420=self.grade420)


@dataclass
class Combo:
    name: str
    Pu: float
    Mxt: float
    Mxb: float
    Myt: float
    Myb: float
    Vux: float = 0.0             # แรงเฉือนขนานแกน x (คู่กับการดัดรอบแกน y)
    Vuy: float = 0.0             # แรงเฉือนขนานแกน y (คู่กับการดัดรอบแกน x)
    curv_x: str = "auto"         # "auto" | "single" | "double"
    curv_y: str = "auto"


@dataclass
class ComboResult:
    combo: Combo
    sx: object = None
    sy: object = None
    points: list = field(default_factory=list)   # (label, Mx, My, Capacity)
    ratio: float = 0.0
    crit: tuple = None
    axial_ok: bool = True
    shear_y: object = None
    shear_x: object = None
    omf_y: dict = None
    omf_x: dict = None
    biax_ok: bool = True
    biax_sum: float = 0.0
    error: str = ""

    @property
    def shear_ratio(self):
        return max(self.shear_x.ratio, self.shear_y.ratio) if self.shear_x else 0.0


def _curv(c):
    return None if c in (None, "", "auto") else c


def check_combo(inp, sec, cb):
    R = ComboResult(cb)
    try:
        R.sx = C.slenderness(sec, "x", inp.lu_x, cb.Pu, cb.Mxt, cb.Mxb, k=inp.k_x, V=cb.Vuy,
                             L=inp.L, curvature=_curv(cb.curv_x), beta_dns=inp.beta_dns,
                             r_method=inp.r_method, EI_method=inp.EI_method)
        R.sy = C.slenderness(sec, "y", inp.lu_y, cb.Pu, cb.Myt, cb.Myb, k=inp.k_y, V=cb.Vux,
                             L=inp.L, curvature=_curv(cb.curv_y), beta_dns=inp.beta_dns,
                             r_method=inp.r_method, EI_method=inp.EI_method)
    except ValueError as e:
        R.error = str(e)
        return R
    pts = [("ปลายบน", cb.Mxt, cb.Myt), ("ปลายล่าง", cb.Mxb, cb.Myb)]
    if R.sx.slender or R.sy.slender:
        pts.append(("กลางเสา (ขยายโมเมนต์)", R.sx.Mc, R.sy.Mc))
    for label, mx, my in pts:
        if math.isinf(mx) or math.isinf(my):
            R.points.append((label, mx, my, None))
            R.ratio = math.inf
            continue
        cap = C.capacity_at(sec, cb.Pu, mx, my)
        R.points.append((label, mx, my, cap))
        R.axial_ok &= cap.ok_axial
        if cap.ratio >= R.ratio:
            R.ratio, R.crit = cap.ratio, (label, mx, my, cap)
    for direction, V, lu, attr in (("y", cb.Vuy, inp.lu_x, "y"), ("x", cb.Vux, inp.lu_y, "x")):
        Vd = abs(V)
        if inp.omf:
            Vd, info = C.omf_shear(sec, direction, cb.Pu, cb.Pu, lu, V)
            setattr(R, "omf_" + attr, info)
        legs = inp.legs_x if direction == "x" else inp.legs_y
        setattr(R, "shear_" + attr, C.shear_check(sec, direction, Vd, cb.Pu, inp.s, legs))
    R.biax_ok, R.biax_sum = C.biaxial_shear(R.shear_x.ratio, R.shear_y.ratio)
    return R


def run(inp, combos):
    sec = inp.section()
    out = {"sec": sec, "inp": inp}
    # ระบบตรวจ sway / non-sway ถูกถอดออกจากแอป (incoming) — ถือว่าเป็นโครง non-sway
    # ฟังก์ชัน classify_stories / nonsway_gate ยังอยู่ใน skill สำหรับนำกลับมาใช้
    out["results"] = [check_combo(inp, sec, cb) for cb in combos]
    good = [r for r in out["results"] if not r.error]
    out["gov"] = max(good, key=lambda r: r.ratio) if good else None
    out["gov_shear"] = max(good, key=lambda r: r.shear_ratio) if good else None
    out["long"] = C.longitudinal_checks(sec)
    out["ties"] = C.tie_checks(sec, inp.s, inp.legs_x, inp.legs_y, inp.cover_min)
    out["summary"] = summary(out)
    return out


def _st(ok):
    if ok is None:
        return NOT_CHECKED
    return PASS if ok else FAIL


SHEAR_NAME = {"y": "Fy (คู่กับ Mz)", "x": "Fz (คู่กับ My)"}     # ชื่อแบบ STAAD


def summary(out):
    rows = [("โครง sway / non-sway", NONSWAY_NOTE, NOT_CHECKED, "6.6.4.3")]
    res = [r for r in out.get("results", []) if not r.error]
    for r in out.get("results", []):
        if r.error:
            rows.append((f"Combination {r.combo.name}", r.error, FAIL, "6.2.5.1"))
    if res:
        sec = out["sec"]
        Pmax = max(r.combo.Pu for r in res)
        rows.append(("φPn,max ≥ Pu", f"{sec.phiPn_max / 1e3:,.1f} ≥ {Pmax / 1e3:,.1f} kN",
                     _st(all(r.axial_ok for r in res)), "22.4.2"))
        sl = [r for r in res if r.sx.slender or r.sy.slender]
        stable = all(r.sx.stable and r.sy.stable for r in res)
        ok14 = all(r.sx.ok_14 and r.sy.ok_14 for r in res)
        rows.append(("ความชะลูด / ขยายโมเมนต์",
                     f"ชะลูด {len(sl)}/{len(res)} combination" + ("" if stable else ", ไม่เสถียร"),
                     _st(stable and ok14), "6.2.5, 6.6.4, 6.2.6"))
        g = out["gov"]
        rows.append(("3D interaction (ratio สูงสุด)",
                     f"{g.ratio:.3f} — {g.combo.name} {g.crit[0] if g.crit else ''}",
                     _st(g.ratio <= 1.0 + 1e-9 and g.axial_ok), "22.4, 21.2.2"))
        gs = out["gov_shear"]
        for d in ("y", "x"):
            sr = getattr(gs, "shear_" + d)
            rows.append((f"แรงเฉือน {SHEAR_NAME[d]} (สูงสุด)",
                         f"Vu/φVn = {sr.ratio:.3f} — {gs.combo.name}", _st(sr.ok),
                         "22.5, 10.6.2, 10.7.6.5"))
        rows.append(("แรงเฉือนสองทิศ", f"ผลรวม {gs.biax_sum:.3f}", _st(all(r.biax_ok for r in res)),
                     "22.5.1.11"))
        omf = out["inp"].omf
        rows.append(("§18.3.3 OMF", "ใช้ (a) Mn ที่ปลายเสา" if omf else "ไม่ได้เลือก",
                     _st(True) if omf else NA, "18.3.3"))
    for name, ok, val, ref in out["long"] + out["ties"]:
        rows.append((name, val, _st(ok) if ok is not None else "ตรวจตามแบบ", ref))
    rows.append(("รอยต่อคาน-เสา, ระยะทาบ/ฝังยึด", "-", NOT_CHECKED, "Ch.15, Ch.25"))
    return rows
