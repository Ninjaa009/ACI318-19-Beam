"""เคสทดสอบจาก skill rc-beam-aci318m19 (§10) + สูตรปิดที่เขียนแยกจาก solver"""
import math

import pytest

from rcbeam import units as u
from rcbeam.flexure import (
    analyze, design_flexure, tension_layers, compression_layer, bar_area, eps_ty,
    c_max,
)
from rcbeam.shear import check_stirrups, design_stirrups

FC, FY = 28.0, 420.0
approx = pytest.approx


def test_T1_singly_design():
    D = design_flexure(300, 600, FC, FY, 250e6, 40, 10, 25, 20)
    r = D.result
    assert D.kind == "singly" and D.counts == [3]
    # สูตรปิด: a = d − √(d² − 2Mu/(φ0.85f′cb)), As = 0.85f′cba/fy
    d = 600 - 40 - 10 - 12.5
    a = d - math.sqrt(d ** 2 - 2 * 250e6 / (0.9 * 0.85 * FC * 300))
    assert D.As_req == approx(0.85 * FC * 300 * a / FY, rel=1e-9)
    assert D.As_req / 100 == approx(13.27, abs=0.01)
    assert r.phiMn / 1e6 == approx(275.1, abs=0.1)
    assert r.et == approx(0.0128, abs=1e-4)
    assert r.As_min / 100 == approx(5.375, abs=1e-3)
    assert r.cmax == approx(199.1, abs=0.1)
    assert c_max(d, eps_ty(420, True)) == approx(201.6, abs=0.1)


def test_T2_doubly_design():
    D = design_flexure(300, 450, FC, FY, 330e6, 40, 10, 25, 20)
    r = D.result
    assert D.kind == "doubly" and D.counts == [4, 2] and D.n_c == 4
    assert D.Asc_req / 100 == approx(9.57, abs=0.01)
    assert D.As_req / 100 == approx(28.15, abs=0.01)
    assert r.As / 100 == approx(29.45, abs=0.01)
    assert r.As_comp / 100 == approx(12.57, abs=0.01)
    assert r.phiMn / 1e6 == approx(346.9, abs=0.1)
    assert r.et == approx(0.0054, abs=1e-4) and r.strain_ok


def test_T3_check_two_layers():
    L = tension_layers(600, 40, 10, 25, [4, 2]) + [compression_layer(40, 10, 2, 16)]
    r = analyze(300, 600, FC, FY, L)
    assert r.c == approx(178.6, abs=0.1)
    assert r.et == approx(0.00603, abs=1e-5)
    assert r.Mn / 1e6 == approx(553.1, abs=0.1)
    assert r.phiMn / 1e6 == approx(497.8, abs=0.1)
    assert r.d != r.dt


def test_E1_compression_steel_not_yielding():
    L = tension_layers(450, 40, 10, 25, [4, 1]) + [compression_layer(40, 10, 2, 20)]
    r = analyze(350, 450, FC, FY, L)
    comp = [s for s in r.steel if s.layer.role == "compression"][0]
    assert 0 < comp.eps < r.ety
    assert r.c == approx(120.9, abs=0.1)
    assert r.phiMn / 1e6 == approx(301.2, abs=0.1)


def test_E2_multilayer_strain_fails():
    r = analyze(300, 600, FC, FY, tension_layers(600, 40, 10, 25, [4, 4]))
    assert r.et == approx(0.00293, abs=1e-5)
    assert not r.strain_ok
    assert r.phiMn / 1e6 == approx(471.1, abs=0.1)


def test_E3_strain_fails_single_layer():
    r = analyze(300, 450, FC, FY, tension_layers(450, 40, 10, 28, [4]))
    assert r.et == approx(0.00379, abs=1e-5)
    assert r.phi == approx(0.791, abs=1e-3)
    assert r.phiMn / 1e6 == approx(256.6, abs=0.1)
    assert not r.strain_ok


def test_E4_compression_steel_outside_block():
    L = tension_layers(450, 60, 10, 25, [4, 2]) + [compression_layer(60, 10, 2, 20)]
    r = analyze(350, 450, 49.0, FY, L)
    assert r.beta1 == approx(0.70)
    comp = [s for s in r.steel if s.layer.role == "compression"][0]
    assert r.a == approx(77.6, abs=0.1) and r.c == approx(110.9, abs=0.1)
    assert r.a < comp.layer.y < r.c and not comp.in_block
    assert r.phiMn / 1e6 == approx(343.5, abs=0.1)


def test_E5_shear():
    As = 6 * bar_area(25)
    d = 537.5
    for s, eq, vc in [(200, "a", 145.1), (628.3, "a", 145.1), (700, "c", 118.2)]:
        r = check_stirrups(150e3, FC, FY, 300, d, As, 10, 2, s)
        assert r.vc_eq == eq and r.Vc / 1e3 == approx(vc, abs=0.1)
    assert r.vcs["lambda_s"] == approx(0.797, abs=1e-3)
    assert r.Av_min_s == approx(0.25)
    # สูตรปิด Vc (a)
    assert r.vcs["a"] == approx(0.17 * math.sqrt(FC) * 300 * d, rel=1e-9)
    r = design_stirrups(150e3, FC, FY, 300, d, As, 10, 2)
    assert r.s == 250 and r.s_max == approx(268.75)
    assert r.Av / r.s == approx(0.628, abs=1e-3)
    assert r.phiVn / 1e3 == approx(215.2, abs=0.1)
    assert r.ok


def test_kgfm_matches_si():
    """รันด้วยอินพุต kgf–m แล้วได้ผลเดียวกับ SI หลังแปลงหน่วย (T1)"""
    fc = u.ksc_to_mpa(FC / u.KSC_TO_MPA)
    fy = u.ksc_to_mpa(FY / u.KSC_TO_MPA)
    Mu = u.kgfm_to_nmm(250e6 / u.KGFM_TO_NMM)
    D = design_flexure(u.m_to_mm(0.30), u.m_to_mm(0.60), fc, fy, Mu, 40, 10, 25, 20)
    assert u.nmm_to_kgfm(D.result.phiMn) == approx(28_051, abs=1)
    assert FC / u.KSC_TO_MPA == approx(285.5, abs=0.1)


def test_grade420_exception_only_for_420():
    with pytest.raises(ValueError):
        eps_ty(400.0, True)


def test_calsheet_a4_html():
    from rcbeam.report import Inputs, detailing_checks, summary_rows
    from rcbeam.calsheet import ProjectInfo, DesignInfo, build_calsheet
    D = design_flexure(300, 450, FC, FY, -330e6, 40, 10, 25, 20)
    fr = D.result
    sr = design_stirrups(150e3, FC, FY, 300, fr.d, fr.As, 10, 2)
    inp = Inputs(b=300, h=450, fc=FC, fy=FY, fyt=FY, cover=40, ds=10, legs=2,
                 dagg=20, Mu=-330e6, Vu=150e3)
    rows = summary_rows(inp, fr, sr, detailing_checks(inp, fr, D.counts, 25))
    html = build_calsheet("T2", ProjectInfo(project="<b>x</b>", member="B1"), inp, fr,
                          sr, rows, "steel", "stirrup",
                          DesignInfo(D.kind, D.As_req, D.Asc_req, D.notes))
    assert "size: A4 portrait" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
    assert "<svg" in html and "346.95 kN·m" in html
