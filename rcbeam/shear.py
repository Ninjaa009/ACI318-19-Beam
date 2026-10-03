"""แรงเฉือนคานสี่เหลี่ยม ปลอกตั้งฉาก ตาม ACI 318M-19 (หน่วย MPa–mm–N)"""
from dataclasses import dataclass, field
import math

from .flexure import bar_area

PHI_V = 0.75    # Table 21.2.1


def sqrt_fc(fc):
    """§22.5.3.1: √f′c ≤ 8.3 MPa"""
    return min(math.sqrt(fc), 8.3)


def av_min_per_s(fc, bw, fyt):
    """Table 9.6.3.4"""
    return max(0.062 * math.sqrt(fc) * bw / fyt, 0.35 * bw / fyt)


def lambda_s(d):
    """§22.5.5.1.3"""
    return min(1.0, math.sqrt(2.0 / (1.0 + d / 250.0)))


def vc_eqs(fc, bw, d, As, lam=1.0):
    """Table 22.5.5.1 สมการ (a), (b), (c) และเพดาน 0.42λ√f′c·bw·d"""
    rf = sqrt_fc(fc)
    rho = As / (bw * d)
    cap = 0.42 * lam * rf * bw * d
    return {
        "a": min(0.17 * lam * rf * bw * d, cap),
        "b": min(0.66 * lam * rho ** (1 / 3) * rf * bw * d, cap),
        "c": min(0.66 * lambda_s(d) * lam * rho ** (1 / 3) * rf * bw * d, cap),
        "rho_w": rho,
        "lambda_s": lambda_s(d),
        "cap": cap,
    }


@dataclass
class ShearResult:
    Vu: float
    bw: float
    d: float
    Av: float
    s: float                 # 0 = ไม่มีปลอก
    Av_min_s: float
    Vc: float
    vc_eq: str
    vcs: dict
    Vs: float
    Vs_req: float
    phiVn: float
    s_max: float
    min_required: bool
    section_ok: bool
    section_limit: float
    notes: list = field(default_factory=list)

    @property
    def strength_ok(self):
        return self.phiVn >= self.Vu - 1e-9

    @property
    def av_min_ok(self):
        if not self.min_required:
            return True
        return self.s > 0 and self.Av / self.s >= self.Av_min_s - 1e-12

    @property
    def spacing_ok(self):
        return self.s == 0 or self.s <= self.s_max + 1e-9

    @property
    def ok(self):
        return (self.strength_ok and self.section_ok and self.av_min_ok
                and self.spacing_ok)


def s_max_long(fc, bw, d, Vs_req, lam=1.0):
    """Table 9.7.6.2.2 ระยะปลอกตามยาว (ขอบ 0.33√f′c·bw·d ยังไม่ยืนยันกับตัวเล่ม)"""
    if Vs_req <= 0.33 * lam * sqrt_fc(fc) * bw * d:
        return min(d / 2.0, 600.0)
    return min(d / 4.0, 300.0)


def check_stirrups(Vu, fc, fyt, bw, d, As, ds, legs, s, lam=1.0,
                   exempt_9631=False, vc_simple="a"):
    """ตรวจปลอก 'legs' ขา ขนาด ds @ s (s = 0 → ไม่มีปลอก)"""
    Av = legs * bar_area(ds) if s > 0 else 0.0
    Avmin_s = av_min_per_s(fc, bw, fyt)
    vcs = vc_eqs(fc, bw, d, As, lam)
    if s > 0 and Av / s >= Avmin_s - 1e-12:
        eq = vc_simple
    else:
        eq = "c"
    Vc = vcs[eq]
    Vs = Av * fyt * d / s if s > 0 else 0.0
    Vs_req = max(0.0, Vu / PHI_V - Vc)
    limit = PHI_V * (Vc + 0.66 * sqrt_fc(fc) * bw * d)
    min_req = (not exempt_9631) and Vu > 0.083 * PHI_V * lam * sqrt_fc(fc) * bw * d
    notes = []
    if exempt_9631:
        notes.append("ผู้ใช้ระบุว่าเข้าข้อยกเว้น Table 9.6.3.1 (ต้องตรวจเอง)")
    return ShearResult(
        Vu=Vu, bw=bw, d=d, Av=Av, s=s, Av_min_s=Avmin_s, Vc=Vc, vc_eq=eq,
        vcs=vcs, Vs=Vs, Vs_req=Vs_req, phiVn=PHI_V * (Vc + Vs),
        s_max=s_max_long(fc, bw, d, Vs_req, lam), min_required=min_req,
        section_ok=Vu <= limit + 1e-9, section_limit=limit, notes=notes,
    )


def design_stirrups(Vu, fc, fyt, bw, d, As, ds, legs, lam=1.0,
                    exempt_9631=False, vc_simple="a", step=25.0, always_min=True):
    """เลือกระยะปลอก (ปัดลงทีละ step mm)

    always_min=True (ค่าเริ่มต้น): ใส่ปลอกอย่างน้อยเท่า Av,min และ s ≤ s_max เสมอ แม้ ACI ไม่บังคับ
    (Vu ≤ 0.083φλ√f′c·bw·d) — ยึดเหล็กยืน และกันการวิบัติเฉือนแบบเปราะ; False = ไม่ใส่ถ้าไม่บังคับ
    """
    no = check_stirrups(Vu, fc, fyt, bw, d, As, ds, legs, 0.0, lam,
                        exempt_9631, vc_simple)
    if not no.min_required and no.strength_ok and not always_min:
        no.notes.append("ไม่ต้องใช้ปลอกตามการคำนวณ (Vc จากสมการ (c)) "
                        "แต่ในทางปฏิบัติควรใส่ปลอกขั้นต่ำ")
        return no

    Av = legs * bar_area(ds)
    vcs = vc_eqs(fc, bw, d, As, lam)
    Vc = vcs[vc_simple]
    Vs_req = max(0.0, Vu / PHI_V - Vc)
    cands = [Av / av_min_per_s(fc, bw, fyt), s_max_long(fc, bw, d, Vs_req, lam)]
    if Vs_req > 0:
        cands.append(Av * fyt * d / Vs_req)
    s = math.floor(min(cands) / step) * step
    if s < step:
        s = step
    r = check_stirrups(Vu, fc, fyt, bw, d, As, ds, legs, s, lam, exempt_9631,
                       vc_simple)
    if not no.min_required:
        r.notes.append("ACI ไม่บังคับปลอก (Vu ≤ 0.083φλ√f′c·bw·d) — ใส่ปลอกขั้นต่ำ Av,min @ s ≤ s_max "
                       "ตามแนวปฏิบัติ (ยึดเหล็กยืน, กันวิบัติเฉือนแบบเปราะ)")
    if s < 75.0:
        r.notes.append("ระยะปลอกถี่มาก → พิจารณาเพิ่มขนาด/จำนวนขาปลอกหรือหน้าตัด")
    return r
