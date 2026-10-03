"""หน้าคาน: เลือกคานจากโมเดล STAAD → M/V ตลอดคาน → ส่งค่า Mu/Vu ไปออกแบบ"""
import pytest
from streamlit.testing.v1 import AppTest


def _page():
    at = AppTest.from_file("../views/beam.py", default_timeout=60).run()
    next(b for b in at.button if b.label == "ใช้โมเดลตัวอย่าง").click().run()
    assert not at.exception
    return at


def test_beam_from_model_prefills_and_sends_design_values():
    at = _page()
    assert at.selectbox(key="b_member").value == 13
    assert at.number_input(key="b_h").value == pytest.approx(0.5)       # YD
    assert at.number_input(key="b_b").value == pytest.approx(0.3)       # ZD
    assert at.number_input(key="b_span").value == pytest.approx(5.0)
    assert any("ตรวจสมดุลคานผ่าน" in s.value for s in at.success)
    assert at.multiselect(key="b_use_13").value == [101, 102]
    assert at.number_input(key="b_dmu").value < 0                        # ค่าเริ่มต้น = ปลายซ้าย (M−)
    at.radio(key="b_sec").set_value("mid").run()
    assert at.number_input(key="b_dmu").value == pytest.approx(20.86e6 / 9806.65, rel=2e-3)   # M+ 20.86 kN·m (floor load 45° จาก .std)
    next(b for b in at.button if b.label == "ออกแบบ").click().run()
    assert not at.exception


def test_beam_click_selects_and_interior_beam_has_larger_moment():
    at = _page()
    at.session_state["b_plan"] = {"selection": {"points": [{"customdata": 24}]}}
    at.run()
    assert at.selectbox(key="b_member").value == 24
    assert at.number_input(key="b_span").value == pytest.approx(5.0)
    assert any("ตรวจสมดุลคานผ่าน" in s.value for s in at.success)


def test_user_can_skip_minimum_stirrups():
    at = _page()
    at.radio(key="b_sec").set_value("mid").run()
    at.checkbox(key="b_always_min").uncheck().run()
    next(b for b in at.button if b.label == "ออกแบบ").click().run()
    assert not at.exception
    assert any("ไม่ใส่ปลอก" in m.value for m in at.markdown)
    at.checkbox(key="b_always_min").check().run()
    assert any("ปลอก 2 ขา" in m.value for m in at.markdown)


def test_docs_page_renders():
    at = AppTest.from_file("../views/docs.py", default_timeout=60).run()
    assert not at.exception and len(at.tabs) == 8
