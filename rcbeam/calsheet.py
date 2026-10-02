"""แผ่นรายการคำนวณ (Calsheet) ขนาด A4 สไตล์รายงาน ETABS / LaTeX

- ข้อความไทยใช้ฟอนต์ TH SarabunPSK (ฝังในไฟล์ จึงพิมพ์ได้แม้ไม่ได้ติดตั้งฟอนต์)
- สมการเรนเดอร์แบบ LaTeX (Computer Modern) มีเลขสมการ และอ้างอิงข้อของ ACI
- ตารางแบบ booktabs (เส้นบน/กลาง/ล่าง ไม่มีเส้นตั้ง)
- HTML ไฟล์เดียว เปิดในเบราว์เซอร์แล้วพิมพ์ / Save as PDF
"""
import base64
import functools
import re
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

FC = r"f^{\prime}_{c}"
SQFC = r"\sqrt{f^{\prime}_{c}}"


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
                   f'font-style: {style}; src: url(data:font/ttf;base64,{b64}) '
                   'format("truetype"); }')
    return "\n".join(out)


def _e(x):
    return escape(str(x))


def _n(x, nd=2):
    """ตัวเลขสำหรับ LaTeX (คั่นหลักพันด้วย {,})"""
    return f"{x:,.{nd}f}".replace(",", "{,}")


_GREEK = re.compile(r"([\u0370-\u03ff]+)")
_TEXT = re.compile(r">([^<]+)<")


def _greek(html):
    """TH SarabunPSK ไม่มีอักษรกรีก: ห่อด้วย span ให้ใช้ฟอนต์ serif ขนาดเข้ากับข้อความไทย"""
    return _TEXT.sub(lambda m: ">" + _GREEK.sub(r'<span class="gr">\1</span>', m.group(1))
                     + "<", html)


def _ge(ok):
    return r"\geq" if ok else "<"


def _le(ok):
    return r"\leq" if ok else ">"


def _display(expr):
    """สมการแบบ display: ใช้เศษส่วนขนาดเต็ม (\\dfrac) แบบ LaTeX"""
    return expr.replace(r"\frac", r"\dfrac")


class _Doc:
    """ตัวช่วยเรียงเนื้อหา: หัวข้อ, ย่อหน้า, สมการมีเลขกำกับ"""

    def __init__(self):
        self.parts = []
        self.n_eq = 0

    def h(self, num, th, en):
        self.parts.append(f'<h2><span class="secno">{num}</span>{th}'
                          f'<span class="en">{en}</span></h2>')

    def h3(self, th):
        self.parts.append(f"<h3>{th}</h3>")

    def p(self, html):
        self.parts.append(f"<p>{html}</p>")

    def raw(self, html):
        self.parts.append(html)

    def eq(self, *lines, ref="", check=None):
        """สมการหลายบรรทัด เลขสมการอยู่บรรทัดสุดท้าย, check = True/False → OK/NG"""
        self.n_eq += 1
        rows = []
        for i, ln in enumerate(lines):
            last = i == len(lines) - 1
            no = f"({self.n_eq})" if last else ""
            badge = ""
            if last and check is not None:
                badge = (' <span class="ok">OK</span>' if check
                         else ' <span class="ng">NG</span>')
            rows.append(f'<div class="eq"><div class="ref">{ref if i == 0 else ""}</div>'
                        f'<div class="body">{tex(_display(ln))}</div>'
                        f'<div class="no">{no}{badge}</div></div>')
        self.parts.append('<div class="eqg">' + "".join(rows) + "</div>")

    def html(self):
        return "\n".join(self.parts)


def section_svg(inp, fr, size=210):
    """รูปหน้าตัดพร้อมเหล็กเสริมและแกนสะเทิน (SVG ขาว-ดำ)"""
    b, h = inp.b, inp.h
    pad = 40
    k = (size - 2 * pad) / max(b, h)
    W, H = b * k + 2 * pad + 20, h * k + 2 * pad
    X = lambda x: pad + x * k  # noqa: E731
    Y = lambda y: pad + y * k  # noqa: E731  (y วัดจากผิวบนของรูป)
    top_tension = inp.Mu < 0
    o = inp.cover + inp.ds / 2
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
         f'viewBox="0 0 {W:.1f} {H:.1f}" font-family="THSarabunPSK, serif" font-size="14">',
         '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#aaa" '
         'stroke-width="0.6"/></pattern></defs>',
         f'<rect x="{X(0):.1f}" y="{Y(0):.1f}" width="{b * k:.1f}" height="{h * k:.1f}" '
         'fill="url(#hatch)" stroke="#000" stroke-width="1.1"/>',
         f'<rect x="{X(o):.1f}" y="{Y(o):.1f}" width="{(b - 2 * o) * k:.1f}" '
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
            s.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" '
                     f'r="{max(1.5, L.db / 2 * k):.1f}" fill="{fill}" stroke="#000" '
                     'stroke-width="0.9"/>')
    na = (h - fr.c) if top_tension else fr.c
    s.append(f'<line x1="{X(0) - 6:.1f}" x2="{X(b) + 6:.1f}" y1="{Y(na):.1f}" '
             f'y2="{Y(na):.1f}" stroke="#000" stroke-dasharray="6 2 1 2" stroke-width="0.7"/>')
    s.append(f'<text x="{X(b) + 9:.1f}" y="{Y(na) + 4:.1f}">N.A.</text>')
    yb = Y(h) + 16
    xh = X(0) - 16
    s.append(f'<line x1="{X(0):.1f}" x2="{X(b):.1f}" y1="{yb:.1f}" y2="{yb:.1f}" '
             'stroke="#000" stroke-width="0.5"/>')
    s.append(f'<line x1="{xh:.1f}" x2="{xh:.1f}" y1="{Y(0):.1f}" y2="{Y(h):.1f}" '
             'stroke="#000" stroke-width="0.5"/>')
    for xx in (X(0), X(b)):
        s.append(f'<line x1="{xx - 3:.1f}" x2="{xx + 3:.1f}" y1="{yb + 3:.1f}" '
                 f'y2="{yb - 3:.1f}" stroke="#000" stroke-width="0.8"/>')
    for yy in (Y(0), Y(h)):
        s.append(f'<line x1="{xh - 3:.1f}" x2="{xh + 3:.1f}" y1="{yy + 3:.1f}" '
                 f'y2="{yy - 3:.1f}" stroke="#000" stroke-width="0.8"/>')
    s.append(f'<text x="{(X(0) + X(b)) / 2:.1f}" y="{yb + 14:.1f}" text-anchor="middle">'
             f'{b:.0f}</text>')
    s.append(f'<text transform="translate({xh - 5:.1f},{(Y(0) + Y(h)) / 2:.1f}) rotate(-90)"'
             f' text-anchor="middle">{h:.0f}</text>')
    s.append("</svg>")
    return "".join(s)


def _flexure(D, inp, fr, design):
    fc, fy, b = inp.fc, inp.fy, inp.b
    Mu = abs(inp.Mu)
    side = "ล่าง" if inp.Mu >= 0 else "บน"
    D.h("2", "ออกแบบรับแรงดัด", "Flexural Design")
    D.p(f"โมเมนต์ประลัยทำให้ผิว{side}ของคานรับแรงดึง วัดระยะ y ลงจากผิวรับแรงอัด "
        "และแรงในเหล็กมีค่าเป็นบวกเมื่อเป็นแรงอัด")
    D.eq(rf"M_u = {_n(u.nmm_to_kgfm(Mu), 0)}\ \mathrm{{kgf\cdot m}} = "
         rf"{_n(Mu / 1e6)}\ \mathrm{{kN\cdot m}}")

    D.h3("2.1 ค่าคงที่ของวัสดุและหน้าตัด")
    if fc <= 28.0:
        D.eq(rf"\beta_1 = 0.85 \qquad ({FC} = {_n(fc)}\ \mathrm{{MPa}} \leq 28\ \mathrm{{MPa}})",
             ref="ACI 22.2.2.4.3")
    else:
        D.eq(rf"\beta_1 = 0.85-\frac{{0.05\,({FC}-28)}}{{7}} = "
             rf"0.85-\frac{{0.05\,({_n(fc)}-28)}}{{7}} \geq 0.65",
             rf"\beta_1 = {fr.beta1:.3f}", ref="ACI 22.2.2.4.3")
    if inp.grade420:
        D.eq(r"\varepsilon_{ty} = 0.002 \qquad (\mathrm{Grade\ 420})", ref="ACI 21.2.2.1")
    else:
        D.eq(rf"\varepsilon_{{ty}} = \frac{{f_y}}{{E_s}} = \frac{{{_n(fy)}}}{{200{{,}}000}}"
             rf" = {fr.ety:.5f}", ref="ACI 21.2.2.1")
    D.eq(rf"d = {_n(fr.d, 1)}\ \mathrm{{mm}}, \qquad d_t = {_n(fr.dt, 1)}\ \mathrm{{mm}}")
    D.p("d = ระยะถึงจุดศูนย์ถ่วงเหล็กรับแรงดึง, d<sub>t</sub> = ระยะถึงเหล็กรับแรงดึงชั้นนอกสุด")
    D.eq(r"c_{\max} = \frac{0.003\,d_t}{0.003+\varepsilon_{ty}+0.003} = "
         rf"\frac{{0.003({_n(fr.dt, 1)})}}{{0.006+{fr.ety:.5f}}} = "
         rf"{_n(fr.cmax, 1)}\ \mathrm{{mm}}", ref="ACI 9.3.3.1")

    sub = 2
    if design is not None:
        D.h3("2.2 ปริมาณเหล็กเสริมที่ต้องการ")
        sub = 3
        if design.kind == "singly":
            a_req = design.As_req * fy / (0.85 * fc * b)
            D.eq(r"a = d-\sqrt{d^2-\frac{2M_u}{\phi\,0.85\,f^{\prime}_{c}\,b}}, \qquad "
                 rf"A_{{s,req}} = \frac{{0.85\,{FC}\,b\,a}}{{f_y}} \geq A_{{s,\min}}",
                 rf"a = {_n(a_req, 1)}\ \mathrm{{mm}}, \qquad "
                 rf"A_{{s,req}} = {_n(design.As_req / 100)}\ \mathrm{{cm^2}}",
                 ref="สมดุลแรง")
        else:
            D.p("หน้าตัดเสริมเหล็กรับแรงดึงอย่างเดียวไม่ผ่าน จึงเสริมเหล็กรับแรงอัด "
                "(ค่าเริ่มต้นประมาณที่ c = c<sub>max</sub>)")
            D.eq(r"A^{\prime}_{s} = \frac{M_u/\phi - M_{n1}}{(f^{\prime}_{s}-0.85\,"
                 r"f^{\prime}_{c})\,(d-d^{\prime})}, \qquad A_s = \frac{C_c + A^{\prime}_{s}"
                 r"(f^{\prime}_{s}-0.85\,f^{\prime}_{c})}{f_y}",
                 rf"A_{{s,req}} = {_n(design.As_req / 100)}\ \mathrm{{cm^2}}, \qquad "
                 rf"A^{{\prime}}_{{s,req}} = {_n(design.Asc_req / 100)}\ \mathrm{{cm^2}}",
                 ref="สมดุลแรง")
        for n in design.notes:
            D.p(f"<i>หมายเหตุ: {_e(n)}</i>")

    D.h3(f"2.{sub} วิเคราะห์หน้าตัดด้วย strain compatibility")
    D.p("หาค่า c ที่ทำให้ผลรวมแรงเป็นศูนย์ โดยคำนวณความเครียดและหน่วยแรงของเหล็กทุกชั้นใหม่"
        "ทุกครั้งที่ลองค่า c (bisection)")
    D.eq(r"0.85\,f^{\prime}_{c}\,b\,\beta_1 c + \sum_i A_{si}\,f_{si} = 0, \qquad "
         r"f_{si} = E_s\,\varepsilon_{si} \leq f_y, \qquad "
         r"\varepsilon_{si} = 0.003\,\frac{c-y_i}{c}",
         rf"c = {_n(fr.c, 1)}\ \mathrm{{mm}}, \qquad a = \beta_1 c = "
         rf"{_n(fr.a, 1)}\ \mathrm{{mm}}", ref="ACI 22.2.1–22.2.2")
    D.eq(rf"C_c = 0.85\,{FC}\,b\,a = 0.85({_n(fc)})({b:.0f})({_n(fr.a, 1)}) = "
         rf"{_n(fr.Cc / 1e3, 1)}\ \mathrm{{kN}}", ref="ACI 22.2.2.4.1")

    hdr = "".join(f"<th>{tex(x, 10)}</th>" for x in (
        r"\mathrm{Bars}", r"y\ (\mathrm{mm})", r"A_s\ (\mathrm{cm^2})", r"\varepsilon_s",
        r"f_s\ (\mathrm{MPa})", r"F\ (\mathrm{kN})")) + "<th>หมายเหตุ</th>"
    trs = []
    for st in fr.steel:
        L = st.layer
        note = ("ใน stress block หัก 0.85f′c" if st.in_block else
                ("a &lt; y &lt; c ไม่หักคอนกรีต" if st.fs > 0 else "รับแรงดึง"))
        trs.append(f"<tr><td>{L.n}-DB{L.db:g} ({'อัด' if L.role == 'compression' else 'ดึง'})"
                   f"</td><td>{L.y:.1f}</td><td>{L.area / 100:.2f}</td><td>{st.eps:+.5f}</td>"
                   f"<td>{st.fs:+.1f}</td><td>{st.force / 1e3:+.1f}</td><td>{note}</td></tr>")
    D.raw('<table class="bt num"><caption>ตารางที่ 1 ความเครียดและแรงในเหล็กเสริม</caption>'
          f"<thead><tr>{hdr}</tr></thead><tbody>{''.join(trs)}</tbody></table>")

    D.eq(r"M_n = -\left(C_c\,\frac{a}{2} + \sum_i F_i\,y_i\right) = "
         rf"{_n(fr.Mn / 1e6)}\ \mathrm{{kN\cdot m}}", ref="ACI 22.3.1.1")
    D.eq(rf"\varepsilon_t = 0.003\,\frac{{d_t-c}}{{c}} = 0.003\,"
         rf"\frac{{{_n(fr.dt, 1)}-{_n(fr.c, 1)}}}{{{_n(fr.c, 1)}}} = {fr.et:.5f}\ "
         rf"{_ge(fr.strain_ok)}\ \varepsilon_{{ty}}+0.003 = {fr.et_limit:.5f}",
         ref="ACI 9.3.3.1", check=fr.strain_ok)
    if fr.et >= fr.ety + 0.003:
        D.eq(r"\phi = 0.90 \qquad (\mathrm{tension\ controlled})", ref="ACI Table 21.2.2")
    elif fr.et <= fr.ety:
        D.eq(r"\phi = 0.65 \qquad (\mathrm{compression\ controlled})", ref="ACI Table 21.2.2")
    else:
        D.eq(r"\phi = 0.65+0.25\,\frac{\varepsilon_t-\varepsilon_{ty}}{0.003} = "
             rf"{fr.phi:.3f}", ref="ACI Table 21.2.2")
    ok = fr.phiMn >= Mu - 1e-6
    D.eq(rf"\phi M_n = {fr.phi:.3f}({_n(fr.Mn / 1e6)}) = {_n(fr.phiMn / 1e6)}\ "
         rf"\mathrm{{kN\cdot m}} = {_n(u.nmm_to_kgfm(fr.phiMn), 0)}\ \mathrm{{kgf\cdot m}}"
         rf"\ {_ge(ok)}\ M_u", ref="ACI 9.5.1.1(a)", check=ok)
    D.eq(rf"A_{{s,\min}} = \max\left(\frac{{0.25{SQFC}}}{{f_y}},\ \frac{{1.4}}{{f_y}}\right)"
         rf"b_w d = {_n(fr.As_min / 100)}\ \mathrm{{cm^2}}\ {_le(fr.as_min_ok)}\ "
         rf"A_s = {_n(fr.As / 100)}\ \mathrm{{cm^2}}", ref="ACI 9.6.1.2",
         check=fr.as_min_ok)


def _shear(D, inp, sr):
    rf = sqrt_fc(inp.fc)
    v = sr.vcs
    bw, d = sr.bw, sr.d
    D.h("3", "ออกแบบรับแรงเฉือน", "Shear Design")
    D.p("แรงเฉือนประลัยคิดที่" + ("ระยะ d จากผิวรองรับ (ต้องเข้าเงื่อนไข ACI 9.4.3.2)"
                                   if inp.crit_at_d else "ผิวรองรับ"))
    D.eq(rf"V_u = {_n(u.n_to_kgf(sr.Vu), 0)}\ \mathrm{{kgf}} = {_n(sr.Vu / 1e3, 1)}\ "
         rf"\mathrm{{kN}}, \qquad b_w = {bw:.0f}\ \mathrm{{mm}}, \qquad d = {_n(d, 1)}\ "
         r"\mathrm{mm}",
         rf"{SQFC} = {rf:.3f}\ \mathrm{{MPa}} \leq 8.3\ \mathrm{{MPa}}",
         ref="ACI 22.5.3.1")
    D.eq(r"\frac{A_{v,\min}}{s} = \max\left(0.062\sqrt{f^{\prime}_{c}}\,\frac{b_w}{f_{yt}},\ "
         rf"0.35\,\frac{{b_w}}{{f_{{yt}}}}\right) = {sr.Av_min_s:.4f}\ \mathrm{{mm^2/mm}}",
         ref="ACI Table 9.6.3.4")
    thr = 0.083 * PHI_V * rf * bw * d
    D.eq(rf"0.083\,\phi\lambda{SQFC}\,b_w d = {_n(thr / 1e3, 1)}\ \mathrm{{kN}}\ "
         rf"{_ge(not sr.min_required)}\ V_u", ref="ACI 9.6.3.1")
    D.p("ต้องใส่ปลอกไม่น้อยกว่าปริมาณขั้นต่ำ" if sr.min_required
        else "ไม่บังคับปลอกขั้นต่ำตามการคำนวณ")
    D.eq(rf"\rho_w = \frac{{A_s}}{{b_w d}} = {v['rho_w']:.5f}, \qquad "
         rf"\lambda_s = \sqrt{{\frac{{2}}{{1+d/250}}}} = {v['lambda_s']:.4f} \leq 1",
         ref="ACI 22.5.5.1.3")
    D.eq(rf"(a)\ \ V_c = 0.17\,\lambda{SQFC}\,b_w d = {_n(v['a'] / 1e3, 1)}\ \mathrm{{kN}}",
         rf"(b)\ \ V_c = 0.66\,\lambda\,\rho_w^{{1/3}}{SQFC}\,b_w d = "
         rf"{_n(v['b'] / 1e3, 1)}\ \mathrm{{kN}}",
         rf"(c)\ \ V_c = 0.66\,\lambda_s\lambda\,\rho_w^{{1/3}}{SQFC}\,b_w d = "
         rf"{_n(v['c'] / 1e3, 1)}\ \mathrm{{kN}}",
         rf"V_c \leq 0.42\,\lambda{SQFC}\,b_w d = {_n(v['cap'] / 1e3, 1)}\ \mathrm{{kN}}",
         ref="ACI Table 22.5.5.1")
    why = (r"A_v/s \geq A_{v,\min}/s" if sr.vc_eq != "c" else r"A_v/s < A_{v,\min}/s")
    D.eq(rf"\mathrm{{eq.}}\ ({sr.vc_eq}):\ \ {why} \quad\Rightarrow\quad "
         rf"V_c = {_n(sr.Vc / 1e3, 1)}\ \mathrm{{kN}}", ref="ACI Table 22.5.5.1")
    D.eq(rf"V_{{s,req}} = \frac{{V_u}}{{\phi}}-V_c = \frac{{{_n(sr.Vu / 1e3, 1)}}}{{0.75}}-"
         rf"{_n(sr.Vc / 1e3, 1)} = {_n(sr.Vs_req / 1e3, 1)}\ \mathrm{{kN}}")
    if sr.s > 0:
        D.eq(rf"A_v = {inp.legs}\times\frac{{\pi\,({inp.ds:g})^2}}{{4}} = {_n(sr.Av, 1)}\ "
             rf"\mathrm{{mm^2}}, \qquad V_s = \frac{{A_v f_{{yt}} d}}{{s}} = "
             rf"\frac{{{_n(sr.Av, 1)}({_n(inp.fyt, 1)})({_n(d, 1)})}}{{{sr.s:.0f}}} = "
             rf"{_n(sr.Vs / 1e3, 1)}\ \mathrm{{kN}}", ref="ACI 22.5.8.5.3")
        if sr.min_required:
            D.eq(rf"\frac{{A_v}}{{s}} = {sr.Av / sr.s:.4f}\ {_ge(sr.av_min_ok)}\ "
                 rf"\frac{{A_{{v,\min}}}}{{s}} = {sr.Av_min_s:.4f}", ref="ACI 9.6.3.1",
                 check=sr.av_min_ok)
        D.eq(rf"s = {sr.s:.0f}\ \mathrm{{mm}}\ {_le(sr.spacing_ok)}\ "
             rf"s_{{\max}} = {sr.s_max:.0f}\ \mathrm{{mm}}", ref="ACI Table 9.7.6.2.2",
             check=sr.spacing_ok)
    else:
        D.eq(r"V_s = 0 \qquad (\mathrm{no\ stirrups})")
    D.eq(rf"\phi V_n = 0.75\,(V_c+V_s) = {_n(sr.phiVn / 1e3, 1)}\ \mathrm{{kN}} = "
         rf"{_n(u.n_to_kgf(sr.phiVn), 0)}\ \mathrm{{kgf}}\ {_ge(sr.strength_ok)}\ V_u",
         ref="ACI 9.5.1.1(b)", check=sr.strength_ok)
    D.eq(rf"V_u\ {_le(sr.section_ok)}\ \phi\left(V_c+0.66{SQFC}\,b_w d\right) = "
         rf"{_n(sr.section_limit / 1e3, 1)}\ \mathrm{{kN}}", ref="ACI 22.5.1.2",
         check=sr.section_ok)
    for n in sr.notes:
        D.p(f"<i>หมายเหตุ: {_e(n)}</i>")


def _status(s):
    cls = {PASS: "ok", FAIL: "ng"}.get(s, "nc")
    return f'<span class="{cls}">{_e(s)}</span>'


CSS = """
@page { size: A4 portrait; margin: 16mm 16mm 18mm 22mm;
  @bottom-center { content: "– " counter(page) " / " counter(pages) " –";
    font-family: "THSarabunPSK", serif; font-size: 13pt; } }
* { box-sizing: border-box; }
html, body { margin: 0; background: #fff; color: #000; }
body { font-family: "THSarabunPSK", "Times New Roman", serif; font-size: 15pt;
  line-height: 1.12; }
.sheet { width: 210mm; margin: 0 auto; padding: 16mm 16mm 18mm 22mm; background: #fff; }
@media screen { html { background: #7a7a7a; }
  .sheet { margin: 14px auto; box-shadow: 0 2px 10px #0006; }
  .toolbar { position: sticky; top: 0; z-index: 9; background: #2b2b2b; padding: 8px;
    text-align: center; }
  .toolbar button { font-family: inherit; font-size: 16pt; padding: 2px 22px;
    cursor: pointer; } }
@media print { .toolbar { display: none; }
  .sheet { width: auto; margin: 0; padding: 0; box-shadow: none; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
table { border-collapse: collapse; }
table.page { width: 100%; }
table.page > thead > tr > td, table.page > tbody > tr > td { padding: 0; }
.runhead { display: flex; justify-content: space-between; font-size: 13pt; font-style: italic;
  border-bottom: 0.6pt solid #000; padding-bottom: 1px; margin-bottom: 8px; }
.title { text-align: center; margin: 4px 0 2px; }
.title .t1 { font-size: 24pt; font-weight: 700; line-height: 1.05; }
.title .t2 { font-size: 16pt; font-style: italic; }
table.info { width: 100%; margin: 6px 0 4px; border-top: 1.2pt solid #000;
  border-bottom: 1.2pt solid #000; font-size: 14pt; }
table.info td { padding: 0 6px; }
table.info td.k { font-weight: 700; width: 13%; white-space: nowrap; }
h2 { font-size: 18pt; font-weight: 700; margin: 14px 0 2px; break-after: avoid; }
h2 .secno { display: inline-block; min-width: 1.3em; }
h2 .en { font-weight: 400; font-style: italic; font-size: 15pt; margin-left: 10px;
  color: #333; }
h3 { font-size: 15.5pt; font-weight: 700; margin: 8px 0 1px; break-after: avoid; }
p { margin: 1px 0 3px; text-align: justify; }
img.m { vertical-align: middle; max-width: 100%; height: auto !important; }
.eqg { margin: 3px 0 5px; break-inside: avoid; }
.eq { display: grid; grid-template-columns: 25mm 1fr 19mm; align-items: center;
  min-height: 20px; }
.eq .ref { font-size: 12pt; font-style: italic; color: #333; line-height: 1; }
.eq .body { text-align: center; padding: 1px 4px; }
.eq .no { text-align: right; white-space: nowrap; font-size: 14pt; }
table.bt { margin: 4px auto 8px; border-top: 1.2pt solid #000;
  border-bottom: 1.2pt solid #000; font-size: 14pt; break-inside: avoid; }
table.bt caption { caption-side: top; font-size: 14pt; padding-bottom: 2px; }
table.bt thead tr { border-bottom: 0.6pt solid #000; }
table.bt th, table.bt td { padding: 0 8px; }
table.bt th { font-weight: 700; }
table.num td:not(:first-child):not(:last-child) { text-align: right;
  font-variant-numeric: tabular-nums; }
table.full { width: 100%; }
table.full td:nth-child(3) { text-align: center; white-space: nowrap; }
.datawrap { display: flex; gap: 6px; align-items: center; justify-content: space-between;
  break-inside: avoid; }
table.data td:first-child { padding-right: 14px; }
.fig { text-align: center; font-size: 14pt; line-height: 1.05; }
.gr { font-family: "Times New Roman", "Liberation Serif", serif; font-size: 0.74em; }
.ok, .ng, .nc { font-weight: 700; font-size: 12.5pt; padding: 0 4px; border: 0.8pt solid; }
.ok { color: #0b5d1e; } .ng { color: #a3001b; } .nc { color: #7a5a00; border-style: dashed; }
.result { margin: 8px 0; padding: 2px 10px; border-left: 3pt solid #000; background: #f2f2f2;
  break-inside: avoid; }
ul.notes { margin: 2px 0 0 18px; padding: 0; font-size: 14pt; }
table.sign { width: 100%; margin-top: 22px; break-inside: avoid; text-align: center; }
table.sign td { width: 33.3%; padding-top: 24px; vertical-align: bottom; font-size: 14pt; }
.cert { font-size: 12.5pt; color: #444; margin-top: 10px; text-align: center; }
"""


def build_calsheet(title, proj, inp, fr, sr, summary, steel_text, stirrup_text,
                   design=None):
    """คืนค่า HTML ทั้งหน้าสำหรับพิมพ์ A4"""
    p = proj or ProjectInfo()
    Mu = abs(inp.Mu)
    D = _Doc()

    D.raw(f"""
<div class="title"><div class="t1">รายการคำนวณออกแบบคานคอนกรีตเสริมเหล็ก</div>
<div class="t2">Reinforced Concrete Beam Design — ACI 318M-19</div></div>
<table class="info">
<tr><td class="k">โครงการ</td><td>{_e(p.project) or '–'}</td>
    <td class="k">ชื่อคาน</td><td>{_e(p.member) or '–'}</td></tr>
<tr><td class="k">สถานที่</td><td>{_e(p.location) or '–'}</td>
    <td class="k">ตำแหน่ง</td><td>{_e(p.grid) or '–'}</td></tr>
<tr><td class="k">ผู้คำนวณ</td><td>{_e(p.designer) or '–'}</td>
    <td class="k">วันที่</td><td>{_e(p.date) or '–'}</td></tr>
</table>""")

    D.h("1", "ข้อมูลออกแบบ", "Design Data")
    ksc = lambda x: rf"{u.mpa_to_ksc(x):.0f}\ \mathrm{{ksc}} = {_n(x)}\ \mathrm{{MPa}}"  # noqa: E731
    rows = [
        ("หน้าตัด", r"b \times h", rf"{inp.b:.0f} \times {inp.h:.0f}\ \mathrm{{mm}}"),
        ("ระยะหุ้ม", r"c_c", rf"{inp.cover:.0f}\ \mathrm{{mm}}"),
        ("เหล็กปลอก", r"d_s", rf"{inp.ds:g}\ \mathrm{{mm}},\ {inp.legs}\ \mathrm{{legs}}"),
        ("ขนาดหินใหญ่สุด", r"d_{agg}", rf"{inp.dagg:.0f}\ \mathrm{{mm}}"),
        ("กำลังอัดคอนกรีต", FC, ksc(inp.fc)),
        ("กำลังครากเหล็กหลัก", r"f_y", ksc(inp.fy)),
        ("กำลังครากเหล็กปลอก", r"f_{yt}", ksc(inp.fyt)),
        ("โมดูลัสเหล็ก", r"E_s", r"200{,}000\ \mathrm{MPa}"),
        ("โมเมนต์ประลัย", r"M_u", rf"{_n(u.nmm_to_kgfm(Mu), 0)}\ \mathrm{{kgf\cdot m}}"),
        ("แรงเฉือนประลัย", r"V_u", rf"{_n(u.n_to_kgf(inp.Vu), 0)}\ \mathrm{{kgf}}"),
    ]
    trs = "".join(f"<tr><td>{a}</td><td>{tex(s, 10.5)}</td><td>{tex(v, 10.5)}</td></tr>"
                  for a, s, v in rows)
    D.raw(f"""<div class="datawrap">
<table class="bt data"><thead><tr><th style="text-align:left">รายการ</th><th>สัญลักษณ์</th>
<th style="text-align:left">ค่า</th></tr></thead><tbody>{trs}</tbody></table>
<div class="fig">{section_svg(inp, fr)}<br>รูปที่ 1 หน้าตัดคาน (มม.)<br>
<span style="font-size:13pt">● เหล็กรับแรงดึง &nbsp; ○ เหล็กรับแรงอัด</span></div></div>
<div class="result"><b>ผลออกแบบ:</b> {_e(steel_text)}<br>
<b>เหล็กปลอก:</b> {_e(stirrup_text)}</div>""")

    _flexure(D, inp, fr, design)
    _shear(D, inp, sr)

    D.h("4", "สรุปผลการตรวจสอบ", "Summary")
    srows = "".join(f"<tr><td>{_e(a)}</td><td>{_e(b)}</td><td>{_status(c)}</td>"
                    f"<td>{_e(d)}</td></tr>" for a, b, c, d in summary)
    D.raw('<table class="bt full"><thead><tr><th style="text-align:left">รายการ</th>'
          '<th style="text-align:left">ค่า</th><th>สถานะ</th><th style="text-align:left">'
          f"อ้างอิง ACI 318M-19</th></tr></thead><tbody>{srows}</tbody></table>")

    D.h("5", "สมมติฐานและขอบเขต", "Assumptions")
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
</tr></table>
<div class="cert">เอกสารนี้ใช้ประกอบรายการคำนวณ วิศวกรผู้รับผิดชอบต้องตรวจสอบและลงนามก่อนใช้งาน</div>""")

    run_l = "รายการคำนวณคาน คสล. · ACI 318M-19"
    run_r = " · ".join(x for x in (_e(p.project), _e(p.member)) if x) or _e(title)
    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calsheet {_e(p.member or 'Beam')}</title>
<style>{font_css()}
{CSS}</style></head>
<body>
<div class="toolbar"><button onclick="window.print()">พิมพ์ / Save as PDF (A4)</button></div>
<div class="sheet">
<table class="page"><thead><tr><td>
<div class="runhead"><span>{run_l}</span><span>{run_r}</span></div>
</td></tr></thead>
<tbody><tr><td>
{_greek(D.html())}
</td></tr></tbody></table>
</div>
</body></html>"""
