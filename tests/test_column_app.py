"""ทดสอบ rcbeam.colcheck (ใช้ solver ของ skill) และ Calsheet เสา"""
import pytest

from rcbeam.calsheet import ProjectInfo
from rcbeam.col_calsheet import build_column_calsheet
from rcbeam.colcheck import ColumnInput, Combo, run

STORY = {"sumPu": 24000e3, "do_x": 3.2, "Vus_x": 900e3, "do_y": 3.2, "Vus_y": 900e3, "lc": 5000}


def s1_input(**kw):
    args = dict(lu_x=4500, lu_y=4500, L=5000, story=STORY)
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
    story = dict(STORY, do_x=40.0)
    out = run(s1_input(story=story), [S1])
    assert out["sway"] and out["results"] == []


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
