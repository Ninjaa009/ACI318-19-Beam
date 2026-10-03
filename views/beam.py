"""หน้าออกแบบ/ตรวจสอบคาน คสล. ตาม ACI 318M-19 (เปิดผ่าน app.py)"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
import datetime

import streamlit as st
import streamlit.components.v1 as components

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from rcbeam import units as u
from rcbeam.colcheck import C  # noqa: F401  (เพิ่ม skill scripts เข้า sys.path)
from rcbeam.nav import page_link
from rcbeam.staad_example import load_example
from rcbeam.staad_view import model_figure, plan_figure, column_level
import staad_io as S  # noqa: E402  (skill scripts อยู่ใน sys.path จาก rcbeam.colcheck)
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

# ---------------------------------------------------------------- แหล่งข้อมูล (ต้องอยู่ก่อน sidebar เพื่อเติมค่า)
ss = st.session_state
SM, SF = ss.get("staad_model"), ss.get("staad_forces")
for _k, _v in (("b_b", 0.30), ("b_h", 0.60), ("b_span", 0.0), ("b_dmu", 25_000.0), ("b_dvu", 15_000.0),
               ("b_cmu", 25_000.0), ("b_cvu", 15_000.0)):
    ss.setdefault(_k, _v)
mbeams = ([m for m in SM.beams() if any((m, lc) in SF.data for lc in SF.loads())]
          if SM is not None and SF is not None else [])
SRC = (["model"] if mbeams else []) + ["manual"]
src = st.radio("แหล่งข้อมูล", SRC, horizontal=True, key=f"b_src_{len(SRC)}",
               format_func=lambda x: {"model": "โมเดล STAAD (.std + ตาราง Beam End Force) — ขั้นที่ 1–2",
                                      "manual": "ป้อน Mu / Vu เอง"}[x])
SECT = {"left": "ปลายซ้าย (M−, เหล็กบน)", "mid": "กลางช่วง (M+, เหล็กล่าง)", "right": "ปลายขวา (M−, เหล็กบน)"}
if src == "model":
    # ชั้นของคาน = ระดับตีนของเสาที่หัวเสาอยู่ระดับเดียวกับคาน (ใช้กรองผัง)
    col_top = {round(SM.joints[SM.bottom_top(c)[1]][1], 1): column_level(SM, c) for c in SM.columns()}
    lev_of = {m: col_top.get(round(SM.joints[SM.members[m][0]][1], 1)) for m in mbeams}
    levels = sorted({v for v in lev_of.values() if v is not None})
    try:                                                   # คลิกคานในผัง (รอบก่อน) → เลือกคาน
        pts = ss["b_plan"]["selection"]["points"]
    except (KeyError, TypeError):
        pts = []
    cd = pts[0].get("customdata") if pts else None
    clicked = (cd[0] if isinstance(cd, (list, tuple)) else cd) if cd is not None else None
    if clicked in mbeams and ss.get("b_click_prev") != clicked:
        ss.b_member = clicked
    ss.b_click_prev = clicked
    if ss.get("b_member") not in mbeams:
        ss.b_member = mbeams[0]
    if len(levels) > 1:
        if ss.get("b_level") in levels and ss.get("b_level") != ss.get("b_level_prev") and \
                ss.get("b_level_prev") is not None:
            ss.b_member = next(m for m in mbeams if lev_of[m] == ss.b_level)
        ss.b_level = lev_of[ss.b_member] if lev_of[ss.b_member] is not None else levels[0]
        ss.b_level_prev = ss.b_level
    c1, c2 = st.columns([1, 2])
    lev = (c1.selectbox("ชั้น", levels, key="b_level", format_func=lambda y: f"เสาจาก Y = {y / 1000:.2f} m")
           if len(levels) > 1 else (levels[0] if levels else None))
    bm = c2.selectbox("คาน (member ในโมเดล) — หรือคลิกจุดกลางคานในผังข้างล่าง", mbeams, key="b_member",
                      format_func=lambda m: f"member {m} · {SM.prism.get(m, (0, 0))[0]:.0f}×"
                                            f"{SM.prism.get(m, (0, 0))[1]:.0f} · L {SM.length(m) / 1000:.2f} m")
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(plan_figure(SM, bm, height=360, level=lev, pick="beam", selectable=set(mbeams)), key="b_plan", on_select="rerun",
                        selection_mode="points", width="stretch")
        st.caption("ผังมองจากด้านบน — **คลิกจุดกลางคานเพื่อเลือก** · สีส้ม = คานที่เลือก")
    with g2:
        st.plotly_chart(model_figure(SM, None, bm, member_ids=False, height=360), width="stretch")
        st.caption("โมเดล 3D — แกน local ของคาน (y เขียว = ทิศ YD = ความลึก, z ม่วง = ทิศ ZD = ความกว้าง)")
    if ss.get("b_member_prev") != (bm, id(SM)):
        if bm in SM.prism:
            ss.b_h, ss.b_b = SM.prism[bm][0] / 1000, SM.prism[bm][1] / 1000
        ss.b_span = round(SM.length(bm) / 1000, 3)
        ss.b_member_prev = (bm, id(SM))
    strength = SM.strength_combos()
    avail = [lc for lc in SF.loads() if (bm, lc) in SF.data]
    c1, c2 = st.columns([2, 1])
    use = c1.multiselect("combo ที่ใช้ออกแบบ (ตัด combo ใช้งาน/primary load ออกแล้ว)", avail,
                         [lc for lc in avail if lc in strength], key=f"b_use_{bm}",
                         format_func=lambda x: f"{x}: {SM.loads[x].title}" if x in SM.loads else str(x))
    at_face = c2.checkbox("M− ที่ผิวเสา, Vu ที่ผิวเสา + d", value=True, key="b_face",
                          help="ACI 9.4.2.1 / 9.4.3.2 — คานหล่อเป็นเนื้อเดียวกับเสา")
    d_est = SM.prism.get(bm, (600, 300))[0] - 60.0                         # d ≈ h − 60 mm (ประมาณ)
    R = None
    if use:
        try:
            R = S.beam_design_values(SM, SF, bm, use, d_eff=d_est, at_face=at_face)
        except (ValueError, KeyError) as e:
            st.error(str(e))
    if R:
        bad = [r for r in R["rows"] if r["close"] > 0.02]
        if bad:
            st.error(f"สมดุลคานไม่ปิด ({', '.join(str(r['load']) for r in bad)}): โมเมนต์ที่คำนวณถึงปลายคานไม่ตรงกับ "
                     "ตาราง STAAD — load บนคานจาก .std กับตารางแรงอาจไม่ใช่โมเดลเดียวกัน หรือแผ่นพื้นไม่ใช่สี่เหลี่ยมที่มีคานล้อมครบ")
        else:
            st.success("ตรวจสมดุลคานผ่าน: แรงปลาย start + load บนคาน → ได้ M และ V ที่ปลาย end ตรงกับ STAAD ทุก combo")
        ja, jb = SM.members[bm]
        with st.expander("ที่มาของเครื่องหมาย: Mz ของ STAAD → โมเมนต์ออกแบบ (บวก = ดึงล่าง)", expanded=True):
            st.markdown(
                "ตาราง Beam End Force ของ STAAD เป็น**แรงที่กระทำต่อปลายคาน**ตามกฎมือขวารอบแกน local z "
                "ไม่ใช่โมเมนต์ดัดแบบที่ใช้ออกแบบ จึงต้องแปลง: **ปลาย start: M = −Mz** · **ปลาย end: M = +Mz** · "
                "ผลลบ = ดึงบน (เหล็กบน), ผลบวก = ดึงล่าง (เหล็กล่าง)")
            st.dataframe(pd.DataFrame([{
                "combo": r["load"],
                f"Mz STAAD ที่ N{ja} (start)": SF.data[(bm, r["load"])][ja][5] / 1e6,
                "→ M ปลายซ้าย = −Mz": R["diag"][r["load"]]["M"][0] / 1e6,
                f"Mz STAAD ที่ N{jb} (end)": SF.data[(bm, r["load"])][jb][5] / 1e6,
                "→ M ปลายขวา = +Mz": R["diag"][r["load"]]["M"][-1] / 1e6,
                "M+ สูงสุดในช่วง": r["M_mid"] / 1e6} for r in R["rows"]]), hide_index=True, width="stretch",
                column_config={c: st.column_config.NumberColumn(format="%.3f") for c in (
                    f"Mz STAAD ที่ N{ja} (start)", "→ M ปลายซ้าย = −Mz", f"Mz STAAD ที่ N{jb} (end)",
                    "→ M ปลายขวา = +Mz", "M+ สูงสุดในช่วง")})
            st.caption("หน่วย kN·m ที่จุดต่อ (c/c) — ค่าออกแบบข้างล่างใช้ที่ผิวเสา · ตรวจได้: คานต่อเนื่องรับน้ำหนักแนวดิ่ง"
                       "ต้องได้ลบที่ปลายทั้งสองและบวกกลางช่วง")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                            subplot_titles=("โมเมนต์ (kN·m, บวก = ดึงล่าง)", "แรงเฉือน (kN)"))
        for lc, D in R["diag"].items():
            xm = [x / 1000 for x in D["x"]]
            fig.add_trace(go.Scatter(x=xm, y=[m / 1e6 for m in D["M"]], name=f"COMB {lc}", mode="lines"), 1, 1)
            fig.add_trace(go.Scatter(x=xm, y=[v / 1e3 for v in D["V"]], name=f"COMB {lc}", mode="lines",
                                     showlegend=False), 2, 1)
        for xf in (R["faces"][0], R["L"] - R["faces"][1]):
            fig.add_vline(x=xf / 1000, line_dash="dot", line_color="#888")
        fig.update_yaxes(autorange="reversed", row=1, col=1)          # วาดโมเมนต์บวกลงล่างแบบไดอะแกรมคาน
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), xaxis2_title="ระยะจาก start (m)")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(pd.DataFrame([{
            "หน้าตัด": SECT[k], "Mu (kgf·m)": u.nmm_to_kgfm(v[0]), "Vu (kgf)": u.n_to_kgf(v[1]),
            "Mu (kN·m)": v[0] / 1e6, "Vu (kN)": v[1] / 1e3, "combo": v[2], "ที่ระยะ (m)": v[3] / 1000}
            for k, v in R["env"].items()]), hide_index=True, width="stretch",
            column_config={c: st.column_config.NumberColumn(format="%.2f") for c in
                           ("Mu (kgf·m)", "Vu (kgf)", "Mu (kN·m)", "Vu (kN)", "ที่ระยะ (m)")})
        st.caption(f"ผิวเสา: {R['faces'][0]:.0f} / {R['faces'][1]:.0f} mm จากจุดต่อ · Vu ที่ผิวเสา + d โดย d ≈ "
                   f"h − 60 = {d_est:.0f} mm · ซ้าย = start (N{SM.members[bm][0]}), ขวา = end (N{SM.members[bm][1]})")
        sec = st.radio("ส่งค่าไปออกแบบ/ตรวจหน้าตัด", list(SECT), horizontal=True, key="b_sec", format_func=SECT.get)
        if ss.get("b_sec_prev") != (bm, sec, tuple(use), at_face):
            Mu_, Vu_ = R["env"][sec][0], R["env"][sec][1]
            ss.b_dmu = ss.b_cmu = round(u.nmm_to_kgfm(Mu_), 1)
            ss.b_dvu = ss.b_cvu = round(u.n_to_kgf(Vu_), 1)
            ss.b_sec_prev = (bm, sec, tuple(use), at_face)
elif SM is None or SF is None:
    c1, c2 = st.columns([3, 1])
    with c1:
        page_link("views/staad_model.py", label="นำเข้าโมเดล STAAD ในขั้นที่ 1–2 เพื่อเลือกคานจากโมเดล", icon="🧊")
    if c2.button("ใช้โมเดลตัวอย่าง", key="b_example"):
        load_example(ss)
        st.rerun()
else:
    st.info("ตารางแรงในขั้นที่ 2 ยังไม่มีคาน — คัดลอกตาราง Beam End Force **ทั้งตาราง (รวมคาน)** มาวาง")

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
    b = u.m_to_mm(st.number_input("b (m) — ZD ใน STAAD", min_value=0.10, max_value=2.00, step=0.05,
                                  format="%.2f", key="b_b"))
    h = u.m_to_mm(st.number_input("h (m) — YD ใน STAAD", min_value=0.15, max_value=3.00, step=0.05,
                                  format="%.2f", key="b_h"))
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
    always_min = st.checkbox(
        "ใส่ปลอกขั้นต่ำเสมอ แม้ ACI ไม่บังคับ", value=True, key="b_always_min",
        help="เมื่อ Vu ≤ 0.083φλ√f′c·bw·d (หรือเข้าข้อยกเว้น) ACI ไม่บังคับปลอก — "
             "ติ๊ก = ใส่ Av,min @ s ≤ d/2 (แนะนำ: ยึดเหล็กยืน กันวิบัติเฉือนแบบเปราะ, ได้ใช้ Vc สมการ (a)/(b)) · "
             "ไม่ติ๊ก = ไม่ใส่ปลอก ใช้ Vc สมการ (c) ที่มี size effect λs")

    st.header("ความลึกขั้นต่ำ (ไม่บังคับ)")
    span = u.m_to_mm(st.number_input("ช่วงคาน ℓ (m), 0 = ไม่ตรวจ", min_value=0.0, max_value=30.0, step=0.5,
                                     key="b_span"))
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
    Mu = c1.number_input("Mu (kgf·m) + ดึงล่าง / − ดึงบน", step=500.0, key="b_dmu")
    Vu = c2.number_input("Vu (kgf)", step=500.0, min_value=0.0, key="b_dvu")
    db = c3.selectbox("เหล็กหลัก DB (mm)", BARS, index=3, key="b_ddb")
    db_c = c4.selectbox("เหล็กอัด DB (mm)", BARS, index=2, key="b_ddbc")
    if st.button("ออกแบบ", type="primary"):
        st.session_state.design_go = True
    if st.session_state.get("design_go"):
        inp = make_inputs(Mu, Vu)
        D = design_flexure(b, h, fc, fy, inp.Mu, cover, ds, db, db_c, dagg, ety)
        fr = D.result
        sr = design_stirrups(inp.Vu, fc, fyt, b, fr.d, fr.As, ds, int(legs),
                             exempt_9631=exempt, vc_simple=vc_simple, always_min=always_min)
        kind = {"singly": "Singly reinforced", "doubly": "Doubly reinforced",
                "fail": "ออกแบบไม่สำเร็จ"}[D.kind]
        side_t, side_c = ("ล่าง", "บน") if inp.Mu >= 0 else ("บน", "ล่าง")
        steel = f"เหล็กดึง ({side_t}) {' + '.join(str(n) for n in D.counts)}-DB{db} ({cm2(fr.As)})"
        if D.n_c and D.kind != "singly":
            steel += f" · เหล็กอัด ({side_c}) {D.n_c}-DB{db_c} ({cm2(fr.As_comp)})"
        stir = (f"ปลอก {int(legs)} ขา Ø{ds} @ {sr.s:.0f} mm" if sr.s > 0
                else "ไม่ใส่ปลอก (ACI ไม่บังคับ — ผู้ออกแบบเลือกไม่ใส่ปลอกขั้นต่ำ)")
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
    Mu_c = c1.number_input("Mu (kgf·m) + ดึงล่าง / − ดึงบน", step=500.0, key="b_cmu")
    Vu_c = c2.number_input("Vu (kgf)", step=500.0, min_value=0.0, key="b_cvu")
    c1, c2, c3, c4, c5 = st.columns(5)
    counts_txt = c1.text_input("เหล็กดึงต่อชั้น (นอก→ใน)", "3", help="เช่น 4,2")
    db_t = c2.selectbox("DB เหล็กดึง", BARS, index=3, key="b_cdb")
    n_c = c3.number_input("จำนวนเหล็กอัด", 0, 12, 2, 1)
    db_cc = c4.selectbox("DB เหล็กอัด", BARS, index=2, key="b_cdbc")
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
