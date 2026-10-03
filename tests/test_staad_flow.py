"""ทดสอบ workflow ใหม่: ขั้นที่ 1 .std → ขั้นที่ 2 .anl → ขั้นที่ 3 ออกแบบเสาจากโมเดล"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rcbeam.colcheck import C  # noqa: F401  (เพิ่ม skill scripts เข้า sys.path)
import staad_io as S  # noqa: E402

EX = Path(__file__).resolve().parent.parent / "skills" / "rc-column-aci318m19" / "references" / "staad_example"
STD = (EX / "frame_3x2.std").read_text()
ANL = (EX / "frame_3x2_cols11_12.anl").read_text()


def test_model_page_reads_example_and_checks_equilibrium():
    at = AppTest.from_file("../views/staad_model.py", default_timeout=60)
    at.session_state["std_text"], at.session_state["std_name"] = STD, "x"
    at.session_state["anl_text"], at.session_state["anl_name"] = ANL, "y"
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
    at.session_state["staad_forces"] = S.parse_anl(ANL)
    at.run()
    assert not at.exception
    assert at.selectbox(key="c_member").value == 11
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


REAL = (EX / "frame_3x2_real_noforces.anl").read_text()


def test_real_anl_without_member_forces_explains_fix():
    """.anl จริง (PRINT ALL อย่างเดียว): ใช้แทน .std ได้, น้ำหนักรวมตรง STAAD, และบอกให้เพิ่ม PRINT MEMBER FORCES"""
    at = AppTest.from_file("../views/staad_model.py", default_timeout=60)
    at.session_state["std_text"], at.session_state["std_name"] = S.extract_input_echo(REAL), "x"
    at.session_state["anl_text"], at.session_state["anl_name"] = REAL, "x"
    at.run()
    assert not at.exception
    assert any("น้ำหนักรวมทุก load ตรงกับ STAAD" in s.value for s in at.success)
    assert any("ไม่มีตาราง MEMBER END FORCES" in e.value for e in at.error)
    assert any("PRINT MEMBER FORCES" in c.value for c in at.code)
    assert "staad_forces" not in at.session_state
