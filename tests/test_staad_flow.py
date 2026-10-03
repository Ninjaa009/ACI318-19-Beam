"""ทดสอบ workflow: ขั้นที่ 1 .std → ขั้นที่ 2 ตาราง Beam End Force → ขั้นที่ 3 ออกแบบเสาจากโมเดล"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rcbeam.colcheck import C  # noqa: F401  (เพิ่ม skill scripts เข้า sys.path)
import staad_io as S  # noqa: E402

EX = Path(__file__).resolve().parent.parent / "skills" / "rc-column-aci318m19" / "references" / "staad_example"
STD = (EX / "frame_3x2.std").read_text()
TABLE = (EX / "frame_3x2_beam_end_force.txt").read_text()


def _table_forces():
    return S.forces_from_table(TABLE, C.parse_staad_end_forces, C.STAAD_FORCE_UNITS, C.STAAD_MOMENT_UNITS)


def test_model_page_reads_example_and_checks_equilibrium():
    at = AppTest.from_file("../views/staad_model.py", default_timeout=60)
    at.session_state["std_text"], at.session_state["std_name"] = STD, "x"
    at.session_state["sm_table"] = TABLE
    at.run()
    assert not at.exception and not at.error
    assert any("ตรวจสมดุลเสาทุกต้นทุก load ผ่าน" in s.value for s in at.success)
    assert any("FCU" in w.value for w in at.warning)                 # เตือนกำลังลูกบาศก์
    assert at.session_state["staad_model"].prism[12] == (500.0, 400.0)


def test_model_page_without_files_asks_for_std():
    at = AppTest.from_file("../views/staad_model.py", default_timeout=60).run()
    assert not at.exception and any(".std" in i.value for i in at.info)


def test_column_page_from_model_prefills_and_designs():
    at = AppTest.from_file("../views/column.py", default_timeout=60)
    at.session_state["staad_model"] = S.parse_std(STD)
    at.session_state["staad_forces"] = _table_forces()
    at.run()
    assert not at.exception
    assert at.selectbox(key="c_member").value == 1
    at.selectbox(key="c_member").set_value(11).run()
    assert at.number_input(key="c_h").value == pytest.approx(0.5)      # YD จาก PRIS
    assert at.number_input(key="c_b").value == pytest.approx(0.4)
    assert at.number_input(key="c_L").value == pytest.approx(3.5)
    assert at.multiselect(key="c_muse_11").value == [101, 102]        # ตัด service 103 และ primary
    at.selectbox(key="c_member").set_value(12).run()
    assert at.multiselect(key="c_muse_12").value == [101, 102]
    df = at.dataframe[-1].value
    assert df.iloc[1, 1] == pytest.approx(7764.665 * 9.80665e-3, rel=1e-5)   # P combo 102 (kN)
    next(b for b in at.button if b.label == "ตรวจสอบเสา").click().run()
    assert not at.exception
    # ด้าน YD 500 mm: เหล็กกลางห่างเหล็กมุม 170 mm > 150 mm ต้องมีปลอกยึด (§25.7.2.3) — ผลจริงของหน้าตัดนี้
    assert [e.value for e in at.error] == ["มีรายการไม่ผ่าน — ดูตารางสรุป"]




def test_pasted_beam_end_force_table_all_columns():
    """ตาราง Beam End Force จริงจากหน้าจอ STAAD (Beam/L/C เว้นว่างในแถวต่อมา, แรง kg + โมเมนต์ kN-m)"""
    from rcbeam.colcheck import C as CC
    M = S.parse_std(STD)
    F = S.forces_from_table(TABLE, CC.parse_staad_end_forces, CC.STAAD_FORCE_UNITS, CC.STAAD_MOMENT_UNITS)
    assert F.members() == list(range(1, 15)) + [17, 24] and F.loads() == [1, 2, 3, 101, 102, 103]
    assert all(S.check_equilibrium(M, F, m, lc)[0] for m in M.columns() for lc in F.loads())
    for lid, exp in ((1, 507.60), (2, 432.00), (3, 294.20), (101, 1315.44), (102, 1598.24)):
        got, n, nsup = S.base_reactions(M, F, lid)
        assert (n, nsup) == (12, 12) and got / 1e3 == pytest.approx(exp, abs=0.02)
    f = S.column_forces(M, F, 6, 102, CC.from_staad)
    assert f["Pu"] / 1e3 == pytest.approx(25063.016 * 9.80665e-3, rel=1e-6)   # เสากลางรับแรงมากสุด


def test_model_page_example_uses_real_table():
    at = AppTest.from_file("../views/staad_model.py", default_timeout=60).run()
    next(b for b in at.button if b.label == "ใช้โมเดลตัวอย่าง").click().run()
    assert not at.exception and not at.error
    msgs = [s.value for s in at.success]
    assert any("ตรวจสมดุลเสาทุกต้นทุก load ผ่าน" in m for m in msgs)
    assert any("แรงอัดที่ฐานเสาทุกต้นรวมกันเท่ากับน้ำหนักรวม" in m for m in msgs)
    assert at.session_state["staad_forces"].members() == list(range(1, 15)) + [17, 24]


def test_column_page_example_button_and_plan_click():
    at = AppTest.from_file("../views/column.py", default_timeout=60).run()
    next(b for b in at.button if b.label == "ใช้โมเดลตัวอย่าง").click().run()
    assert not at.exception
    assert at.selectbox(key="c_member").value == 1
    assert len(at.get("plotly_chart")) >= 2                          # ผัง + 3D
    at.session_state["c_plan"] = {"selection": {"points": [{"customdata": 6}]}}   # จำลองการคลิกเสา 6
    at.run()
    assert at.selectbox(key="c_member").value == 6
    at.selectbox(key="c_member").set_value(12).run()                 # เลือกจาก selectbox ยังทำงาน
    assert at.selectbox(key="c_member").value == 12
    assert at.number_input(key="c_h").value == pytest.approx(0.5)
