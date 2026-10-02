"""แผ่นรายการคำนวณ (Calsheet) ขนาด A4 รูปแบบเอกสารตรวจสอบการคำนวณอย่างเป็นทางการ

- ไล่การคำนวณทีละบรรทัด: คำอธิบาย → สมการ = แทนค่า = ผลลัพธ์ (ชิดซ้าย)
- ตัวอักษรละตินและสมการแบบ Times (STIX), ข้อความไทยใช้ TH SarabunPSK (ฝังในไฟล์)
- หัวกระดาษและท้ายกระดาษทุกหน้า, อ้างอิงข้อ ACI ชิดขวา
- HTML ไฟล์เดียว เปิดในเบราว์เซอร์แล้วพิมพ์ / Save as PDF
"""
import base64
import functools
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from . import units as u
from .report import PASS, FAIL
from .shear import PHI_V, sqrt_fc
from .texmath import tex

FONT_DIR = Path(__file__).parent / "fonts"
FONT_FILES = {
    (400, "normal"): "THSarabunPSK-Regular.ttf",
    (700, "normal"): "THSarabunPSK-Bold.ttf",
    (400, "italic"): "THSarabunPSK-Italic.ttf",
    (700, "italic"): "THSarabunPSK-BoldItalic.ttf",
}
# TH SarabunPSK ตัวเล็กกว่า Times ที่ขนาด pt เดียวกัน จึงขยายให้สูงเท่ากัน
SARABUN_SIZE_ADJUST = "138%"

FC = r"f^{\prime}_{c}"
SQFC = r"\sqrt{f^{\prime}_{c}}"
X = r" \bullet "     # เครื่องหมายคูณแบบเอกสาร CSI


@dataclass
class ProjectInfo:
    project: str = ""
    location: str = ""
    member: str = ""
    grid: str = ""
    designer: str = ""
    checker: str = ""
    date: str = ""


@dataclass
class DesignInfo:
    """ผลจากโหมดออกแบบ (ไม่มีในโหมดตรวจสอบ)"""
    kind: str
    As_req: float
    Asc_req: float
    notes: list = field(default_factory=list)


@functools.lru_cache(maxsize=1)
def font_css():
    out = []
    for (weight, style), fname in FONT_FILES.items():
        p = FONT_DIR / fname
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        out.append(f'@font-face {{ font-family: "THSarabunPSK"; font-weight: {weight}; '
                   f'font-style: {style}; size-adjust: {SARABUN_SIZE_ADJUST}; '
                   f'src: url(data:font/ttf;base64,{b64}) format("truetype"); }}')
    return "\n".join(out)


def _e(x):
    return escape(str(x))


def _n(x, nd=2):
    """ตัวเลขสำหรับสมการ (คั่นหลักพันด้วย {,})"""
    return f"{x:,.{nd}f}".replace(",", "{,}")


def _ge(ok):
    return r"\geq" if ok else "<"


def _le(ok):
    return r"\leq" if ok else ">"


def _disp(expr):
    return expr.replace(r"\frac", r"\dfrac")


class _Doc:
    """ตัวช่วยเรียงเนื้อหา: หัวข้อ (ตัวหนา), หัวข้อย่อย (ขีดเส้นใต้), คำอธิบาย, สมการ"""

    def __init__(self):
        self.parts = []

    def h(self, th, en=""):
        en = f" <span class='en'>({en})</span>" if en else ""
        self.parts.append(f'<div class="h">{th}{en}:</div>')

    def sub(self, th):
        self.parts.append(f'<div class="sub"><u>{th}:</u></div>')

    def p(self, html):
        self.parts.append(f'<div class="desc">{html}</div>')

    def raw(self, html):
        self.parts.append(html)

    def eq(self, *lines, ref="", check=None, note=""):
        """สมการชิดซ้าย บรรทัดต่อเนื่องย่อหน้าเข้า; check → OK/NG ตัวหนาท้ายบรรทัด"""
        rows = []
        for i, ln in enumerate(lines):
            last = i == len(lines) - 1
            tail = ""
            if last and check is not None:
                tail = (' <b class="ok">OK</b>' if check else ' <b class="ng">NG</b>')
            if last and note:
                tail += f' <b>{note}</b>'
            r = f"[{ref}]" if (ref and i == 0) else ""
            side = f'<span class="ref">{r}{tail}</span>' if (r or tail) else ""
            rows.append(f'<div class="ln{" cont" if i else ""}"><span class="body">'
                        f"{tex(_disp(ln))}</span>{side}</div>")
        self.parts.append('<div class="eqg">' + "".join(rows) + "</div>")

    def html(self):
        return "\n".join(self.parts)


def section_svg(inp, fr, size=200):
    """รูปหน้าตัดพร้อมเหล็กเสริมและแกนสะเทิน (SVG ขาว-ดำ)"""
    b, h = inp.b, inp.h
    pad = 38
    k = (size - 2 * pad) / max(b, h)
    W, H = b * k + 2 * pad + 20, h * k + 2 * pad
    Xc = lambda x: pad + x * k  # noqa: E731
    Yc = lambda y: pad + y * k  # noqa: E731  (y วัดจากผิวบนของรูป)
    top_tension = inp.Mu < 0
    o = inp.cover + inp.ds / 2
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
         f'viewBox="0 0 {W:.1f} {H:.1f}" font-family="Times New Roman, Liberation Serif, '
         'serif" font-size="11">',
         '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#aaa" '
         'stroke-width="0.6"/></pattern></defs>',
         f'<rect x="{Xc(0):.1f}" y="{Yc(0):.1f}" width="{b * k:.1f}" height="{h * k:.1f}" '
         'fill="url(#hatch)" stroke="#000" stroke-width="1.1"/>',
         f'<rect x="{Xc(o):.1f}" y="{Yc(o):.1f}" width="{(b - 2 * o) * k:.1f}" '
         f'height="{(h - 2 * o) * k:.1f}" rx="{2 * inp.ds * k:.1f}" fill="none" '
         f'stroke="#000" stroke-width="{max(0.7, inp.ds * k):.1f}"/>']
    for st in fr.steel:
        L = st.layer
        y = (h - L.y) if top_tension else L.y
        x0 = inp.cover + inp.ds + L.db / 2
        x1 = b - x0
        xs = [x0] if L.n == 1 else [x0 + i * (x1 - x0) / (L.n - 1) for i in range(L.n)]
        fill = "#000" if L.role == "tension" else "#fff"
        for x in xs:
            s.append(f'<circle cx="{Xc(x):.1f}" cy="{Yc(y):.1f}" '
                     f'r="{max(1.5, L.db / 2 * k):.1f}" fill="{fill}" stroke="#000" '
                     'stroke-width="0.9"/>')
    na = (h - fr.c) if top_tension else fr.c
    s.append(f'<line x1="{Xc(0) - 6:.1f}" x2="{Xc(b) + 6:.1f}" y1="{Yc(na):.1f}" '
             f'y2="{Yc(na):.1f}" stroke="#000" stroke-dasharray="6 2 1 2" '
             'stroke-width="0.7"/>')
    s.append(f'<text x="{Xc(b) + 9:.1f}" y="{Yc(na) + 4:.1f}">N.A.</text>')
    yb = Yc(h) + 15
    xh = Xc(0) - 15
    s.append(f'<line x1="{Xc(0):.1f}" x2="{Xc(b):.1f}" y1="{yb:.1f}" y2="{yb:.1f}" '
             'stroke="#000" stroke-width="0.5"/>')
    s.append(f'<line x1="{xh:.1f}" x2="{xh:.1f}" y1="{Yc(0):.1f}" y2="{Yc(h):.1f}" '
             'stroke="#000" stroke-width="0.5"/>')
    for xx in (Xc(0), Xc(b)):
        s.append(f'<line x1="{xx - 3:.1f}" x2="{xx + 3:.1f}" y1="{yb + 3:.1f}" '
                 f'y2="{yb - 3:.1f}" stroke="#000" stroke-width="0.8"/>')
    for yy in (Yc(0), Yc(h)):
        s.append(f'<line x1="{xh - 3:.1f}" x2="{xh + 3:.1f}" y1="{yy + 3:.1f}" '
                 f'y2="{yy - 3:.1f}" stroke="#000" stroke-width="0.8"/>')
    s.append(f'<text x="{(Xc(0) + Xc(b)) / 2:.1f}" y="{yb + 13:.1f}" text-anchor="middle">'
             f'b = {b:.0f}</text>')
    s.append(f'<text transform="translate({xh - 5:.1f},{(Yc(0) + Yc(h)) / 2:.1f}) '
             f'rotate(-90)" text-anchor="middle">h = {h:.0f}</text>')
    s.append("</svg>")
    return "".join(s)


def _flexure(D, inp, fr, design, steel_text):
    fc, fy, b, h = inp.fc, inp.fy, inp.b, inp.h
    Mu = abs(inp.Mu)
    side = "ล่าง" if inp.Mu >= 0 else "บน"
    tens = [s.layer for s in fr.steel if s.layer.role == "tension"]
    comp = [s.layer for s in fr.steel if s.layer.role == "compression"]

    D.h("การออกแบบรับแรงดัด", "Design for Flexural Strength")
    D.sub("โมเมนต์ดัดที่ต้องการ (Required Flexural Strength)")
    D.eq(rf"M_u = {_n(u.nmm_to_kgfm(Mu), 0)}\ \mathrm{{kgf\cdot m}} = "
         rf"{_n(u.nmm_to_kgfm(Mu), 0)}{X}9.80665{X}10^{{-3}} = "
         rf"{_n(Mu / 1e6)}\ \mathrm{{kN\cdot m}}")
    D.p(f"ผิว{side}ของคานรับแรงดึง วัดระยะ y ลงจากผิวรับแรงอัด")

    D.sub("ค่าคงที่ของวัสดุและหน้าตัด (Material and Section Properties)")
    D.p("ตัวคูณความลึก stress block:")
    if fc <= 28.0:
        D.eq(rf"\beta_1 = 0.85 \qquad \mathrm{{for}}\ {FC} = {_n(fc)}\ \mathrm{{MPa}} "
             r"\leq 28\ \mathrm{MPa}", ref="ACI 22.2.2.4.3")
    else:
        D.eq(rf"\beta_1 = 0.85-\frac{{0.05\,({FC}-28)}}{{7}} = 0.85-"
             rf"\frac{{0.05{X}({_n(fc)}-28)}}{{7}} = {fr.beta1:.3f} \geq 0.65",
             ref="ACI 22.2.2.4.3")
    D.p("ความเครียดครากของเหล็กเสริม:")
    if inp.grade420:
        D.eq(r"\varepsilon_{ty} = 0.002 \qquad (\mathrm{Grade\ 420\ exception})",
             ref="ACI 21.2.2.1")
    else:
        D.eq(rf"\varepsilon_{{ty}} = \frac{{f_y}}{{E_s}} = \frac{{{_n(fy)}}}{{200{{,}}000}} = "
             rf"{fr.ety:.5f}", ref="ACI 21.2.2.1")
    D.p("ความลึกถึงเหล็กรับแรงดึงชั้นนอกสุด และความลึกประสิทธิผล:")
    db = tens[0].db
    D.eq(rf"d_t = h-c_c-d_s-\frac{{d_b}}{{2}} = {h:.0f}-{inp.cover:.0f}-{inp.ds:g}-"
         rf"\frac{{{db:g}}}{{2}} = {_n(fr.dt, 1)}\ \mathrm{{mm}}")
    if len(tens) > 1:
        num = " + ".join(f"{L.area:,.0f}{X}{L.y:.1f}".replace(",", "{,}") for L in tens)
        den = " + ".join(f"{L.area:,.0f}".replace(",", "{,}") for L in tens)
        D.eq(rf"d = \frac{{\sum A_i\,y_i}}{{\sum A_i}} = \frac{{{num}}}{{{den}}} = "
             rf"{_n(fr.d, 1)}\ \mathrm{{mm}}")
    else:
        D.eq(rf"d = d_t = {_n(fr.d, 1)}\ \mathrm{{mm}}")
    if comp:
        L = comp[0]
        D.eq(rf"d^{{\prime}} = c_c+d_s+\frac{{d_b^{{\prime}}}}{{2}} = {inp.cover:.0f}+"
             rf"{inp.ds:g}+\frac{{{L.db:g}}}{{2}} = {_n(L.y, 1)}\ \mathrm{{mm}}")
    D.p("ระยะแกนสะเทินสูงสุดสำหรับหน้าตัดควบคุมด้วยแรงดึง:")
    D.eq(r"c_{\max} = \frac{0.003\,d_t}{0.003+\varepsilon_{ty}+0.003} = "
         rf"\frac{{0.003{X}{_n(fr.dt, 1)}}}{{0.003+{fr.ety:.5f}+0.003}} = "
         rf"{_n(fr.cmax, 1)}\ \mathrm{{mm}}", ref="ACI 9.3.3.1")

    if design is not None:
        D.sub("ปริมาณเหล็กเสริมที่ต้องการ (Required Reinforcement)")
        if design.kind == "singly":
            a_req = design.As_req * fy / (0.85 * fc * b)
            D.p("ความลึก stress block ที่ต้องการ (สมมติ φ = 0.90):")
            D.eq(r"a = d-\sqrt{d^2-\frac{2M_u}{\phi\,0.85\,f^{\prime}_{c}\,b}}",
                 rf"= {_n(fr.d, 1)}-\sqrt{{{_n(fr.d, 1)}^2-\frac{{2{X}{_n(Mu / 1e6)}{X}10^6}}"
                 rf"{{0.90{X}0.85{X}{_n(fc)}{X}{b:.0f}}}}} = {_n(a_req, 1)}\ \mathrm{{mm}}")
            D.p("พื้นที่เหล็กรับแรงดึงที่ต้องการ:")
            D.eq(rf"A_{{s,req}} = \frac{{0.85\,{FC}\,b\,a}}{{f_y}} = "
                 rf"\frac{{0.85{X}{_n(fc)}{X}{b:.0f}{X}{_n(a_req, 1)}}}{{{_n(fy)}}} = "
                 rf"{_n(design.As_req, 0)}\ \mathrm{{mm^2}} = "
                 rf"{_n(design.As_req / 100)}\ \mathrm{{cm^2}}")
        else:
            D.p("หน้าตัดเสริมเหล็กรับแรงดึงอย่างเดียวไม่ผ่าน จึงเสริมเหล็กรับแรงอัด "
                "(ประมาณค่าเริ่มต้นที่ c = c<sub>max</sub>):")
            D.eq(r"A^{\prime}_{s} = \frac{M_u/\phi - M_{n1}}{(f^{\prime}_{s}-0.85\,"
                 r"f^{\prime}_{c})\,(d-d^{\prime})}"
                 rf" = {_n(design.Asc_req / 100)}\ \mathrm{{cm^2}}")
            D.eq(r"A_s = \frac{C_c + A^{\prime}_{s}(f^{\prime}_{s}-0.85\,f^{\prime}_{c})}{f_y}"
                 rf" = {_n(design.As_req / 100)}\ \mathrm{{cm^2}}")
        for n in design.notes:
            D.p(f"<i>หมายเหตุ: {_e(n)}</i>")
        D.p(f"<b>เลือกใช้:</b> {_e(steel_text)}")

    D.sub("กำลังรับแรงดัดระบุ (Nominal Flexural Strength)")
    D.p("สมดุลแรงและ strain compatibility (หาค่า c ด้วยวิธี bisection):")
    D.eq(r"0.85\,f^{\prime}_{c}\,b\,\beta_1 c + \sum A_{si}\,f_{si} = 0, \qquad "
         r"f_{si} = E_s\,\varepsilon_{si} \leq f_y, \qquad "
         r"\varepsilon_{si} = 0.003\,\frac{c-y_i}{c}", ref="ACI 22.2.1, 22.2.2")
    D.eq(rf"c = {_n(fr.c, 1)}\ \mathrm{{mm}}")
    D.eq(rf"a = \beta_1 c = {fr.beta1:.3f}{X}{_n(fr.c, 1)} = {_n(fr.a, 1)}\ \mathrm{{mm}}",
         ref="ACI 22.2.2.4.1")
    D.eq(rf"C_c = 0.85\,{FC}\,b\,a = 0.85{X}{_n(fc)}{X}{b:.0f}{X}{_n(fr.a, 1)}{X}10^{{-3}}"
         rf" = {_n(fr.Cc / 1e3, 1)}\ \mathrm{{kN}}")

    hdr = "".join(f"<th>{tex(x, 11)}</th>" for x in (
        r"\mathrm{Bars}", r"y\ (\mathrm{mm})", r"A_s\ (\mathrm{mm^2})", r"\varepsilon_s",
        r"f_s\ (\mathrm{MPa})", r"F\ (\mathrm{kN})")) + "<th>Remark</th>"
    trs = []
    for st in fr.steel:
        L = st.layer
        note = ("ใน stress block หัก 0.85f′c" if st.in_block else
                ("a &lt; y &lt; c ไม่หักคอนกรีต" if st.fs > 0 else "รับแรงดึง"))
        trs.append(f"<tr><td>{L.n}-DB{L.db:g} ({'อัด' if L.role == 'compression' else 'ดึง'})"
                   f"</td><td>{L.y:.1f}</td><td>{L.area:,.0f}</td><td>{st.eps:+.5f}</td>"
                   f"<td>{st.fs:+.1f}</td><td>{st.force / 1e3:+.1f}</td><td>{note}</td></tr>")
    D.raw(f'<table class="grid num"><thead><tr>{hdr}</tr></thead>'
          f"<tbody>{''.join(trs)}</tbody></table>")

    D.p("โมเมนต์ระบุ (คิดรอบผิวรับแรงอัด แรงอัดเป็นบวก):")
    D.eq(r"M_n = -\left(C_c\,\frac{a}{2} + \sum F_i\,y_i\right) = "
         rf"{_n(fr.Mn / 1e6)}\ \mathrm{{kN\cdot m}}", ref="ACI 22.3.1.1")
    D.p("ตรวจสอบหน้าตัดควบคุมด้วยแรงดึง:")
    D.eq(rf"\varepsilon_t = 0.003\,\frac{{d_t-c}}{{c}} = 0.003{X}"
         rf"\frac{{{_n(fr.dt, 1)}-{_n(fr.c, 1)}}}{{{_n(fr.c, 1)}}} = {fr.et:.5f}\ "
         rf"{_ge(fr.strain_ok)}\ \varepsilon_{{ty}}+0.003 = {fr.et_limit:.5f}",
         ref="ACI 9.3.3.1", check=fr.strain_ok)
    if fr.et >= fr.ety + 0.003:
        D.eq(r"\phi = 0.90 \qquad (\mathrm{tension\ controlled})", ref="ACI Table 21.2.2")
    elif fr.et <= fr.ety:
        D.eq(r"\phi = 0.65 \qquad (\mathrm{compression\ controlled})", ref="ACI Table 21.2.2")
    else:
        D.eq(rf"\phi = 0.65+0.25\,\frac{{\varepsilon_t-\varepsilon_{{ty}}}}{{0.003}} = "
             rf"0.65+0.25{X}\frac{{{fr.et:.5f}-{fr.ety:.5f}}}{{0.003}} = {fr.phi:.3f}",
             ref="ACI Table 21.2.2")
    D.p("กำลังรับแรงดัดที่ออกแบบได้:")
    ok = fr.phiMn >= Mu - 1e-6
    D.eq(rf"\phi M_n = {fr.phi:.3f}{X}{_n(fr.Mn / 1e6)} = {_n(fr.phiMn / 1e6)}\ "
         rf"\mathrm{{kN\cdot m}} = {_n(u.nmm_to_kgfm(fr.phiMn), 0)}\ \mathrm{{kgf\cdot m}}",
         rf"{_ge(ok)}\ M_u = {_n(u.nmm_to_kgfm(Mu), 0)}\ \mathrm{{kgf\cdot m}}",
         ref="ACI 9.5.1.1(a)", check=ok)
    D.p("เหล็กเสริมขั้นต่ำ:")
    fy_ = min(fy, 550.0)
    D.eq(rf"A_{{s,\min}} = \max\left(\frac{{0.25{SQFC}}}{{f_y}},\ \frac{{1.4}}{{f_y}}\right)"
         r"b_w\,d",
         rf"= \max\left(\frac{{0.25{X}\sqrt{{{_n(fc)}}}}}{{{_n(fy_)}}},\ "
         rf"\frac{{1.4}}{{{_n(fy_)}}}\right){X}{b:.0f}{X}{_n(fr.d, 1)} = "
         rf"{_n(fr.As_min, 0)}\ \mathrm{{mm^2}}\ {_le(fr.as_min_ok)}\ "
         rf"A_s = {_n(fr.As, 0)}\ \mathrm{{mm^2}}", ref="ACI 9.6.1.2", check=fr.as_min_ok)


def _shear(D, inp, sr):
    rf = sqrt_fc(inp.fc)
    v = sr.vcs
    bw, d, fyt = sr.bw, sr.d, inp.fyt
    D.h("การออกแบบรับแรงเฉือน", "Design for Shear Strength")
    D.sub("แรงเฉือนที่ต้องการ (Required Shear Strength)")
    D.eq(rf"V_u = {_n(u.n_to_kgf(sr.Vu), 0)}\ \mathrm{{kgf}} = "
         rf"{_n(u.n_to_kgf(sr.Vu), 0)}{X}9.80665{X}10^{{-3}} = "
         rf"{_n(sr.Vu / 1e3, 1)}\ \mathrm{{kN}}")
    D.p("คิดที่" + ("ระยะ d จากผิวรองรับ (ต้องเข้าเงื่อนไข ACI 9.4.3.2)"
                    if inp.crit_at_d else "ผิวรองรับ"))

    D.sub("กำลังรับแรงเฉือนของคอนกรีต (Concrete Shear Strength)")
    D.eq(rf"{SQFC} = \sqrt{{{_n(inp.fc)}}} = {rf:.3f}\ \mathrm{{MPa}} \leq 8.3\ "
         r"\mathrm{MPa}", ref="ACI 22.5.3.1")
    D.p("ปริมาณเหล็กปลอกขั้นต่ำ:")
    D.eq(r"\frac{A_{v,\min}}{s} = \max\left(0.062\sqrt{f^{\prime}_{c}}\,\frac{b_w}{f_{yt}},\ "
         r"0.35\,\frac{b_w}{f_{yt}}\right)",
         rf"= \max\left(0.062{X}{rf:.3f}{X}\frac{{{bw:.0f}}}{{{_n(fyt)}}},\ 0.35{X}"
         rf"\frac{{{bw:.0f}}}{{{_n(fyt)}}}\right) = {sr.Av_min_s:.4f}\ \mathrm{{mm^2/mm}}",
         ref="ACI Table 9.6.3.4")
    thr = 0.083 * PHI_V * rf * bw * d
    D.p("ตรวจความจำเป็นของเหล็กปลอกขั้นต่ำ:")
    D.eq(rf"0.083\,\phi\,\lambda{SQFC}\,b_w d",
         rf"= 0.083{X}0.75{X}1.0{X}{rf:.3f}{X}{bw:.0f}{X}{_n(d, 1)}{X}10^{{-3}} = "
         rf"{_n(thr / 1e3, 1)}\ \mathrm{{kN}}\ {_ge(not sr.min_required)}\ V_u",
         ref="ACI 9.6.3.1")
    D.p("∴ ต้องใส่เหล็กปลอกไม่น้อยกว่าปริมาณขั้นต่ำ" if sr.min_required
        else "∴ ไม่บังคับเหล็กปลอกขั้นต่ำตามการคำนวณ")
    D.eq(rf"\rho_w = \frac{{A_s}}{{b_w\,d}} = \frac{{{_n(v['rho_w'] * bw * d, 0)}}}"
         rf"{{{bw:.0f}{X}{_n(d, 1)}}} = {v['rho_w']:.5f}", ref="ACI 22.5.5.1")
    D.eq(rf"\lambda_s = \sqrt{{\frac{{2}}{{1+d/250}}}} = \sqrt{{\frac{{2}}{{1+{_n(d, 1)}/250}}}}"
         rf" = {v['lambda_s']:.4f} \leq 1.0", ref="ACI 22.5.5.1.3")
    bd = rf"{rf:.3f}{X}{bw:.0f}{X}{_n(d, 1)}{X}10^{{-3}}"
    D.p("กำลังรับแรงเฉือนของคอนกรีต ตามตาราง 22.5.5.1:")
    D.eq(rf"(a)\quad V_c = 0.17\,\lambda{SQFC}\,b_w d",
         rf"= 0.17{X}1.0{X}{bd} = {_n(v['a'] / 1e3, 1)}\ \mathrm{{kN}}",
         ref="ACI Table 22.5.5.1")
    D.eq(rf"(b)\quad V_c = 0.66\,\lambda\,\rho_w^{{1/3}}{SQFC}\,b_w d",
         rf"= 0.66{X}1.0{X}{v['rho_w']:.5f}^{{1/3}}{X}{bd} = "
         rf"{_n(v['b'] / 1e3, 1)}\ \mathrm{{kN}}")
    D.eq(rf"(c)\quad V_c = 0.66\,\lambda_s\lambda\,\rho_w^{{1/3}}{SQFC}\,b_w d",
         rf"= 0.66{X}{v['lambda_s']:.4f}{X}1.0{X}{v['rho_w']:.5f}^{{1/3}}{X}{bd} = "
         rf"{_n(v['c'] / 1e3, 1)}\ \mathrm{{kN}}")
    D.eq(rf"V_{{c,\max}} = 0.42\,\lambda{SQFC}\,b_w d",
         rf"= 0.42{X}1.0{X}{bd} = {_n(v['cap'] / 1e3, 1)}\ \mathrm{{kN}}",
         ref="ACI 22.5.5.1.1")
    why = ("A_v/s \\geq A_{v,\\min}/s" if sr.vc_eq != "c" else "A_v/s < A_{v,\\min}/s")
    D.eq(rf"\mathrm{{Use\ eq.}}\ ({sr.vc_eq})\ \ \mathrm{{since}}\ \ {why}: \qquad "
         rf"V_c = {_n(sr.Vc / 1e3, 1)}\ \mathrm{{kN}}", note="controls")

    D.sub("เหล็กเสริมรับแรงเฉือน (Shear Reinforcement)")
    D.eq(rf"V_{{s,req}} = \frac{{V_u}}{{\phi}}-V_c = \frac{{{_n(sr.Vu / 1e3, 1)}}}{{0.75}}-"
         rf"{_n(sr.Vc / 1e3, 1)} = {_n(sr.Vs_req / 1e3, 1)}\ \mathrm{{kN}}")
    if sr.s > 0:
        D.eq(rf"A_v = n_{{legs}}\,\frac{{\pi d_s^2}}{{4}} = {inp.legs}{X}"
             rf"\frac{{\pi{X}{inp.ds:g}^2}}{{4}} = {_n(sr.Av, 1)}\ \mathrm{{mm^2}}")
        D.eq(rf"V_s = \frac{{A_v\,f_{{yt}}\,d}}{{s}} = \frac{{{_n(sr.Av, 1)}{X}{_n(fyt)}{X}"
             rf"{_n(d, 1)}}}{{{sr.s:.0f}}}{X}10^{{-3}} = {_n(sr.Vs / 1e3, 1)}\ \mathrm{{kN}}",
             ref="ACI 22.5.8.5.3")
        if sr.min_required:
            D.eq(rf"\frac{{A_v}}{{s}} = \frac{{{_n(sr.Av, 1)}}}{{{sr.s:.0f}}} = "
                 rf"{sr.Av / sr.s:.4f}\ {_ge(sr.av_min_ok)}\ \frac{{A_{{v,\min}}}}{{s}} = "
                 rf"{sr.Av_min_s:.4f}", ref="ACI 9.6.3.1", check=sr.av_min_ok)
        D.eq(rf"s = {sr.s:.0f}\ \mathrm{{mm}}\ {_le(sr.spacing_ok)}\ s_{{\max}} = "
             rf"{sr.s_max:.0f}\ \mathrm{{mm}}", ref="ACI Table 9.7.6.2.2",
             check=sr.spacing_ok)
    else:
        D.eq(r"V_s = 0 \qquad (\mathrm{no\ stirrups})")
    D.sub("กำลังรับแรงเฉือนที่ออกแบบได้ (Design Shear Strength)")
    D.eq(rf"\phi V_n = \phi\,(V_c+V_s) = 0.75{X}({_n(sr.Vc / 1e3, 1)}+{_n(sr.Vs / 1e3, 1)})"
         rf" = {_n(sr.phiVn / 1e3, 1)}\ \mathrm{{kN}}",
         rf"= {_n(u.n_to_kgf(sr.phiVn), 0)}\ \mathrm{{kgf}}\ {_ge(sr.strength_ok)}\ "
         rf"V_u = {_n(u.n_to_kgf(sr.Vu), 0)}\ \mathrm{{kgf}}", ref="ACI 9.5.1.1(b)",
         check=sr.strength_ok)
    D.p("ตรวจขนาดหน้าตัด:")
    D.eq(rf"\phi\left(V_c+0.66{SQFC}\,b_w d\right)",
         rf"= 0.75{X}({_n(sr.Vc / 1e3, 1)}+0.66{X}{bd}) = "
         rf"{_n(sr.section_limit / 1e3, 1)}\ \mathrm{{kN}}\ {_ge(sr.section_ok)}\ V_u",
         ref="ACI 22.5.1.2", check=sr.section_ok)
    for n in sr.notes:
        D.p(f"<i>หมายเหตุ: {_e(n)}</i>")


def _status(s):
    cls = {PASS: "ok", FAIL: "ng"}.get(s, "nc")
    return f'<b class="{cls}">{_e(s)}</b>'


CSS = """
@page { size: A4 portrait; margin: 14mm 18mm 16mm 22mm;
  @bottom-right { content: "__FOOT__ - " counter(page);
    font-family: "Times New Roman", "Liberation Serif", serif; font-size: 9pt; }
  @bottom-left { content: "ACI 318M-19 · RC Beam Design";
    font-family: "Times New Roman", "Liberation Serif", serif; font-size: 9pt;
    color: #666; } }
* { box-sizing: border-box; }
html, body { margin: 0; background: #fff; color: #000; }
body { font-family: "Times New Roman", "Liberation Serif", "THSarabunPSK", serif;
  font-size: 11.5pt; line-height: 1.35; }
.sheet { width: 210mm; margin: 0 auto; padding: 14mm 18mm 16mm 22mm; background: #fff; }
@media screen { html { background: #7a7a7a; }
  .sheet { margin: 14px auto; box-shadow: 0 2px 10px #0006; }
  .toolbar { position: sticky; top: 0; z-index: 9; background: #2b2b2b; padding: 8px;
    text-align: center; }
  .toolbar button { font-family: inherit; font-size: 12pt; padding: 4px 22px;
    cursor: pointer; } }
@media print { .toolbar { display: none; }
  .sheet { width: auto; margin: 0; padding: 0; box-shadow: none; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
table { border-collapse: collapse; }
table.page { width: 100%; }
table.page > thead > tr > td, table.page > tbody > tr > td { padding: 0; }
.ph { display: flex; justify-content: space-between; align-items: flex-end;
  border-bottom: 1.4pt solid #000; padding-bottom: 3px; margin-bottom: 14px; }
.ph .mark { font-weight: 700; font-size: 15pt; letter-spacing: 1px; line-height: 1; }
.ph .mark small { display: block; font-weight: 400; font-size: 7.5pt; letter-spacing: 0.5px; }
.ph .rt { text-align: right; }
.ph .ttl { font-size: 17pt; line-height: 1.1; }
.ph .fld { font-size: 8pt; text-transform: uppercase; line-height: 1.5; }
.ph .fld span { display: inline-block; min-width: 34mm; border-bottom: 0.6pt solid #000;
  text-transform: none; font-size: 10pt; text-align: left; padding-left: 4px; }
.h { font-weight: 700; font-size: 12pt; margin: 16px 0 4px; break-after: avoid; }
.h .en { font-weight: 700; }
.sub { margin: 9px 0 2px; break-after: avoid; }
.desc { margin: 2px 0 1px 5mm; break-after: avoid; }
.eqg { margin: 2px 0 6px; break-inside: avoid; }
.ln { display: flex; align-items: center; justify-content: space-between; gap: 6px;
  padding-left: 10mm; min-height: 18px; }
.ln.cont { padding-left: 15mm; }
.ln .body { flex: 1 1 auto; min-width: 0; }
.ln .ref { flex: 0 0 auto; font-size: 8.5pt; color: #444; white-space: nowrap; }
.ln .ref b { font-size: 11pt; margin-left: 6px; color: #000; }
.ln .ref b.ng { color: #b00020; }
img.m { vertical-align: middle; max-width: 100%; height: auto !important; }
.ok { color: #000; } .ng { color: #b00020; } .nc { color: #7a5a00; }
table.grid { margin: 6px 0 8px 7mm; font-size: 10pt; break-inside: avoid; }
table.grid th, table.grid td { border: 0.6pt solid #000; padding: 1px 7px; }
table.grid th { font-weight: 700; background: #f0f0f0; }
table.num td:not(:first-child):not(:last-child) { text-align: right;
  font-variant-numeric: tabular-nums; }
table.full { width: calc(100% - 7mm); }
table.full td:nth-child(3) { text-align: center; white-space: nowrap; }
.titleblk { text-align: center; margin: 4px 0 10px; }
.titleblk .t1 { font-size: 16pt; font-weight: 700; }
.titleblk .t2 { font-size: 11pt; }
table.info { width: 100%; font-size: 10.5pt; margin-bottom: 4px; }
table.info td { border: 0.6pt solid #000; padding: 1px 6px; }
table.info td.k { font-weight: 700; background: #f0f0f0; width: 14%; white-space: nowrap; }
.datawrap { display: flex; gap: 10px; align-items: center; justify-content: space-between;
  break-inside: avoid; }
.data { flex: 1; }
.fig { text-align: center; font-size: 9.5pt; }
.result { margin: 8px 0 0 7mm; padding: 3px 10px; border: 0.8pt solid #000;
  break-inside: avoid; }
ul.notes { margin: 2px 0 0 12mm; padding: 0; font-size: 10.5pt; }
table.sign { width: 100%; margin-top: 26px; break-inside: avoid; text-align: center; }
table.sign td { width: 33.3%; padding-top: 24px; vertical-align: bottom; font-size: 10.5pt; }
"""


def build_calsheet(title, proj, inp, fr, sr, summary, steel_text, stirrup_text,
                   design=None):
    """คืนค่า HTML ทั้งหน้าสำหรับพิมพ์ A4"""
    p = proj or ProjectInfo()
    Mu = abs(inp.Mu)
    D = _Doc()

    D.raw(f"""
<div class="titleblk"><div class="t1">รายการคำนวณออกแบบคานคอนกรีตเสริมเหล็ก</div>
<div class="t2">Reinforced Concrete Beam Design to ACI 318M-19 (Ultimate Strength Design)</div></div>
<table class="info">
<tr><td class="k">โครงการ</td><td>{_e(p.project) or '–'}</td>
    <td class="k">ชื่อคาน</td><td>{_e(p.member) or '–'}</td></tr>
<tr><td class="k">สถานที่</td><td>{_e(p.location) or '–'}</td>
    <td class="k">ตำแหน่ง</td><td>{_e(p.grid) or '–'}</td></tr>
<tr><td class="k">ผู้คำนวณ</td><td>{_e(p.designer) or '–'}</td>
    <td class="k">วันที่</td><td>{_e(p.date) or '–'}</td></tr>
</table>""")

    D.h("ข้อมูลออกแบบ", "Design Data")
    ksc = lambda x: rf"{u.mpa_to_ksc(x):,.0f}".replace(",", "{,}") + \
        rf"\ \mathrm{{ksc}} = {_n(x)}\ \mathrm{{MPa}}"  # noqa: E731
    D.raw('<div class="datawrap"><div class="data">')
    D.sub("หน้าตัดและเหล็กเสริม (Section)")
    D.eq(rf"b \times h = {inp.b:.0f} \times {inp.h:.0f}\ \mathrm{{mm}}, \qquad "
         rf"c_c = {inp.cover:.0f}\ \mathrm{{mm}}, \qquad d_{{agg}} = {inp.dagg:.0f}\ "
         r"\mathrm{mm}")
    D.eq(rf"d_s = {inp.ds:g}\ \mathrm{{mm}}\ ({inp.legs}\ \mathrm{{legs}})")
    D.sub("วัสดุ (Materials)")
    D.eq(rf"{FC} = " + ksc(inp.fc))
    D.eq(r"f_y = " + ksc(inp.fy) + r", \qquad E_s = 200{,}000\ \mathrm{MPa}")
    D.eq(r"f_{yt} = " + ksc(inp.fyt))
    D.sub("แรงประลัย (Factored Loads)")
    D.eq(rf"M_u = {_n(u.nmm_to_kgfm(Mu), 0)}\ \mathrm{{kgf\cdot m}}, \qquad "
         rf"V_u = {_n(u.n_to_kgf(inp.Vu), 0)}\ \mathrm{{kgf}}")
    D.raw(f"""</div><div class="fig">{section_svg(inp, fr)}<br>
รูปที่ 1 หน้าตัดคาน (มม.)<br>● เหล็กรับแรงดึง &nbsp; ○ เหล็กรับแรงอัด</div></div>
<div class="result"><b>ผลออกแบบ:</b> {_e(steel_text)}<br>
<b>เหล็กปลอก:</b> {_e(stirrup_text)}</div>""")

    _flexure(D, inp, fr, design, steel_text)
    _shear(D, inp, sr)

    D.h("สรุปผลการตรวจสอบ", "Summary")
    srows = "".join(f"<tr><td>{_e(a)}</td><td>{_e(b)}</td><td>{_status(c)}</td>"
                    f"<td>{_e(d)}</td></tr>" for a, b, c, d in summary)
    D.raw('<table class="grid full"><thead><tr><th>รายการ</th><th>ค่า</th><th>สถานะ</th>'
          f"<th>อ้างอิง ACI 318M-19</th></tr></thead><tbody>{srows}</tbody></table>")

    D.h("สมมติฐานและขอบเขต", "Assumptions")
    D.raw(f"""<ul class="notes">
<li>ACI 318M-19 (318-19(22) ไม่มีการเปลี่ยนแปลงทางเทคนิค) คำนวณภายในด้วยหน่วย MPa–mm–N
แล้วแปลงผลเป็น kgf–m</li>
<li>สมดุลแรงและ strain compatibility (22.2.1), ε<sub>cu</sub> = 0.003 ไม่คิดกำลังรับแรงดึงของคอนกรีต
(22.2.2), stress block 0.85f′c (22.2.2.4), f<sub>s</sub> = E<sub>s</sub>ε<sub>s</sub> ≤ f<sub>y</sub>
(20.2.2.1)</li>
<li>ε<sub>ty</sub> = {'0.002 (ข้อยกเว้น Grade 420)' if inp.grade420 else 'f<sub>y</sub>/E<sub>s</sub>'};
หน้าตัดวิกฤตแรงเฉือน{'ที่ระยะ d (ต้องเข้าเงื่อนไข 9.4.3.2)' if inp.crit_at_d else 'ที่ผิวรองรับ'}</li>
<li>λ = 1.0, ปลอกตั้งฉาก, ช่องว่างระหว่างชั้นเหล็ก 25 mm, เหล็กรับแรงอัดชั้นเดียว</li>
<li>ไม่รองรับ T/L-beam, แรงบิด, แรงตามแกน, deep beam, SMF/IMF, ปลอกเฉียง</li>
<li>รายการ “ยังไม่ตรวจ” ต้องตรวจสอบเพิ่มเติม และเลขข้อ/สูตรต้องเทียบกับตัวเล่มมาตรฐานและ errata</li>
</ul>
<table class="sign"><tr>
<td>ลงชื่อ ......................................<br>
({_e(p.designer) or '......................................'})<br>ผู้คำนวณ</td>
<td>ลงชื่อ ......................................<br>
({_e(p.checker) or '......................................'})<br>ผู้ตรวจสอบ</td>
<td>ลงชื่อ ......................................<br>
(......................................)<br>วิศวกรผู้รับผิดชอบ</td>
</tr></table>""")

    foot = "".join(ch for ch in f"{p.member or 'Beam'} RC-Beam ACI318M-19"
                   if ch not in '"\\<>{}')
    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calsheet {_e(p.member or 'Beam')}</title>
<style>{font_css()}
{CSS.replace("__FOOT__", foot)}</style></head>
<body>
<div class="toolbar"><button onclick="window.print()">พิมพ์ / Save as PDF (A4)</button></div>
<div class="sheet">
<table class="page"><thead><tr><td>
<div class="ph">
  <div class="mark">RC BEAM<small>ACI 318M-19 · ULTIMATE STRENGTH DESIGN</small></div>
  <div class="rt"><div class="ttl">Calculation Sheet</div>
    <div class="fld">Project: <span>{_e(p.project) or '&nbsp;'}</span></div>
    <div class="fld">Member: <span>{_e(p.member) or '&nbsp;'}</span></div></div>
</div>
</td></tr></thead>
<tbody><tr><td>
{D.html()}
</td></tr></tbody></table>
</div>
</body></html>"""

