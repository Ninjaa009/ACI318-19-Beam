"""Calsheet A4 ของเสา (รูปแบบเดียวกับคาน: ไล่ สูตร = แทนค่า = ผลลัพธ์ ทีละบรรทัด)"""
import math
from html import escape

from .calsheet import (_Doc, _n, _ge, _le, _status, X, FC, SQFC, title_block, sign_block,
                       page_html, ProjectInfo)
from .colcheck import C
from .texmath import tex


def _e(x):
    return escape(str(x))


def kNm(x):
    return x / 1e6


def kN(x):
    return x / 1e3


def column_svg(sec, size=210):
    """หน้าตัดเสา: เหล็กรอบรูป ปลอก แกน x, y"""
    b, h = sec.b, sec.h
    pad = 40
    k = (size - 2 * pad) / max(b, h)
    W, H = b * k + 2 * pad, h * k + 2 * pad
    X0, Y0 = pad + b * k / 2, pad + h * k / 2
    px = lambda x: X0 + x * k  # noqa: E731
    py = lambda y: Y0 - y * k  # noqa: E731
    o = sec.cover + sec.ds / 2
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
         f'viewBox="0 0 {W:.1f} {H:.1f}" font-family="Times New Roman, Liberation Serif, serif" '
         'font-size="11">',
         '<defs><pattern id="ch" width="6" height="6" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#aaa" '
         'stroke-width="0.6"/></pattern></defs>',
         f'<rect x="{px(-b / 2):.1f}" y="{py(h / 2):.1f}" width="{b * k:.1f}" height="{h * k:.1f}"'
         ' fill="url(#ch)" stroke="#000" stroke-width="1.1"/>',
         f'<rect x="{px(-b / 2 + o):.1f}" y="{py(h / 2 - o):.1f}" width="{(b - 2 * o) * k:.1f}" '
         f'height="{(h - 2 * o) * k:.1f}" rx="{2 * sec.ds * k:.1f}" fill="none" stroke="#000" '
         f'stroke-width="{max(0.7, sec.ds * k):.1f}"/>']
    for br in sec.bars:
        s.append(f'<circle cx="{px(br.x):.1f}" cy="{py(br.y):.1f}" r="{max(1.5, br.db / 2 * k):.1f}"'
                 ' fill="#000"/>')
    ax = 0.62 * max(b, h) * k
    s.append(f'<line x1="{X0 - ax:.1f}" y1="{Y0:.1f}" x2="{X0 + ax:.1f}" y2="{Y0:.1f}" '
             'stroke="#000" stroke-width="0.5" stroke-dasharray="6 2 1 2"/>')
    s.append(f'<line x1="{X0:.1f}" y1="{Y0 + ax:.1f}" x2="{X0:.1f}" y2="{Y0 - ax:.1f}" '
             'stroke="#000" stroke-width="0.5" stroke-dasharray="6 2 1 2"/>')
    s.append(f'<text x="{X0 + ax + 3:.1f}" y="{Y0 + 4:.1f}" font-style="italic">x</text>')
    s.append(f'<text x="{X0 - 3:.1f}" y="{Y0 - ax - 4:.1f}" font-style="italic">y</text>')
    s.append(f'<text x="{X0:.1f}" y="{H - 8:.1f}" text-anchor="middle">b = {b:.0f}</text>')
    s.append(f'<text transform="translate({12:.1f},{Y0:.1f}) rotate(-90)" text-anchor="middle">'
             f'h = {h:.0f}</text>')
    s.append("</svg>")
    return "".join(s)


def contour_svg(sec, Pu, points, size=250):
    """เส้นความจุ φMnx–φMny ที่ระดับ Pu พร้อมจุดโหลด (kN·m)"""
    cont = C.contour_at(sec, Pu, 72)
    if not cont:
        return ""
    R = max(max(abs(a), abs(b)) for a, b in cont) * 1.12
    for _, mx, my, _cap in points:
        if not (math.isinf(mx) or math.isinf(my)):
            R = max(R, 1.12 * max(abs(mx), abs(my)))
    pad = 34
    k = (size - 2 * pad) / (2 * R)
    c0 = size / 2
    px = lambda my: c0 + my * k  # noqa: E731   แกนนอน = My
    py = lambda mx: c0 - mx * k  # noqa: E731   แกนตั้ง = Mx
    path = " ".join(f"{'M' if i == 0 else 'L'}{px(b):.1f},{py(a):.1f}" for i, (a, b) in
                    enumerate(cont)) + " Z"
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
         f'viewBox="0 0 {size} {size}" font-family="Times New Roman, Liberation Serif, serif" '
         'font-size="10">',
         f'<line x1="{pad}" y1="{c0}" x2="{size - pad}" y2="{c0}" stroke="#888" stroke-width="0.5"/>',
         f'<line x1="{c0}" y1="{pad}" x2="{c0}" y2="{size - pad}" stroke="#888" stroke-width="0.5"/>',
         f'<path d="{path}" fill="#eef3fb" stroke="#1f4e9c" stroke-width="1.3"/>']
    tick = R / 1.12
    for v in (-tick, tick):
        s.append(f'<text x="{px(v):.1f}" y="{c0 + 12:.1f}" text-anchor="middle">'
                 f'{kNm(v):,.0f}</text>')
        s.append(f'<text x="{c0 + 3:.1f}" y="{py(v) + 3:.1f}">{kNm(v):,.0f}</text>')
    s.append(f'<text x="{size - pad + 2}" y="{c0 - 4}" font-style="italic">M<tspan '
             'font-size="7" dy="2">uy</tspan></text>')
    s.append(f'<text x="{c0 + 4}" y="{pad - 4}" font-style="italic">M<tspan font-size="7" '
             'dy="2">ux</tspan></text>')
    marks = {"ปลายบน": ("#000", "▲"), "ปลายล่าง": ("#000", "▼")}
    for label, mx, my, cap in points:
        if math.isinf(mx) or math.isinf(my):
            continue
        col = "#b00020" if (cap and cap.ratio > 1) else "#000"
        x, y = px(my), py(mx)
        s.append(f'<line x1="{c0}" y1="{c0}" x2="{x:.1f}" y2="{y:.1f}" stroke="{col}" '
                 'stroke-width="0.5" stroke-dasharray="3 2"/>')
        if label in marks:
            s.append(f'<text x="{x:.1f}" y="{y + 3:.1f}" text-anchor="middle" fill="{col}">'
                     f'{marks[label][1]}</text>')
        else:
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{col}"/>')
    s.append("</svg>")
    return "".join(s)


def _slender(D, inp, sec, S, axis, M_t, M_b, V):
    name = "x" if axis == "x" else "y"
    depth = sec.h if axis == "x" else sec.b
    D.sub(f"ความชะลูดเมื่อดัดรอบแกน {name} (Slenderness about {name}-axis)")
    if inp.r_method == "0.3h":
        D.eq(rf"r = 0.3\,h = 0.3{X}{depth:.0f} = {_n(S.r)}\ \mathrm{{mm}}", ref="ACI 6.2.5.2")
    else:
        D.eq(rf"r = \sqrt{{\frac{{I_g}}{{A_g}}}} = \frac{{{depth:.0f}}}{{\sqrt{{12}}}} = "
             rf"{_n(S.r)}\ \mathrm{{mm}}", ref="ACI 6.2.5.2")
    D.eq(rf"\frac{{k\,l_u}}{{r}} = \frac{{{S.k:g}{X}{_n(S.lu, 0)}}}{{{_n(S.r)}}} = {_n(S.klu_r)}")
    D.p("ทิศการดัด: " + _e(S.ratio_note))
    D.eq(rf"\frac{{M_1}}{{M_2}} = {S.ratio_M1M2:+.4f} \qquad (M_{{top}} = {_n(kNm(M_t))},\ "
         rf"M_{{bot}} = {_n(kNm(M_b))}\ \mathrm{{kN\cdot m}})")
    D.eq(rf"\min\left(34+12\,\frac{{M_1}}{{M_2}},\ 40\right) = \min(34+12{X}({S.ratio_M1M2:+.4f}),"
         rf"\ 40) = {_n(S.limit)}", ref="ACI 6.2.5.1",
         note=("→ ชะลูด" if S.slender else "→ ไม่ชะลูด"))
    if not S.slender:
        return
    Ec = C.Ec(sec.fc)
    width = sec.b if axis == "x" else sec.h
    Ig = width * depth ** 3 / 12
    D.p("การขยายโมเมนต์ (non-sway):")
    D.eq(rf"E_c = 4700\sqrt{{f^{{\prime}}_c}} = 4700\sqrt{{{_n(sec.fc)}}} = {_n(Ec, 0)}\ "
         rf"\mathrm{{MPa}}, \qquad I_g = \frac{{{width:.0f}{X}{depth:.0f}^3}}{{12}} = "
         rf"{Ig / 1e9:.4f}{X}10^9\ \mathrm{{mm^4}}", ref="ACI 19.2.2.1")
    if inp.EI_method == "b":
        D.eq(r"(EI)_{eff} = \frac{0.2\,E_c I_g + E_s I_{se}}{1+\beta_{dns}} = "
             rf"{S.EIeff / 1e12:.4f}{X}10^{{12}}\ \mathrm{{N\cdot mm^2}}",
             ref="ACI 6.6.4.4.4(b)")
    else:
        D.eq(rf"(EI)_{{eff}} = \frac{{0.4\,E_c I_g}}{{1+\beta_{{dns}}}} = \frac{{0.4{X}{_n(Ec, 0)}"
             rf"{X}{Ig / 1e9:.4f}{X}10^9}}{{1+{inp.beta_dns:g}}} = {S.EIeff / 1e12:.4f}{X}10^{{12}}"
             r"\ \mathrm{N\cdot mm^2}", ref="ACI 6.6.4.4.4(a)")
    D.eq(rf"P_c = \frac{{\pi^2 (EI)_{{eff}}}}{{(k\,l_u)^2}} = \frac{{\pi^2{X}{S.EIeff / 1e12:.4f}"
         rf"{X}10^{{12}}}}{{({S.k:g}{X}{_n(S.lu, 0)})^2}}{X}10^{{-3}} = {_n(kN(S.Pc), 1)}\ "
         r"\mathrm{kN}", ref="ACI 6.6.4.4.2")
    D.eq(rf"M_{{2,\min}} = P_u\,(15+0.03h) = {_n(kN(S.M2min / (15 + 0.03 * depth)), 1)}{X}"
         rf"(15+0.03{X}{depth:.0f}){X}10^{{-3}} = {_n(kNm(S.M2min))}\ \mathrm{{kN\cdot m}}",
         ref="ACI 6.6.4.5.4")
    if S.notes and "M2,min" in S.notes[0]:
        D.eq(r"C_m = 1.0 \qquad (M_2 < M_{2,\min})", ref="ACI 6.6.4.5.4")
    else:
        D.eq(rf"C_m = 0.6-0.4\,\frac{{M_1}}{{M_2}} = 0.6-0.4{X}({S.ratio_M1M2:+.4f}) = "
             rf"{S.Cm:.4f}", ref="ACI 6.6.4.5.3")
    if not S.stable:
        D.eq(r"P_u \geq 0.75\,P_c \quad\Rightarrow\quad \mathrm{unstable}", check=False)
        return
    Pu = S.M2min / (15 + 0.03 * depth)
    D.eq(rf"\delta = \frac{{C_m}}{{1-P_u/(0.75\,P_c)}} = \frac{{{S.Cm:.4f}}}{{1-{_n(kN(Pu), 1)}/"
         rf"(0.75{X}{_n(kN(S.Pc), 1)})}} = {S.delta:.4f} \geq 1.0", ref="ACI 6.6.4.5.2")
    M2d = S.Mc / S.delta
    D.eq(rf"M_c = \delta\,M_2 = {S.delta:.4f}{X}{_n(kNm(M2d))} = {_n(kNm(S.Mc))}\ "
         rf"\mathrm{{kN\cdot m}}")
    D.eq(rf"\frac{{M_c}}{{M_2}} = {S.delta:.3f}\ {_le(S.ok_14)}\ 1.4", ref="ACI 6.2.6",
         check=S.ok_14)


def _capacity_detail(D, sec, Pu, label, mx, my, cap):
    D.sub(f"ตรวจแรงอัดร่วมดัดสองแกน ณ {label} (Biaxial Interaction)")
    D.p("หาความลึกแกนสะเทิน c และมุม θ ที่ทำให้ φP<sub>n</sub> = P<sub>u</sub> และทิศโมเมนต์"
        "ความจุตรงกับทิศโหลด (ตัด 3D interaction surface ที่ระดับ P<sub>u</sub>):")
    D.eq(rf"M_{{res}} = \sqrt{{M_{{ux}}^2+M_{{uy}}^2}} = \sqrt{{{_n(kNm(mx))}^2+{_n(kNm(my))}^2}}"
         rf" = {_n(kNm(cap.Mres))}\ \mathrm{{kN\cdot m}}, \qquad \alpha = \tan^{{-1}}"
         rf"\frac{{|M_{{uy}}|}}{{|M_{{ux}}|}} = {math.degrees(math.atan2(abs(my), abs(mx))):.1f}^\circ")
    pt = cap.pt
    D.eq(rf"\theta_{{NA}} = {math.degrees(pt.theta) % 360:.1f}^\circ, \qquad c = {_n(pt.c, 1)}\ "
         rf"\mathrm{{mm}}, \qquad a = \beta_1 c = {_n(pt.a, 1)}\ \mathrm{{mm}}",
         ref="ACI 22.2.1–22.2.2")
    rows = []
    ux, uy = math.cos(pt.theta), math.sin(pt.theta)
    dmax = max(px * ux + py * uy for px in (-sec.b / 2, sec.b / 2) for py in (-sec.h / 2, sec.h / 2))
    for br in sec.bars:
        y = dmax - (br.x * ux + br.y * uy)
        eps = 0.003 * (pt.c - y) / pt.c
        fs = max(-sec.fy, min(sec.fy, 200000 * eps))
        F = br.area * (fs - 0.85 * sec.fc) if (fs > 0 and y <= pt.a) else br.area * fs
        rows.append(f"<tr><td>({br.x:+.0f}, {br.y:+.0f})</td><td>{y:.1f}</td><td>{eps:+.5f}</td>"
                    f"<td>{fs:+.1f}</td><td>{F / 1e3:+.1f}</td></tr>")
    hdr = "".join(f"<th>{tex(t, 10.5)}</th>" for t in (r"(x,\,y)\ \mathrm{mm}", r"d_i\ (\mathrm{mm})",
                                                        r"\varepsilon_s", r"f_s\ (\mathrm{MPa})",
                                                        r"F\ (\mathrm{kN})"))
    D.raw(f'<table class="grid num"><thead><tr>{hdr}</tr></thead><tbody>{"".join(rows)}'
          "</tbody></table>")
    D.eq(rf"\varepsilon_t = {pt.et:.5f} \quad\Rightarrow\quad \phi = {pt.phi:.3f}",
         ref="ACI Table 21.2.2")
    D.eq(rf"\phi P_n = {_n(kN(pt.phiPn), 1)}\ \mathrm{{kN}} = P_u, \qquad \phi M_{{nx}} = "
         rf"{_n(kNm(pt.phiMnx))}, \quad \phi M_{{ny}} = {_n(kNm(pt.phiMny))}\ \mathrm{{kN\cdot m}}")
    D.eq(rf"\phi M_{{cap}} = \sqrt{{\phi M_{{nx}}^2+\phi M_{{ny}}^2}} = {_n(kNm(cap.phiMcap))}\ "
         r"\mathrm{kN\cdot m}")
    D.eq(rf"\frac{{M_{{res}}}}{{\phi M_{{cap}}}} = \frac{{{_n(kNm(cap.Mres))}}}"
         rf"{{{_n(kNm(cap.phiMcap))}}} = {cap.ratio:.3f}\ {_le(cap.ratio <= 1)}\ 1.0",
         ref="ACI 22.4", check=cap.ratio <= 1)


def _shear(D, sec, sr, label, omf):
    rf = C.sqrt_fc(sec.fc)
    bw, d = sr.bw, sr.d
    D.sub(f"แรงเฉือนทิศ {label} (Shear along {label})")
    if omf and omf.get("applies"):
        D.eq(rf"V_{{u1}} = \frac{{M_{{nt}}+M_{{nb}}}}{{l_u}} = \frac{{{_n(kNm(omf['Mnt']))}+"
             rf"{_n(kNm(omf['Mnb']))}}}{{l_u}} = {_n(kN(omf['Vu1']), 1)}\ \mathrm{{kN}}",
             ref="ACI 18.3.3(a)")
        D.p(_e(omf["note"]))
    D.eq(rf"V_u = {_n(kN(sr.Vu), 2)}\ \mathrm{{kN}}, \qquad N_u = {_n(kN(sr.Nu), 1)}\ "
         rf"\mathrm{{kN}}, \qquad b_w = {bw:.0f}\ \mathrm{{mm}}, \qquad d = {_n(d, 1)}\ \mathrm{{mm}}")
    D.eq(r"\frac{A_{v,\min}}{s} = \max\left(0.062\sqrt{f^{\prime}_{c}}\,\frac{b_w}{f_{yt}},\ "
         rf"0.35\,\frac{{b_w}}{{f_{{yt}}}}\right) = {sr.Av_min_s:.4f}, \qquad \frac{{A_v}}{{s}} = "
         rf"{(sr.Av / sr.s if sr.s else 0):.4f}\ \mathrm{{mm^2/mm}}", ref="ACI 10.6.2.2")
    raw = sr.Nu / (6 * sec.Ag)
    D.eq(rf"\frac{{N_u}}{{6A_g}} = \frac{{{_n(kN(sr.Nu), 1)}{X}10^3}}{{6{X}{_n(sec.Ag, 0)}}} = "
         rf"{raw:.3f}\ {_le(raw <= 0.05 * sec.fc)}\ 0.05\,{FC} = "
         rf"{0.05 * sec.fc:.2f} \quad\Rightarrow\quad {sr.axial_term:.3f}\ \mathrm{{MPa}}",
         ref="ACI Table 22.5.5.1")
    if sr.vc_eq == "a":
        D.eq(rf"V_c = \left(0.17\,\lambda{SQFC} + \frac{{N_u}}{{6A_g}}\right) b_w d = "
             rf"(0.17{X}{rf:.3f}+{sr.axial_term:.3f}){X}{bw:.0f}{X}{_n(d, 1)}{X}10^{{-3}} = "
             rf"{_n(kN((0.17 * rf + sr.axial_term) * bw * d), 1)}\ \mathrm{{kN}}",
             ref="ACI 22.5.5.1(a)")
    else:
        D.eq(rf"V_c = \left(0.66\,\lambda_s\lambda\,\rho_w^{{1/3}}{SQFC} + "
             rf"\frac{{N_u}}{{6A_g}}\right) b_w d = {_n(kN(sr.Vc), 1)}\ \mathrm{{kN}}",
             ref="ACI 22.5.5.1(c)")
    D.eq(rf"V_{{c,\max}} = 0.42\,\lambda{SQFC}\,b_w d = {_n(kN(sr.Vc_max), 1)}\ \mathrm{{kN}} "
         rf"\quad\Rightarrow\quad V_c = {_n(kN(sr.Vc), 1)}\ \mathrm{{kN}}", ref="ACI 22.5.5.1.1")
    D.eq(rf"0.5\,\phi V_c = {_n(kN(0.5 * 0.75 * sr.Vc), 1)}\ \mathrm{{kN}}\ "
         rf"{_ge(not sr.min_required)}\ V_u", ref="ACI 10.6.2.1",
         note="→ ต้องมีปลอกรับแรงเฉือน" if sr.min_required else "→ ไม่บังคับ")
    if sr.s > 0:
        D.eq(rf"V_s = \frac{{A_v f_{{yt}} d}}{{s}} = \frac{{{_n(sr.Av, 1)}{X}{_n(sec.fyt)}{X}"
             rf"{_n(d, 1)}}}{{{sr.s:.0f}}}{X}10^{{-3}} = {_n(kN(sr.Vs), 1)}\ \mathrm{{kN}}",
             ref="ACI 22.5.8.5.3")
    D.eq(rf"\phi V_n = 0.75\,(V_c+V_s) = {_n(kN(sr.phiVn), 1)}\ \mathrm{{kN}}\ "
         rf"{_ge(sr.strength_ok)}\ V_u", ref="ACI 22.5.1.1", check=sr.strength_ok)
    D.eq(rf"\phi\left(V_c+0.66{SQFC}\,b_w d\right) = {_n(kN(sr.section_limit), 1)}\ \mathrm{{kN}}\ "
         rf"{_ge(sr.section_ok)}\ V_u", ref="ACI 22.5.1.2", check=sr.section_ok)
    if sr.min_required:
        D.eq(rf"s = {sr.s:.0f}\ {_le(sr.spacing_ok)}\ s_{{\max}} = {sr.s_max:.0f}\ \mathrm{{mm}}",
             ref="ACI 10.7.6.5.2", check=sr.spacing_ok)


def build_column_calsheet(proj, out):
    p = proj or ProjectInfo()
    inp, sec = out["inp"], out["sec"]
    D = _Doc()
    D.raw(title_block(p, "รายการคำนวณออกแบบเสาคอนกรีตเสริมเหล็ก",
                      "Reinforced Concrete Column Design to ACI 318M-19 (Tied, Non-sway, Biaxial)",
                      "ชื่อเสา"))
    D.h("ข้อมูลออกแบบ", "Design Data")
    nbar = len(sec.bars)
    D.raw('<div class="datawrap"><div class="data">')
    D.eq(rf"b \times h = {sec.b:.0f} \times {sec.h:.0f}\ \mathrm{{mm}}, \qquad "
         rf"A_g = {_n(sec.Ag, 0)}\ \mathrm{{mm^2}}")
    D.eq(rf"{nbar}\ \mathrm{{DB}}{inp.db:g}: \quad A_{{st}} = {nbar}{X}\frac{{\pi{X}{inp.db:g}^2}}{{4}}"
         rf" = {_n(sec.Ast, 1)}\ \mathrm{{mm^2}}, \quad \rho_g = {_n(sec.rho * 100)}\%")
    D.eq(rf"\mathrm{{Ties}}\ \varnothing{inp.ds:g} @ {inp.s:.0f}\ \mathrm{{mm}}, \qquad "
         rf"c_c = {_n(sec.cover, 1)}\ \mathrm{{mm\ (to\ ties)}}")
    D.eq(rf"{FC} = {_n(sec.fc)}\ \mathrm{{MPa}}, \qquad f_y = {_n(sec.fy)}, \quad f_{{yt}} = "
         rf"{_n(sec.fyt)}\ \mathrm{{MPa}}")
    D.eq(rf"l_{{u,x}} = {inp.lu_x:,.0f}, \quad l_{{u,y}} = {inp.lu_y:,.0f}\ \mathrm{{mm}}, \qquad "
         rf"k_x = {inp.k_x:g}, \quad k_y = {inp.k_y:g}, \qquad \beta_{{dns}} = {inp.beta_dns:g}"
         .replace(",", "{,}"))
    D.raw(f'</div><div class="fig">{column_svg(sec)}<br>รูปที่ 1 หน้าตัดเสา (มม.)</div></div>')

    rows = "".join(
        f"<tr><td>{_e(r.combo.name)}</td><td>{kN(r.combo.Pu):,.1f}</td>"
        f"<td>{kNm(r.combo.Mxt):,.2f}</td><td>{kNm(r.combo.Mxb):,.2f}</td>"
        f"<td>{kNm(r.combo.Myt):,.2f}</td><td>{kNm(r.combo.Myb):,.2f}</td>"
        f"<td>{kN(r.combo.Vuy):,.2f}</td><td>{kN(r.combo.Vux):,.2f}</td></tr>"
        for r in out["results"])
    hdr = "".join(f"<th>{tex(t, 10.5)}</th>" for t in (
        r"\mathrm{Combo}", r"P_u", r"M_{ux,top}", r"M_{ux,bot}", r"M_{uy,top}", r"M_{uy,bot}",
        r"V_{uy}", r"V_{ux}"))
    D.sub("แรงประลัย (Factored Loads) หน่วย kN, kN·m")
    D.raw(f'<table class="grid num full"><thead><tr>{hdr}</tr></thead><tbody>{rows}</tbody></table>')

    D.h("การจำแนกโครง sway / non-sway", "Stability Index")
    if out["classes"]:
        D.p("ตรวจทุกชั้นทุกทิศ ใช้ Q สูงสุดจากทุก combination ที่มีแรงด้านข้าง; Δ<sub>o</sub> จากการวิเคราะห์"
            "ลำดับหนึ่งของโมเดลที่ลด stiffness (คาน 0.35I<sub>g</sub>, เสา 0.70I<sub>g</sub>, ACI 6.6.3.1.1)")
        D.eq(r"Q = \frac{\sum P_u\,\Delta_o}{V_{us}\,l_c} \leq 0.05", ref="ACI 6.6.4.3(b)",
             note="→ non-sway")
        trs = []
        for c in out["classes"]:
            mark = (' style="font-weight:700"' if c.story == str(inp.story_name) else "")
            for cb, P, V, do, lc, Q in c.rows:
                trs.append(f"<tr{mark}><td>{_e(c.story)}</td><td>{c.direction.upper()}</td>"
                           f"<td>{_e(cb)}</td><td>{kN(P):,.1f}</td><td>{kN(V):,.2f}</td>"
                           f"<td>{do:g}</td><td>{lc / 1000:g}</td><td>{Q:.4f}</td>"
                           f"<td>{_e(c.status) if cb == c.combo else ''}</td></tr>")
            if not c.rows:
                trs.append(f"<tr{mark}><td>{_e(c.story)}</td><td>{c.direction.upper()}</td>"
                           f"<td colspan='7'>{_e(c.status)}</td></tr>")
        D.raw('<table class="grid num full"><thead><tr><th>ชั้น</th><th>ทิศ</th><th>Combo</th>'
              "<th>ΣP<sub>u</sub> (kN)</th><th>V<sub>us</sub> (kN)</th><th>Δ<sub>o</sub> (mm)</th>"
              "<th>l<sub>c</sub> (m)</th><th>Q</th><th>ผล</th></tr></thead><tbody>"
              + "".join(trs) + "</tbody></table>")
        for c in out["Q"]:
            if not c.rows:
                continue
            g = next(r for r in c.rows if r[0] == c.combo)
            D.eq(rf"Q_{{{c.direction}}} = \frac{{{_n(kN(g[1]), 1)}{X}{g[3]:g}}}{{{_n(kN(g[2]), 2)}"
                 rf"{X}{_n(g[4], 0)}}} = {c.Q_max:.4f}\ {_le(c.Q_max <= 0.05)}\ 0.05",
                 ref="ACI 6.6.4.4.1", check=c.status == "non-sway",
                 note=f"ชั้น {_e(c.story)} ทิศ {c.direction.upper()}: {_e(c.status)}")
            for n in c.notes:
                D.p(f"<i>หมายเหตุ: {_e(n)}</i>")
        D.p(f"เสาต้นนี้อยู่ชั้น <b>{_e(inp.story_name)}</b> — การดัดรอบแกน x ใช้ผลการเซทิศ Y "
            "และการดัดรอบแกน y ใช้ผลการเซทิศ X")
    else:
        D.p("ไม่ได้ป้อนข้อมูลชั้น — สมมติว่าเป็นโครง non-sway (ต้องยืนยันด้วย Q ≤ 0.05 ตาม ACI 6.6.4.3)")
    if out["sway"]:
        D.p("<b>โครงเป็น sway — อยู่นอกขอบเขตของโปรแกรม หยุดการตรวจ</b>")
        D.raw(sign_block(p))
        return page_html(p, D.html(), "RC COLUMN", "RC-Column", "ACI 318M-19 · RC Column Design")

    g = out["gov"]
    cb = g.combo
    D.h(f"ความชะลูด — Combination วิกฤต {_e(cb.name)}", "Slenderness")
    D.eq(rf"P_u = {_n(kN(cb.Pu), 1)}\ \mathrm{{kN}}")
    _slender(D, inp, sec, g.sx, "x", cb.Mxt, cb.Mxb, cb.Vuy)
    _slender(D, inp, sec, g.sy, "y", cb.Myt, cb.Myb, cb.Vux)

    D.h("กำลังรับแรงอัดสูงสุด", "Maximum Axial Strength")
    fy = min(sec.fy, 550.0)
    D.eq(rf"P_o = 0.85\,{FC}(A_g-A_{{st}})+f_y A_{{st}} = 0.85{X}{_n(sec.fc)}{X}({_n(sec.Ag, 0)}-"
         rf"{_n(sec.Ast, 1)})+{_n(fy)}{X}{_n(sec.Ast, 1)} = {_n(kN(sec.Po), 1)}\ \mathrm{{kN}}",
         ref="ACI 22.4.2.2")
    Pmax = max(r.combo.Pu for r in out["results"] if not r.error)
    D.eq(rf"\phi P_{{n,\max}} = 0.65{X}0.80\,P_o = {_n(kN(sec.phiPn_max), 1)}\ \mathrm{{kN}}\ "
         rf"{_ge(sec.phiPn_max >= Pmax)}\ P_{{u,\max}} = {_n(kN(Pmax), 1)}\ \mathrm{{kN}}",
         ref="ACI Table 22.4.2.1", check=sec.phiPn_max >= Pmax)

    D.h("แรงอัดร่วมดัดสองแกน", "Biaxial Interaction")
    label, mx, my, cap = g.crit
    if cap is not None and cap.pt is not None:
        _capacity_detail(D, sec, cb.Pu, label, mx, my, cap)
        svg = contour_svg(sec, cb.Pu, g.points)
        D.raw(f'<div class="fig" style="margin:6px 0">{svg}<br>รูปที่ 2 เส้นความจุ φM<sub>nx</sub>'
              f"–φM<sub>ny</sub> ที่ P<sub>u</sub> = {kN(cb.Pu):,.1f} kN ({_e(cb.name)}) · "
              "▲ ปลายบน ▼ ปลายล่าง ● กลางเสา (kN·m)</div>")
    D.sub("ผลทุก Combination")
    trs = []
    for r in out["results"]:
        if r.error:
            trs.append(f"<tr><td>{_e(r.combo.name)}</td><td colspan='6'>{_e(r.error)}</td></tr>")
            continue
        for lab, a, b_, cp in r.points:
            if cp is None:
                trs.append(f"<tr><td>{_e(r.combo.name)}</td><td>{_e(lab)}</td>"
                           "<td colspan='5'>ไม่เสถียร</td></tr>")
                continue
            trs.append(f"<tr><td>{_e(r.combo.name)}</td><td>{_e(lab)}</td><td>{kNm(a):,.2f}</td>"
                       f"<td>{kNm(b_):,.2f}</td><td>{kNm(cp.Mres):,.2f}</td>"
                       f"<td>{kNm(cp.phiMcap):,.2f}</td><td>{_status('ผ่าน' if cp.ok else 'ไม่ผ่าน')} "
                       f"{cp.ratio:.3f}</td></tr>")
    D.raw('<table class="grid num full"><thead><tr><th>Combo</th><th>ตำแหน่ง</th>'
          "<th>M<sub>ux</sub></th><th>M<sub>uy</sub></th><th>M<sub>res</sub></th>"
          "<th>φM<sub>cap</sub></th><th>ratio</th></tr></thead><tbody>"
          + "".join(trs) + "</tbody></table>")

    gs = out["gov_shear"]
    D.h(f"การออกแบบรับแรงเฉือน — Combination {_e(gs.combo.name)}", "Shear Design")
    _shear(D, sec, gs.shear_y, "y", gs.omf_y)
    _shear(D, sec, gs.shear_x, "x", gs.omf_x)
    D.eq(rf"\frac{{V_{{ux}}}}{{\phi V_{{nx}}}} + \frac{{V_{{uy}}}}{{\phi V_{{ny}}}} = "
         rf"{gs.shear_x.ratio:.3f}+{gs.shear_y.ratio:.3f} = {gs.biax_sum:.3f}", ref="ACI 22.5.1.11",
         check=gs.biax_ok, note="(ตรวจเมื่อทั้งสองอัตราส่วน > 0.5)")

    D.h("รายละเอียดเหล็กเสริม", "Detailing")
    for name, ok, val, ref in out["long"] + out["ties"]:
        D.p(f"{_e(name)}: {_e(val)} — {_status('ผ่าน' if ok else 'ไม่ผ่าน') if ok is not None else 'ตรวจตามแบบ'}"
            f" <span style='color:#555;font-size:9pt'>[ACI {_e(ref)}]</span>")

    D.h("สรุปผลการตรวจสอบ", "Summary")
    srows = "".join(f"<tr><td>{_e(a)}</td><td>{_e(b)}</td><td>{_status(c)}</td><td>{_e(d)}</td></tr>"
                    for a, b, c, d in out["summary"])
    D.raw('<table class="grid full"><thead><tr><th>รายการ</th><th>ค่า</th><th>สถานะ</th>'
          f"<th>อ้างอิง ACI 318M-19</th></tr></thead><tbody>{srows}</tbody></table>")
    D.h("สมมติฐานและขอบเขต", "Assumptions")
    D.raw(f"""<ul class="notes">
<li>ACI 318M-19; strain compatibility (22.2), stress block 0.85f′c, φ ตาม ε<sub>t</sub> (Table 21.2.2)
ε<sub>ty</sub> = {'0.002 (Grade 420)' if sec.grade420 else 'f<sub>y</sub>/E<sub>s</sub>'}</li>
<li>3D interaction: ตัด surface ที่ P<sub>u</sub> และวัดตามทิศของโมเมนต์ลัพธ์ (ไม่เทียบกับเส้นแกนเดียว)</li>
<li>ทิศการดัด (M<sub>1</sub>/M<sub>2</sub>) ตัดสินจากสมดุลแรงเฉือน; M<sub>1</sub> = M<sub>2</sub> = 0 ใช้ −1 (เกณฑ์ 22)</li>
<li>r = {'0.3h' if inp.r_method == '0.3h' else '√(I<sub>g</sub>/A<sub>g</sub>)'}, (EI)<sub>eff</sub> วิธี
({inp.EI_method}), β<sub>dns</sub> = {inp.beta_dns:g}; กลางเสาใช้ M<sub>c</sub> ของทั้งสองแกนพร้อมกัน</li>
<li>ปลอกรับแรงเฉือนจำเป็นเมื่อ V<sub>u</sub> &gt; 0.5φV<sub>c</sub> (10.6.2.1); ไม่รองรับโครง sway, SMF/IMF,
เสากลม/ปลอกเกลียว; ระยะทาบ/ฝังยึดและรอยต่อยังไม่ตรวจ</li>
</ul>""")
    D.raw(sign_block(p))
    return page_html(p, D.html(), "RC COLUMN", "RC-Column", "ACI 318M-19 · RC Column Design")
