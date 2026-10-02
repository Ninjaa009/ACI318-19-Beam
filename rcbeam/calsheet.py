"""แผ่นรายการคำนวณ (Calsheet) ขนาด A4 เป็น HTML สำหรับพิมพ์ / Save as PDF จากเบราว์เซอร์

รูปแบบ 3 คอลัมน์: อ้างอิง | รายการคำนวณ | ผล
"""
from dataclasses import dataclass, field
from html import escape

from . import units as u
from .shear import PHI_V, sqrt_fc
from .report import PASS, FAIL, kgfm, kgf, cm2


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


def _e(x):
    return escape(str(x))


def _badge(ok):
    return ('<span class="ok">OK</span>' if ok else '<span class="ng">NG</span>')


def _status_badge(s):
    cls = {PASS: "ok", FAIL: "ng"}.get(s, "nc")
    return f'<span class="{cls}">{_e(s)}</span>'


def section_svg(inp, fr, size=230):
    """รูปหน้าตัดพร้อมเหล็กเสริมและแกนสะเทิน (SVG)"""
    b, h = inp.b, inp.h
    pad = 46
    k = (size - 2 * pad) / max(b, h)
    W, H = b * k + 2 * pad, h * k + 2 * pad
    X = lambda x: pad + x * k  # noqa: E731
    Y = lambda y: pad + y * k  # noqa: E731  (y วัดจากผิวบน)
    top_tension = inp.Mu < 0
    o = inp.cover + inp.ds / 2
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
         f'viewBox="0 0 {W:.1f} {H:.1f}" font-family="inherit" font-size="10">',
         f'<rect x="{X(0):.1f}" y="{Y(0):.1f}" width="{b * k:.1f}" height="{h * k:.1f}" '
         'fill="#eee" stroke="#000" stroke-width="1.2"/>',
         f'<rect x="{X(o):.1f}" y="{Y(o):.1f}" width="{(b - 2 * o) * k:.1f}" '
         f'height="{(h - 2 * o) * k:.1f}" rx="{2 * inp.ds * k:.1f}" fill="none" '
         f'stroke="#444" stroke-width="{max(0.8, inp.ds * k):.1f}"/>']
    for st in fr.steel:
        L = st.layer
        y = (h - L.y) if top_tension else L.y          # y จากผิวบนของรูป
        x0 = inp.cover + inp.ds + L.db / 2
        x1 = b - x0
        xs = [x0] if L.n == 1 else [x0 + i * (x1 - x0) / (L.n - 1) for i in range(L.n)]
        fill = "#000" if L.role == "tension" else "#fff"
        for x in xs:
            s.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="{max(1.5, L.db / 2 * k):.1f}"'
                     f' fill="{fill}" stroke="#000" stroke-width="1"/>')
    na = (h - fr.c) if top_tension else fr.c
    s.append(f'<line x1="{X(0) - 8:.1f}" x2="{X(b) + 8:.1f}" y1="{Y(na):.1f}" '
             f'y2="{Y(na):.1f}" stroke="#000" stroke-dasharray="4 3" stroke-width="0.8"/>')
    s.append(f'<text x="{X(b) + 10:.1f}" y="{Y(na) + 3:.1f}">N.A.</text>')
    # มิติ
    yb = Y(h) + 18
    s.append(f'<line x1="{X(0):.1f}" x2="{X(b):.1f}" y1="{yb:.1f}" y2="{yb:.1f}" '
             'stroke="#000" stroke-width="0.6"/>')
    s.append(f'<text x="{(X(0) + X(b)) / 2:.1f}" y="{yb + 13:.1f}" text-anchor="middle">'
             f'b = {b:.0f}</text>')
    xh = X(0) - 18
    s.append(f'<line x1="{xh:.1f}" x2="{xh:.1f}" y1="{Y(0):.1f}" y2="{Y(h):.1f}" '
             'stroke="#000" stroke-width="0.6"/>')
    s.append(f'<text transform="translate({xh - 5:.1f},{(Y(0) + Y(h)) / 2:.1f}) rotate(-90)"'
             f' text-anchor="middle">h = {h:.0f}</text>')
    for yy in (Y(0), Y(h)):
        s.append(f'<line x1="{xh - 4:.1f}" x2="{xh + 4:.1f}" y1="{yy:.1f}" y2="{yy:.1f}" '
                 'stroke="#000" stroke-width="0.6"/>')
    for xx in (X(0), X(b)):
        s.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{yb - 4:.1f}" y2="{yb + 4:.1f}" '
                 'stroke="#000" stroke-width="0.6"/>')
    s.append("</svg>")
    return "".join(s)


def _rows_html(rows):
    out = []
    for ref, calc, res in rows:
        if ref == "##":
            out.append(f'<tr class="sub"><td colspan="3">{calc}</td></tr>')
        else:
            out.append(f'<tr><td class="ref">{ref}</td><td class="calc">{calc}</td>'
                       f'<td class="res">{res}</td></tr>')
    return "\n".join(out)


def _flexure_rows(inp, fr, design):
    fc, fy, b = inp.fc, inp.fy, inp.b
    Mu = abs(inp.Mu)
    side = "ล่าง" if inp.Mu >= 0 else "บน"
    R = []
    R.append(("", f"M<sub>u</sub> = {kgfm(Mu)} = {Mu / 1e6:.2f} kN·m "
                  f"→ เหล็กรับแรงดึงอยู่ด้าน{side}", ""))
    R.append(("§22.2.2.4.3", f"β<sub>1</sub> = {fr.beta1:.3f} "
              f"(f′c = {fc:.2f} MPa)", ""))
    if inp.grade420:
        R.append(("§21.2.2.1", "ε<sub>ty</sub> = 0.002 (ข้อยกเว้นเหล็ก Grade 420)", ""))
    else:
        R.append(("§21.2.2.1", f"ε<sub>ty</sub> = f<sub>y</sub>/E<sub>s</sub> = "
                  f"{fy:.2f}/200,000 = {fr.ety:.5f}", ""))
    R.append(("", f"d = {fr.d:.1f} mm (จุดศูนย์ถ่วงเหล็กดึง), "
                  f"d<sub>t</sub> = {fr.dt:.1f} mm (ชั้นนอกสุด)", ""))
    if design is not None:
        if design.kind == "singly":
            R.append(("สมดุล", "a = d − √(d² − 2M<sub>u</sub>/(φ·0.85f′c·b)), "
                      "A<sub>s,req</sub> = 0.85f′c·b·a/f<sub>y</sub> "
                      "(ไม่น้อยกว่า A<sub>s,min</sub>)",
                      f"A<sub>s,req</sub> = {cm2(design.As_req)}"))
        else:
            R.append(("สมดุล", "ประมาณค่าที่ c = c<sub>max</sub>: "
                      "A′<sub>s</sub> = (M<sub>n,req</sub> − M<sub>n1</sub>)/"
                      "[(f′<sub>s</sub> − 0.85f′c)(d − d′)], "
                      "A<sub>s</sub> = (C<sub>c</sub> + A′<sub>s</sub>(f′<sub>s</sub> − 0.85f′c))/f<sub>y</sub>",
                      f"A<sub>s,req</sub> = {cm2(design.As_req)}<br>"
                      f"A′<sub>s,req</sub> = {cm2(design.Asc_req)}"))
        for n in design.notes:
            R.append(("", f"<i>{_e(n)}</i>", ""))
    R.append(("§9.3.3.1", "c<sub>max</sub> = 0.003·d<sub>t</sub>/(0.003 + ε<sub>ty</sub> + 0.003)"
              f" = 0.003×{fr.dt:.1f}/(0.006 + {fr.ety:.5f})", f"{fr.cmax:.1f} mm"))
    R.append(("§22.2.1.1–2", "หาค่า c จากสมดุลแรง ΣF(c) = 0 พร้อม strain compatibility "
              "(คำนวณหน่วยแรงเหล็กทุกชั้นทุกครั้งที่ลองค่า c)",
              f"c = {fr.c:.1f} mm"))
    R.append(("§22.2.2.4.1", f"a = β<sub>1</sub>c = {fr.beta1:.3f}×{fr.c:.1f}",
              f"a = {fr.a:.1f} mm"))
    R.append(("§22.2.2.4.1", f"C<sub>c</sub> = 0.85f′c·b·a = 0.85×{fc:.2f}×{b:.0f}×"
              f"{fr.a:.1f}", f"{fr.Cc / 1e3:.1f} kN"))
    trs = []
    for st in fr.steel:
        L = st.layer
        note = ("ใน stress block (หัก 0.85f′c)" if st.in_block else
                ("a &lt; d′ &lt; c (ไม่หักคอนกรีต)" if st.fs > 0 else "ดึง"))
        trs.append(f"<tr><td>{L.n}-DB{L.db:g} ({'อัด' if L.role == 'compression' else 'ดึง'})</td>"
                   f"<td>{L.y:.1f}</td><td>{L.area / 100:.2f}</td><td>{st.eps:+.5f}</td>"
                   f"<td>{st.fs:+.1f}</td><td>{st.force / 1e3:+.1f}</td><td>{note}</td></tr>")
    R.append(("§20.2.2.1", "ε<sub>s</sub> = 0.003(c − y)/c, f<sub>s</sub> = E<sub>s</sub>ε<sub>s</sub>"
              " ≤ f<sub>y</sub>"
              '<table class="inner"><tr><th>เหล็ก</th><th>y (mm)</th><th>A (cm²)</th>'
              "<th>ε<sub>s</sub></th><th>f<sub>s</sub> (MPa)</th><th>F (kN)</th><th></th></tr>"
              + "".join(trs) + "</table>", ""))
    R.append(("§22.3.1.1", "M<sub>n</sub> = ΣF<sub>i</sub>·(แขนโมเมนต์)",
              f"M<sub>n</sub> = {fr.Mn / 1e6:.2f} kN·m"))
    R.append(("§9.3.3.1", f"ε<sub>t</sub> = 0.003(d<sub>t</sub> − c)/c = "
              f"0.003({fr.dt:.1f} − {fr.c:.1f})/{fr.c:.1f} = {fr.et:.5f} "
              f"{'≥' if fr.strain_ok else '&lt;'} ε<sub>ty</sub> + 0.003 = {fr.et_limit:.5f}",
              _badge(fr.strain_ok)))
    R.append(("Table 21.2.2", f"φ = {fr.phi:.3f}", ""))
    ok = fr.phiMn >= Mu - 1e-6
    R.append(("§9.5.1.1(a)", f"φM<sub>n</sub> = {fr.phi:.3f}×{fr.Mn / 1e6:.2f} = "
              f"<b>{fr.phiMn / 1e6:.2f} kN·m = {kgfm(fr.phiMn)}</b> "
              f"{'≥' if ok else '&lt;'} M<sub>u</sub> = {kgfm(Mu)}", _badge(ok)))
    R.append(("§9.6.1.2", "A<sub>s,min</sub> = max(0.25√f′c/f<sub>y</sub>, 1.4/f<sub>y</sub>)"
              f"·b<sub>w</sub>·d = {cm2(fr.As_min)}; A<sub>s</sub> = {cm2(fr.As)}",
              _badge(fr.as_min_ok)))
    return R


def _shear_rows(inp, sr):
    rf = sqrt_fc(inp.fc)
    v = sr.vcs
    R = []
    R.append(("§9.4.3.2" if inp.crit_at_d else "",
              f"V<sub>u</sub> = {kgf(sr.Vu)} = {sr.Vu / 1e3:.1f} kN "
              + ("(ที่ระยะ d จากผิวรองรับ)" if inp.crit_at_d else "(ที่ผิวรองรับ)"), ""))
    R.append(("§22.5.3.1", f"b<sub>w</sub> = {sr.bw:.0f} mm, d = {sr.d:.1f} mm, "
              f"√f′c = {rf:.3f} MPa (≤ 8.3)", ""))
    R.append(("Table 9.6.3.4", "A<sub>v,min</sub>/s = max(0.062√f′c·b<sub>w</sub>/f<sub>yt</sub>, "
              "0.35b<sub>w</sub>/f<sub>yt</sub>)", f"{sr.Av_min_s:.4f} mm²/mm"))
    thr = 0.083 * PHI_V * rf * sr.bw * sr.d
    R.append(("§9.6.3.1", f"0.083φλ√f′c·b<sub>w</sub>·d = {thr / 1e3:.1f} kN → "
              f"ปลอกขั้นต่ำ{'จำเป็น' if sr.min_required else 'ไม่จำเป็น'}", ""))
    R.append(("§22.5.5.1", f"ρ<sub>w</sub> = A<sub>s</sub>/(b<sub>w</sub>d) = {v['rho_w']:.5f}, "
              f"λ<sub>s</sub> = √(2/(1 + d/250)) = {v['lambda_s']:.4f}", ""))
    R.append(("Table 22.5.5.1",
              f"(a) 0.17λ√f′c·b<sub>w</sub>d = {v['a'] / 1e3:.1f} kN<br>"
              f"(b) 0.66λρ<sub>w</sub><sup>1/3</sup>√f′c·b<sub>w</sub>d = {v['b'] / 1e3:.1f} kN<br>"
              f"(c) 0.66λ<sub>s</sub>λρ<sub>w</sub><sup>1/3</sup>√f′c·b<sub>w</sub>d = "
              f"{v['c'] / 1e3:.1f} kN<br>เพดาน 0.42λ√f′c·b<sub>w</sub>d = {v['cap'] / 1e3:.1f} kN",
              ""))
    why = ("A<sub>v</sub>/s ≥ A<sub>v,min</sub>/s" if sr.vc_eq != "c"
           else "A<sub>v</sub>/s &lt; A<sub>v,min</sub>/s หรือไม่มีปลอก")
    R.append(("Table 22.5.5.1", f"ใช้สมการ ({sr.vc_eq}) เพราะ {why}",
              f"V<sub>c</sub> = {sr.Vc / 1e3:.1f} kN"))
    R.append(("", f"V<sub>s,req</sub> = V<sub>u</sub>/φ − V<sub>c</sub> = "
              f"{sr.Vu / 1e3:.1f}/0.75 − {sr.Vc / 1e3:.1f}", f"{sr.Vs_req / 1e3:.1f} kN"))
    if sr.s > 0:
        R.append(("§22.5.8.5.3", f"ปลอก {inp.legs} ขา Ø{inp.ds:g} @ {sr.s:.0f} mm: "
                  f"A<sub>v</sub> = {sr.Av:.1f} mm², V<sub>s</sub> = A<sub>v</sub>f<sub>yt</sub>d/s"
                  f" = {sr.Av:.1f}×{inp.fyt:.1f}×{sr.d:.1f}/{sr.s:.0f}",
                  f"V<sub>s</sub> = {sr.Vs / 1e3:.1f} kN"))
        if sr.min_required:
            R.append(("§9.6.3.1", f"A<sub>v</sub>/s = {sr.Av / sr.s:.4f} ≥ "
                      f"A<sub>v,min</sub>/s = {sr.Av_min_s:.4f}", _badge(sr.av_min_ok)))
        R.append(("Table 9.7.6.2.2", f"s = {sr.s:.0f} ≤ s<sub>max</sub> = {sr.s_max:.0f} mm",
                  _badge(sr.spacing_ok)))
    else:
        R.append(("", "ไม่มีปลอก: V<sub>s</sub> = 0", ""))
    R.append(("§9.5.1.1(b)", f"φV<sub>n</sub> = 0.75(V<sub>c</sub> + V<sub>s</sub>) = "
              f"<b>{sr.phiVn / 1e3:.1f} kN = {kgf(sr.phiVn)}</b> "
              f"{'≥' if sr.strength_ok else '&lt;'} V<sub>u</sub>", _badge(sr.strength_ok)))
    R.append(("§22.5.1.2", "V<sub>u</sub> ≤ φ(V<sub>c</sub> + 0.66√f′c·b<sub>w</sub>d) = "
              f"{sr.section_limit / 1e3:.1f} kN", _badge(sr.section_ok)))
    for n in sr.notes:
        R.append(("", f"<i>{_e(n)}</i>", ""))
    return R


CSS = """
@page { size: A4 portrait; margin: 14mm 12mm 16mm 18mm;
  @bottom-right { content: "หน้า " counter(page) " / " counter(pages); font-size: 8pt; }
  @bottom-left { content: "ACI 318M-19 · RC Beam"; font-size: 8pt; color: #555; } }
* { box-sizing: border-box; }
html, body { margin: 0; background: #fff; color: #000; }
body { font-family: "Sarabun", "TH Sarabun New", Tahoma, sans-serif; font-size: 10pt;
  line-height: 1.35; }
.sheet { width: 210mm; margin: 0 auto; padding: 14mm 12mm 16mm 18mm; background: #fff; }
@media screen { html { background: #888; } .sheet { margin: 12px auto; box-shadow: 0 2px 8px #0005; }
  .toolbar { position: sticky; top: 0; z-index: 9; background: #333; padding: 8px; text-align: center; }
  .toolbar button { font: inherit; font-size: 11pt; padding: 6px 18px; cursor: pointer; } }
@media print { .toolbar { display: none; } .sheet { width: auto; margin: 0; padding: 0; box-shadow: none; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
table { border-collapse: collapse; width: 100%; }
table.page > thead > tr > td, table.page > tbody > tr > td { padding: 0; border: 0; }
table.page > thead > tr > td { padding-bottom: 4px; }
.hdr td { border: 1px solid #000; padding: 2px 5px; font-size: 9pt; vertical-align: top; }
.hdr .t { font-size: 13pt; font-weight: 700; text-align: center; }
.hdr .k { color: #444; width: 17%; white-space: nowrap; }
h2 { font-size: 11pt; margin: 10px 0 3px; padding: 2px 5px; background: #e6e6e6;
  border-left: 4px solid #000; break-after: avoid; }
.calc-t td, .calc-t th { border: 1px solid #888; padding: 2px 5px; vertical-align: top; }
.calc-t th { background: #f2f2f2; font-weight: 600; }
.calc-t td.ref { width: 17%; font-size: 8.5pt; color: #333; }
.calc-t td.res { width: 20%; text-align: right; white-space: nowrap; }
.calc-t tr { break-inside: avoid; }
.calc-t tr.sub td { background: #fafafa; font-weight: 600; }
table.inner { margin: 3px 0; font-size: 8.5pt; }
table.inner td, table.inner th { border: 1px solid #bbb; padding: 1px 4px; text-align: right; }
table.inner td:first-child, table.inner td:last-child { text-align: left; }
.data { display: flex; gap: 10px; align-items: flex-start; break-inside: avoid; }
.data table td { border: 1px solid #888; padding: 2px 5px; }
.data table td:first-child { width: 42%; color: #333; }
.fig { text-align: center; font-size: 8.5pt; }
.result { border: 2px solid #000; padding: 5px 8px; margin: 6px 0; font-size: 10.5pt;
  break-inside: avoid; }
.ok { font-weight: 700; color: #0a6b22; } .ng { font-weight: 700; color: #b00020; }
.nc { color: #8a6d00; font-weight: 600; }
.summary td, .summary th { border: 1px solid #888; padding: 2px 5px; }
.summary th { background: #f2f2f2; }
.summary td:nth-child(3) { text-align: center; white-space: nowrap; }
ul.notes { margin: 3px 0 0 16px; padding: 0; font-size: 8.5pt; }
.sign { margin-top: 14px; break-inside: avoid; }
.sign td { border: 1px solid #000; height: 22mm; vertical-align: bottom; text-align: center;
  width: 33.3%; font-size: 9pt; padding-bottom: 3px; }
"""


def build_calsheet(title, proj, inp, fr, sr, summary, steel_text, stirrup_text,
                   design=None):
    """คืนค่า HTML ทั้งหน้าสำหรับพิมพ์ A4"""
    p = proj or ProjectInfo()
    Mu = abs(inp.Mu)
    hdr = f"""
<table class="hdr">
<tr><td colspan="4" class="t">รายการคำนวณออกแบบคาน คสล. (ACI 318M-19)</td></tr>
<tr><td class="k">โครงการ</td><td>{_e(p.project)}</td>
    <td class="k">ชื่อคาน</td><td>{_e(p.member)}</td></tr>
<tr><td class="k">สถานที่</td><td>{_e(p.location)}</td>
    <td class="k">ตำแหน่ง / Grid</td><td>{_e(p.grid)}</td></tr>
<tr><td class="k">ผู้คำนวณ</td><td>{_e(p.designer)}</td>
    <td class="k">วันที่</td><td>{_e(p.date)}</td></tr>
</table>"""

    data = f"""
<h2>1. ข้อมูลออกแบบ</h2>
<div class="data">
<table>
<tr><td>หน้าตัด b × h</td><td>{inp.b:.0f} × {inp.h:.0f} mm</td></tr>
<tr><td>ระยะหุ้ม (cover)</td><td>{inp.cover:.0f} mm</td></tr>
<tr><td>ปลอก</td><td>Ø{inp.ds:g} mm, {inp.legs} ขา</td></tr>
<tr><td>ขนาดหินใหญ่สุด</td><td>{inp.dagg:.0f} mm</td></tr>
<tr><td>f′c</td><td>{u.mpa_to_ksc(inp.fc):.0f} ksc ({inp.fc:.2f} MPa)</td></tr>
<tr><td>f<sub>y</sub> เหล็กหลัก</td><td>{u.mpa_to_ksc(inp.fy):.0f} ksc ({inp.fy:.2f} MPa)</td></tr>
<tr><td>f<sub>yt</sub> ปลอก</td><td>{u.mpa_to_ksc(inp.fyt):.0f} ksc ({inp.fyt:.2f} MPa)</td></tr>
<tr><td>E<sub>s</sub></td><td>200,000 MPa</td></tr>
<tr><td>M<sub>u</sub></td><td>{kgfm(Mu)} ({Mu / 1e6:.2f} kN·m), เหล็กดึงด้าน{'ล่าง' if inp.Mu >= 0 else 'บน'}</td></tr>
<tr><td>V<sub>u</sub></td><td>{kgf(inp.Vu)} ({inp.Vu / 1e3:.1f} kN)</td></tr>
</table>
<div class="fig">{section_svg(inp, fr)}<br>หน้าตัดคาน (mm) · ● เหล็กดึง ○ เหล็กอัด</div>
</div>
<div class="result"><b>สรุป:</b> {_e(title)} — {_e(steel_text)}; {_e(stirrup_text)}</div>"""

    flex = ('<h2>2. ออกแบบรับแรงดัด</h2><table class="calc-t">'
            "<tr><th>อ้างอิง</th><th>รายการคำนวณ</th><th>ผล</th></tr>"
            + _rows_html(_flexure_rows(inp, fr, design)) + "</table>")
    shear = ('<h2>3. ออกแบบรับแรงเฉือน</h2><table class="calc-t">'
             "<tr><th>อ้างอิง</th><th>รายการคำนวณ</th><th>ผล</th></tr>"
             + _rows_html(_shear_rows(inp, sr)) + "</table>")
    srows = "".join(f"<tr><td>{_e(a)}</td><td>{_e(b)}</td><td>{_status_badge(c)}</td>"
                    f"<td>{_e(d)}</td></tr>" for a, b, c, d in summary)
    summ = ('<h2>4. สรุปผลการตรวจสอบ</h2><table class="summary">'
            "<tr><th>รายการ</th><th>ค่า</th><th>สถานะ</th><th>อ้างอิง</th></tr>"
            + srows + "</table>")
    notes = f"""
<h2>5. สมมติฐานและขอบเขต</h2>
<ul class="notes">
<li>ACI 318M-19 (318-19(22) ไม่มีการเปลี่ยนแปลงทางเทคนิค); หน่วยภายใน MPa–mm–N แปลงผลเป็น kgf–m</li>
<li>สมดุลและ strain compatibility §22.2.1; ε<sub>cu</sub> = 0.003 และไม่คิดแรงดึงคอนกรีต §22.2.2;
stress block 0.85f′c §22.2.2.4; f<sub>s</sub> = E<sub>s</sub>ε<sub>s</sub> ≤ f<sub>y</sub> §20.2.2.1</li>
<li>ε<sub>ty</sub>: {'0.002 (ข้อยกเว้น Grade 420)' if inp.grade420 else 'f<sub>y</sub>/E<sub>s</sub>'};
Critical section แรงเฉือน: {'ที่ระยะ d (ต้องเข้าเงื่อนไข §9.4.3.2)' if inp.crit_at_d else 'ที่ผิวรองรับ'}</li>
<li>λ = 1.0, ปลอกตั้งฉาก, ช่องว่างระหว่างชั้นเหล็ก 25 mm, เหล็กอัดชั้นเดียว</li>
<li>ไม่รองรับ: T/L-beam, แรงบิด, แรงตามแกน, deep beam, SMF/IMF, ปลอกเฉียง</li>
<li>รายการ "ยังไม่ตรวจ" ต้องตรวจเพิ่ม; เลขข้อ/สูตรต้องเทียบกับตัวเล่มและ errata
— วิศวกรผู้รับผิดชอบต้องตรวจสอบและลงนาม</li>
</ul>
<table class="sign"><tr>
<td>ลงชื่อ ...................................<br>ผู้คำนวณ {('(' + _e(p.designer) + ')') if p.designer else ''}</td>
<td>ลงชื่อ ...................................<br>ผู้ตรวจสอบ {('(' + _e(p.checker) + ')') if p.checker else ''}</td>
<td>ลงชื่อ ...................................<br>ผู้อนุมัติ / วิศวกรผู้รับผิดชอบ</td>
</tr></table>"""

    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calsheet {_e(p.member or 'Beam')}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body>
<div class="toolbar"><button onclick="window.print()">🖨️ พิมพ์ / Save as PDF (A4)</button></div>
<div class="sheet">
<table class="page"><thead><tr><td>{hdr}</td></tr></thead>
<tbody><tr><td>
{data}
{flex}
{shear}
{summ}
{notes}
</td></tr></tbody></table>
</div>
</body></html>"""

