"""เรนเดอร์สมการแบบ LaTeX (ฟอนต์ Computer Modern) เป็น SVG ด้วย matplotlib mathtext"""
import base64
import functools
import io
import re
from html import escape

import matplotlib

matplotlib.use("Agg")
from matplotlib import mathtext  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402

_SIZE_RE = re.compile(rb'<svg[^>]*?width="([\d.]+)pt"[^>]*?height="([\d.]+)pt"')


@functools.lru_cache(maxsize=1024)
def tex_svg(expr, size=11.0):
    """คืน (svg bytes, width pt, height pt)"""
    buf = io.BytesIO()
    with matplotlib.rc_context({"svg.fonttype": "path", "svg.hashsalt": "rcbeam"}):
        mathtext.math_to_image(f"${expr}$", buf, format="svg",
                               prop=FontProperties(size=size, math_fontfamily="cm"))
    svg = buf.getvalue()
    m = _SIZE_RE.search(svg)
    w, h = (float(m.group(1)), float(m.group(2))) if m else (0.0, size)
    return svg, w, h


def tex(expr, size=11.0, cls="m"):
    """แท็ก <img> ของสมการ (ขนาดคงตามหน่วย pt จึงพิมพ์ได้คมชัด)"""
    svg, w, h = tex_svg(expr, size)
    b64 = base64.b64encode(svg).decode("ascii")
    return (f'<img class="{cls}" alt="{escape(expr)}" style="width:{w:.2f}pt;'
            f'height:{h:.2f}pt" src="data:image/svg+xml;base64,{b64}">')
