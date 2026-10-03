"""ขั้นที่ 1–2: นำเข้าโมเดล STAAD.Pro (.std) และผลวิเคราะห์ (.anl) — เปิดผ่าน app.py"""
import pandas as pd
import streamlit as st

from rcbeam.nav import page_link
from rcbeam.colcheck import C
from rcbeam.staad_example import load_example
from rcbeam.staad_view import model_figure, plan_figure
import staad_io as S   # noqa: E402  (อยู่ใน skills/rc-column-aci318m19/scripts ซึ่ง colcheck เพิ่มเข้า sys.path แล้ว)


st.title("โมเดล STAAD.Pro")
st.caption("ขั้นที่ 1 Geometry (.std) → ขั้นที่ 2 ผลวิเคราะห์ (.anl) → ขั้นที่ 3 ออกแบบ (หน้าเสา) · "
           "อ่านแกน, หน้าตัด, start node, ความยาว, หน่วย และ combo จากไฟล์โดยตรง ไม่ต้องเดา")


def _read(up):
    raw = up.getvalue()
    for enc in ("utf-8", "cp874", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


# ---------------------------------------------------------------- ขั้นที่ 1
st.header("ขั้นที่ 1 · Geometry และน้ำหนักบรรทุก (.std)")
c1, c2 = st.columns([3, 1])
up = c1.file_uploader("ไฟล์ input ของ STAAD (.std) — หรือใช้ไฟล์ .anl ก็ได้ (อ่านจากสำเนา input ต้นไฟล์)",
                      type=["std", "anl", "txt"], key="sm_std")
if c2.button("ใช้โมเดลตัวอย่าง", help="โครง 1 ชั้น 3×2 ช่วง (references/staad_example/frame_3x2.std ของ skill)"):
    load_example(st.session_state)
if up is not None and st.session_state.get("std_name") != up.name + str(up.size):
    raw = _read(up)
    echo = S.extract_input_echo(raw) if up.name.lower().endswith((".anl", ".txt")) else None
    st.session_state.std_text = echo or raw
    st.session_state.std_name = up.name + str(up.size)
    st.session_state.pop("anl_text", None)
    if echo:                                        # .anl ไฟล์เดียว: ใช้เป็นผลวิเคราะห์ด้วย
        st.session_state.anl_text = raw
        st.session_state.anl_name = up.name + str(up.size)

if not st.session_state.get("std_text"):
    st.info("อัปโหลดไฟล์ .std หรือกด **ใช้โมเดลตัวอย่าง**")
    st.stop()

try:
    M = S.parse_std(st.session_state.std_text)
except Exception as e:                                  # noqa: BLE001 — แจ้งผู้ใช้แทนการล่ม
    st.error(f"อ่านไฟล์ .std ไม่ได้: {e}")
    st.stop()
st.session_state.staad_model = M
if not M.members:
    st.error("ไม่พบ JOINT COORDINATES / MEMBER INCIDENCES ในไฟล์")
    st.stop()

cols, beams = M.columns(), M.beams()
k = st.columns(5)
k[0].metric("joint", len(M.joints))
k[1].metric("member", len(M.members))
k[2].metric("เสา (แนวดิ่ง)", len(cols))
k[3].metric("load case / combo", f"{len(M.primaries())} / {len(M.combos())}")
k[4].metric("หน่วยในไฟล์", " ".join(M.units))
miss = [m for m in M.members if m not in M.prism]
if miss:
    st.warning(f"member ที่ไม่มีหน้าตัด PRIS (อาจเป็นเหล็กรูปพรรณหรือไม่ได้กำหนด): {miss[:20]}"
               + (" …" if len(miss) > 20 else ""))

loads = list(M.loads)
v1, v2, v3 = st.columns([2, 2, 1])
show_load = v1.selectbox("แสดงน้ำหนักบรรทุก", [None] + loads, key="sm_load",
                         format_func=lambda x: "— ไม่แสดง —" if x is None else
                         f"{x}: {M.loads[x].title}")
hl = v2.selectbox("เน้นเสา / แสดงแกน local", [None] + cols, key="sm_hl",
                  format_func=lambda x: "— ไม่เลือก —" if x is None else f"member {x}")
jid = v3.checkbox("เลข joint", key="sm_jid")
g1, g2 = st.columns([3, 2])
with g1:
    st.plotly_chart(model_figure(M, show_load, hl, joint_ids=jid), width="stretch")
with g2:
    st.markdown("**ผังมองจากด้านบน** (หน้าตัดเสาตามขนาดจริง)")
    st.plotly_chart(plan_figure(M, hl), width="stretch")
    st.caption("เสาแนวดิ่ง beta = 0: YD ขนานแกนโลก X (Mz ใช้ความลึก YD), ZD ขนานแกนโลก Z (My ใช้ความลึก ZD)")

t1, t2, t3, t4 = st.tabs(["เสา", "คาน", "Load case", "Load combination"])
with t1:
    st.dataframe(pd.DataFrame([{
        "member": m, "start": M.members[m][0], "end": M.members[m][1],
        "start อยู่": "ล่าง" if M.bottom_top(m)[0] == M.members[m][0] else "บน", "L (m)": M.length(m) / 1000,
        "YD (mm)": M.prism.get(m, (None, None))[0], "ZD (mm)": M.prism.get(m, (None, None))[1],
        "beta (°)": M.beta.get(m, 0.0)} for m in cols]), hide_index=True, width="stretch")
    top = [m for m in cols if M.bottom_top(m)[0] != M.members[m][0]]
    if top:
        st.info(f"เสา {top} วาดจากบนลงล่าง (start node อยู่บน) — แอปยังใช้ Fx ที่ start node เป็น P ได้ถูกต้อง")
with t2:
    st.dataframe(pd.DataFrame([{"member": m, "start": M.members[m][0], "end": M.members[m][1],
                                "L (m)": M.length(m) / 1000, "YD (mm)": M.prism.get(m, (None, None))[0],
                                "ZD (mm)": M.prism.get(m, (None, None))[1]} for m in beams]),
                 hide_index=True, width="stretch")
with t3:
    st.dataframe(pd.DataFrame([{"LOAD": lc.id, "ชนิด": lc.loadtype, "ชื่อ": lc.title,
                                "แรงด้านข้าง": "มี" if lc.lateral else "-",
                                "คำสั่ง": " · ".join(lc.lines)} for lc in M.primaries()]),
                 hide_index=True, width="stretch")
with t4:
    st.dataframe(pd.DataFrame([{
        "COMB": lc.id, "ชื่อ": lc.title,
        "ตัวคูณ": " + ".join(f"{f:g}×LC{k}" for k, f in lc.factors.items()),
        "ประเภท": "ใช้งาน (service) — ไม่ใช้ออกแบบกำลัง" if M.is_service(lc.id) else "กำลัง (strength)",
        "แรงด้านข้าง": "มี" if M.is_lateral(lc.id) else "-"} for lc in M.combos()]),
        hide_index=True, width="stretch")
    st.caption("combo ที่ตัวคูณทุกตัว = 1.0 หรือชื่อมีคำว่า SERVICE / ASD / DEFLECTION ถือเป็น service "
               "และถูกตัดออกจากการออกแบบกำลังโดยอัตโนมัติ (แก้ได้ในหน้าออกแบบ)")
for name, mat in M.material.items():
    if "STRENGTH FCU" in mat:
        st.warning(f"วัสดุ {name}: STRENGTH FCU = {mat['STRENGTH FCU']:.1f} MPa เป็นกำลังแท่ง**ลูกบาศก์** (BS) — "
                   "ACI ใช้ f′c แท่งทรงกระบอก (ต่ำกว่า) กำหนด f′c เองในหน้าออกแบบ")
if not any(M.is_lateral(c.id) for c in M.combos()):
    st.info("โมเดลนี้มีแต่น้ำหนักแนวดิ่ง (ไม่พบลม/แผ่นดินไหว/แรงด้านข้าง)")

# ---------------------------------------------------------------- ขั้นที่ 2
st.header("ขั้นที่ 2 · ผลวิเคราะห์ (แรงใน member)")
SRC2 = {"table": "วางตาราง Beam End Force จาก STAAD (แนะนำ)", "anl": "อัปโหลดไฟล์ .anl"}
src2 = st.radio("แหล่งแรง", list(SRC2), horizontal=True, key="sm_src2", format_func=SRC2.get)
anl_text = st.session_state.get("anl_text")
if src2 == "table":
    st.caption("ใน STAAD (หน้า Postprocessing) เปิดตาราง **Beam End Force** → คลิกมุมซ้ายบนของตารางเพื่อเลือกทั้งหมด → "
               "**Ctrl+C** → วางข้างล่าง · ต้องติดแถวหัวตาราง (มีหน่วย เช่น kg, kN-m) มาด้วย · "
               "แถวที่เว้น Beam / L/C ว่างไว้ แอปเติมจากแถวบนให้เอง")
    tbl = st.text_area("ตาราง Beam End Force (ทุก member)", height=180, key="sm_table",
                       placeholder="Beam\tL/C\tNode\tAxial Force kg\tShear-Y kg\t...")
    if not tbl.strip():
        st.info("วางตารางเพื่อไปขั้นที่ 3")
        st.session_state.pop("staad_forces", None)
        st.stop()
    try:
        Fo = S.forces_from_table(tbl, C.parse_staad_end_forces, C.STAAD_FORCE_UNITS, C.STAAD_MOMENT_UNITS)
    except ValueError as e:
        st.error(str(e))
        st.session_state.pop("staad_forces", None)
        st.stop()
    if not Fo.data:
        st.error("อ่านแถวข้อมูลไม่ได้ — ต้องมีคอลัมน์ Beam, L/C, Node, Axial, Shear-Y, Shear-Z, Torsion, Moment-Y, Moment-Z")
        st.session_state.pop("staad_forces", None)
        st.stop()
else:
    st.caption("ไฟล์ .anl ต้องมีตาราง MEMBER END FORCES — ในไฟล์ .std ต้องมีบรรทัด `PRINT MEMBER FORCES` ต่อจาก "
               "`PERFORM ANALYSIS` (`PRINT ALL` อย่างเดียวไม่พิมพ์แรงใน member) · หน่วยอ่านจากบรรทัด `ALL UNITS ARE` · "
               "ถ้าอัปโหลด .anl ไว้ในขั้นที่ 1 แล้วไม่ต้องอัปโหลดซ้ำ")
    up2 = st.file_uploader("ไฟล์ผลวิเคราะห์ (.anl)", type=["anl", "txt"], key="sm_anl")
    if up2 is not None and st.session_state.get("anl_name") != up2.name + str(up2.size):
        st.session_state.anl_text = anl_text = _read(up2)
        st.session_state.anl_name = up2.name + str(up2.size)
    if not anl_text:
        st.info("อัปโหลดไฟล์ .anl เพื่อไปขั้นที่ 3")
        st.session_state.pop("staad_forces", None)
        st.stop()
    try:
        Fo = S.parse_anl(anl_text)
    except ValueError as e:
        st.error(str(e))
        st.stop()
# ตรวจน้ำหนักรวมของแต่ละ load: STAAD (SUMMATION FORCE-Y) เทียบกับที่แอปคำนวณจาก geometry/หน้าตัด/หน่วยที่อ่านได้
tot = S.applied_totals(anl_text) if anl_text else {}
if tot:
    rows, ok_all = [], True
    for lid, (fx, fy, fz) in sorted(tot.items()):
        est, how = M.vertical_total(lid) if lid in M.loads and M.loads[lid].kind == "primary" else (None, "")
        diff = None if est is None or abs(fy) < 1e-9 else (est - fy) / abs(fy)
        ok = diff is not None and abs(diff) <= 0.01
        ok_all &= ok or est is None
        rows.append({"LOAD": lid, "ชื่อ": M.loads[lid].title if lid in M.loads else "",
                     "STAAD ΣFy (kN)": fy / 1e3, "แอปคำนวณ (kN)": None if est is None else est / 1e3,
                     "ต่าง (%)": None if diff is None else diff * 100, "วิธี": how,
                     "ผล": "✓" if ok else ("ตรวจไม่ได้" if est is None else "✗")})
    with st.expander("ตรวจน้ำหนักรวมแต่ละ load กับ STAAD", expanded=not ok_all):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.2f")
                                    for c in ("STAAD ΣFy (kN)", "แอปคำนวณ (kN)", "ต่าง (%)")})
    (st.success if ok_all else st.warning)(
        "น้ำหนักรวมทุก load ตรงกับ STAAD (±1%) — geometry, หน้าตัด, วัสดุ และหน่วยที่อ่านจาก .std ถูกต้อง"
        if ok_all else "น้ำหนักรวมบาง load ไม่ตรงกับ STAAD — ตรวจว่าไฟล์ .std กับ .anl เป็นโมเดลเดียวกัน")
if src2 == "anl" and not Fo.data:
    st.error("**ไฟล์ .anl นี้ไม่มีตาราง MEMBER END FORCES** — `PERFORM ANALYSIS PRINT ALL` ไม่ได้พิมพ์แรงใน member "
             "ให้เพิ่มคำสั่งพิมพ์ในไฟล์ .std ต่อจากบรรทัด PERFORM ANALYSIS แล้วรันใหม่:")
    st.code("PERFORM ANALYSIS PRINT ALL\nPRINT MEMBER FORCES\nFINISH", language=None)
    st.caption("ถ้าโมเดลใหญ่ พิมพ์เฉพาะเสาได้ เช่น `PRINT MEMBER FORCES LIST 1 TO 12` · ใน STAAD ทำผ่านเมนู "
               "Analysis → Post-Analysis Print → Member Forces ก็ได้ · หรือเลือก **วางตาราง Beam End Force** แทน")
    st.session_state.pop("staad_forces", None)
    st.stop()

unknown = [m for m in Fo.members() if m not in M.members]
if unknown:
    st.error(f"member {unknown[:10]} อยู่ใน .anl แต่ไม่มีใน .std — ไฟล์ไม่ใช่โมเดลเดียวกัน?")
    st.stop()
st.session_state.staad_forces = Fo
# ตรวจว่าแรงครบทุกเสา: แรงอัดที่ฐานเสาทุกต้นรวมกัน = น้ำหนักแนวดิ่งรวมที่คำนวณจาก .std
rows_b, ok_b = [], True
for lid in Fo.loads():
    if lid not in M.loads:
        continue
    exp_ = 0.0
    for p, fct in M.expand(lid).items():
        v, _ = M.vertical_total(p)
        if v is None:
            exp_ = None
            break
        exp_ += fct * v
    got, n, nsup = S.base_reactions(M, Fo, lid)
    ok = exp_ is not None and n == nsup and abs(got + exp_) <= 0.01 * max(abs(exp_), 1.0)
    ok_b &= ok
    rows_b.append({"load": lid, "ชื่อ": M.loads[lid].title, "Σ แรงอัดฐานเสา (kN)": got / 1e3,
                   "น้ำหนักแนวดิ่งจาก .std (kN)": None if exp_ is None else -exp_ / 1e3,
                   "เสาที่มีแรง": f"{n}/{nsup}", "ผล": "✓" if ok else "✗"})
if rows_b:
    with st.expander("ตรวจแรงที่ฐานเสาเทียบน้ำหนักรวม", expanded=not ok_b):
        st.dataframe(pd.DataFrame(rows_b), hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in
                                    ("Σ แรงอัดฐานเสา (kN)", "น้ำหนักแนวดิ่งจาก .std (kN)")})
    (st.success if ok_b else st.warning)(
        "แรงอัดที่ฐานเสาทุกต้นรวมกันเท่ากับน้ำหนักรวมทุก load (±1%) — แรงครบทุกเสา หน่วยและ start/end ถูกต้อง"
        if ok_b else "แรงที่ฐานเสาไม่ตรงกับน้ำหนักรวม — ข้อมูลแรงอาจไม่ครบทุกเสา, หน่วยผิด, มีแรงด้านข้าง "
                     "หรือไม่ใช่โมเดลเดียวกัน (ตรวจตารางข้างใน)")
fcols = [m for m in cols if any((m, lc) in Fo.data for lc in Fo.loads())]
k = st.columns(4)
k[0].metric("หน่วยในตาราง", ", ".join(Fo.units))
k[1].metric("member ที่มีแรง", len(Fo.members()))
k[2].metric("เสาที่มีแรง", f"{len(fcols)}/{len(cols)}")
k[3].metric("load ในผล", len(Fo.loads()))
nocomb = [c for c in M.strength_combos() if c not in Fo.loads()]
if nocomb:
    st.warning(f"combo กำลัง {nocomb} ไม่มีในผลวิเคราะห์")

# ตรวจสมดุลของเสาทุกต้นด้วยความยาวจาก geometry (ยืนยันแกน/หน่วย/การจับคู่ start-end)
bad = []
for m in fcols:
    for lc in Fo.loads():
        if (m, lc) in Fo.data:
            try:
                ok, err = S.check_equilibrium(M, Fo, m, lc)
            except KeyError:
                ok, err = False, float("nan")
            if not ok:
                bad.append((m, lc, err))
if bad:
    st.error(f"สมดุลของเสาไม่ตรง {len(bad)} รายการ (เช่น member {bad[0][0]} load {bad[0][1]}) — "
             "อาจมีแรงกระทำกลางเสา หรือไฟล์ .anl ไม่ตรงกับ .std")
else:
    st.success("ตรวจสมดุลเสาทุกต้นทุก load ผ่าน (|F|·L = |Mt| ± |Mb| ด้วยความยาวจาก geometry) — "
               "แกน หน่วย และ start/end ถูกต้อง")

pick = st.selectbox("ดูแรงของเสา", fcols, key="sm_pick", format_func=lambda m: f"member {m}")
rows = []
CV = {"single": "ทางเดียว", "double": "สองทาง", "auto": "ปลายหนึ่ง = 0"}
for lc in Fo.loads():
    if (pick, lc) not in Fo.data:
        continue
    f = S.column_forces(M, Fo, pick, lc, C.from_staad)
    rows.append({"load": lc, "ชื่อ": M.loads[lc].title if lc in M.loads else "",
                 "ใช้ออกแบบ": "✓" if lc in M.strength_combos() else "",
                 "Pu ตีนเสา (kN)": f["Pu"] / 1e3,
                 "|Mz| ล่าง / บน (kN·m)": f"{f['Mxb'] / 1e6:.3f} / {f['Mxt'] / 1e6:.3f}", "Mz โค้ง": CV[f["curv_x"]],
                 "|My| ล่าง / บน (kN·m)": f"{f['Myb'] / 1e6:.3f} / {f['Myt'] / 1e6:.3f}", "My โค้ง": CV[f["curv_y"]],
                 "|Fy| (kN)": f["Vuy"] / 1e3, "|Fz| (kN)": f["Vux"] / 1e3})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
             column_config={c: st.column_config.NumberColumn(format="%.3f")
                            for c in ("Pu ตีนเสา (kN)", "|Fy| (kN)", "|Fz| (kN)")})
page_link("views/column.py", label="ไปขั้นที่ 3 · ออกแบบเสา", icon="🏛️")
