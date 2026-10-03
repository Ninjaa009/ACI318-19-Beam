"""หน้าออกแบบ/ตรวจสอบเสา คสล. ตาม ACI 318M-19 (tied, non-sway, biaxial) — เปิดผ่าน app.py"""
import datetime
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from rcbeam import units as u
from rcbeam.calsheet import ProjectInfo
from rcbeam.col_calsheet import build_column_calsheet, column_svg
from rcbeam.nav import page_link
from rcbeam.colcheck import C, ColumnInput, Combo, PASS, FAIL, run
import staad_io as S_IO  # noqa: E402  (skill scripts อยู่ใน sys.path จาก rcbeam.colcheck)

BARS = [12, 16, 19.1, 20, 25, 28, 32, 36]
TIES = [6, 9, 9.5, 10, 12]
CURV = ["auto", "single", "double"]

st.title("ออกแบบ/ตรวจสอบเสา คสล. ตาม ACI 318M-19")
st.caption("หน้าตัดสี่เหลี่ยม ปลอกเดี่ยว · โครง non-sway · 3D interaction (P–Mz–My) · ชื่อแกนตาม STAAD.Pro · "
           "ความชะลูด + ขยายโมเมนต์ · แรงเฉือนสองทิศ · ใช้ solver ของ skill rc-column-aci318m19")

# ---------------------------------------------------------------- แหล่งข้อมูล (ต้องอยู่ก่อน sidebar เพื่อเติมค่า)
SM, SF = st.session_state.get("staad_model"), st.session_state.get("staad_forces")
SRC = (["model"] if SM is not None and SF is not None else []) + ["manual"]
src = st.radio("แหล่งข้อมูล", SRC, horizontal=True, key=f"c_src_{len(SRC)}",
               format_func=lambda x: {"model": "โมเดล STAAD (.std + .anl) — ขั้นที่ 1–2",
                                      "manual": "ป้อน Mz / My เอง"}[x])
sel = None
for _k, _v in (("c_h", 0.40), ("c_b", 0.40), ("c_L", 5.0), ("c_lux", 4.5), ("c_luy", 4.5)):
    st.session_state.setdefault(_k, _v)
if src == "model":
    mcols = [m for m in SM.columns() if any((m, lc) in SF.data for lc in SF.loads())]
    sel = st.selectbox("เสา (member ในโมเดล)", mcols, key="c_member",
                       format_func=lambda m: f"member {m} · {SM.prism.get(m, (0, 0))[0]:.0f}×"
                                             f"{SM.prism.get(m, (0, 0))[1]:.0f} · L {SM.length(m) / 1000:.2f} m")
    if st.session_state.get("c_member_prev") != (sel, id(SM)):
        if sel in SM.prism:
            st.session_state.c_h = SM.prism[sel][0] / 1000
            st.session_state.c_b = SM.prism[sel][1] / 1000
        st.session_state.c_L = SM.length(sel) / 1000
        st.session_state.c_lux = st.session_state.c_luy = SM.length(sel) / 1000
        st.session_state.c_member_prev = (sel, id(SM))
    st.caption("YD, ZD และความยาวเติมจากโมเดลแล้ว (แก้ได้ในแถบข้าง) · l_u เริ่มต้น = ความยาว c/c "
               "(อนุรักษ์นิยม — ลดได้ตามระยะช่องว่างจริงระหว่างคาน)")
elif SM is None or SF is None:
    page_link("views/staad_model.py", label="หรือนำเข้าโมเดล STAAD (.std + .anl) ก่อน", icon="🧊")

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
    h = u.m_to_mm(st.number_input("YD (m) — ความลึกตามแกน local y", min_value=0.15, max_value=2.0, step=0.05,
                                  format="%.2f", key="c_h", help="ตรงกับ YD ในหน้าต่าง Prismatic ของ STAAD"))
    b = u.m_to_mm(st.number_input("ZD (m) — ความกว้างตามแกน local z", min_value=0.15, max_value=2.0, step=0.05,
                                  format="%.2f", key="c_b", help="ตรงกับ ZD ในหน้าต่าง Prismatic ของ STAAD"))
    cover = st.number_input("cover (mm)", 20.0, 100.0, 40.0, 5.0, key="c_cov")
    cover_to = st.radio("cover วัดถึง", ["tie", "long"], horizontal=True, key="c_covto",
                        format_func=lambda x: {"tie": "ผิวปลอก (ACI)", "long": "เหล็กยืน (RCDC)"}[x])
    db = st.selectbox("เหล็กยืน DB (mm)", BARS, index=3, key="c_db")
    c1, c2 = st.columns(2)
    nx = c1.number_input("เส้น/ด้าน ZD", 2, 12, 3, 1, key="c_nx")
    ny = c2.number_input("เส้น/ด้าน YD", 2, 12, 3, 1, key="c_ny")
    ds = st.selectbox("ปลอก (mm)", TIES, index=3, key="c_ds")
    s = st.number_input("ระยะปลอก s (mm)", 50.0, 600.0, 250.0, 25.0, key="c_s")
    c1, c2 = st.columns(2)
    legs_y = c1.number_input("ขาปลอกรับ Fy", 2, 8, 2, 1, key="c_ly", help="ขาที่ขนานแกน y (ตาม YD)")
    legs_x = c2.number_input("ขาปลอกรับ Fz", 2, 8, 2, 1, key="c_lx", help="ขาที่ขนานแกน z (ตาม ZD)")
    dagg = st.number_input("ขนาดหินใหญ่สุด (mm)", 10.0, 40.0, 20.0, 5.0, key="c_agg")
    cover_min = st.number_input("cover ขั้นต่ำที่ต้องการ (mm)", 20.0, 75.0, 40.0, 5.0, key="c_covmin",
                                help="Table 20.5.1.3.1 — เสาในอาคาร 40 mm")
    try:
        _bars, _tc = C.rect_bars(b, h, cover, float(ds), float(db), int(nx), int(ny), cover_to)
        st.markdown(column_svg(C.Section(b, h, fc, fy, fyt, _bars, _tc, float(ds))),
                    unsafe_allow_html=True)
        st.caption("หน้าตัดตามหน้าต่าง Prismatic ของ STAAD: Mz ดัดรอบแกน z (ความลึก YD), "
                   "My ดัดรอบแกน y (ความลึก ZD)")
    except ValueError as e:
        st.error(f"หน้าตัด: {e}")

    st.header("ความยาวและความชะลูด")
    c1, c2 = st.columns(2)
    lu_x = u.m_to_mm(c1.number_input("l_u ของ Mz (m)", min_value=0.5, max_value=30.0, step=0.1, key="c_lux"))
    lu_y = u.m_to_mm(c2.number_input("l_u ของ My (m)", min_value=0.5, max_value=30.0, step=0.1, key="c_luy"))
    k_x = c1.number_input("k ของ Mz", 0.5, 1.0, 1.0, 0.05, key="c_kx")
    k_y = c2.number_input("k ของ My", 0.5, 1.0, 1.0, 0.05, key="c_ky")
    L = u.m_to_mm(st.number_input("ความยาวชิ้นส่วน c/c (m)", min_value=0.5, max_value=30.0, step=0.1, key="c_L",
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

lunit = st.radio("หน่วยแรง", ["kN", "kgf"], horizontal=True, key="c_lunit",
                 format_func=lambda x: {"kN": "kN, kN·m", "kgf": "kgf, kgf·m"}[x])
F = 1e3 if lunit == "kN" else u.G                 # → N
M = 1e6 if lunit == "kN" else u.KGFM_TO_NMM       # → N·mm
fu, mu = ("kN", "kN·m") if lunit == "kN" else ("kgf", "kgf·m")
fF = lambda x: x / F  # noqa: E731   N → หน่วยผู้ใช้
fM = lambda x: x / M  # noqa: E731
num = lambda lab: st.column_config.NumberColumn(lab, format="%.2f")  # noqa: E731


def val(x, d=0.0):
    try:
        x = float(x)
        return d if math.isnan(x) else x
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------- ออกแบบ non-sway
st.info("ออกแบบเป็น **เสาในโครง non-sway** — ผู้ออกแบบต้องยืนยันเองว่าโครงไม่เซ (Q ≤ 0.05 ตาม ACI 6.6.4.3 "
        "หรือมีผนังรับแรงเฉือน/โครงค้ำยัน) · 🚧 **Incoming:** ระบบตรวจ sway / non-sway และการออกแบบเสา sway")
st.header("ข้อมูลแรง")
mode = "model" if src == "model" else "app"
if mode == "model":
    strength = SM.strength_combos()
    avail = [lc for lc in SF.loads() if (sel, lc) in SF.data]
    c1, c2 = st.columns(2)
    use = c1.multiselect("combo ที่ใช้ออกแบบ (ตัด combo ใช้งาน/primary load ออกแล้ว)", avail,
                         [lc for lc in avail if lc in strength], key=f"c_muse_{sel}",
                         format_func=lambda x: f"{x}: {SM.loads[x].title}" if x in SM.loads else str(x))
    c2.markdown("**ตรวจเครื่องหมาย P:** ใช้ combo ที่ไม่มีแรงด้านข้าง (อ่านจากนิยาม load ในไฟล์ .std)")
    a_, b_ = SM.members[sel]
    st.caption(f"member {sel}: start = N{a_} ({'ล่าง' if SM.bottom_top(sel)[0] == a_ else 'บน'}), end = N{b_} · "
               f"P = Fx ที่ N{a_} · Mz คู่ Fy (ความลึก YD) · My คู่ Fz (ความลึก ZD) · หน่วยจาก .anl: "
               f"{', '.join(SF.units)}")
    rows_in = []
    for lc in use:
        f = S_IO.column_forces(SM, SF, sel, lc, C.from_staad)
        cx, cy = f.pop("curv_x"), f.pop("curv_y")                             # จากเครื่องหมายโมเมนต์ปลาย
        f = {k: v / (M if k[0] == "M" else F) for k, v in f.items()}            # N, N·mm → หน่วยที่แสดง
        rows_in.append((str(lc), f, not SM.is_lateral(lc), cx, cy))
    if rows_in:
        with st.expander(f"ค่าที่ใช้คำนวณ ({fu}, {mu})", expanded=True):
            CV = {"single": "ทางเดียว", "double": "สองทาง", "auto": "ปลายหนึ่ง = 0"}
            st.dataframe(pd.DataFrame([{"combo": n, f"Pu ตีนเสา ({fu})": f["Pu"],
                                        f"|Mz| บน ({mu})": f["Mxt"], f"|Mz| ล่าง ({mu})": f["Mxb"],
                                        "Mz โค้ง": CV[cx],
                                        f"|My| บน ({mu})": f["Myt"], f"|My| ล่าง ({mu})": f["Myb"],
                                        "My โค้ง": CV[cy],
                                        f"|Fy| ({fu})": f["Vuy"], f"|Fz| ({fu})": f["Vux"]}
                                       for n, f, _g, cx, cy in rows_in]), hide_index=True, width="stretch")
            st.caption("บน/ล่างตัดสินจากพิกัด Y ของ joint · ทิศการดัดจากเครื่องหมายโมเมนต์ปลายใน STAAD "
                       "(เครื่องหมายเดียวกัน = โค้งสองทาง) · M2 = ปลายที่โมเมนต์มากกว่า, M1 = ปลายที่น้อยกว่า")
    else:
        st.warning("ยังไม่ได้เลือก combo")
else:
    st.caption("ชื่อแกนตาม STAAD · Mz ดัดรอบแกน z (ความลึก YD) คู่กับ Fy · My ดัดรอบแกน y (ความลึก ZD) "
               "คู่กับ Fz · P > 0 = อัด · ทิศการดัด auto = ตัดสินจาก |F|·L")
    default = pd.DataFrame([
        {"Combo": "S1", "แนวดิ่งล้วน": False, "Pu": 1600.0, "Mz_top": 90.0, "Mz_bot": 60.0,
         "My_top": 30.0, "My_bot": 20.0, "Fy": 6.0, "Fz": 10.0, "โค้ง z": "auto", "โค้ง y": "auto"},
        {"Combo": "LC2", "แนวดิ่งล้วน": False, "Pu": 900.0, "Mz_top": 40.0, "Mz_bot": -35.0,
         "My_top": 10.0, "My_bot": 5.0, "Fy": 15.0, "Fz": 3.0, "โค้ง z": "auto", "โค้ง y": "auto"},
    ])
    df = st.data_editor(
        default, num_rows="dynamic", width="stretch", key="c_loads",
        column_config={
            "Pu": num(f"Pu ({fu})"), "Mz_top": num(f"Mz บน ({mu})"), "Mz_bot": num(f"Mz ล่าง ({mu})"),
            "My_top": num(f"My บน ({mu})"), "My_bot": num(f"My ล่าง ({mu})"),
            "Fy": num(f"Fy ({fu})"), "Fz": num(f"Fz ({fu})"),
            "โค้ง z": st.column_config.SelectboxColumn(options=CURV),
            "โค้ง y": st.column_config.SelectboxColumn(options=CURV),
            "แนวดิ่งล้วน": st.column_config.CheckboxColumn(help="combo ที่มีแต่ D, L (ใช้ตรวจเครื่องหมาย P)"),
        })
    rows_in = []
    for i, r in df.iterrows():
        if pd.isna(r.get("Pu")):
            continue
        f = {"Pu": val(r["Pu"]), "Mxt": val(r["Mz_top"]), "Mxb": val(r["Mz_bot"]),
             "Myt": val(r["My_top"]), "Myb": val(r["My_bot"]), "Vuy": val(r["Fy"]),
             "Vux": val(r["Fz"])}
        rows_in.append((str(r.get("Combo") or f"#{i + 1}"), f, bool(r.get("แนวดิ่งล้วน")),
                        r.get("โค้ง z") or "auto", r.get("โค้ง y") or "auto"))

# ตรวจเครื่องหมาย P จาก combo แนวดิ่งล้วน
sign_ok, sign_msgs = C.check_axial_sign([(n, f["Pu"], g) for n, f, g, *_ in rows_in])
for m in sign_msgs:
    (st.warning if sign_ok else st.error)(m)
ready = sign_ok

if st.button("ตรวจสอบเสา", type="primary", disabled=not ready,
             help=None if ready else "ต้องตรวจเครื่องหมาย P ก่อน"):
    st.session_state.col_go = True
if not ready:
    st.info("ปุ่ม **ตรวจสอบเสา** จะใช้ได้เมื่อเครื่องหมาย P ถูกต้อง")
    st.stop()
if not st.session_state.get("col_go"):
    st.info("กรอกข้อมูลแล้วกด **ตรวจสอบเสา**" + ("" if src == "model" else
            " — ค่าเริ่มต้นคือตัวอย่างเสาชะลูด S1 ในเอกสารของสกิล"))
    st.stop()

combos = [Combo(n, f["Pu"] * F, f["Mxt"] * M, f["Mxb"] * M, f["Myt"] * M, f["Myb"] * M,
                Vux=f["Vux"] * F, Vuy=f["Vuy"] * F, curv_x=cx, curv_y=cy)
          for n, f, _g, cx, cy in rows_in]
if not combos:
    st.error("ยังไม่มี load combination")
    st.stop()

try:
    inp = ColumnInput(b, h, fc, fy, fyt, cover, float(db), int(nx), int(ny), float(ds), s,
                      int(legs_x), int(legs_y), cover_to, dagg, grade420, lu_x, lu_y, k_x, k_y, L,
                      beta, r_method, EI_method, omf=omf, cover_min=cover_min)
    out = run(inp, combos)
except ValueError as e:
    st.error(f"ข้อมูลไม่ถูกต้อง: {e}")
    st.stop()
sec = out["sec"]

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
if all(row[2] == PASS for row in checked) and not bad:
    st.success("รายการที่ตรวจแล้วผ่านทั้งหมด — รายการ \"ยังไม่ตรวจ\" / \"ไม่มีข้อมูล\" ต้องตรวจเพิ่มเอง")
else:
    st.error("มีรายการไม่ผ่าน — ดูตารางสรุป")

t3d, t2d, tres, tsl, tsh, tsum = st.tabs(["3D interaction", "กราฟตัดที่ Pu", "ผลทุก combo",
                                         "ความชะลูด", "แรงเฉือน", "สรุป"])

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
        xaxis_title=f"φMny ({mu})", yaxis_title=f"φMnz ({mu})", zaxis_title=f"φPn ({fu})"))
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
    fig2.update_layout(height=520, xaxis_title=f"My ({mu})", yaxis_title=f"Mz ({mu})",
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
                         f"Mz ({mu})": fM(mx), f"My ({mu})": fM(my),
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
            rows.append({"Combo": r.combo.name, "แกน": "Mz" if S.axis == "x" else "My",
                         "klu/r": S.klu_r,
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
            rows.append({"Combo": r.combo.name, "แรง": "Fy" if sr.direction == "y" else "Fz",
                         f"Vu ({fu})": fF(sr.Vu),
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
