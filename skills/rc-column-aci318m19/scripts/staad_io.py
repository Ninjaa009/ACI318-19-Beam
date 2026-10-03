"""อ่านไฟล์ STAAD.Pro: input (.std) และผลวิเคราะห์ (.anl)

หน่วยภายใน: mm, N, N·mm (เหมือน column.py)

parse_std(text)  -> Model   : geometry, หน้าตัด PRIS, beta, ฐานรองรับ, load case, load combination
parse_anl(text)  -> Forces  : ตาราง MEMBER END FORCES ทุกชุด (แกน local) พร้อมหน่วยจากหัวตาราง
column_forces(model, forces, member, load) -> dict ของ from_staad (P = Fx ที่ start node)

ข้อจำกัด
- รองรับคำสั่งหลักที่ใช้กับโครงข้อแข็ง คสล.: JOINT COORDINATES, MEMBER INCIDENCES, MEMBER PROPERTY (PRIS),
  CONSTANTS (BETA), SUPPORTS, LOAD / LOAD COMB, UNIT — คำสั่งอื่นถูกข้ามและเก็บไว้ใน Model.skipped
- รูปแบบ .anl ต่างกันได้ตามเวอร์ชัน STAAD ⚠️ ต้องทดสอบกับไฟล์จริงของผู้ใช้ก่อนใช้งานจริง
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
        'SUMMATION FORCE-Y' ใน .anl เพื่อยืนยันว่า geometry / หน้าตัด / หน่วยถูกต้อง
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


_HEADS = ("JOINT COORD", "MEMBER INCI", "MEMBER PROP", "CONSTANT", "SUPPORT", "DEFINE MATERIAL",
          "END DEFINE", "LOAD", "PERFORM", "FINISH", "UNIT", "PRINT", "START ", "END JOB", "STAAD",
          "INPUT", "SET ", "MEMBER RELEASE", "MEMBER TRUSS", "MEMBER OFFSET", "ELEMENT", "SPRING",
          "DEFINE", "CHANGE", "PARAMETER", "CHECK", "SELECT", "LOAD LIST", "ANALYSIS")


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


# ---------------------------------------------------------------- .anl
def extract_input_echo(text):
    """ดึงสำเนาไฟล์ input ที่ STAAD พิมพ์ไว้ต้นไฟล์ .anl (บรรทัด "    12. MEMBER INCIDENCES")
    คืนข้อความ .std หรือ None ถ้าไม่พบ — ใช้ .anl ไฟล์เดียวแทน .std ได้
    """
    out = []
    for raw in str(text).splitlines():
        m = re.match(r"^\s{0,10}(\d+)\.\s(.*)$", raw)
        if not m:
            continue
        out.append(m.group(2).rstrip())
        if m.group(2).strip().upper() == "FINISH":
            break
    return "\n".join(out) if out and out[0].strip().upper().startswith("STAAD") else None


def applied_totals(text):
    """'TOTAL APPLIED LOAD (...) SUMMARY (LOADING n)' ใน .anl → {n: (ΣFx, ΣFy, ΣFz) หน่วย N}"""
    out, cur, uf = {}, None, None
    for raw in str(text).splitlines():
        U = raw.upper()
        m = re.search(r"TOTAL APPLIED LOAD\s*\(\s*(\S+)\s+(\S+)\s*\)\s*SUMMARY\s*\(LOADING\s+(\d+)", U)
        if m:
            k = _unit_key(m.group(1), FORCE)
            cur, uf = int(m.group(3)), FORCE[k] if k else None
            out[cur] = [None, None, None]
            continue
        m = re.search(r"SUMMATION FORCE-([XYZ])\s*=\s*([-\d.Ee+]+)", U)
        if m and cur is not None and uf:
            out[cur]["XYZ".index(m.group(1))] = float(m.group(2)) * uf
            if m.group(1) == "Z":
                cur = None
    return {k: tuple(v) for k, v in out.items() if None not in v}


@dataclass
class Forces:
    data: dict = field(default_factory=dict)   # (member, load) -> {joint: (fx, fy, fz, mx, my, mz)} N, N·mm
    units: list = field(default_factory=list)  # หัวตารางหน่วยที่พบ เช่น "KN METE"
    tables: int = 0

    def members(self):
        return sorted({m for m, _ in self.data})

    def loads(self):
        return sorted({lc for _, lc in self.data})


_STOP = ("REACTION", "DISPLACE", "ENVELOPE", "SECTION FORCE", "STRESS", "END OF", "STATIC LOAD",
         "MAXIMUM", "SUMMARY", "STATICS CHECK", "MODE", "FREQUENC")


def _units_from(line):
    m = re.search(r"ALL\s+UNITS\s+ARE\s*-*\s*(\S+)\s+(\S+)", line.upper())
    if not m:
        return None
    f, l = _unit_key(m.group(1), FORCE), _unit_key(m.group(2), LEN)
    if not f or not l:
        return None
    return FORCE[f], LEN[l], f"{m.group(1)} {m.group(2)}"


def parse_anl(text):
    """อ่านตาราง MEMBER END FORCES ทุกชุดใน .anl → Forces (N, N·mm, แกน local ของ member)"""
    out = Forces()
    on, uf, ul = False, None, None
    member = load = None
    pending = None                       # หน่วยที่อ่านได้ก่อนเข้าหัวตาราง
    for raw in str(text).splitlines():
        s = raw.strip()
        U = s.upper()
        u = _units_from(U)
        if u:
            pending = u
            if on:
                uf, ul = u[0], u[1]
            continue
        if "MEMBER END FORCES" in U:
            on, member, load = True, None, None
            out.tables += 1
            if pending:
                uf, ul = pending[0], pending[1]
            continue
        if not on or not s:
            continue
        if any(w in U for w in _STOP) and not re.match(r"^[\d\s.Ee+-]+$", U):
            on = False
            continue
        v = s.split()
        if not all(_is_number(x) for x in v):
            continue                     # หัวคอลัมน์ / หัวหน้ากระดาษ
        if uf is None:
            raise ValueError("ไม่พบบรรทัด 'ALL UNITS ARE' ก่อนตาราง MEMBER END FORCES — ไม่รู้หน่วย")
        if len(v) == 9:
            member, load, joint = int(float(v[0])), int(float(v[1])), int(float(v[2]))
        elif len(v) == 8 and member is not None:
            load, joint = int(float(v[0])), int(float(v[1]))
        elif len(v) == 7 and load is not None:
            joint = int(float(v[0]))
        else:
            continue
        f = [float(x) for x in v[-6:]]
        vals = (f[0] * uf, f[1] * uf, f[2] * uf, f[3] * uf * ul, f[4] * uf * ul, f[5] * uf * ul)
        out.data.setdefault((member, load), {})[joint] = vals
        if pending and pending[2] not in out.units:
            out.units.append(pending[2])
    return out


def forces_from_table(text, parse_table, force_units, moment_units, fu=None, mu=None):
    """ตาราง Beam End Force ที่คัดลอกจากหน้าจอ STAAD (ทุก member) → Forces เหมือนอ่านจาก .anl

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
    out.tables = 1
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


def column_forces(model, forces, member, load, from_staad):
    """แรงของเสาใน load หนึ่ง → dict ของ from_staad (P = Fx ที่ start node ตาม incidences)"""
    a, b = model.members[member]
    d = forces.data.get((member, load))
    if not d or a not in d or b not in d:
        raise KeyError(f"ไม่มีแรงของ member {member} load {load} ครบทั้ง 2 joint ใน .anl")
    s, e = d[a], d[b]
    return from_staad(s[0], s[1], s[2], s[4], s[5], e[4], e[5])


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
