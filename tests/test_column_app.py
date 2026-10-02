"""ทดสอบ rcbeam.colcheck (ใช้ solver ของ skill) และ Calsheet เสา"""
import pytest

from rcbeam.calsheet import ProjectInfo
from rcbeam.col_calsheet import build_column_calsheet
from rcbeam.colcheck import ColumnInput, Combo, run

STORY = [dict(story="1", direction=d, combo="W", sumPu=24000e3, Vus=900e3, delta_o=3.2,
              lc=5000, reduced=True) for d in ("x", "y")]


def s1_input(**kw):
    args = dict(lu_x=4500, lu_y=4500, L=5000, stories=STORY, story_name="1")
    args.update(kw)
    return ColumnInput(400, 400, 28, 420, 420, 40, 20, 3, 3, 10, 250, **args)


S1 = Combo("S1", 1600e3, 90e6, 60e6, 30e6, 20e6, Vux=10e3, Vuy=6e3)


def test_s1_matches_worked_example():
    out = run(s1_input(), [S1])
    r = out["gov"]
    assert r.sx.slender and not r.sy.slender
    assert r.sx.delta == pytest.approx(1.2935, abs=1e-4)
    assert r.crit[0].startswith("กลางเสา") and r.ratio == pytest.approx(0.750, abs=0.002)
    assert all(row[2] != "ไม่ผ่าน" for row in out["summary"])


def test_sway_stops_checks():
    stories = [dict(STORY[0], delta_o=40.0), STORY[1]]
    out = run(s1_input(stories=stories), [S1])
    assert out["sway"] and out["results"] == []


def test_design_blocked_without_sway_check():
    out = run(s1_input(stories=[]), [S1])
    assert not out["gate_ok"] and out["results"] == [] and len(out["gate_msgs"]) == 2
    out = run(s1_input(stories=STORY[:1]), [S1])          # มีแต่ทิศ x
    assert not out["gate_ok"] and "ทิศ y" in out["gate_msgs"][0]


def test_bypass_with_reason_allows_design_and_is_reported():
    out = run(s1_input(stories=[], sway_bypass="มีผนังรับแรงเฉือนครบสองทิศ"), [S1])
    assert out["gate_ok"] and out["bypass"] and out["results"]
    row = [r for r in out["summary"] if r[0] == "ด่านตรวจ sway ก่อนออกแบบ"][0]
    assert row[2] == "ผู้ใช้ยืนยัน" and "ผนัง" in row[1]
    html = build_column_calsheet(ProjectInfo(member="C1"), out)
    assert "ผนังรับแรงเฉือนครบสองทิศ" in html


def test_bypass_refused_when_data_shows_sway():
    stories = [dict(STORY[0], delta_o=40.0), STORY[1]]
    out = run(s1_input(stories=stories, sway_bypass="ยืนยัน"), [S1])
    assert not out["gate_ok"] and out["results"] == []


def test_other_story_does_not_affect_column():
    stories = STORY + [dict(STORY[0], story="2", delta_o=40.0)]
    out = run(s1_input(stories=stories), [S1])
    assert not out["sway"] and len(out["classes"]) == 3


def test_rcdc_column_with_rb9_ties_fails_tie_size():
    inp = ColumnInput(300, 300, 25, 420, 420, 50, 19.1, 2, 2, 9.0, 100, cover_to="long",
                      lu_x=1100, lu_y=1100, L=1500, stories=STORY, story_name="1")
    out = run(inp, [Combo("12", 57.08e3, -11.9e6, 0, 0, 0, Vuy=7.93e3)])
    tie = {r[0]: r[2] for r in out["summary"]}
    assert tie["ขนาดปลอก"] == "ไม่ผ่าน"
    assert out["gov"].ratio == pytest.approx(0.219, abs=0.003)


def test_column_calsheet_renders():
    out = run(s1_input(), [S1, Combo("LC2", 900e3, 40e6, -35e6, 10e6, 5e6, Vux=3e3, Vuy=15e3)])
    html = build_column_calsheet(ProjectInfo(member="C-S1"), out)
    assert "size: A4 portrait" in html and "RC COLUMN" in html
    assert "1.2935" in html and "<svg" in html           # δ และรูปหน้าตัด/เส้นความจุ


def test_staad_import_matches_manual_input():
    from rcbeam.colcheck import C
    f = C.from_staad(1600e3, -6e3, 10e3, -20e6, 60e6, -30e6, -90e6)
    cb = Combo("S1", f["Pu"], f["Mxt"], f["Mxb"], f["Myt"], f["Myb"], Vux=f["Vux"], Vuy=f["Vuy"])
    assert run(s1_input(), [cb])["gov"].ratio == pytest.approx(0.750, abs=0.002)


def test_mismatched_shear_reported_as_combo_error():
    cb = Combo("bad", 1600e3, 90e6, 60e6, 30e6, 20e6, Vux=6e3, Vuy=10e3)   # V สลับแกน
    out = run(s1_input(), [cb])
    assert out["results"][0].error and "จับคู่แกน" in out["results"][0].error


def _column_page():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("../views/column.py", default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_column_page_uses_staad_names_and_designs():
    at = _column_page()
    labels = [n.label for n in at.number_input]
    assert any(lb.startswith("YD") for lb in labels) and any(lb.startswith("ZD") for lb in labels)
    assert not any(lb.startswith("b (m)") for lb in labels)
    btn = next(b for b in at.button if b.label == "ตรวจสอบเสา")
    btn.click().run()
    assert not at.exception
    charts = [p.proto.spec for p in at.get("plotly_chart")]
    assert charts and any("Mnz" in c for c in charts)


def test_beta90_swaps_story_direction_only():
    at = _column_page()
    before = [m.label for m in at.metric if m.label.startswith("ทิศ")]
    at.checkbox(key="c_beta90").check().run()
    after = [m.label for m in at.metric if m.label.startswith("ทิศ")]
    assert before == ["ทิศ X → ใช้กับ Mz", "ทิศ Z → ใช้กับ My"]
    assert after == ["ทิศ Z → ใช้กับ Mz", "ทิศ X → ใช้กับ My"]


USER_STAAD = """Beam\tL/C\tNode\tAxial Force\tShear-Y\tShear-Z\tTorsion\tMoment-Y\tMoment-Z
\t\t\tkg\tkg\tkg\tkN-m\tkN-m\tkN-m
12\t102\t24\t-5708.917\t-890.992\t753.547\t0.009\t17.505\t20.958
12\t101\t24\t-4601.253\t-686.815\t580.044\t0.005\t13.475\t16.155
12\t102\t12\t7764.665\t890.992\t-753.547\t-0.009\t8.359\t9.624
12\t101\t12\t6999.626\t686.815\t-580.044\t-0.005\t6.434\t7.419"""


def test_paste_staad_table_with_mixed_units():
    at = _column_page()
    at.text_area(key="c_staad_txt").set_value(USER_STAAD).run()
    at.number_input(key="c_L").set_value(3.5).run()
    assert at.selectbox(key="c_sfu_kg").value == "kg" and at.selectbox(key="c_smu_kN-m").value == "kN-m"
    assert at.selectbox(key="c_snode_24_12").value == "12"
    df = at.dataframe[-1].value
    assert df.iloc[0, 1] == pytest.approx(7764.665 * 9.80665e-3, rel=1e-6)   # 76.15 kN ไม่ใช่ 7764
    assert df.iloc[0, 2] == pytest.approx(20.958)
    next(b for b in at.button if b.label == "ตรวจสอบเสา").click().run()
    assert not at.exception and not at.error
