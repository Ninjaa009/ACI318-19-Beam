"""คู่มือสูตร: อธิบายทุกสูตรที่แอปใช้คำนวณ พร้อมความหมายของตัวแปรทุกตัว — เปิดผ่าน app.py

เนื้อหาต้องตรงกับโค้ดจริง: rcbeam/flexure.py, rcbeam/shear.py, rcbeam/report.py,
skills/rc-column-aci318m19/scripts/column.py และ staad_io.py
"""
import streamlit as st

st.title("คู่มือสูตรที่ใช้คำนวณ")
st.caption("ทุกสูตรในหน้านี้คือสูตรเดียวกับที่โปรแกรมใช้จริง · อ้างอิง ACI 318M-19 (หน่วย SI) · "
           "คำนวณภายในด้วย N, mm, MPa แล้วแปลงเป็น kgf, m, ksc ตอนแสดงผล")


def eq(latex, note=None, ref=None):
    """แสดงสมการ + บรรทัดอธิบาย/มาตราใต้สมการ"""
    st.latex(latex)
    tail = " · ".join(x for x in (note, f"ACI {ref}" if ref else None) if x)
    if tail:
        st.caption(tail)


def var(rows):
    """ตารางตัวแปร: (สัญลักษณ์ LaTeX, ความหมาย, หน่วย, มาจากไหน)"""
    md = ["| ตัวแปร | ความหมาย | หน่วย | ได้มาจาก |", "|---|---|---|---|"]
    md += [f"| ${s}$ | {m} | {u} | {f} |" for s, m, u, f in rows]
    st.markdown("\n".join(md))


tabs = st.tabs(["หน่วย & ค่าคงที่", "STAAD → แอป", "คาน · แรงดัด", "คาน · แรงเฉือน",
                "คาน · รายละเอียด", "เสา · กำลัง P–M", "เสา · ความชะลูด", "เสา · เฉือน & รายละเอียด"])

# ======================================================================== หน่วย
with tabs[0]:
    st.header("หน่วยและค่าคงที่")
    st.markdown("ผู้ใช้ป้อนค่าเป็น **kgf, kgf·m, ksc, m** (หรือ kN, MPa) → โปรแกรมแปลงเป็น **N, mm, MPa** "
                "ก่อนคำนวณทุกครั้ง แล้วแปลงกลับตอนแสดงผล")
    eq(r"1\ \mathrm{kgf} = 9.80665\ \mathrm{N} \qquad 1\ \mathrm{ksc} = 1\ \mathrm{kgf/cm^2} = 0.0980665\ \mathrm{MPa}"
       r"\qquad 1\ \mathrm{kgf\cdot m} = 9{,}806.65\ \mathrm{N\cdot mm}")
    var([
        (r"E_s", "โมดูลัสยืดหยุ่นของเหล็กเสริม", "200,000 MPa", "ค่าคงที่ §20.2.2.2"),
        (r"\varepsilon_{cu}", "ความเครียดสูงสุดที่ผิวคอนกรีตรับแรงอัด", "0.003", "ค่าคงที่ §22.2.2.1"),
        (r"f'_c", "กำลังอัดคอนกรีตทรงกระบอก (ไม่ใช่ลูกบาศก์ FCU)", "MPa", "ผู้ใช้ป้อน"),
        (r"f_y", "กำลังครากเหล็กยืน/เหล็กหลัก", "MPa", "ผู้ใช้ป้อน"),
        (r"f_{yt}", "กำลังครากเหล็กปลอก", "MPa", "ผู้ใช้ป้อน"),
        (r"\lambda", "ตัวคูณคอนกรีตมวลเบา (คอนกรีตปกติ = 1.0)", "-", "1.0 คงที่"),
        (r"\varepsilon_{ty}", r"ความเครียดครากของเหล็ก $= f_y/E_s$ (หรือ 0.002 ถ้าเลือกข้อยกเว้น Grade 420)",
         "-", "§21.2.2.1"),
        (r"\beta_1", "อัตราส่วนความลึก stress block ต่อแกนสะเทิน", "-", "สูตรข้างล่าง §22.2.2.4.3"),
        (r"E_c", r"โมดูลัสคอนกรีต $= 4700\sqrt{f'_c}$", "MPa", "§19.2.2.1(b)"),
    ])
    eq(r"\beta_1 = \begin{cases} 0.85 & f'_c \le 28 \\ 0.85 - \dfrac{0.05\,(f'_c-28)}{7} \ge 0.65 & f'_c > 28 \end{cases}",
       ref="Table 22.2.2.4.3")
    eq(r"\sqrt{f'_c} \le 8.3\ \mathrm{MPa}", "ใช้กับทุกสูตรแรงเฉือน", "§22.5.3.1")
    st.subheader("ตัวคูณลดกำลัง φ")
    eq(r"\phi = \begin{cases} 0.65 & \varepsilon_t \le \varepsilon_{ty} \quad (\text{ควบคุมด้วยแรงอัด}) \\"
       r" 0.65 + 0.25\,\dfrac{\varepsilon_t-\varepsilon_{ty}}{0.003} & \text{ช่วงเปลี่ยนผ่าน} \\"
       r" 0.90 & \varepsilon_t \ge \varepsilon_{ty}+0.003 \quad (\text{ควบคุมด้วยแรงดึง}) \end{cases}"
       r"\qquad \phi_v = 0.75\ (\text{แรงเฉือน})",
       "ใช้ทั้งคาน (แรงดัด) และเสาปลอกเดี่ยว (แรงอัดร่วมดัด)", "Table 21.2.1, 21.2.2")
    var([(r"\varepsilon_t", "ความเครียดดึงสุทธิในเหล็กชั้นที่ไกลผิวรับแรงอัดที่สุด", "-",
          "คำนวณจากตำแหน่งแกนสะเทิน c")])

# ======================================================================== STAAD
with tabs[1]:
    st.header("จาก STAAD.Pro เข้าแอป")
    st.subheader("1. ชื่อแกนและแรง")
    st.markdown("แรงในตาราง **Beam End Force** เป็นแรงที่กระทำ**ต่อปลาย member** ตามแกน local "
                "(x ตามแนว member จาก start → end, y ตามความลึก YD, z ตามความกว้าง ZD) — บวกตามทิศแกนที่ทั้งสองปลาย")
    var([
        (r"Y_D", "ความลึกหน้าตัดตามแกน local y (PRIS YD) → h ในแอป", "mm", ".std"),
        (r"Z_D", "ความกว้างหน้าตัดตามแกน local z (PRIS ZD) → b ในแอป", "mm", ".std"),
        (r"F_x", "แรงตามแนวแกน — ที่ปลาย start บวก = แรงอัด", "N", "ตาราง"),
        (r"F_y,\ F_z", "แรงเฉือนตามแกน local y, z", "N", "ตาราง"),
        (r"M_z", "โมเมนต์รอบแกน local z — ดัดในระนาบ YD (คู่กับ Fy)", "N·mm", "ตาราง"),
        (r"M_y", "โมเมนต์รอบแกน local y — ดัดในระนาบ ZD (คู่กับ Fz)", "N·mm", "ตาราง"),
        (r"L", "ความยาว member จากพิกัด joint", "mm", ".std"),
    ])
    st.subheader("2. ตรวจสมดุลของ member (ไม่มีแรงกระทำระหว่างช่วง)")
    eq(r"M_{z,s} + M_{z,e} + F_{y,e}\,L = 0 \qquad M_{y,s} + M_{y,e} - F_{z,e}\,L = 0",
       "s = ปลาย start, e = ปลาย end · ผ่านแปลว่าแกน หน่วย และ start/end อ่านถูก (ยอมให้คลาด 2%)")
    st.subheader("3. ตรวจแรงครบทุกเสา")
    eq(r"\sum_{\text{เสาทุกต้นที่ฐาน}} P_{\text{ฐาน}} = \sum W_{\text{load}}",
       "แรงอัดที่ตีนเสาทุกต้นรวมกัน ต้องเท่ากับน้ำหนักแนวดิ่งรวมที่คำนวณจาก .std (selfweight + floor + member + joint load)")
    eq(r"W_{\text{self}} = \sum Y_D\,Z_D\,L\,\gamma \qquad W_{\text{floor}} = w \times \text{พื้นที่ XRANGE} \times \text{ZRANGE}")
    var([(r"\gamma", "หน่วยน้ำหนักวัสดุ (DENSITY ใน .std)", "N/mm³", ".std"),
         (r"w", "แรงแผ่บนพื้น (FLOAD)", "N/mm²", ".std")])
    st.subheader("4. เสา: บน/ล่าง และแรงอัด")
    st.markdown("ปลายบน/ล่างตัดสินจาก**พิกัด Y ของ joint** (ไม่สมมติว่า start อยู่ล่าง)")
    eq(r"P_u = \begin{cases} +F_{x,s} & \text{start อยู่ล่าง} \\ -F_{x,e} & \text{end อยู่ล่าง} \end{cases}"
       r"\qquad M_{x} \leftarrow M_z,\quad M_{y} \leftarrow M_y,\quad V_{uy} \leftarrow F_y,\quad V_{ux} \leftarrow F_z")
    st.markdown("**ทิศการดัด:** โมเมนต์ปลายสองข้างของ STAAD **เครื่องหมายเดียวกัน = โค้งสองทาง** (double), "
                "**ต่างกัน = โค้งทางเดียว** (single) → ใช้กำหนดเครื่องหมาย M1/M2 (ดูแท็บความชะลูด)")
    st.subheader("5. คาน: แปลงเครื่องหมายเป็นโมเมนต์ออกแบบ (บวก = ดึงล่าง)")
    eq(r"M_{\text{ซ้าย}} = -M_{z,s} \qquad M_{\text{ขวา}} = +M_{z,e}",
       "คานแนวราบ beta 0 เท่านั้น — M ลบ = ดึงบน (M−), M บวก = ดึงล่าง (M+)")
    eq(r"M(x) = -M_{z,s} + F_{y,s}\,x + \sum P_i\,(x-a_i) + \int_0^{x} w(t)\,(x-t)\,dt"
       r"\qquad V(x) = F_{y,s} + \sum P_i + \int_0^{x} w(t)\,dt")
    var([(r"x", "ระยะจากปลาย start ตามแนวคาน", "mm", "-"),
         (r"P_i,\ a_i", "แรงจุดบนคาน (+ ขึ้น) และตำแหน่งจาก start", "N, mm", ".std MEMBER LOAD CON"),
         (r"w(t)", "แรงแผ่บนคาน (+ ขึ้น) = selfweight + floor load + member UNI", "N/mm", ".std"),
         (r"M(x),\ V(x)", "โมเมนต์ (บวก = ดึงล่าง) และแรงเฉือนตลอดคาน", "N·mm, N", "สูตรนี้")])
    eq(r"\text{ตรวจปิด:}\quad M(L) = M_{z,e},\qquad V(L) = -F_{y,e}",
       "ถ้าปิดไม่ได้ (> 2%) แปลว่า load บนคานจาก .std ไม่ตรงกับที่ STAAD ใช้")
    st.subheader("6. FLOOR LOAD กระจายลงคาน (เส้น 45°)")
    st.markdown("แผ่นพื้น = ช่องสี่เหลี่ยมที่มีคานล้อมครบ 4 ด้าน ในช่วง YRANGE/XRANGE/ZRANGE · "
                "คานแต่ละด้านรับแรงแผ่:")
    eq(r"q(t) = w \cdot \min\!\left(t,\ \ell - t,\ \tfrac{s}{2}\right)",
       "ด้านยาว → สี่เหลี่ยมคางหมู, ด้านสั้น → สามเหลี่ยม · ตรงกับที่ STAAD แปลง (ΣP, ΣP·x, ΣP·x²)")
    var([(r"t", "ระยะตามขอบแผ่นจากมุม", "mm", "-"),
         (r"\ell", "ความยาวขอบแผ่น (ด้านที่คานรับ)", "mm", "geometry"),
         (r"s", "ด้านสั้นของแผ่นพื้น", "mm", "geometry"),
         (r"w", "แรงแผ่บนพื้น FLOAD (ลบ = ลง)", "N/mm²", ".std")])
    st.subheader("7. ค่าออกแบบของคาน")
    eq(r"M^-_{u} = M(x_{\text{ผิวเสา}}) \qquad x_{\text{ผิวเสา}} = \tfrac{1}{2}\,(\text{ด้านเสาในแนวคาน})",
       "โมเมนต์ลบที่ผิวเสา เมื่อคานหล่อเป็นเนื้อเดียวกับเสา", "§9.4.2.1")
    eq(r"M^+_{u} = \max_{x} M(x) \qquad V_u = |V(x_{\text{ผิวเสา}} + d)|,\quad d \approx h - 60\ \mathrm{mm}",
       "แรงเฉือนวิกฤตที่ระยะ d จากผิวเสา", "§9.4.3.2")

# ======================================================================== คาน ดัด
with tabs[2]:
    st.header("คาน · กำลังดัด (หน้าตัดสี่เหลี่ยม singly / doubly)")
    st.markdown("ใช้ **strain compatibility** ทุกชั้นเหล็ก: ระยะ $y$ ทุกตัววัด**ลงจากผิวรับแรงอัด** · "
                "แรงในเหล็ก บวก = อัด, ลบ = ดึง")
    var([
        (r"b,\ h", "ความกว้าง (ZD) และความลึก (YD) ของคาน", "mm", "ผู้ใช้ / STAAD"),
        (r"c_c", "ระยะหุ้ม (clear cover) ถึงผิวปลอก", "mm", "ผู้ใช้"),
        (r"d_s", "ขนาดเหล็กปลอก", "mm", "ผู้ใช้"),
        (r"d_b,\ d'_b", "ขนาดเหล็กดึง, เหล็กอัด", "mm", "ผู้ใช้"),
        (r"d", "ความลึกประสิทธิผล = ระยะถึงจุดศูนย์ถ่วงของเหล็กดึงทุกชั้น", "mm", "จากการวางเหล็ก"),
        (r"d_t", "ระยะถึงเหล็กดึงชั้นนอกสุด", "mm", "จากการวางเหล็ก"),
        (r"d'", "ระยะถึงศูนย์กลางเหล็กอัด", "mm", r"$c_c + d_s + d'_b/2$"),
        (r"c", "ระยะแกนสะเทินจากผิวรับแรงอัด", "mm", "แก้สมการ ΣF = 0"),
        (r"a", r"ความลึก stress block $= \beta_1 c \le h$", "mm", "-"),
        (r"A_s,\ A'_s", "พื้นที่เหล็กดึง, เหล็กอัด", "mm²", "-"),
        (r"M_u", "โมเมนต์ประลัย (ค่าบวก)", "N·mm", "ผู้ใช้ / STAAD"),
        (r"M_n,\ \phi M_n", "กำลังดัดระบุ, กำลังดัดออกแบบ", "N·mm", "-"),
    ])
    st.subheader("1. การวางเหล็ก")
    eq(r"y_1 = h - c_c - d_s - \tfrac{d_b}{2} \qquad y_{k+1} = y_k - (d_b + 25)",
       "ชั้นเหล็กดึง ชั้นแรกอยู่นอกสุด ช่องว่างระหว่างชั้น 25 mm", "§25.2.2")
    eq(r"s_{\text{clear}} = \max\!\left(25,\ d_b,\ \tfrac{4}{3} d_{agg}\right) \qquad "
       r"n_{\max} = \left\lfloor \frac{b - 2(c_c + d_s) + s_{\text{clear}}}{d_b + s_{\text{clear}}} \right\rfloor",
       "จำนวนเหล็กสูงสุดต่อชั้น", "§25.2.1")
    eq(r"d = \frac{\sum A_i\,y_i}{\sum A_i}\ (\text{เหล็กดึง}) \qquad d_t = \max y_i")
    st.subheader("2. ความเครียดและแรง (strain compatibility)")
    eq(r"\varepsilon_i = 0.003\,\frac{c - y_i}{c} \qquad f_{s,i} = E_s\,\varepsilon_i,\quad -f_y \le f_{s,i} \le f_y",
       "ความเครียดเชิงเส้นตามความลึก, เหล็กแบบ elastic–perfectly plastic", "§22.2.1, §20.2.2.1")
    eq(r"C_c = 0.85\,f'_c\,b\,a")
    eq(r"F_i = \begin{cases} A_i\,(f_{s,i} - 0.85 f'_c) & \text{เหล็กอัดที่อยู่ใน stress block } (y_i \le a) \\"
       r" A_i\,f_{s,i} & \text{กรณีอื่น} \end{cases}",
       "หักพื้นที่คอนกรีตที่เหล็กอัดแทนที่")
    eq(r"C_c + \sum F_i = 0 \;\Rightarrow\; c \quad (\text{แก้ด้วย bisection})")
    eq(r"M_n = -\left(C_c\,\tfrac{a}{2} + \sum F_i\,y_i\right)", "โมเมนต์รอบผิวรับแรงอัด")
    eq(r"\varepsilon_t = 0.003\,\frac{d_t - c}{c} \qquad \phi M_n \ge M_u")
    st.subheader("3. ข้อจำกัดความเครียด และเหล็กขั้นต่ำ")
    eq(r"\varepsilon_t \ge \varepsilon_{ty} + 0.003 \quad\Leftrightarrow\quad "
       r"c \le c_{\max} = \frac{0.003\,d_t}{0.003 + \varepsilon_{ty} + 0.003}",
       "คานต้องเป็น tension-controlled (ไม่เช่นนั้นต้องใช้ doubly)", "§9.3.3.1")
    eq(r"A_{s,\min} = \max\!\left(\frac{0.25\sqrt{f'_c}}{f_y},\ \frac{1.4}{f_y}\right) b\,d,"
       r"\qquad f_y \le 550\ \mathrm{MPa}", ref="§9.6.1.2")
    st.subheader("4. ขั้นตอนออกแบบ singly")
    eq(r"a = d - \sqrt{d^2 - \frac{2 M_u}{\phi\,0.85 f'_c\,b}} \qquad "
       r"A_{s,req} = \max\!\left(\frac{0.85 f'_c\,b\,a}{f_y},\ A_{s,\min}\right),\quad \phi = 0.90",
       "ได้จากสมดุลแรง C = T และ Mn = C(d − a/2) · ถ้าในรากเป็นลบ → หน้าตัดเล็กเกิน ใช้ doubly")
    st.markdown(r"เลือกจำนวนเหล็ก $n = \lceil A_{s,req}/A_b \rceil \ge 2$ → วิเคราะห์จริงด้วยข้อ 2 → "
                r"ถ้า $\phi M_n < M_u$ เพิ่มทีละเส้น · ถ้าไม่ผ่าน strain limit → doubly")
    st.subheader("5. ขั้นตอนออกแบบ doubly (ค่าเริ่มต้นที่ c = cmax)")
    eq(r"a = \beta_1 c_{\max} \qquad C_c = 0.85 f'_c\,b\,a \qquad M_{n1} = C_c\left(d - \tfrac{a}{2}\right)"
       r"\qquad M_{n2} = \frac{M_u}{0.90} - M_{n1}")
    eq(r"f'_s = E_s\,0.003\,\frac{c - d'}{c} \le f_y \qquad "
       r"A'_{s,req} = \frac{M_{n2}}{(f'_s - 0.85 f'_c)(d - d')} \qquad "
       r"A_{s,req} = \frac{C_c + A'_{s,req}(f'_s - 0.85 f'_c)}{f_y}",
       r"ใช้ $f'_s$ (ไม่หัก 0.85f′c) ถ้า d′ > a · จากนั้นวิเคราะห์จริงด้วยข้อ 2 และเพิ่มเหล็กจนผ่าน")

# ======================================================================== คาน เฉือน
with tabs[3]:
    st.header("คาน · แรงเฉือน (ปลอกตั้งฉาก)")
    var([
        (r"V_u", "แรงเฉือนประลัย (ที่ระยะ d จากผิวรองรับ ถ้าเลือก)", "N", "ผู้ใช้ / STAAD"),
        (r"b_w", "ความกว้างเอว = b", "mm", "-"),
        (r"d", "ความลึกประสิทธิผลจากการออกแบบแรงดัด", "mm", "แท็บแรงดัด"),
        (r"\rho_w", r"อัตราส่วนเหล็กดึง $= A_s/(b_w d)$", "-", "-"),
        (r"\lambda_s", "ตัวคูณผลของขนาด (size effect)", "-", "สูตรข้างล่าง"),
        (r"A_v", r"พื้นที่ปลอกทุกขาในระยะ s $= n_{legs}\,\pi d_s^2/4$", "mm²", "ผู้ใช้"),
        (r"s", "ระยะห่างปลอก", "mm", "ออกแบบ / ผู้ใช้"),
        (r"V_c,\ V_s", "กำลังเฉือนจากคอนกรีต, จากเหล็กปลอก", "N", "-"),
        (r"\phi V_n", r"กำลังเฉือนออกแบบ $= 0.75(V_c + V_s)$", "N", "-"),
    ])
    st.subheader("1. กำลังของคอนกรีต Vc")
    eq(r"\lambda_s = \sqrt{\frac{2}{1 + d/250}} \le 1.0", ref="§22.5.5.1.3")
    eq(r"\begin{aligned}"
       r"(a)\quad V_c &= 0.17\,\lambda\sqrt{f'_c}\,b_w d && \text{เมื่อ } A_v \ge A_{v,\min}\\"
       r"(b)\quad V_c &= 0.66\,\lambda\,\rho_w^{1/3}\sqrt{f'_c}\,b_w d && \text{เมื่อ } A_v \ge A_{v,\min}\\"
       r"(c)\quad V_c &= 0.66\,\lambda_s\lambda\,\rho_w^{1/3}\sqrt{f'_c}\,b_w d && \text{เมื่อ } A_v < A_{v,\min}"
       r" \text{ หรือไม่มีปลอก}\end{aligned}"
       r"\qquad V_c \le 0.42\,\lambda\sqrt{f'_c}\,b_w d",
       "เลือก (a) หรือ (b) ได้ที่แถบด้านซ้าย · (c) ใช้อัตโนมัติเมื่อปลอกน้อยกว่าขั้นต่ำ", "Table 22.5.5.1")
    st.subheader("2. ปลอกขั้นต่ำ — บังคับเมื่อไร")
    eq(r"V_u > 0.083\,\phi\,\lambda\sqrt{f'_c}\,b_w d \;\Rightarrow\; \text{ต้องมี } A_{v,\min}",
       "ยกเว้นคานเข้าข้อยกเว้น Table 9.6.3.1 (h ≤ 250 mm, คานหล่อกับพื้นที่ตื้น ฯลฯ)", "§9.6.3.1")
    eq(r"\frac{A_{v,\min}}{s} = \max\!\left(0.062\sqrt{f'_c}\,\frac{b_w}{f_{yt}},\ 0.35\,\frac{b_w}{f_{yt}}\right)",
       ref="Table 9.6.3.4")
    st.info("**ผู้ใช้ตัดสินใจเอง** (แถบด้านซ้ายหน้าคาน: \"ใส่ปลอกขั้นต่ำเสมอ แม้ ACI ไม่บังคับ\") — "
            "เมื่อ Vu ต่ำกว่าเส้นแบ่งข้างบนและคอนกรีตรับพอ: ติ๊ก (ค่าเริ่มต้น) = ใส่ Av,min @ s ≤ s_max และใช้ Vc สมการ (a)/(b); "
            "ไม่ติ๊ก = ไม่ใส่ปลอก ใช้ Vc สมการ (c)")
    st.subheader("3. เหล็กปลอก")
    eq(r"V_{s,req} = \frac{V_u}{\phi} - V_c \ge 0 \qquad V_s = \frac{A_v\,f_{yt}\,d}{s}", ref="§22.5.8.5.3")
    eq(r"s_{\max} = \begin{cases} \min(d/2,\ 600) & V_{s,req} \le 0.33\,\lambda\sqrt{f'_c}\,b_w d \\"
       r" \min(d/4,\ 300) & \text{กรณีอื่น} \end{cases}", ref="Table 9.7.6.2.2")
    eq(r"s = \left\lfloor \frac{1}{25}\min\!\left(\frac{A_v}{A_{v,\min}/s},\ s_{\max},\ "
       r"\frac{A_v f_{yt} d}{V_{s,req}}\right) \right\rfloor \times 25\ \mathrm{mm}",
       "ระยะที่แอปเลือก: ค่าน้อยที่สุดของ 3 เงื่อนไข ปัดลงทีละ 25 mm")
    st.subheader("4. ตรวจกำลังและขนาดหน้าตัด")
    eq(r"\phi V_n = 0.75\,(V_c + V_s) \ge V_u", ref="§9.5.1.1(b)")
    eq(r"V_u \le \phi\left(V_c + 0.66\sqrt{f'_c}\,b_w d\right)", "ถ้าไม่ผ่าน ต้องขยายหน้าตัด", "§22.5.1.2")

# ======================================================================== คาน รายละเอียด
with tabs[4]:
    st.header("คาน · รายละเอียดเหล็กและความลึก")
    st.subheader("ระยะเหล็กควบคุมรอยร้าว")
    eq(r"s \le \min\!\left(380\,\frac{280}{f_s} - 2.5\,c_c,\ 300\,\frac{280}{f_s}\right),\qquad f_s = \tfrac{2}{3} f_y",
       ref="Table 24.3.2, §24.3.2.1")
    var([(r"s", "ระยะศูนย์กลางเหล็กดึงชั้นนอกสุด", "mm", r"$(b - 2(c_c+d_s) - d_b)/(n-1)$"),
         (r"c_c", "ระยะหุ้มจากผิวคอนกรีตถึงผิวเหล็กหลัก", "mm", r"$c_c + d_s$"),
         (r"f_s", "หน่วยแรงในเหล็กขณะใช้งาน (ประมาณ)", "MPa", "2fy/3")])
    st.subheader("ความลึกขั้นต่ำ (แทนการคำนวณระยะแอ่นตัว)")
    eq(r"h_{\min} = \frac{\ell}{k} \times \left(0.4 + \frac{f_y}{700}\right)_{\text{ถ้า } f_y \ne 420}",
       "k = 16 ช่วงเดี่ยว, 18.5 ต่อเนื่องปลายเดียว, 21 ต่อเนื่องสองปลาย, 8 คานยื่น", "Table 9.3.1.1")
    var([(r"\ell", "ช่วงคาน (ศูนย์ถึงศูนย์)", "mm", "ผู้ใช้ / STAAD")])

# ======================================================================== เสา P–M
with tabs[5]:
    st.header("เสา · กำลังแรงอัดร่วมดัดสองแกน (3D interaction surface)")
    var([
        (r"b,\ h", "ด้านตามแกน x (ZD) และแกน y (YD)", "mm", "ผู้ใช้ / STAAD"),
        (r"A_g", r"พื้นที่หน้าตัด $= b h$", "mm²", "-"),
        (r"A_{st}", "พื้นที่เหล็กยืนทั้งหมด", "mm²", "จากจำนวน/ขนาดเหล็ก"),
        (r"(x_i, y_i)", "พิกัดเหล็กเส้นที่ i จากศูนย์กลางหน้าตัด", "mm", "จัดเหล็กรอบรูป"),
        (r"\theta", "มุมทิศของแกนสะเทิน (เวกเตอร์ชี้ไปด้านรับแรงอัด)", "rad", "ค้นหาอัตโนมัติ"),
        (r"P_u", "แรงอัดประลัย (บวก = อัด)", "N", "ผู้ใช้ / STAAD"),
        (r"M_{ux},\ M_{uy}", "โมเมนต์ประลัยรอบแกน x (Mz STAAD) และแกน y (My STAAD)", "N·mm", "ผู้ใช้ / STAAD"),
    ])
    st.subheader("1. แรงอัดสูงสุด")
    eq(r"P_o = 0.85 f'_c\,(A_g - A_{st}) + f_y A_{st},\quad f_y \le 550 \qquad "
       r"\phi P_{n,\max} = 0.65 \times 0.80\,P_o", "เสาปลอกเดี่ยว", "§22.4.2.2, Table 22.4.2.1")
    st.subheader("2. หนึ่งจุดบน surface (กำหนด θ และ c)")
    eq(r"\mathbf{u} = (\cos\theta,\ \sin\theta) \qquad y_i = d_{\max} - (x_i\cos\theta + y_i\sin\theta)",
       "ระยะของเหล็กแต่ละเส้นจากมุมที่รับแรงอัดมากที่สุด")
    eq(r"a = \beta_1 c \qquad C_c = 0.85 f'_c\,A_{\text{comp}}",
       "A_comp = พื้นที่หน้าตัดที่ถูกตัดด้วยเส้นขนานแกนสะเทินลึก a (polygon clipping) มีจุดศูนย์ถ่วง (x_c, y_c)")
    eq(r"\varepsilon_i = 0.003\,\frac{c - y_i}{c} \qquad f_{s,i} = E_s\varepsilon_i,\ |f_{s,i}| \le f_y "
       r"\qquad F_i = A_i(f_{s,i} - 0.85 f'_c)\ \text{ถ้าอยู่ใน block, ไม่เช่นนั้น } A_i f_{s,i}")
    eq(r"P_n = C_c + \sum F_i \qquad M_{nx} = C_c\,y_c + \sum F_i\,y_i \qquad M_{ny} = C_c\,x_c + \sum F_i\,x_i",
       "ผลรวมรอบศูนย์กลางหน้าตัด", "§22.2")
    eq(r"\varepsilon_t = \max_i(-\varepsilon_i) \;\Rightarrow\; \phi\ (\text{0.65 → 0.90 ตามแท็บหน่วย})")
    st.subheader("3. กำลังที่ระดับ Pu ตามทิศโมเมนต์ (load contour)")
    eq(r"M_{\text{res}} = \sqrt{M_{ux}^2 + M_{uy}^2} \qquad \alpha = \operatorname{atan2}(M_{ux},\ M_{uy})")
    st.markdown(r"ค้นหา $\theta$ (และ $c$ ที่ทำให้ $\phi P_n = P_u$) จนทิศของ $(\phi M_{nx}, \phi M_{ny})$ ตรงกับ $\alpha$ "
                "— มุมแกนสะเทินไม่จำเป็นต้องเท่ากับมุมโหลด")
    eq(r"\phi M_{\text{cap}} = \phi\sqrt{M_{nx}^2 + M_{ny}^2} \qquad "
       r"\text{ratio} = \frac{M_{\text{res}}}{\phi M_{\text{cap}}} \le 1.0")
    st.markdown("ตรวจ 3 จุด: **ปลายบน**, **ปลายล่าง** และ**กลางเสา (โมเมนต์ขยาย Mc)** ถ้าเสาชะลูด — ใช้ ratio สูงสุด")

# ======================================================================== เสา ชะลูด
with tabs[6]:
    st.header("เสา · ความชะลูดและการขยายโมเมนต์ (non-sway)")
    var([
        (r"k", "ตัวคูณความยาวประสิทธิผล (non-sway ≤ 1.0)", "-", "ผู้ใช้"),
        (r"\ell_u", "ความยาวเสาไม่ค้ำยัน (ช่องว่างระหว่างคาน)", "mm", "ผู้ใช้ / STAAD"),
        (r"r", "รัศมีไจเรชัน", "mm", "สูตรข้างล่าง"),
        (r"M_1,\ M_2", "โมเมนต์ปลายค่าน้อย / ค่ามาก (ลำดับหนึ่ง)", "N·mm", "ปลายบน/ล่าง"),
        (r"\beta_{dns}", "อัตราส่วนแรงอัดคงค้างต่อแรงอัดทั้งหมด", "-", "ผู้ใช้ (0.6)"),
        (r"I_g", "โมเมนต์ความเฉื่อยหน้าตัดรวม รอบแกนที่ดัด", "mm⁴", r"$b h^3/12$"),
        (r"I_{se}", "โมเมนต์ความเฉื่อยของเหล็กยืนรอบแกนศูนย์กลาง", "mm⁴", r"$\sum A_i y_i^2$"),
        (r"P_c", "แรงวิกฤต (Euler)", "N", "-"),
        (r"C_m", "ตัวคูณแปลงโมเมนต์ปลายเป็นโมเมนต์สม่ำเสมอ", "-", "-"),
        (r"\delta", "ตัวขยายโมเมนต์", "-", "-"),
    ])
    eq(r"r = \sqrt{I_g/A_g}\ \ (\text{หรือ } 0.3h)", ref="§6.2.5.2")
    st.subheader("1. ตรวจว่าชะลูดหรือไม่")
    eq(r"\frac{k\,\ell_u}{r} \le \min\!\left(34 + 12\,\frac{M_1}{M_2},\ 40\right) \;\Rightarrow\; \text{ไม่ชะลูด}",
       ref="§6.2.5.1(b)")
    eq(r"\frac{M_1}{M_2} = \begin{cases} -\dfrac{|M_1|}{|M_2|} & \text{โค้งทางเดียว (single)} \\[10pt]"
       r" +\dfrac{|M_1|}{|M_2|} & \text{โค้งสองทาง (double)} \end{cases}"
       r"\qquad M_1 = M_2 = 0 \Rightarrow -1",
       "M2 = ปลายที่ค่าสัมบูรณ์มากกว่า · ทิศการดัดจากเครื่องหมายโมเมนต์ปลายใน STAAD หรือจากสมดุลแรงเฉือน |V|·L")
    st.subheader("2. โมเมนต์ขยาย (เมื่อชะลูด)")
    eq(r"(EI)_{\text{eff}} = \frac{0.4\,E_c I_g}{1 + \beta_{dns}}\ \ \text{หรือ}\ \ "
       r"\frac{0.2\,E_c I_g + E_s I_{se}}{1 + \beta_{dns}}", ref="§6.6.4.4.4")
    eq(r"P_c = \frac{\pi^2 (EI)_{\text{eff}}}{(k\,\ell_u)^2}", ref="§6.6.4.4.2")
    eq(r"C_m = 0.6 - 0.4\,\frac{M_1}{M_2}\quad (= 1.0 \text{ ถ้ามีแรงกระทำตามขวางระหว่างปลาย})", ref="§6.6.4.5.3")
    eq(r"M_{2,\min} = P_u\,(15 + 0.03h)\ \ [\mathrm{mm}] \quad\text{ถ้า } M_2 < M_{2,\min}\text{ ใช้ } M_{2,\min},\ C_m = 1.0",
       ref="§6.6.4.5.4")
    eq(r"\delta = \frac{C_m}{1 - \dfrac{P_u}{0.75\,P_c}} \ge 1.0 \qquad M_c = \delta\,M_2",
       r"ถ้า Pu ≥ 0.75Pc → เสาไม่เสถียร", "§6.6.4.5.2")
    eq(r"M_c \le 1.4\,M_2", "โมเมนต์ลำดับสองไม่เกิน 1.4 เท่าลำดับหนึ่ง", "§6.2.6")

# ======================================================================== เสา เฉือน + รายละเอียด
with tabs[7]:
    st.header("เสา · แรงเฉือนและรายละเอียดเหล็ก")
    var([
        (r"N_u", "แรงอัดที่เกิดพร้อม Vu (= Pu ของ combo เดียวกัน)", "N", "-"),
        (r"b_w", "ความกว้างตั้งฉากแรงเฉือน (Vuy → b, Vux → h)", "mm", "-"),
        (r"d", "ระยะจากผิวรับแรงอัดถึงเหล็กแถวที่ไกลที่สุด", "mm", r"$h/2 + \max(-y_i)$"),
        (r"\rho_w", "อัตราส่วนเหล็กด้านดึง (เหล็กแถวกลางนับครึ่ง) ต่อ bw·d", "-", "-"),
        (r"\ell_u,\ c_1", "ความยาวไม่ค้ำยัน, ด้านเสาในทิศแรงเฉือน", "mm", "-"),
    ])
    st.subheader("1. Vc ที่คิดแรงอัด")
    eq(r"\frac{N_u}{6A_g} \le 0.05 f'_c")
    eq(r"\begin{aligned}(a)\quad V_c &= \left(0.17\,\lambda\sqrt{f'_c} + \frac{N_u}{6A_g}\right) b_w d"
       r" && A_v \ge A_{v,\min}\\"
       r"(c)\quad V_c &= \left(0.66\,\lambda_s\lambda\,\rho_w^{1/3}\sqrt{f'_c} + \frac{N_u}{6A_g}\right) b_w d"
       r" && A_v < A_{v,\min}\end{aligned}\qquad 0 \le V_c \le 0.42\,\lambda\sqrt{f'_c}\,b_w d",
       ref="Table 22.5.5.1")
    eq(r"V_u > 0.5\,\phi V_c \;\Rightarrow\; \text{ต้องมีปลอก} \ge A_{v,\min},\ "
       r"s \le s_{\max}\ (\text{เหมือนคาน})", ref="§10.6.2.1, §10.7.6.5.2")
    eq(r"V_s = \frac{A_v f_{yt} d}{s} \qquad \phi V_n = 0.75(V_c + V_s) \ge V_u \qquad "
       r"V_u \le \phi\left(V_c + 0.66\sqrt{f'_c}\,b_w d\right)")
    st.subheader("2. แรงเฉือนสองทิศ")
    eq(r"\frac{V_{ux}}{\phi V_{nx}} > 0.5 \text{ และ } \frac{V_{uy}}{\phi V_{ny}} > 0.5 \;\Rightarrow\; "
       r"\frac{V_{ux}}{\phi V_{nx}} + \frac{V_{uy}}{\phi V_{ny}} \le 1.5", ref="§22.5.1.11")
    st.subheader("3. OMF ใน SDC B (ถ้าเลือก)")
    eq(r"\ell_u \le 5c_1 \;\Rightarrow\; V_u = \max\!\left(V_{u,\text{analysis}},\ \frac{M_{nt} + M_{nb}}{\ell_u}\right)",
       "Mnt, Mnb = กำลังดัด**ระบุ (ไม่คูณ φ)** ที่ปลายบน/ล่างภายใต้ Pu", "§18.3.3")
    st.subheader("4. เหล็กยืน")
    eq(r"0.01 \le \rho_g = \frac{A_{st}}{A_g} \le 0.08 \qquad n \ge 4", ref="§10.6.1.1, §10.7.3.1")
    eq(r"\text{ช่องว่างเหล็กยืน} \ge \max\!\left(40,\ 1.5\,d_b,\ \tfrac{4}{3}d_{agg}\right)", ref="§25.2.3")
    st.subheader("5. เหล็กปลอกเสา (ต้องมีเสมอ ไม่ขึ้นกับแรงเฉือน)")
    eq(r"s \le \min\!\left(16\,d_b,\ 48\,d_{bt},\ \text{ด้านแคบของเสา}\right)", ref="§25.7.2.1")
    eq(r"d_{bt} \ge \begin{cases} 9.5\ \mathrm{mm\ (No.10)} & d_b \le 32 \\ 12.7\ \mathrm{mm\ (No.13)} & d_b > 32"
       r" \text{ หรือมัดรวม} \end{cases}", ref="§25.7.2.2")
    eq(r"\text{เหล็กที่ไม่ได้อยู่มุมปลอก ต้องห่างจากเหล็กที่ถูกยึด} \le 150\ \mathrm{mm}"
       r"\ (\text{ไม่เช่นนั้นต้องมี crosstie})", ref="§25.7.2.3")
    eq(r"c_c \ge 40\ \mathrm{mm}\ (\text{ถึงผิวปลอก, ไม่สัมผัสดิน/อากาศ})", ref="Table 20.5.1.3.1")
