"""อ่านไฟล์ STAAD.Pro: input (.std) + ตาราง Beam End Force ที่คัดลอกจากหน้าจอ STAAD

หน่วยภายใน: mm, N, N·mm (เหมือน column.py)

parse_std(text)  -> Model   : geometry, หน้าตัด PRIS, beta, ฐานรองรับ, load case, load combination
forces_from_table(text, ...) -> Forces : ตาราง Beam End Force ทุก member (แกน local) หน่วยจากหัวตาราง
column_forces(model, forces, member, load) -> dict ของ from_staad + ทิศการดัด (บน/ล่างจาก geometry)

ข้อจำกัด
- รองรับคำสั่งหลักที่ใช้กับโครงข้อแข็ง คสล.: JOINT COORDINATES, MEMBER INCIDENCES, MEMBER PROPERTY (PRIS),
  CONSTANTS (BETA), SUPPORTS, LOAD / LOAD COMB, UNIT — คำสั่งอื่นถูกข้ามและเก็บไว้ใน Model.skipped
- FLOOR LOAD กระจายลงคานแบบเส้น 45° เฉพาะแผ่นสี่เหลี่ยมที่มีคานล้อมครบ (ยืนยันกับ STAAD แล้วสำหรับแผ่นจัตุรัส)
"""
from dataclasses import dataclass, field
import math
import re

LEN = {"METER": 1000.0, "METE": 1000.0, "M": 1000.0, "MMS": 1.0, "MM": 1.0, "CMS": 10.0, "CM": 10.0,
       "FEET": 304.8, "FT": 304.8, "INCHES": 25.4, "INCH": 25.4, "IN": 25.4, "DME": 100.0}
FORCE = {"KN": 1e3, "KNS": 1e3, "NEWTON": 1.0, "NEW": 1.0, "NEWT": 1.0, "N": 1.0, "KG": 9.80665,
         "KGS": 9.80665, "MTON": 9806.65, "MTO": 9806.65, "KIP": 4448.222, "KIPS": 4448.222,
         "POUND": 4.448222, "POUN": 4.448222, "LB": 4.448222, "MNS": 1e6}

_LATERAL = {"GX", "GZ", "FX", "FZ", "PX", "PZ", "WIND", "SEISMIC", "ELOAD", "SPECTRUM", "UBC", "IBC",
            "AIJ", "IS1893", "NOTIONAL"}
_SERVICE_WORDS = ("SERVICE", "SLS", "ASD", "ALLOWABLE", "DEFLECTION", "UNFACTOR")


def _unit_key(tok, table):
    t = tok.upper()
    for k in sorted(table, key=len, reverse=True):
        if t.startswith(k):
            return k
    return None


def ids(spec):
    """แปลงรายการ STAAD เช่น "1 TO 12 15 17" → [1..12, 15, 17] (ข้ามคำที่ไม่ใช่ตัวเลข)"""
    t = spec.split()
    out, i = [], 0
    while i < len(t):
        if i + 2 < len(t) and t[i + 1].upper() == "TO" and t[i].isdigit() and t[i + 2].isdigit():
            a, b = int(t[i]), int(t[i + 2])
            step = 1
            if i + 4 < len(t) and t[i + 3].upper() == "BY" and t[i + 4].isdigit():
                step = int(t[i + 4])
                i += 2
            out += list(range(a, b + 1, step))
            i += 3
        elif t[i].isdigit():
            out.append(int(t[i]))
            i += 1
        else:
            i += 1
    return out


@dataclass
class LoadCase:
    id: int
    kind: str              # "primary" | "comb" | "repeat"
    title: str = ""
    loadtype: str = ""     # Dead, Live, Wind, ... (จาก LOADTYPE)
    lines: list = field(default_factory=list)     # คำสั่งดิบ (สำหรับแสดง)
    factors: dict = field(default_factory=dict)   # comb/repeat: {load id: factor}
    items: list = field(default_factory=list)     # primary: dict ของน้ำหนักบรรทุกที่อ่านได้ (หน่วย N, mm)
    lateral: bool = False


@dataclass
class Model:
    joints: dict = field(default_factory=dict)      # id -> (x, y, z) mm
    members: dict = field(default_factory=dict)     # id -> (start joint, end joint)
    prism: dict = field(default_factory=dict)       # id -> (YD, ZD) mm
    beta: dict = field(default_factory=dict)        # id -> องศา
    supports: dict = field(default_factory=dict)    # joint -> "FIXED" | "PINNED" | ...
    loads: dict = field(default_factory=dict)       # id -> LoadCase (เรียงตามลำดับในไฟล์)
    material: dict = field(default_factory=dict)    # ชื่อ -> {E, FCU, ...} (หน่วย N, mm)
    mat_of: dict = field(default_factory=dict)      # member -> ชื่อวัสดุ (CONSTANTS MATERIAL)
    units: tuple = ("METER", "KN")                  # หน่วยสุดท้ายที่ประกาศ
    skipped: list = field(default_factory=list)

    # ---------------------------------------------------------------- geometry
    def length(self, m):
        a, b = self.members[m]
        return math.dist(self.joints[a], self.joints[b])

    def is_vertical(self, m, tol=1e-6):
        a, b = self.members[m]
        (x1, _, z1), (x2, _, z2) = self.joints[a], self.joints[b]
        return abs(x1 - x2) < tol and abs(z1 - z2) < tol

    def columns(self):
        return [m for m in self.members if self.is_vertical(m)]

    def beams(self):
        return [m for m in self.members if not self.is_vertical(m)]

    def bottom_top(self, m):
        """(joint ล่าง, joint บน) ของเสา"""
        a, b = self.members[m]
        return (a, b) if self.joints[a][1] <= self.joints[b][1] else (b, a)

    # ---------------------------------------------------------------- load
    def primaries(self):
        return [lc for lc in self.loads.values() if lc.kind == "primary"]

    def combos(self):
        return [lc for lc in self.loads.values() if lc.kind in ("comb", "repeat")]

    def expand(self, lid, _seen=None):
        """ตัวคูณของ primary load ทั้งหมดใน load id (คลี่ REPEAT/COMB ซ้อนกัน)"""
        lc = self.loads.get(lid)
        if lc is None:
            return {}
        if lc.kind == "primary":
            return {lid: 1.0}
        _seen = (_seen or set()) | {lid}
        out = {}
        for k, f in lc.factors.items():
            if k in _seen:
                continue
            for p, g in self.expand(k, _seen).items():
                out[p] = out.get(p, 0.0) + f * g
        return out

    def is_lateral(self, lid):
        return any(self.loads[p].lateral for p in self.expand(lid) if p in self.loads)

    def is_service(self, lid):
        """combo ใช้งาน (ไม่คูณ factor): ตัวคูณทุกตัว = 1.0 หรือชื่อบอกว่าเป็น service / ASD"""
        lc = self.loads[lid]
        if lc.kind == "primary":
            return False
        if any(w in lc.title.upper() for w in _SERVICE_WORDS):
            return True
        f = list(self.expand(lid).values())
        return bool(f) and all(abs(x - 1.0) < 1e-9 for x in f)

    def vertical_total(self, lid):
        """ประมาณแรงแนวดิ่งรวม (N, ลง = ลบ) ของ primary load จากข้อมูลที่อ่านได้ — ใช้เทียบกับ
        แรงอัดที่ฐานเสารวมจากตาราง Beam End Force เพื่อยืนยันว่า geometry / หน้าตัด / หน่วย / แรงครบ
        FLOOR LOAD คิดพื้นที่เป็นกรอบสี่เหลี่ยมของ XRANGE/ZRANGE ตัดกับขอบโมเดล (แม่นเมื่อพื้นเต็มกรอบ)
        คืน (ค่า, หมายเหตุ) — None ถ้ามีน้ำหนักชนิดที่ประมาณไม่ได้
        """
        lc = self.loads[lid]
        tot, notes = 0.0, []
        X = [p[0] for p in self.joints.values()]
        Z = [p[2] for p in self.joints.values()]
        for it in lc.items:
            if it["type"] == "selfweight":
                if it["dir"] != "Y":
                    continue
                w = 0.0
                for m in self.members:
                    mat = self.material.get(self.mat_of.get(m, ""), {})
                    if m not in self.prism or "DENSITY" not in mat:
                        return None, f"member {m} ไม่มีหน้าตัด PRIS หรือ DENSITY"
                    YD, ZD = self.prism[m]
                    w += YD * ZD * self.length(m) * mat["DENSITY"]
                tot += it["factor"] * w
                notes.append("selfweight")
            elif it["type"] == "floor":
                r = it["range"]
                x0, x1 = (max(min(X), r["X"][0]), min(max(X), r["X"][1])) if "X" in r else (min(X), max(X))
                z0, z1 = (max(min(Z), r["Z"][0]), min(max(Z), r["Z"][1])) if "Z" in r else (min(Z), max(Z))
                tot += it["w"] * max(x1 - x0, 0) * max(z1 - z0, 0)
                notes.append("floor (กรอบสี่เหลี่ยม)")
            elif it["type"] == "member" and it["dir"] in ("GY", "PY"):
                if it["kind"] == "UNI" and not it["rest"]:
                    tot += it["w"] * self.length(it["member"])
                elif it["kind"] == "CON":
                    tot += it["w"]
                else:
                    return None, f"member load {it['kind']} {it['rest']}"
            elif it["type"] == "joint":
                tot += it.get("FY", 0.0)
            elif it["type"] != "member":
                return None, it["type"]
        return tot, ", ".join(notes)

    def strength_combos(self):
        return [lc.id for lc in self.combos() if not self.is_service(lc.id)]


def _logical_lines(text):
    """รวมบรรทัดที่ต่อด้วย '-' แยกคำสั่งด้วย ';' ตัดหมายเหตุ ('*' ต้นบรรทัด)"""
    out, buf = [], ""
    for raw in str(text).splitlines():
        s = raw.strip()
        if not s or s.startswith("*"):
            continue
        if s == "-" or s.endswith(" -"):
            buf += s[:-1] + " "
            continue
        s = buf + s
        buf = ""
        out += [p.strip() for p in s.split(";") if p.strip()]
    if buf:
        out.append(buf.strip())
    return out


def _is_number(t):
    try:
        float(t)
        return True
    except ValueError:
        return False


def parse_std(text):
    M = Model()
    L, F = 1000.0, 1e3                     # ค่าเริ่มต้นของ STAAD ถ้าไม่ประกาศ: ใช้ METER KN (ปลอดภัยกว่า)
    lu, fu = "METER", "KN"
    sec, mat_name, cur = None, None, None
    sub = None                             # หัวข้อย่อยใน LOAD: FLOOR LOAD, MEMBER LOAD, JOINT LOAD, ...
    for line in _logical_lines(text):
        U = line.upper()
        tok = U.split()
        if tok[0] == "UNIT":
            for t in tok[1:]:
                if t in LEN:
                    L, lu = LEN[t], t
                elif t in FORCE or _unit_key(t, FORCE):
                    F, fu = FORCE[t] if t in FORCE else FORCE[_unit_key(t, FORCE)], t
            M.units = (lu, fu)
            continue
        if U.startswith("JOINT COORD"):
            sec = "joint"
            continue
        if U.startswith("MEMBER INCI"):
            sec = "member"
            continue
        if U.startswith("MEMBER PROP"):
            sec = "prop"
            continue
        if U.startswith("CONSTANT"):
            sec = "const"
            continue
        if U.startswith("SUPPORT"):
            sec = "support"
            continue
        if U.startswith("DEFINE MATERIAL"):
            sec = "material"
            continue
        if U.startswith("END DEFINE"):
            sec = None
            continue
        m = re.match(r"LOAD\s+COMB(?:INATION)?\s+(\d+)\s*(.*)", U)
        if m:
            lid = int(m.group(1))
            cur = M.loads[lid] = LoadCase(lid, "comb", line.split(None, 3)[3] if len(line.split()) > 3 else "")
            sec, sub = "comb", None
            continue
        m = re.match(r"LOAD\s+(\d+)\b(.*)", U)
        if m and not U.startswith("LOAD LIST"):
            lid = int(m.group(1))
            rest = line[m.start(2):]
            lt = re.search(r"LOADTYPE\s+(\S+)", rest, re.I)
            tt = re.search(r"TITLE\s+(.*)", rest, re.I)
            cur = M.loads[lid] = LoadCase(lid, "primary", tt.group(1).strip() if tt else rest.strip(),
                                          lt.group(1) if lt else "")
            if lt and lt.group(1).upper() in ("WIND", "SEISMIC", "SEISMIC-H", "EARTHQUAKE"):
                cur.lateral = True
            sec, sub = "load", None
            continue
        if U.startswith(("PERFORM", "FINISH", "LOAD LIST", "PRINT", "PARAMETER", "CHECK", "SELECT",
                         "START ", "END JOB", "STAAD", "INPUT", "SET ")):
            sec = None
            if not U.startswith(("FINISH", "STAAD", "INPUT", "SET ", "START ", "END JOB")):
                M.skipped.append(line)
            continue

        if sec == "joint":
            v = line.split()
            if len(v) >= 4 and all(_is_number(x) for x in v[:4]):
                M.joints[int(v[0])] = tuple(float(x) * L for x in v[1:4])
        elif sec == "member":
            v = line.split()
            if len(v) >= 3 and all(x.isdigit() for x in v[:3]):
                M.members[int(v[0])] = (int(v[1]), int(v[2]))
        elif sec == "prop":
            mm = re.match(r"(.*?)\bPRIS\b(.*)", U)
            if mm:
                yd = re.search(r"YD\s+([\d.Ee+-]+)", mm.group(2))
                zd = re.search(r"ZD\s+([\d.Ee+-]+)", mm.group(2))
                for k in ids(mm.group(1)):
                    if yd:
                        Y = float(yd.group(1)) * L
                        M.prism[k] = (Y, float(zd.group(1)) * L if zd else Y)
            else:
                M.skipped.append(line)
        elif sec == "const":
            mb = re.match(r"BETA\s+([\d.Ee+-]+)\s+(.*)", U)
            if mb:
                ang = float(mb.group(1))
                tgt = mb.group(2)
                lst = list(M.members) if re.search(r"\bALL\b", tgt) else ids(tgt.replace("MEMB", " "))
                for k in lst:
                    M.beta[k] = ang
            mm_ = re.match(r"MATERIAL\s+(\S+)\s+(.*)", U)
            if mm_:
                tgt = mm_.group(2)
                lst = list(M.members) if re.search(r"\bALL\b", tgt) else ids(tgt.replace("MEMB", " "))
                for k in lst:
                    M.mat_of[k] = mm_.group(1)
        elif sec == "support":
            ms = re.match(r"(.*?)\b(FIXED|PINNED|ENFORCED)\b", U)
            if ms:
                for j in ids(ms.group(1)):
                    M.supports[j] = ms.group(2)
        elif sec == "material":
            v = line.split()
            if tok[0] == "ISOTROPIC" and len(v) > 1:
                mat_name = v[1].upper()
                M.material[mat_name] = {}
            elif mat_name and len(v) >= 2 and _is_number(v[-1]):
                key = " ".join(tok[:-1])
                val = float(v[-1])
                if key in ("E", "G", "STRENGTH FCU", "STRENGTH FC", "STRENGTH FY"):
                    val *= F / L ** 2                 # แรง/พื้นที่ → MPa
                elif key == "DENSITY":
                    val *= F / L ** 3                 # แรง/ปริมาตร → N/mm³
                M.material[mat_name][key] = val
        elif sec == "comb":
            v = line.split()
            if all(_is_number(x) for x in v) and len(v) % 2 == 0:
                for a, b in zip(v[::2], v[1::2]):
                    cur.factors[int(float(a))] = cur.factors.get(int(float(a)), 0.0) + float(b)
        elif sec == "load" and cur is not None:
            cur.lines.append(line)
            if U.startswith("REPEAT LOAD"):
                cur.kind, sub = "repeat", "repeat"
                continue
            if sub == "repeat":
                v = line.split()
                if all(_is_number(x) for x in v) and len(v) % 2 == 0:
                    for a, b in zip(v[::2], v[1::2]):
                        cur.factors[int(float(a))] = cur.factors.get(int(float(a)), 0.0) + float(b)
                    continue
            if any(w in _LATERAL for w in re.split(r"[\s,]+", U)):
                cur.lateral = True
            if U.startswith("SELFWEIGHT") or U.startswith("SELF WEIGHT"):
                d = re.search(r"\b([XYZ])\s+([\d.Ee+-]+)", U)
                cur.items.append({"type": "selfweight", "dir": d.group(1) if d else "Y",
                                  "factor": float(d.group(2)) if d else -1.0})
                if d and d.group(1) in "XZ":
                    cur.lateral = True
                continue
            if U in ("FLOOR LOAD", "MEMBER LOAD", "JOINT LOAD", "ELEMENT LOAD", "ONEWAY LOAD"):
                sub = U
                continue
            if sub in ("FLOOR LOAD", "ONEWAY LOAD"):
                fl = re.search(r"FLOAD\s+([\d.Ee+-]+)", U)
                rng = {a: tuple(float(x) * L for x in re.search(rf"{a}RANGE\s+([\d.Ee+-]+)\s+([\d.Ee+-]+)",
                                                                  U).groups())
                       for a in "XYZ" if re.search(rf"{a}RANGE\s+", U)}
                if fl:
                    cur.items.append({"type": "floor", "w": float(fl.group(1)) * F / L ** 2,
                                      "range": rng, "dir": "GY" if " GX" not in U and " GZ" not in U else "lat"})
            elif sub == "MEMBER LOAD":
                mm = re.match(r"(.*?)\b(UNI|UMOM|CON|CMOM|LIN|TRAP)\b\s+(\S+)\s+([\d.Ee+-]+)(.*)", U)
                if mm:
                    kind, d, w = mm.group(2), mm.group(3), float(mm.group(4))
                    scale = F / L if kind in ("UNI", "LIN", "TRAP") else F
                    for k in ids(mm.group(1)):
                        cur.items.append({"type": "member", "member": k, "kind": kind, "dir": d,
                                          "w": w * scale, "rest": mm.group(5).strip()})
            elif sub == "JOINT LOAD":
                mj = re.match(r"(.*?)\b((?:F[XYZ]|M[XYZ])\b.*)", U)
                if mj:
                    comp = dict(re.findall(r"\b(F[XYZ]|M[XYZ])\s+([\d.Ee+-]+)", mj.group(2)))
                    for j in ids(mj.group(1)):
                        cur.items.append({"type": "joint", "joint": j,
                                          **{k: float(v) * (F if k[0] == "F" else F * L) for k, v in comp.items()}})
        elif sec is None:
            M.skipped.append(line)
    return M


# ---------------------------------------------------------------- แรงใน member
@dataclass
class Forces:
    data: dict = field(default_factory=dict)   # (member, load) -> {joint: (fx, fy, fz, mx, my, mz)} N, N·mm
    units: list = field(default_factory=list)  # หัวตารางหน่วยที่พบ เช่น "KN METE"

    def members(self):
        return sorted({m for m, _ in self.data})

    def loads(self):
        return sorted({lc for _, lc in self.data})


def forces_from_table(text, parse_table, force_units, moment_units, fu=None, mu=None):
    """ตาราง Beam End Force ที่คัดลอกจากหน้าจอ STAAD (ทุก member) → Forces (N, N·mm, แกน local ของ member)

    parse_table / force_units / moment_units = column.parse_staad_end_forces, STAAD_FORCE_UNITS,
    STAAD_MOMENT_UNITS (ส่งเข้ามาเพื่อไม่ให้ staad_io ผูกกับ column.py)
    หน่วยอ่านจากหัวตาราง (เช่น "Axial Force kg", "Moment-Y kN-m") หรือส่ง fu / mu เอง — ไม่มีหน่วย → ValueError
    """
    rows, fu_d, mu_d = parse_table(text)
    fu, mu = fu or fu_d, mu or mu_d
    if rows and not (fu and mu):
        raise ValueError("ไม่พบหน่วยในหัวตาราง — คัดลอกตาราง Beam End Force พร้อมแถวหัวตาราง (มี kg / kN-m ฯลฯ)")
    out = Forces()
    if not rows:
        return out
    kf, km = force_units[fu], moment_units[mu]
    for r in rows:
        try:
            m, lc, j = int(r["beam"]), int(str(r["lc"]).split()[0]), int(r["node"])
        except ValueError:
            continue
        out.data.setdefault((m, lc), {})[j] = (r["fx"] * kf, r["fy"] * kf, r["fz"] * kf,
                                                r["mx"] * km, r["my"] * km, r["mz"] * km)
    out.units = [f"{fu}, {mu}"]
    return out


def base_reactions(model, forces, load):
    """ΣFx ที่ joint ฐานรองรับของเสาทุกต้น (N) — เทียบกับน้ำหนักแนวดิ่งรวมของ load เพื่อตรวจว่าแรงครบทุกเสา
    คืน (ผลรวม, จำนวนเสาที่มีข้อมูล, จำนวนเสาที่ต่อกับฐานรองรับ)"""
    tot, n, nsup = 0.0, 0, 0
    for m in model.columns():
        lo, _ = model.bottom_top(m)
        if lo not in model.supports:
            continue
        nsup += 1
        d = forces.data.get((m, load))
        if d and lo in d:
            f = d[lo][0] if model.members[m][0] == lo else -d[lo][0]   # แรงอัดที่ฐาน (บวก)
            tot += f
            n += 1
    return tot, n, nsup


def end_curvature(m_start, m_end, tiny=1e3):
    """ทิศการดัดจากเครื่องหมายโมเมนต์ปลายใน member end forces ของ STAAD (แรงกระทำต่อชิ้นส่วน, แกน local)
    เครื่องหมายเดียวกัน = โค้งสองทาง (double), ต่างกัน = โค้งทางเดียว (single) — ไม่ต้องใช้ความยาว
    ปลายใดเป็นศูนย์ (< tiny N·mm) → "auto" ให้ curvature_ratio จัดการกรณี M1 = 0 / M1 = M2 = 0
    """
    if abs(m_start) < tiny or abs(m_end) < tiny:
        return "auto"
    return "double" if m_start * m_end > 0 else "single"


def column_forces(model, forces, member, load, from_staad):
    """แรงของเสาใน load หนึ่ง → dict ของ from_staad + ทิศการดัด (curv_x, curv_y)

    ใช้ geometry ตัดสินบน/ล่าง ไม่สมมติว่า start node อยู่ล่าง:
    - Mxt / Myt = โมเมนต์ที่ joint บน, Mxb / Myb = ที่ joint ล่าง (ใช้ขนาด)
    - Pu = แรงอัดที่ joint ล่าง (มากกว่าที่หัวเสาเท่าน้ำหนักเสาเอง): start ล่าง → +Fx(start), end ล่าง → −Fx(end)
    - curv_x / curv_y จากเครื่องหมายโมเมนต์ปลาย (end_curvature) — M1/M2 ตัดสินจากขนาดใน slenderness
    """
    a, b = model.members[member]
    d = forces.data.get((member, load))
    if not d or a not in d or b not in d:
        raise KeyError(f"ไม่มีแรงของ member {member} load {load} ครบทั้ง 2 joint")
    s, e = d[a], d[b]
    f = from_staad(s[0], s[1], s[2], s[4], s[5], e[4], e[5])     # t = end, b = start
    lo, _ = model.bottom_top(member)
    if lo != a:                                                  # start อยู่บน: สลับป้ายบน/ล่าง
        f["Mxt"], f["Mxb"], f["Myt"], f["Myb"] = f["Mxb"], f["Mxt"], f["Myb"], f["Myt"]
        f["Pu"] = -e[0]
    f["curv_x"] = end_curvature(s[5], e[5])                      # Mz (ภายใน x)
    f["curv_y"] = end_curvature(s[4], e[4])                      # My
    return f


def check_equilibrium(model, forces, member, load, tol=0.02):
    """ตรวจว่าแรงในตารางสมดุลกับความยาวจาก geometry: ΣF ≈ 0 (ยกเว้นน้ำหนักตัวเองตามแกน) และ
    Mz_s + Mz_e + Fy_e·L ≈ 0, My_s + My_e − Fz_e·L ≈ 0 (สมดุลรอบ start node, แกน local)
    คืน (ผ่านหรือไม่, ค่าคลาดเคลื่อนสัมพัทธ์สูงสุด)
    """
    a, b = model.members[member]
    d = forces.data[(member, load)]
    s, e = d[a], d[b]
    L = model.length(member)
    rz = s[5] + e[5] + e[1] * L
    ry = s[4] + e[4] - e[2] * L
    scale = max(abs(s[5]), abs(e[5]), abs(s[4]), abs(e[4]), abs(e[1] * L), abs(e[2] * L), 1e3)
    err = max(abs(rz), abs(ry)) / scale
    return err <= tol, err


# ---------------------------------------------------------------- คาน: โมเมนต์/แรงเฉือนตลอดช่วง
def _is_horizontal(model, m, tol=1e-6):
    a, b = model.members[m]
    return abs(model.joints[a][1] - model.joints[b][1]) < tol


def floor_beam_loads(model, item, tol=1.0):
    """กระจาย FLOOR LOAD ลงคานแบบเส้น 45° (two-way) — แผ่นพื้น = ช่องสี่เหลี่ยมที่มีคานล้อมครบ 4 ด้าน
    ในระนาบ YRANGE และอยู่ใน XRANGE/ZRANGE; คานแต่ละด้านรับ w·min(t, ℓ − t, s/2) (s = ด้านสั้นของแผ่น)
    → ด้านยาวได้สี่เหลี่ยมคางหมู ด้านสั้นได้สามเหลี่ยม (ตรงกับที่ STAAD แปลง floor load เป็น member load)
    คืน ({member: [("LIN", w1, w2, a, b)]}, จำนวนแผ่น) หน่วย N/mm, mm (w ลบ = ลง)
    """
    r = item["range"]
    inside = lambda v, ax: ax not in r or r[ax][0] - tol <= v <= r[ax][1] + tol   # noqa: E731
    lines = {"X": {}, "Z": {}}       # แนวคาน: ("X", z) -> [(x0, x1, member)] ; ("Z", x) -> [(z0, z1, member)]
    for m in model.beams():
        a, b = (model.joints[j] for j in model.members[m])
        if not (inside(a[1], "Y") and inside(b[1], "Y")):
            continue
        if abs(a[2] - b[2]) < tol:
            lines["X"].setdefault(round(a[2], 3), []).append((min(a[0], b[0]), max(a[0], b[0]), m))
        elif abs(a[0] - b[0]) < tol:
            lines["Z"].setdefault(round(a[0], 3), []).append((min(a[2], b[2]), max(a[2], b[2]), m))
    xs = sorted({round(v, 3) for seg in lines["X"].values() for x0, x1, _ in seg for v in (x0, x1)} | set(lines["Z"]))
    zs = sorted({round(v, 3) for seg in lines["Z"].values() for z0, z1, _ in seg for v in (z0, z1)} | set(lines["X"]))

    def covered(segs, lo, hi):
        pos = lo
        for s0, s1, _ in sorted(segs or []):
            if s0 <= pos + tol and s1 > pos:
                pos = s1
        return pos >= hi - tol

    out, n = {}, 0
    w = item["w"]

    def put(segs, lo, hi, s, ax):
        le = hi - lo
        knots = sorted({0.0, min(s / 2, le / 2), max(le - s / 2, le / 2), le})
        q = lambda t: w * min(t, le - t, s / 2)            # noqa: E731
        for s0, s1, m in segs:
            a_, b_ = max(s0, lo), min(s1, hi)
            if b_ - a_ <= tol:
                continue
            j0 = model.joints[model.members[m][0]]
            start_lo = abs(j0[ax] - s0) < tol                 # joint start อยู่ฝั่งพิกัดน้อย?
            ts = sorted({a_ - lo, b_ - lo} | {k for k in knots if a_ - lo < k < b_ - lo})
            for t0, t1 in zip(ts, ts[1:]):
                p0, p1 = lo + t0, lo + t1                    # พิกัดโลกตามแนวคาน
                x0, x1 = (p0 - s0, p1 - s0) if start_lo else (s1 - p0, s1 - p1)
                w0, w1 = q(t0), q(t1)
                if x0 > x1:
                    x0, x1, w0, w1 = x1, x0, w1, w0
                out.setdefault(m, []).append(("LIN", w0, w1, x0, x1))

    for x0, x1 in zip(xs, xs[1:]):
        for z0, z1 in zip(zs, zs[1:]):
            if not (inside((x0 + x1) / 2, "X") and inside((z0 + z1) / 2, "Z")):
                continue
            edges = [(lines["X"].get(z0), x0, x1, 0), (lines["X"].get(z1), x0, x1, 0),
                     (lines["Z"].get(x0), z0, z1, 2), (lines["Z"].get(x1), z0, z1, 2)]
            if not all(covered(sg, lo, hi) for sg, lo, hi, _ in edges):
                continue
            n += 1
            s = min(x1 - x0, z1 - z0)
            for sg, lo, hi, ax in edges:
                put(sg, lo, hi, s, ax)
    return out, n


def beam_primary_loads(model, member, lid):
    """แรงตามขวางในแกน local y (+ ขึ้น) ของคานแนวราบ beta 0 สำหรับ primary load หนึ่ง จาก .std
    — selfweight จาก PRIS × DENSITY, FLOOR LOAD กระจายแบบ 45° (floor_beam_loads), MEMBER LOAD UNI / CON
    คืน list ของ (kind, w0, w1, a, b): UDL / LIN = แรงแผ่ N/mm จาก a ถึง b (w0 → w1); CON = แรง N ที่ a
    """
    lc = model.loads[lid]
    L = model.length(member)
    out = []
    cache = model.__dict__.setdefault("_floor_cache", {})
    for k, it in enumerate(lc.items):
        if it["type"] == "selfweight" and it["dir"] == "Y":
            mat = model.material.get(model.mat_of.get(member, ""), {})
            if member not in model.prism or "DENSITY" not in mat:
                raise ValueError(f"member {member}: ไม่มีหน้าตัด PRIS หรือ DENSITY สำหรับ selfweight")
            YD, ZD = model.prism[member]
            w = it["factor"] * YD * ZD * mat["DENSITY"]
            out.append(("UDL", w, w, 0.0, L))
        elif it["type"] == "floor":
            if it["dir"] != "GY":
                raise ValueError(f"LOAD {lid}: FLOOR LOAD ทิศแนวราบยังไม่รองรับ")
            if (lid, k) not in cache:
                cache[(lid, k)] = floor_beam_loads(model, it)[0]
            out += cache[(lid, k)].get(member, [])
        elif it["type"] == "member" and it["member"] == member:
            if it["dir"] not in ("GY", "Y"):
                raise ValueError(f"member {member} load {lid}: แรงทิศ {it['dir']} ยังไม่รองรับ")
            nums = [float(x) for x in it["rest"].split() if _is_number(x)]
            if it["kind"] == "UNI":
                a, b = (nums[0] * 1000, nums[1] * 1000) if len(nums) >= 2 else (0.0, L)   # ⚠️ ระยะใน .std เป็นหน่วยความยาวของไฟล์
                out.append(("UDL", it["w"], it["w"], a, b))
            elif it["kind"] == "CON":
                out.append(("CON", it["w"], it["w"], (nums[0] * 1000 if nums else L / 2), 0.0))
            else:
                raise ValueError(f"member load {it['kind']} ยังไม่รองรับ")
    return out


def beam_diagram(model, forces, member, load, n=61):
    """โมเมนต์ (บวก = ดึงล่าง) และแรงเฉือนตลอดคาน จากแรงปลาย start + load บนคาน (คานแนวราบ beta 0)

    M(x) = −Mz_s + Fy_s·x + Σ P(x − a) + Σ ∫w(t)(x − t)dt   ;   V(x) = Fy_s + Σ P + Σ ∫w dt  (ทางซ้ายของ x)
    ตรวจปิด: M(L) ต้องเท่ากับ +Mz_e และ V(L) = −Fy_e จากตาราง → ยืนยันแกน/หน่วย/load ที่อ่านได้
    คืน dict(x, M, V, close_M, close_V) หน่วย mm, N·mm, N
    """
    if not _is_horizontal(model, member):
        raise ValueError(f"member {member} ไม่ใช่คานแนวราบ")
    if abs(model.beta.get(member, 0.0)) > 1e-6:
        raise ValueError(f"member {member} มี beta = {model.beta[member]:g}° — ยังไม่รองรับ")
    a, b = model.members[member]
    d = forces.data.get((member, load))
    if not d or a not in d or b not in d:
        raise KeyError(f"ไม่มีแรงของ member {member} load {load} ครบทั้ง 2 joint")
    s, e = d[a], d[b]
    L = model.length(member)
    items = []
    for p, f in model.expand(load).items():
        items += [(k, f * w0, f * w1, x1, x2) for k, w0, w1, x1, x2 in beam_primary_loads(model, member, p)]
    pts = sorted({i * L / (n - 1) for i in range(n)} | {it[3] for it in items if it[0] == "CON"})
    xs, Ms, Vs = [], [], []
    for x in pts:
        M, V = -s[5] + s[1] * x, s[1]
        for k, w0, w1, x1, x2 in items:
            if k == "CON":
                if x1 < x - 1e-9:
                    M += w0 * (x - x1)
                    V += w0
            else:
                ln = min(max(x - x1, 0.0), x2 - x1)
                if ln > 0:                       # แรงแผ่เชิงเส้น w0 → w1 ส่วนที่อยู่ทางซ้ายของ x
                    wx = w0 + (w1 - w0) * ln / ((x2 - x1) or 1.0)
                    R = (w0 + wx) / 2 * ln
                    xc = x1 + (ln * (w0 + 2 * wx) / (3 * (w0 + wx)) if abs(w0 + wx) > 1e-12 else ln / 2)
                    M += R * (x - xc)
                    V += R
        xs.append(x); Ms.append(M); Vs.append(V)
    scale_M = max(max(abs(v) for v in Ms), abs(e[5]), 1e3)
    scale_V = max(max(abs(v) for v in Vs), abs(e[1]), 1.0)
    return dict(x=xs, M=Ms, V=Vs, close_M=abs(Ms[-1] - e[5]) / scale_M, close_V=abs(Vs[-1] + e[1]) / scale_V)


def support_face(model, member, end):
    """ระยะจาก joint ถึงผิวเสาที่ปลายคาน (mm) — ครึ่งหนึ่งของด้านเสาในแนวคาน; ไม่มีเสา → 0"""
    j = model.members[member][0 if end == "start" else 1]
    a, b = model.joints[model.members[member][0]], model.joints[model.members[member][1]]
    along_x = abs(b[0] - a[0]) >= abs(b[2] - a[2])
    best = 0.0
    for c in model.columns():
        if j in model.members[c] and c in model.prism:
            YD, ZD = model.prism[c]
            beta = abs(model.beta.get(c, 0.0)) % 180
            yd_along_x = beta < 45 or beta > 135          # เสาแนวดิ่ง beta 0: YD ขนานแกนโลก X
            dim = YD if yd_along_x == along_x else ZD
            best = max(best, dim / 2)
    return best


def beam_design_values(model, forces, member, loads, d_eff=None, at_face=True):
    """ค่าออกแบบของคานจาก combo กำลัง: M− ที่ผิวเสาซ้าย/ขวา, M+ สูงสุดในช่วง, Vu ที่ผิวเสา + d
    คืน dict: rows (ต่อ combo), env (ซ้าย/กลาง/ขวา → (Mu N·mm, Vu N, combo, x)), diag (ต่อ combo), faces
    """
    L = model.length(member)
    fl = support_face(model, member, "start") if at_face else 0.0
    fr = support_face(model, member, "end") if at_face else 0.0
    dd = d_eff or 0.0

    def at(D, xq, key):
        xs, ys = D["x"], D[key]
        for i in range(1, len(xs)):
            if xs[i] >= xq:
                t = (xq - xs[i - 1]) / ((xs[i] - xs[i - 1]) or 1.0)
                return ys[i - 1] + t * (ys[i] - ys[i - 1])
        return ys[-1]

    env = {"left": (0.0, 0.0, None, fl), "mid": (0.0, 0.0, None, L / 2), "right": (0.0, 0.0, None, L - fr)}
    rows, diags = [], {}
    for lc in loads:
        D = beam_diagram(model, forces, member, lc)
        diags[lc] = D
        mL, mR = at(D, fl, "M"), at(D, L - fr, "M")
        vL, vR = abs(at(D, min(fl + dd, L / 2), "V")), abs(at(D, max(L - fr - dd, L / 2), "V"))
        inner = [(x, m) for x, m in zip(D["x"], D["M"]) if fl <= x <= L - fr]
        xp, mP = max(inner, key=lambda t: t[1])
        vP = abs(at(D, xp, "V"))
        rows.append(dict(load=lc, M_left=mL, M_mid=mP, x_mid=xp, M_right=mR, V_left=vL, V_right=vR,
                         close=max(D["close_M"], D["close_V"])))
        if mL < env["left"][0]:
            env["left"] = (mL, max(vL, env["left"][1]), lc, fl)
        else:
            env["left"] = (env["left"][0], max(vL, env["left"][1]), env["left"][2], fl)
        if mR < env["right"][0]:
            env["right"] = (mR, max(vR, env["right"][1]), lc, L - fr)
        else:
            env["right"] = (env["right"][0], max(vR, env["right"][1]), env["right"][2], L - fr)
        if mP > env["mid"][0]:
            env["mid"] = (mP, max(vP, env["mid"][1]), lc, xp)
    return dict(rows=rows, env=env, diag=diags, faces=(fl, fr), L=L)
