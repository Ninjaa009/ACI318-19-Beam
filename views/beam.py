"""หน้าออกแบบ/ตรวจสอบคาน คสล. ตาม ACI 318M-19 (เปิดผ่าน app.py)"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
import datetime

import streamlit as st
import streamlit.components.v1 as components

from rcbeam import units as u
from rcbeam.flexure import (
    analyze, design_flexure, eps_ty, tension_layers, compression_layer,
    bars_per_layer,
)
from rcbeam.shear import check_stirrups, design_stirrups
from rcbeam.calsheet import ProjectInfo, DesignInfo, build_calsheet
from rcbeam.report import (
    Inputs, build_report, detailing_checks, flexure_steps, shear_steps,
    SUPPORT_DIVISOR, PASS, FAIL, kgfm, kgf, cm2,
)

BARS = [12, 16, 20, 25, 28, 32]
STIRRUPS = [6, 9, 10, 12]

st.title("ออกแบบ/ตรวจสอบคาน คสล. ตาม ACI 318M-19")
st.caption("หน้าตัดสี่เหลี่ยม singly / doubly — แรงดัด + แรงเฉือน · อินพุต kgf–m · "
           "คำนวณภายในด้วย MPa–mm–N")

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("วัสดุ")
    unit = st.radio("หน่วยกำลังวัสดุ", ["ksc", "MPa"], horizontal=True)
    if unit == "ksc":
        fc = u.ksc_to_mpa(st.number_input("f′c (ksc)", 100.0, 1000.0, 280.0, 10.0))
        fy = u.ksc_to_mpa(st.number_input("fy เหล็กหลัก (ksc)", 2000.0, 7000.0, 4000.0, 100.0))
        fyt = u.ksc_to_mpa(st.number_input("fyt ปลอก (ksc)", 2000.0, 7000.0, 2400.0, 100.0))
    else:
        fc = st.number_input("f′c (MPa)", 10.0, 100.0, 28.0, 1.0)
        fy = st.number_input("fy เหล็กหลัก (MPa)", 200.0, 700.0, 420.0, 10.0)
        fyt = st.number_input("fyt ปลอก (MPa)", 200.0, 700.0, 420.0, 10.0)
    st.caption(f"= f′c {fc:.2f} · fy {fy:.2f} · fyt {fyt:.2f} MPa")
    g420_allowed = abs(fy - 420.0) <= 0.5
    grade420 = st.checkbox(
        "ใช้ข้อยกเว้น Grade 420 (εty = 0.002)", value=False, disabled=not g420_allowed,
        help="§21.2.2.1 — ใช้ได้เฉพาะ fy = 420 MPa และต้องระบุในรายงาน",
    )

    st.header("หน้าตัด")
    b = u.m_to_mm(st.number_input("b (m)", 0.10, 2.00, 0.30, 0.05, format="%.2f"))
    h = u.m_to_mm(st.number_input("h (m)", 0.15, 3.00, 0.60, 0.05, format="%.2f"))
    cover = st.number_input("ระยะหุ้ม cover (mm)", 20.0, 100.0, 40.0, 5.0,
                            help="เลือกตามสภาพแวดล้อม Table 20.5.1.3.1")
    ds = st.selectbox("ขนาดปลอก (mm)", STIRRUPS, index=1)
    legs = st.number_input("จำนวนขาปลอก", 2, 6, 2, 1)
    dagg = st.number_input("ขนาดหินใหญ่สุด (mm)", 10.0, 40.0, 20.0, 5.0)

    st.header("แรงเฉือน")
    crit_at_d = st.checkbox("Vu ที่ระยะ d จากผิวรองรับ", value=True,
                            help="ใช้ได้เมื่อเข้าเงื่อนไข §9.4.3.2")
    vc_simple = st.radio("สมการ Vc เมื่อ Av ≥ Av,min", ["a", "b"], horizontal=True,
                         format_func=lambda x: {"a": "(a) 0.17λ√f′c", "b": "(b) ρw^⅓"}[x])
    exempt = st.checkbox("เข้าข้อยกเว้น Table 9.6.3.1", value=False)

    st.header("ความลึกขั้นต่ำ (ไม่บังคับ)")
    span = u.m_to_mm(st.number_input("ช่วงคาน ℓ (m), 0 = ไม่ตรวจ", 0.0, 30.0, 0.0, 0.5))
    support = st.selectbox("สภาพรองรับ", list(SUPPORT_DIVISOR))

    with st.expander("ข้อมูลโครงการ (หัว Calsheet)"):
        proj = ProjectInfo(
            project=st.text_input("โครงการ", ""),
            location=st.text_input("สถานที่", ""),
            member=st.text_input("ชื่อคาน", "B1"),
            grid=st.text_input("ตำแหน่ง / Grid", ""),
            designer=st.text_input("ผู้คำนวณ", ""),
            checker=st.text_input("ผู้ตรวจสอบ", ""),
            date=st.date_input("วันที่", datetime.date.today()).strftime("%d/%m/%Y"),
        )

ety = eps_ty(fy, grade420)


def make_inputs(Mu, Vu):
    return Inputs(b=b, h=h, fc=fc, fy=fy, fyt=fyt, cover=cover, ds=ds, legs=int(legs),
                  dagg=dagg, Mu=u.kgfm_to_nmm(Mu), Vu=u.kgf_to_n(abs(Vu)),
                  grade420=grade420, span=span, support=support,
                  crit_at_d=crit_at_d, exempt_9631=exempt)


def draw_section(inp, fr):
    fig, ax = plt.subplots(figsize=(3.2, 3.2 * inp.h / inp.b if inp.h < 2.2 * inp.b else 6))
    ax.add_patch(Rectangle((0, 0), inp.b, inp.h, fc="#d9d9d9", ec="#333", lw=1.5))
    o = inp.cover + inp.ds / 2
    ax.add_patch(Rectangle((o, o), inp.b - 2 * o, inp.h - 2 * o, fill=False,
                           ec="#555", lw=inp.ds / 4))
    top_tension = inp.Mu < 0
    for L in fr.steel:
        lay = L.layer
        y = lay.y if top_tension else inp.h - lay.y
        x0 = inp.cover + inp.ds + lay.db / 2
        x1 = inp.b - x0
        xs = [x0] if lay.n == 1 else [x0 + i * (x1 - x0) / (lay.n - 1) for i in range(lay.n)]
        color = "#c0392b" if lay.role == "tension" else "#2c6fbb"
        for x in xs:
            ax.add_patch(Circle((x, y), lay.db / 2, color=color))
    ax.set_xlim(-20, inp.b + 20)
    ax.set_ylim(-20, inp.h + 20)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.axhline(fr.c if top_tension else inp.h - fr.c, color="#e67e22", ls="--", lw=1)
    ax.set_title("red = tension, blue = compression, dashed = N.A.", fontsize=7)
    return fig


def show(title, inp, fr, sr, counts, db, header, steel_text, stirrup_text,
         design=None, key="d"):
    det = detailing_checks(inp, fr, counts, db)
    md, rows = build_report(title, inp, fr, sr, det, header)
    all_ok = all(r[2] == PASS for r in rows if r[2] in (PASS, FAIL))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("φMn", kgfm(fr.phiMn), f"Mu = {kgfm(abs(inp.Mu))}", delta_color="off")
    m2.metric("εt", f"{fr.et:.5f}", f"ต้อง ≥ {fr.et_limit:.5f}", delta_color="off")
    m3.metric("φVn", kgf(sr.phiVn), f"Vu = {kgf(sr.Vu)}", delta_color="off")
    m4.metric("φ ดัด", f"{fr.phi:.3f}")

    if all_ok:
        st.success("รายการที่ตรวจแล้วผ่านทั้งหมด — รายการ \"ยังไม่ตรวจ\" ต้องตรวจเพิ่มเอง")
    else:
        st.error("มีรายการไม่ผ่าน — ดูตารางสรุป")

    c1, c2 = st.columns([1, 2])
    with c1:
        st.pyplot(draw_section(inp, fr), width="content")
    with c2:
        st.dataframe(
            [{"รายการ": a, "ค่า": b_, "สถานะ": c, "อ้างอิง": d} for a, b_, c, d in rows],
            hide_index=True, width="stretch", height=36 * (len(rows) + 1) + 3,
        )
    with st.expander("รายการคำนวณแรงดัด", expanded=False):
        st.markdown(flexure_steps(inp, fr))
    with st.expander("รายการคำนวณแรงเฉือน", expanded=False):
        st.markdown(shear_steps(inp, sr))
    sheet = build_calsheet(title, proj, inp, fr, sr, rows, steel_text, stirrup_text,
                           design)
    fname = f"calsheet_{proj.member or 'beam'}".replace(" ", "_")
    d1, d2 = st.columns(2)
    d1.download_button("🖨️ ดาวน์โหลด Calsheet A4 (.html)", sheet,
                       file_name=f"{fname}.html", mime="text/html", type="primary", key=f"{key}_cs",
                       help="เปิดไฟล์ในเบราว์เซอร์ แล้วกดปุ่มพิมพ์ หรือ Ctrl+P → Save as PDF")
    d2.download_button("ดาวน์โหลดรายงาน (.md)", md, file_name=f"{fname}.md",
                       mime="text/markdown", key=f"{key}_md")
    with st.expander("ดูตัวอย่าง Calsheet A4"):
        components.html(sheet, height=900, scrolling=True)


tab_design, tab_check = st.tabs(["ออกแบบ", "ตรวจสอบ"])

with tab_design:
    c1, c2, c3, c4 = st.columns(4)
    Mu = c1.number_input("Mu (kgf·m) + ดึงล่าง / − ดึงบน", value=25_000.0, step=500.0,
                         key="d_mu")
    Vu = c2.number_input("Vu (kgf)", value=15_000.0, step=500.0, min_value=0.0,
                         key="d_vu")
    db = c3.selectbox("เหล็กหลัก DB (mm)", BARS, index=3, key="d_db")
    db_c = c4.selectbox("เหล็กอัด DB (mm)", BARS, index=2, key="d_dbc")
    if st.button("ออกแบบ", type="primary"):
        st.session_state.design_go = True
    if st.session_state.get("design_go"):
        inp = make_inputs(Mu, Vu)
        D = design_flexure(b, h, fc, fy, inp.Mu, cover, ds, db, db_c, dagg, ety)
        fr = D.result
        sr = design_stirrups(inp.Vu, fc, fyt, b, fr.d, fr.As, ds, int(legs),
                             exempt_9631=exempt, vc_simple=vc_simple)
        kind = {"singly": "Singly reinforced", "doubly": "Doubly reinforced",
                "fail": "ออกแบบไม่สำเร็จ"}[D.kind]
        side_t, side_c = ("ล่าง", "บน") if inp.Mu >= 0 else ("บน", "ล่าง")
        steel = f"เหล็กดึง ({side_t}) {' + '.join(str(n) for n in D.counts)}-DB{db} ({cm2(fr.As)})"
        if D.n_c and D.kind != "singly":
            steel += f" · เหล็กอัด ({side_c}) {D.n_c}-DB{db_c} ({cm2(fr.As_comp)})"
        stir = (f"ปลอก {int(legs)} ขา Ø{ds} @ {sr.s:.0f} mm" if sr.s > 0
                else "ไม่ต้องใช้ปลอกตามการคำนวณ")
        st.subheader(f"{kind}: {steel}")
        st.markdown(f"**{stir}**")
        for n in D.notes:
            st.info(n)
        header = [f"**ผลออกแบบ:** {kind} — {steel}; {stir}",
                  f"- As,req = {cm2(D.As_req)}" +
                  (f", A′s,req = {cm2(D.Asc_req)} (ค่าประมาณที่ c = cmax)"
                   if D.kind != "singly" else "")]
        header += [f"- {n}" for n in D.notes]
        show("รายการคำนวณออกแบบคาน", inp, fr, sr, D.counts, db, header,
             f"{kind}: {steel}", stir,
             DesignInfo(D.kind, D.As_req, D.Asc_req, D.notes))

with tab_check:
    c1, c2 = st.columns(2)
    Mu_c = c1.number_input("Mu (kgf·m) + ดึงล่าง / − ดึงบน", value=25_000.0,
                           step=500.0, key="c_mu")
    Vu_c = c2.number_input("Vu (kgf)", value=15_000.0, step=500.0, min_value=0.0,
                           key="c_vu")
    c1, c2, c3, c4, c5 = st.columns(5)
    counts_txt = c1.text_input("เหล็กดึงต่อชั้น (นอก→ใน)", "3", help="เช่น 4,2")
    db_t = c2.selectbox("DB เหล็กดึง", BARS, index=3, key="c_db")
    n_c = c3.number_input("จำนวนเหล็กอัด", 0, 12, 2, 1)
    db_cc = c4.selectbox("DB เหล็กอัด", BARS, index=2, key="c_dbc")
    s = c5.number_input("ระยะปลอก s (mm), 0 = ไม่มี", 0.0, 600.0, 200.0, 25.0)
    if st.button("ตรวจสอบ", type="primary"):
        st.session_state.check_go = True
    if st.session_state.get("check_go"):
        try:
            counts = [int(x) for x in counts_txt.replace(" ", "").split(",") if x]
            if not counts or min(counts) <= 0:
                raise ValueError
        except ValueError:
            st.error("รูปแบบจำนวนเหล็กไม่ถูกต้อง ใช้เช่น 4,2")
            st.stop()
        nmax = bars_per_layer(b, cover, ds, db_t, dagg)
        if max(counts) > nmax:
            st.warning(f"เหล็ก DB{db_t} ใส่ได้สูงสุด {nmax} เส้นต่อชั้น (§25.2.1)")
        inp = make_inputs(Mu_c, Vu_c)
        layers = tension_layers(h, cover, ds, db_t, counts)
        if n_c > 0:
            layers.append(compression_layer(cover, ds, n_c, db_cc))
        fr = analyze(b, h, fc, fy, layers, ety)
        sr = check_stirrups(inp.Vu, fc, fyt, b, fr.d, fr.As, ds, int(legs), s,
                            exempt_9631=exempt, vc_simple=vc_simple)
        side_t, side_c = ("ล่าง", "บน") if inp.Mu >= 0 else ("บน", "ล่าง")
        steel = (f"เหล็กดึง ({side_t}) {' + '.join(str(n) for n in counts)}-DB{db_t} "
                 f"({cm2(fr.As)})")
        if n_c > 0:
            steel += f" · เหล็กอัด ({side_c}) {n_c}-DB{db_cc} ({cm2(fr.As_comp)})"
        stir = (f"ปลอก {int(legs)} ขา Ø{ds} @ {s:.0f} mm" if s > 0 else "ไม่มีปลอก")
        show("รายการตรวจสอบคาน", inp, fr, sr, counts, db_t, [], f"ตรวจสอบ: {steel}",
             stir, key="c")

st.divider()
st.caption("ผลลัพธ์ใช้ประกอบแผ่นคำนวณเท่านั้น ต้องมีวิศวกรผู้รับผิดชอบตรวจสอบและลงนาม · "
           "ยังไม่ตรวจ: development length, การค้ำยันเหล็กอัด, ระยะขาปลอกตามขวาง, "
           "การแอ่นตัว (นอกจากตรวจความลึกขั้นต่ำ)")
