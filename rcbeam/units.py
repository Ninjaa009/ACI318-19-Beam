"""แปลงหน่วย kgf–m (ผู้ใช้) <-> MPa–mm–N (ภายใน)"""

G = 9.80665                  # kgf -> N
KSC_TO_MPA = 0.0980665       # kgf/cm² -> MPa
KGFM_TO_NMM = 9806.65        # kgf·m -> N·mm
CM2_TO_MM2 = 100.0


def ksc_to_mpa(x):
    return x * KSC_TO_MPA


def mpa_to_ksc(x):
    return x / KSC_TO_MPA


def kgf_to_n(x):
    return x * G


def n_to_kgf(x):
    return x / G


def kgfm_to_nmm(x):
    return x * KGFM_TO_NMM


def nmm_to_kgfm(x):
    return x / KGFM_TO_NMM


def mm2_to_cm2(x):
    return x / CM2_TO_MM2


def m_to_mm(x):
    return x * 1000.0
