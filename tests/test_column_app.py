"""ทดสอบ rcbeam.colcheck (ใช้ solver ของ skill) และ Calsheet เสา"""
import pytest

from rcbeam.calsheet import ProjectInfo
from rcbeam.col_calsheet import build_column_calsheet
from rcbeam.colcheck import ColumnInput, Combo, run

def s1_input(**kw):
    args = dict(lu_x=4500, lu_y=4500, L=5000)
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


def test_nonsway_assumed_and_reported():
    """ระบบตรวจ sway ถูกถอดออก (incoming): ออกแบบได้ทันที และแจ้งสมมติฐาน non-sway ในสรุป/Calsheet"""
    out = run(s1_input(), [S1])
    assert out["results"] and "classes" not in out
    row = out["summary"][0]
    assert row[0] == "โครง sway / non-sway" and "incoming" in row[1] and row[2] == "ยังไม่ตรวจ"
    html = build_column_calsheet(ProjectInfo(member="C1"), out)
    assert "สมมติว่าเป็น<b>โครง non-sway</b>" in html


def test_rcdc_column_with_rb9_ties_fails_tie_size():
    inp = ColumnInput(300, 300, 25, 420, 420, 50, 19.1, 2, 2, 9.0, 100, cover_to="long",
                      lu_x=1100, lu_y=1100, L=1500)
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


def test_column_page_has_no_sway_step():
    at = _column_page()
    assert not [c for c in at.checkbox if c.key in ("c_beta90", "c_bypass")]
    assert any("Incoming" in i.value for i in at.info)
