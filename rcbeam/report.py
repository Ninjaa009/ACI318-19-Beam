"""สร้างรายงานคำนวณ (Markdown): สูตร → แทนค่า (MPa–mm) → ผล (kgf–m, cm²)"""
from dataclasses import dataclass

from . import units as u
from .flexure import crack_spacing, bar_spacing
from .shear import PHI_V, sqrt_fc

PASS, FAIL, NOT_CHECKED = "ผ่าน", "ไม่ผ่าน", "ยังไม่ตรวจ"

# Table 9.3.1.1: ความลึกต่ำสุด h = ℓ / ตัวหาร
SUPPORT_DIVISOR = {
    "ช่วงเดี่ยว (simply supported)": 16.0,
    "ต่อเนื่องปลายเดียว": 18.5,
    "ต่อเนื่องสองปลาย": 21.0,
    "คานยื่น (cantilever)": 8.0,
}


@dataclass
class Inputs:
    b: float          # mm
    h: float          # mm
    fc: float         # MPa
    fy: float         # MPa
    fyt: float        # MPa
    cover: float      # mm
    ds: float         # mm
    legs: int
    dagg: float       # mm
    Mu: float         # N·mm (มีเครื่องหมาย)
    Vu: float         # N
    grade420: bool = False
    span: float = 0.0             # mm, 0 = ไม่ตรวจ
    support: str = ""
    crit_at_d: bool = True
    exempt_9631: bool = False


def kgfm(nmm):
    return f"{u.nmm_to_kgfm(nmm):,.0f} kgf·m"


def kgf(n):
    return f"{u.n_to_kgf(n):,.0f} kgf"


def cm2(mm2):
    return f"{u.mm2_to_cm2(mm2):.2f} cm²"


def status(ok):
    return PASS if ok else FAIL


def detailing_checks(inp, fr, counts, db):
    """คืนรายการ (หัวข้อ, ค่า, สถานะ, อ้างอิง)"""
    rows = []
    rows.append(("As ≥ As,min", f"{cm2(fr.As)} ≥ {cm2(fr.As_min)}",
                 status(fr.as_min_ok), "§9.6.1.2"))

    s_clear_min = max(25.0, db, 4.0 / 3.0 * inp.dagg)
    n1 = counts[0] if counts else 0
    if n1 >= 2:
        sc = bar_spacing(inp.b, inp.cover, inp.ds, n1, db) - db
        rows.append(("ช่องว่างเหล็กในชั้น", f"{sc:.0f} mm ≥ {s_clear_min:.0f} mm",
                     status(sc >= s_clear_min - 1e-6), "§25.2.1"))
        s_cc = bar_spacing(inp.b, inp.cover, inp.ds, n1, db)
        cc = inp.cover + inp.ds
        smax = crack_spacing(inp.fy, cc)
        rows.append(("ระยะเหล็กควบคุมรอยร้าว",
                     f"{s_cc:.0f} mm ≤ {smax:.0f} mm (cc = {cc:.0f} mm, fs = 2fy/3)",
                     status(s_cc <= smax + 1e-6), "Table 24.3.2"))
    if len(counts) > 1:
        rows.append(("ช่องว่างระหว่างชั้นเหล็ก", "25 mm (กำหนดในแบบจำลอง)", PASS,
                     "§25.2.2"))

    if inp.span > 0 and inp.support in SUPPORT_DIVISOR:
        hmin = inp.span / SUPPORT_DIVISOR[inp.support]
        note = ""
        if abs(inp.fy - 420.0) > 0.5:
            hmin *= 0.4 + inp.fy / 700.0
            note = f" × (0.4 + fy/700) = ×{0.4 + inp.fy / 700.0:.3f}"
        rows.append(("ความลึกขั้นต่ำ (แทนการคำนวณแอ่นตัว)",
                     f"h = {inp.h:.0f} ≥ ℓ/{SUPPORT_DIVISOR[inp.support]:g}{note}"
                     f" = {hmin:.0f} mm", status(inp.h >= hmin - 1e-6),
                     "Table 9.3.1.1, §9.3.1.1.1"))
    else:
        rows.append(("ความลึกขั้นต่ำ / การแอ่นตัว", "ไม่ได้ระบุช่วงคาน",
                     NOT_CHECKED, "Table 9.3.1.1"))
    if fr.As_comp > 0:
        rows.append(("การค้ำยันเหล็กอัด", "-", NOT_CHECKED, "§9.7.6.4"))
    rows.append(("ระยะขาปลอกตามขวาง", "-", NOT_CHECKED, "Table 9.7.6.2.2"))
    rows.append(("Development / anchorage", "-", NOT_CHECKED, "Ch. 25"))
    return rows


def summary_rows(inp, fr, sr, det_rows):
    Mu = abs(inp.Mu)
    rows = [
        ("กำลังดัด φMn ≥ Mu", f"{kgfm(fr.phiMn)} ≥ {kgfm(Mu)}",
         status(fr.phiMn >= Mu - 1e-6), "§9.5.1.1(a)"),
        ("Strain limit εt ≥ εty + 0.003",
         f"{fr.et:.5f} ≥ {fr.et_limit:.5f}", status(fr.strain_ok), "§9.3.3.1"),
        ("กำลังเฉือน φVn ≥ Vu", f"{kgf(sr.phiVn)} ≥ {kgf(sr.Vu)}",
         status(sr.strength_ok), "§9.5.1.1(b)"),
        ("ขนาดหน้าตัดรับเฉือน", f"Vu ≤ {kgf(sr.section_limit)}",
         status(sr.section_ok), "§22.5.1.2"),
        ("ปลอกขั้นต่ำ Av/s ≥ Av,min/s",
         ("ไม่ต้องใช้" if not sr.min_required else
          f"{(sr.Av / sr.s if sr.s else 0):.3f} ≥ {sr.Av_min_s:.3f} mm²/mm"),
         status(sr.av_min_ok), "§9.6.3.1, Table 9.6.3.4"),
        ("ระยะปลอกตามยาว s ≤ smax",
         "-" if sr.s == 0 else f"{sr.s:.0f} ≤ {sr.s_max:.0f} mm",
         status(sr.spacing_ok), "Table 9.7.6.2.2"),
    ]
    return rows + det_rows


def _table(rows):
    out = ["| รายการ | ค่า | สถานะ | อ้างอิง |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | **{c}** | {d} |" for a, b, c, d in rows]
    return "\n".join(out)


def flexure_steps(inp, fr):
    fc, fy, b = inp.fc, inp.fy, inp.b
    L = []
    side = "ล่าง" if inp.Mu >= 0 else "บน"
    L.append(f"- Mu = {kgfm(abs(inp.Mu))} = {abs(inp.Mu) / 1e6:.2f} kN·m "
             f"→ เหล็กรับแรงดึงอยู่ด้าน**{side}**")
    L.append(f"- β1 = {fr.beta1:.3f} (§22.2.2.4.3)")
    L.append(f"- εty = {'0.002 (ข้อยกเว้น Grade 420, §21.2.2.1)' if inp.grade420 else f'fy/Es = {fy:.2f}/200000 = {fr.ety:.5f}'}")
    L.append(f"- d = {fr.d:.1f} mm (จุดศูนย์ถ่วงเหล็กดึง), dt = {fr.dt:.1f} mm "
             f"(ชั้นนอกสุด)")
    L.append(f"- cmax = 0.003·dt/(0.003 + εty + 0.003) = {fr.cmax:.1f} mm")
    L.append(f"- หาค่า c จาก ΣF(c) = 0 (§22.2.1.1, bisection): "
             f"**c = {fr.c:.1f} mm**, a = β1c = {fr.a:.1f} mm")
    L.append(f"- Cc = 0.85f′c·b·a = 0.85×{fc:.2f}×{b:.0f}×{fr.a:.1f} = "
             f"{fr.Cc / 1e3:.1f} kN")
    L.append("")
    L.append("| ชั้นเหล็ก | y (mm) | As (cm²) | εs | fs (MPa) | F (kN) | หมายเหตุ |")
    L.append("|---|---|---|---|---|---|---|")
    for s in fr.steel:
        Ly = s.layer
        note = ("อยู่ใน stress block: หัก 0.85f′c" if s.in_block else
                ("a < d′ < c: ไม่หักคอนกรีต" if s.fs > 0 else "รับแรงดึง"))
        L.append(f"| {Ly.n}-DB{Ly.db:g} ({'อัด' if Ly.role == 'compression' else 'ดึง'})"
                 f" | {Ly.y:.1f} | {Ly.area / 100:.2f} | {s.eps:+.5f} | "
                 f"{s.fs:+.1f} | {s.force / 1e3:+.1f} | {note} |")
    L.append("")
    L.append(f"- Mn = {fr.Mn / 1e6:.2f} kN·m = {kgfm(fr.Mn)}")
    L.append(f"- εt = 0.003(dt − c)/c = 0.003({fr.dt:.1f} − {fr.c:.1f})/{fr.c:.1f}"
             f" = {fr.et:.5f}")
    L.append(f"- φ = {fr.phi:.3f} (Table 21.2.2) → **φMn = {fr.phiMn / 1e6:.2f} kN·m"
             f" = {kgfm(fr.phiMn)}**")
    L.append(f"- As,min = max(0.25√f′c/fy, 1.4/fy)·bw·d = {cm2(fr.As_min)} (§9.6.1.2)")
    if not fr.strain_ok:
        L.append("- ⚠️ εt < εty + 0.003 → **Strain limit: ไม่ผ่าน** "
                 "(ไม่ถือว่าผ่านแม้ลด φ แล้วกำลังพอ)")
    return "\n".join(L)


def shear_steps(inp, sr):
    rf = sqrt_fc(inp.fc)
    v = sr.vcs
    L = []
    L.append(f"- Vu = {kgf(sr.Vu)} = {sr.Vu / 1e3:.1f} kN"
             + (" (ที่ระยะ d จากผิวรองรับ — ต้องเข้าเงื่อนไข §9.4.3.2)"
                if inp.crit_at_d else " (ที่ผิวรองรับ)"))
    L.append(f"- bw = {sr.bw:.0f} mm, d = {sr.d:.1f} mm, √f′c = {rf:.3f} MPa (≤ 8.3)")
    L.append(f"- Av,min/s = max(0.062√f′c·bw/fyt, 0.35bw/fyt) = "
             f"{sr.Av_min_s:.4f} mm²/mm (Table 9.6.3.4)")
    thr = 0.083 * PHI_V * rf * sr.bw * sr.d
    L.append(f"- 0.083φλ√f′c·bw·d = {thr / 1e3:.1f} kN → ปลอกขั้นต่ำ"
             f"{'จำเป็น' if sr.min_required else 'ไม่จำเป็น'} (§9.6.3.1)")
    L.append(f"- ρw = As/(bw·d) = {v['rho_w']:.5f}, λs = {v['lambda_s']:.4f}")
    L.append(f"- Vc (a) 0.17λ√f′c·bw·d = {v['a'] / 1e3:.1f} kN; "
             f"(b) 0.66λρw^⅓√f′c·bw·d = {v['b'] / 1e3:.1f} kN; "
             f"(c) 0.66λsλρw^⅓√f′c·bw·d = {v['c'] / 1e3:.1f} kN; "
             f"เพดาน 0.42λ√f′c·bw·d = {v['cap'] / 1e3:.1f} kN")
    why = ("Av/s ≥ Av,min/s" if sr.vc_eq != "c" else "Av/s < Av,min/s หรือไม่มีปลอก")
    L.append(f"- ใช้สมการ **({sr.vc_eq})** เพราะ {why} → **Vc = {sr.Vc / 1e3:.1f} kN**"
             " (Table 22.5.5.1)")
    L.append(f"- Vs,required = Vu/φ − Vc = {sr.Vs_req / 1e3:.1f} kN")
    if sr.s > 0:
        L.append(f"- ปลอก {inp.legs} ขา DB/RB{inp.ds:g}: Av = {sr.Av:.1f} mm² @ "
                 f"{sr.s:.0f} mm → Vs,provided = Av·fyt·d/s = {sr.Vs / 1e3:.1f} kN"
                 " (§22.5.8.5.3)")
        L.append(f"- smax = {sr.s_max:.0f} mm (Table 9.7.6.2.2)")
    else:
        L.append("- ไม่มีปลอก: Vs = 0")
    L.append(f"- **φVn = 0.75(Vc + Vs) = {sr.phiVn / 1e3:.1f} kN = {kgf(sr.phiVn)}**")
    L.append(f"- ตรวจหน้าตัด: φ(Vc + 0.66√f′c·bw·d) = {sr.section_limit / 1e3:.1f} kN"
             " (§22.5.1.2)")
    L += [f"- {n}" for n in sr.notes]
    return "\n".join(L)


def assumptions(inp):
    return "\n".join([
        "- มาตรฐาน: ACI 318M-19 (318-19(22) ไม่มีการเปลี่ยนแปลงทางเทคนิค)",
        "- สมดุลและ strain compatibility §22.2.1; εcu = 0.003, ไม่คิดแรงดึงคอนกรีต "
        "§22.2.2; stress block 0.85f′c §22.2.2.4; fs = Esεs ≤ fy §20.2.2.1",
        f"- εty: {'0.002 (ข้อยกเว้น Grade 420)' if inp.grade420 else 'fy/Es'}",
        f"- Critical section แรงเฉือน: {'ที่ระยะ d (§9.4.3.2)' if inp.crit_at_d else 'ที่ผิวรองรับ'}",
        "- λ = 1.0 (คอนกรีตน้ำหนักปกติ), ปลอกตั้งฉาก, ช่องว่างระหว่างชั้นเหล็ก 25 mm",
        "- ไม่รองรับ: T/L-beam, แรงบิด, แรงตามแกน, deep beam, SMF/IMF, ปลอกเฉียง",
        "- เลขข้อ/สูตรยังไม่ได้เทียบกับตัวเล่มและ errata ทั้งหมด — วิศวกรผู้รับผิดชอบต้องตรวจ"
        "และลงนามเอง",
    ])


def build_report(title, inp, fr, sr, det_rows, header_lines=()):
    rows = summary_rows(inp, fr, sr, det_rows)
    parts = [f"# {title}", ""]
    parts += list(header_lines)
    parts += [
        "",
        "## ข้อมูล",
        f"- b × h = {inp.b:.0f} × {inp.h:.0f} mm, cover = {inp.cover:.0f} mm, "
        f"ปลอก {inp.ds:g} mm ({inp.legs} ขา), dagg = {inp.dagg:.0f} mm",
        f"- f′c = {inp.fc:.2f} MPa ({u.mpa_to_ksc(inp.fc):.0f} ksc), "
        f"fy = {inp.fy:.2f} MPa ({u.mpa_to_ksc(inp.fy):.0f} ksc), "
        f"fyt = {inp.fyt:.2f} MPa ({u.mpa_to_ksc(inp.fyt):.0f} ksc)",
        f"- Mu = {kgfm(abs(inp.Mu))}, Vu = {kgf(inp.Vu)}",
        "",
        "## สรุปผล",
        _table(rows),
        "",
        "## แรงดัด",
        flexure_steps(inp, fr),
        "",
        "## แรงเฉือน",
        shear_steps(inp, sr),
        "",
        "## สมมติฐานและขอบเขต",
        assumptions(inp),
    ]
    return "\n".join(parts), rows
