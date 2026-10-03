"""โมเดล STAAD ตัวอย่าง (โครง 1 ชั้น 3×2 ช่วง) — ใช้ร่วมกันทุกหน้า"""
from pathlib import Path

from rcbeam.colcheck import C
import staad_io as S  # noqa: E402  (skill scripts อยู่ใน sys.path จาก rcbeam.colcheck)

EXAMPLE_DIR = (Path(__file__).resolve().parent.parent / "skills" / "rc-column-aci318m19" / "references"
               / "staad_example")
STD = EXAMPLE_DIR / "frame_3x2.std"
TABLE = EXAMPLE_DIR / "frame_3x2_beam_end_force.txt"


def load_example(ss):
    """ใส่โมเดลตัวอย่าง (.std จริง + ตาราง Beam End Force จริง) ลงใน session_state"""
    ss.std_text, ss.std_name = STD.read_text(), STD.name
    ss.pop("anl_text", None)
    ss.sm_src2 = "table"
    ss.sm_table = TABLE.read_text()
    ss.staad_model = S.parse_std(ss.std_text)
    ss.staad_forces = S.forces_from_table(ss.sm_table, C.parse_staad_end_forces, C.STAAD_FORCE_UNITS,
                                          C.STAAD_MOMENT_UNITS)
