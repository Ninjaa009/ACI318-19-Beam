"""หน้าออกแบบ/ตรวจสอบเสา คสล. ตาม ACI 318M-19 (tied, non-sway, biaxial) — เปิดผ่าน app.py"""
import datetime
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from rcbeam import units as u
from rcbeam.calsheet import ProjectInfo
from rcbeam.col_calsheet import build_column_calsheet
from rcbeam.colcheck import C, ColumnInput, Combo, PASS, FAIL, run

BARS = [12, 16, 19.1, 20, 25, 28, 32, 36]
TIES = [6, 9, 9.5, 10, 12]
CURV = ["auto", "single", "double"]

st.title("ออกแบบ/ตรวจสอบเสา คสล. ตาม ACI 318M-19")
st.caption("หน้าตัดสี่เหลี่ยม ปลอกเดี่ยว · โครง non-sway · 3D interaction (P–Mx–My) · "
           "ความชะลูด + ขยายโมเมนต์ · แรงเฉือนสองทิศ · ใช้ solver ของ skill rc-column-aci318m19")

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("วัสดุ")
    unit = st.radio("หน่วยกำลังวัสดุ", ["MPa", "ksc"], horizontal=True, key="c_unit")
    if unit == "ksc":
        fc = u.ksc_to_mpa(st.number_input("f′c (ksc)", 100.0, 1000.0, 285.5, 10.0, key="c_fc"))
        fy = u.ksc_to_mpa(st.number_input("fy เหล็กยืน (ksc)", 2000.0, 7000.0, 4282.8, 100.0,
                                          key="c_fy"))
        fyt = u.ksc_to_mpa(st.number_input("fyt ปลอก (ksc)", 2000.0, 7000.0, 4282.8, 100.0,
                                           key="c_fyt"))
    else:
        fc = st.number_input("f′c (MPa)", 10.0, 100.0, 28.0, 1.0, key="c_fc_m")
        fy = st.number_input("fy เหล็กยืน (MPa)", 200.0, 700.0, 420.0, 10.0, key="c_fy_m")
        fyt = st.number_input("fyt ปลอก (MPa)", 200.0, 700.0, 420.0, 10.0, key="c_fyt_m")
    st.caption(f"= f′c {fc:.2f} · fy {fy:.2f} · fyt {fyt:.2f} MPa")
    grade420 = st.checkbox("ใช้ข้อยกเว้น Grade 420 (εty = 0.002)", value=False,
                           disabled=abs(fy - 420) > 0.5, key="c_g420")

    st.header("หน้าตัดและเหล็ก")
    b = u.m_to_mm(st.number_input("b (m) ตามแกน x", 0.15, 2.0, 0.40, 0.05, format="%.2f", key="c_b"))
    h = u.m_to_mm(st.number_input("h (m) ตามแกน y", 0.15, 2.0, 0.40, 0.05, format="%.2f", key="c_h"))
    cover = st.number_input("cover (mm)", 20.0, 100.0, 40.0, 5.0, key="c_cov")
    cover_to = st.radio("cover วัดถึง", ["tie", "long"], horizontal=True, key="c_covto",
                        format_func=lambda x: {"tie": "ผิวปลอก (ACI)", "long": "เหล็กยืน (RCDC)"}[x])
    db = st.selectbox("เหล็กยืน DB (mm)", BARS, index=3, key="c_db")
    c1, c2 = st.columns(2)
    nx = c1.number_input("เส้น/ด้าน b", 2, 12, 3, 1, key="c_nx")
    ny = c2.number_input("เส้น/ด้าน h", 2, 12, 3, 1, key="c_ny")
    ds = st.selectbox("ปลอก (mm)", TIES, index=3, key="c_ds")
    s = st.number_input("ระยะปลอก s (mm)", 50.0, 600.0, 250.0, 25.0, key="c_s")
    c1, c2 = st.columns(2)
    legs_x = c1.number_input("ขาปลอกทิศ x", 2, 8, 2, 1, key="c_lx")
    legs_y = c2.number_input("ขาปลอกทิศ y", 2, 8, 2, 1, key="c_ly")
    dagg = st.number_input("ขนาดหินใหญ่สุด (mm)", 10.0, 40.0, 20.0, 5.0, key="c_agg")
    cover_min = st.number_input("cover ขั้นต่ำที่ต้องการ (mm)", 20.0, 75.0, 40.0, 5.0, key="c_covmin",
                                help="Table 20.5.1.3.1 — เสาในอาคาร 40 mm")

    st.header("ความยาวและความชะลูด")
    c1, c2 = st.columns(2)
    lu_x = u.m_to_mm(c1.number_input("l_u ดัดรอบ x (m)", 0.5, 30.0, 4.5, 0.1, key="c_lux"))
    lu_y = u.m_to_mm(c2.number_input("l_u ดัดรอบ y (m)", 0.5, 30.0, 4.5, 0.1, key="c_luy"))
    k_x = c1.number_input("k_x", 0.5, 1.0, 1.0, 0.05, key="c_kx")
    k_y = c2.number_input("k_y", 0.5, 1.0, 1.0, 0.05, key="c_ky")
    L = u.m_to_mm(st.number_input("ความยาวชิ้นส่วน c/c (m)", 0.5, 30.0, 5.0, 0.1, key="c_L",
                                  help="ใช้ตัดสินทิศการดัดจากแรงเฉือน |V|·L"))
    beta = st.number_input("βdns", 0.0, 1.0, 0.6, 0.05, key="c_beta",
                           help="สัดส่วนแรงอัดค้าง (sustained) ต่อแรงอัดประลัยทั้งหมด")
    r_method = st.radio("r", ["exact", "0.3h"], horizontal=True, key="c_r",
                        format_func=lambda x: {"exact": "√(Ig/Ag)", "0.3h": "0.3h"}[x])
    EI_method = st.radio("(EI)eff", ["a", "b"], horizontal=True, key="c_ei",
                         format_func=lambda x: {"a": "(a) 0.4EcIg", "b": "(b) 0.2EcIg+EsIse"}[x])

    omf = st.checkbox("§18.3.3 เสา OMF ใน SDC B", value=False, key="c_omf",
                      help="แรงเฉือนจาก Mn ที่ปลายเสา (ใช้เมื่อ l_u ≤ 5c1)")

    with st.expander("ข้อมูลโครงการ (หัว Calsheet)"):
        proj = ProjectInfo(
            project=st.text_input("โครงการ", "", key="c_pj"),
            location=st.text_input("สถานที่", "", key="c_loc"),
            member=st.text_input("ชื่อเสา", "C1", key="c_mem"),
            grid=st.text_input("ตำแหน่ง / Grid", "", key="c_grid"),
            designer=st.text_input("ผู้คำนวณ", "", key="c_des"),
            checker=st.text_input("ผู้ตรวจสอบ", "", key="c_chk"),
            date=st.date_input("วันที่", datetime.date.today(), key="c_date").strftime("%d/%m/%Y"),
        )

# ---------------------------------------------------------------- loads
st.subheader("แรงประลัยทุก Load Combination")
lunit = st.radio("หน่วยแรง", ["kN", "kgf"], horizontal=True, key="c_lunit",
                 format_func=lambda x: {"kN": "kN, kN·m", "kgf": "kgf, kgf·m"}[x])
F = 1e3 if lunit == "kN" else u.G                 # → N
M = 1e6 if lunit == "kN" else u.KGFM_TO_NMM       # → N·mm
fu, mu = ("kN", "kN·m") if lunit == "kN" else ("kgf", "kgf·m")
st.caption("แกน x ขนานด้าน b · Mx = โมเมนต์รอบแกน x (ใช้ความลึก h) · Vuy = แรงเฉือนขนานแกน y "
           "(คู่กับ Mx) · P > 0 = อัด · ทิศการดัด auto = ตัดสินจาก |V|·L")
default = pd.DataFrame([
    {"Combo": "S1", "Pu": 1600.0, "Mx_top": 90.0, "Mx_bot": 60.0, "My_top": 30.0, "My_bot": 20.0,
     "Vuy": 6.0, "Vux": 10.0, "โค้ง x": "auto", "โค้ง y": "auto"},
    {"Combo": "LC2", "Pu": 900.0, "Mx_top": 40.0, "Mx_bot": -35.0, "My_top": 10.0, "My_bot": 5.0,
     "Vuy": 15.0, "Vux": 3.0, "โค้ง x": "auto", "โค้ง y": "auto"},
])
num = lambda lab: st.column_config.NumberColumn(lab, format="%.2f")  # noqa: E731
df = st.data_editor(
    default, num_rows="dynamic", width="stretch", key="c_loads",
    column_config={
        "Pu": num(f"Pu ({fu})"), "Mx_top": num(f"Mx บน ({mu})"), "Mx_bot": num(f"Mx ล่าง ({mu})"),
        "My_top": num(f"My บน ({mu})"), "My_bot": num(f"My ล่าง ({mu})"),
        "Vuy": num(f"Vuy ({fu})"), "Vux": num(f"Vux ({fu})"),
        "โค้ง x": st.column_config.SelectboxColumn(options=CURV),
        "โค้ง y": st.column_config.SelectboxColumn(options=CURV),
    })

# ---------------------------------------------------------------- stories (sway / non-sway)
st.subheader("ข้อมูลชั้น: จำแนก sway / non-sway (ACI 6.6.4.3)")
st.caption(f"ป้อนทุกชั้น ทุกทิศ ทุก combo ที่มีแรงด้านข้าง · Q = ΣPu·Δo/(Vus·lc) · ΣPu รวมทุกเสา/ผนังในชั้น · "
           f"Vus = แรงเฉือนของชั้น (ไม่ใช่ base shear) · Δo = ค่าบน − ค่าล่าง จากการวิเคราะห์ลำดับหนึ่ง · "
           f"lc = ความสูงชั้น c/c · แรงใช้หน่วย {fu}")
story_default = pd.DataFrame([
    {"ชั้น": "1", "ทิศ": "x", "Combo": "W+X", "ΣPu": 24000.0, "Vus": 900.0, "Δo (mm)": 3.2,
     "lc (m)": 5.0, "ลด stiffness แล้ว": True},
    {"ชั้น": "1", "ทิศ": "y", "Combo": "W+Y", "ΣPu": 24000.0, "Vus": 900.0, "Δo (mm)": 3.2,
     "lc (m)": 5.0, "ลด stiffness แล้ว": True},
])
sdf = st.data_editor(
    story_default, num_rows="dynamic", width="stretch", key="c_stories",
    column_config={
        "ทิศ": st.column_config.SelectboxColumn(options=["x", "y"], required=True),
        "ΣPu": num(f"ΣPu ({fu})"), "Vus": num(f"Vus ({fu})"),
        "ลด stiffness แล้ว": st.column_config.CheckboxColumn(
            help="Δo จากโมเดลที่ใช้ 0.35Ig คาน / 0.70Ig เสา (ACI 6.6.3.1.1)"),
    })
story_names = [str(x) for x in sdf["ชั้น"].dropna().unique()] if len(sdf) else []
story_name = st.selectbox("เสาต้นนี้อยู่ชั้น", story_names or ["(ไม่มีข้อมูลชั้น)"], key="c_mystory")

if st.button("ตรวจสอบเสา", type="primary"):
    st.session_state.col_go = True
if not st.session_state.get("col_go"):
    st.info("กรอกข้อมูลแล้วกด **ตรวจสอบเสา** — ค่าเริ่มต้นคือตัวอย่างเสาชะลูด S1 ในเอกสารของสกิล")
    st.stop()


def val(x, d=0.0):
    try:
        x = float(x)
        return d if math.isnan(x) else x
    except (TypeError, ValueError):
        return d


combos = []
for i, r in df.iterrows():
    if pd.isna(r.get("Pu")):
        continue
    combos.append(Combo(str(r.get("Combo") or f"#{i + 1}"), val(r["Pu"]) * F,
                        val(r["Mx_top"]) * M, val(r["Mx_bot"]) * M,
                        val(r["My_top"]) * M, val(r["My_bot"]) * M,
                        Vux=val(r["Vux"]) * F, Vuy=val(r["Vuy"]) * F,
                        curv_x=r.get("โค้ง x") or "auto", curv_y=r.get("โค้ง y") or "auto"))
if not combos:
    st.error("ยังไม่มี load combination")
    st.stop()

stories = []
for _, r in sdf.iterrows():
    if pd.isna(r.get("ชั้น")) or pd.isna(r.get("ΣPu")):
        continue
    stories.append(dict(story=str(r["ชั้น"]), direction=r.get("ทิศ") or "x",
                        combo=str(r.get("Combo") or ""), sumPu=val(r["ΣPu"]) * F,
                        Vus=val(r["Vus"]) * F, delta_o=val(r["Δo (mm)"]),
                        lc=u.m_to_mm(val(r["lc (m)"])), reduced=bool(r.get("ลด stiffness แล้ว"))))

try:
    inp = ColumnInput(b, h, fc, fy, fyt, cover, float(db), int(nx), int(ny), float(ds), s,
                      int(legs_x), int(legs_y), cover_to, dagg, grade420, lu_x, lu_y, k_x, k_y, L,
                      beta, r_method, EI_method, stories, story_name, omf, cover_min)
    out = run(inp, combos)
except ValueError as e:
    st.error(f"ข้อมูลไม่ถูกต้อง: {e}")
    st.stop()
sec = out["sec"]

fF = lambda x: x / F  # noqa: E731   N → หน่วยผู้ใช้
fM = lambda x: x / M  # noqa: E731

def show_classes():
    rows = []
    for c in out["classes"]:
        for cb, P, V, do, lc_, Q in c.rows:
            rows.append({"ชั้น": c.story, "ทิศ": c.direction, "Combo": cb, f"ΣPu ({fu})": fF(P),
                         f"Vus ({fu})": fF(V), "Δo (mm)": do, "lc (m)": lc_ / 1000, "Q": Q,
                         "ผล (Q max ของชั้น/ทิศ)": c.status if cb == c.combo else ""})
        if not c.rows:
            rows.append({"ชั้น": c.story, "ทิศ": c.direction, "ผล (Q max ของชั้น/ทิศ)": c.status})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"Q": st.column_config.NumberColumn(format="%.4f")})
    for c in out["classes"]:
        for n in c.notes:
            (st.warning if c.status == "ต้องยืนยัน" else st.info)(f"ชั้น {c.story} ทิศ {c.direction}: {n}")


if out["sway"]:
    mine = [f"ทิศ {c.direction} (Q = {c.Q_max:.4f})" for c in out["Q"] if c.status == "sway"]
    st.error(f"ชั้น {story_name} เป็นโครง **sway** {', '.join(mine)} — อยู่นอกขอบเขตของโปรแกรม "
             "(ยังไม่รองรับ δs) ใช้โมเมนต์จาก P-Δ analysis หรือรอส่วน sway")
    show_classes()
    st.dataframe(pd.DataFrame(out["summary"], columns=["รายการ", "ค่า", "สถานะ", "อ้างอิง"]),
                 hide_index=True, width="stretch")
    st.stop()

g = out["gov"]
gs = out["gov_shear"]
bad = [r for r in out["results"] if r.error]
for r in bad:
    st.error(f"{r.combo.name}: {r.error}")

m1, m2, m3, m4 = st.columns(4)
if g:
    m1.metric("ratio 3D สูงสุด", f"{g.ratio:.3f}", f"{g.combo.name} · {g.crit[0]}", delta_color="off")
m2.metric("φPn,max", f"{fF(sec.phiPn_max):,.1f} {fu}", f"ρg = {sec.rho * 100:.2f}%",
          delta_color="off")
if gs:
    m3.metric("Vu/φVn สูงสุด", f"{gs.shear_ratio:.3f}", gs.combo.name, delta_color="off")
nsl = sum(1 for r in out["results"] if not r.error and (r.sx.slender or r.sy.slender))
m4.metric("ชะลูด", f"{nsl}/{len(out['results'])} combo")

checked = [row for row in out["summary"] if row[2] in (PASS, FAIL)]
confirm = [row for row in out["summary"] if row[2] == "ต้องยืนยัน"]
if confirm and all(row[2] == PASS for row in checked) and not bad:
    st.warning("กำลังผ่าน แต่การจำแนก non-sway **ต้องยืนยัน** (โมเดลยังไม่ลด stiffness) — ดูแท็บ sway / non-sway")
elif all(row[2] == PASS for row in checked) and not bad:
    st.success("รายการที่ตรวจแล้วผ่านทั้งหมด — รายการ \"ยังไม่ตรวจ\" / \"ไม่มีข้อมูล\" ต้องตรวจเพิ่มเอง")
else:
    st.error("มีรายการไม่ผ่าน — ดูตารางสรุป")

t3d, t2d, tres, tq, tsl, tsh, tsum = st.tabs(["3D interaction", "กราฟตัดที่ Pu", "ผลทุก combo",
                                              "sway / non-sway", "ความชะลูด", "แรงเฉือน", "สรุป"])

with tq:
    show_classes()
    st.caption("Mx (ดัดรอบแกน x) ใช้ผลการเซทิศ y · My ใช้ผลการเซทิศ x · combo ที่มีแต่แรงแนวดิ่ง"
               "ใช้ผลจำแนกของชั้น/ทิศ")

with t3d:
    surf = C.surface(sec, n_theta=48, n_c=28)
    surf.append(surf[0])
    X = [[fM(p[2]) for p in row] for row in surf]
    Y = [[fM(p[1]) for p in row] for row in surf]
    Z = [[fF(p[0]) for p in row] for row in surf]
    fig = go.Figure(go.Surface(x=X, y=Y, z=Z, opacity=0.55, colorscale="Blues", showscale=False,
                               name="φ-surface", hoverinfo="skip"))
    xs, ys, zs, cs, tx = [], [], [], [], []
    for r in out["results"]:
        if r.error:
            continue
        for lab, mx, my, cap in r.points:
            if cap is None:
                continue
            xs.append(fM(my))
            ys.append(fM(mx))
            zs.append(fF(r.combo.Pu))
            cs.append("#c62828" if cap.ratio > 1 else "#111")
            tx.append(f"{r.combo.name} {lab}<br>ratio {cap.ratio:.3f}")
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="markers", text=tx, hoverinfo="text",
                               marker=dict(size=5, color=cs), name="จุดโหลด"))
    fig.update_layout(height=620, margin=dict(l=0, r=0, t=10, b=0), scene=dict(
        xaxis_title=f"φMny ({mu})", yaxis_title=f"φMnx ({mu})", zaxis_title=f"φPn ({fu})"))
    st.plotly_chart(fig, width="stretch")
    st.caption("ผิวสีฟ้า = φ-surface (ตัดที่ φPn,max) · จุดดำ = โหลดที่ผ่าน · จุดแดง = เกินความจุ · "
               "ลากเพื่อหมุนกราฟ")

with t2d:
    names = [r.combo.name for r in out["results"] if not r.error]
    pick = st.selectbox("Combination", names, index=names.index(g.combo.name) if g else 0,
                        key="c_pick")
    rr = next(r for r in out["results"] if r.combo.name == pick)
    cont = C.contour_at(sec, rr.combo.Pu, 96)
    fig2 = go.Figure()
    if cont:
        fig2.add_trace(go.Scatter(x=[fM(p[1]) for p in cont], y=[fM(p[0]) for p in cont],
                                  mode="lines", fill="toself", name="φM ที่ Pu",
                                  fillcolor="rgba(31,78,156,0.12)",
                                  line=dict(color="#1f4e9c")))
    for lab, mx, my, cap in rr.points:
        if cap is None:
            continue
        fig2.add_trace(go.Scatter(x=[0, fM(my)], y=[0, fM(mx)], mode="lines+markers",
                                  name=f"{lab} ({cap.ratio:.3f})",
                                  marker=dict(size=[0, 10]), line=dict(dash="dot")))
    fig2.update_layout(height=520, xaxis_title=f"Muy ({mu})", yaxis_title=f"Mux ({mu})",
                       yaxis_scaleanchor="x", margin=dict(l=10, r=10, t=30, b=10),
                       title=f"Pu = {fF(rr.combo.Pu):,.1f} {fu}")
    st.plotly_chart(fig2, width="stretch")

with tres:
    rows = []
    for r in out["results"]:
        if r.error:
            rows.append({"Combo": r.combo.name, "ตำแหน่ง": r.error})
            continue
        for lab, mx, my, cap in r.points:
            rows.append({"Combo": r.combo.name, "ตำแหน่ง": lab, f"Pu ({fu})": fF(r.combo.Pu),
                         f"Mux ({mu})": fM(mx), f"Muy ({mu})": fM(my),
                         f"Mres ({mu})": fM(cap.Mres) if cap else None,
                         f"φMcap ({mu})": fM(cap.phiMcap) if cap else None,
                         "φ": cap.pt.phi if cap and cap.pt else None,
                         "ratio": cap.ratio if cap else None})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={k: st.column_config.NumberColumn(format="%.3f" if k in ("φ", "ratio")
                                                                 else "%.2f")
                                for k in rows[0] if k not in ("Combo", "ตำแหน่ง")} if rows else None)

with tsl:
    rows = []
    for r in out["results"]:
        if r.error:
            continue
        for S in (r.sx, r.sy):
            rows.append({"Combo": r.combo.name, "แกน": S.axis, "klu/r": S.klu_r,
                         "M1/M2": S.ratio_M1M2, "เกณฑ์": S.limit, "ชะลูด": "ใช่" if S.slender else "-",
                         "δ": S.delta if S.slender else None,
                         f"Mc ({mu})": fM(S.Mc) if S.slender and S.stable else None,
                         "ทิศการดัด": S.ratio_note})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

with tsh:
    rows = []
    for r in out["results"]:
        if r.error:
            continue
        for sr in (r.shear_y, r.shear_x):
            rows.append({"Combo": r.combo.name, "ทิศ": sr.direction, f"Vu ({fu})": fF(sr.Vu),
                         "สมการ Vc": sr.vc_eq, f"Vc ({fu})": fF(sr.Vc), f"Vs ({fu})": fF(sr.Vs),
                         f"φVn ({fu})": fF(sr.phiVn), "Vu/φVn": sr.ratio,
                         "ต้องมีปลอกรับเฉือน": "ใช่" if sr.min_required else "-",
                         "สถานะ": PASS if sr.ok else FAIL})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

with tsum:
    st.dataframe(pd.DataFrame(out["summary"], columns=["รายการ", "ค่า", "สถานะ", "อ้างอิง"]),
                 hide_index=True, width="stretch")

sheet = build_column_calsheet(proj, out)
fname = f"calsheet_{proj.member or 'column'}".replace(" ", "_")
st.download_button("🖨️ ดาวน์โหลด Calsheet A4 (.html)", sheet, file_name=f"{fname}.html",
                   mime="text/html", type="primary", key="c_dl",
                   help="เปิดไฟล์ในเบราว์เซอร์ แล้วกดปุ่มพิมพ์ หรือ Ctrl+P → Save as PDF")
with st.expander("ดูตัวอย่าง Calsheet A4"):
    components.html(sheet, height=900, scrolling=True)
st.caption("ผลลัพธ์ใช้ประกอบรายการคำนวณ วิศวกรผู้รับผิดชอบต้องตรวจสอบและลงนาม · ยังไม่ตรวจ: "
           "รอยต่อคาน-เสา, ระยะทาบ/ฝังยึด · ไม่รองรับโครง sway, SMF/IMF, เสากลม")
