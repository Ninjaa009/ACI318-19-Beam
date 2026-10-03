"""รูปโมเดล STAAD สำหรับแอป (Plotly): 3D โมเดล + น้ำหนักบรรทุก และผังมองจากด้านบน

พิกัดตาม STAAD (Y ชี้ขึ้น) หน่วยที่แสดง: เมตร
"""
import math

import plotly.graph_objects as go

COL, BEAM, HL = "#c0392b", "#2e6da4", "#f39c12"


def _m(p):
    return tuple(c / 1000 for c in p)


def local_axes(model, m):
    """แกน local (x, y, z) ของ member ตามกติกา STAAD (beta หมุน y, z รอบ x) — เวกเตอร์หนึ่งหน่วยในแกนโลก"""
    a, b = model.members[m]
    pa, pb = model.joints[a], model.joints[b]
    L = math.dist(pa, pb)
    x = tuple((pb[i] - pa[i]) / L for i in range(3))
    if model.is_vertical(m):
        # ชิ้นส่วนแนวดิ่ง: z local ขนานแกนโลก Z, y = z × x
        z = (0.0, 0.0, 1.0)
    else:
        # ชิ้นส่วนอื่น: y local อยู่ในระนาบดิ่ง → z = x × Y แล้ว normalize
        z = (x[1] * 0 - x[2] * 1, x[2] * 0 - x[0] * 0, x[0] * 1 - x[1] * 0)
        n = math.sqrt(sum(c * c for c in z))
        z = tuple(c / n for c in z)
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    beta = math.radians(model.beta.get(m, 0.0))
    if beta:
        c, s = math.cos(beta), math.sin(beta)
        y, z = (tuple(c * y[i] + s * z[i] for i in range(3)), tuple(-s * y[i] + c * z[i] for i in range(3)))
    return x, y, z


def model_figure(model, load=None, highlight=None, member_ids=True, joint_ids=False, height=620):
    fig = go.Figure()
    cols = set(model.columns())
    for group, color, width, name in ((cols, COL, 7, "เสา"), (set(model.members) - cols, BEAM, 5, "คาน")):
        xs, ys, zs, tx = [], [], [], []
        for m in sorted(group):
            a, b = model.members[m]
            pa, pb = _m(model.joints[a]), _m(model.joints[b])
            YD, ZD = model.prism.get(m, (0, 0))
            info = (f"member {m}<br>{a} → {b}<br>L = {model.length(m) / 1000:.3f} m<br>"
                    f"YD × ZD = {YD:.0f} × {ZD:.0f} mm" + (f"<br>β = {model.beta[m]:g}°" if m in model.beta else ""))
            for p in (pa, pb):
                xs.append(p[0]); ys.append(p[1]); zs.append(p[2]); tx.append(info)
            xs.append(None); ys.append(None); zs.append(None); tx.append(None)
        fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=color, width=width),
                                   name=name, hovertext=tx, hoverinfo="text"))
    if highlight in model.members:
        a, b = model.members[highlight]
        pa, pb = _m(model.joints[a]), _m(model.joints[b])
        fig.add_trace(go.Scatter3d(x=[pa[0], pb[0]], y=[pa[1], pb[1]], z=[pa[2], pb[2]], mode="lines",
                                   line=dict(color=HL, width=14), name=f"member {highlight}", hoverinfo="skip"))
        ax = local_axes(model, highlight)
        mid = [(pa[i] + pb[i]) / 2 for i in range(3)]
        span = max(model.length(highlight) / 1000 * 0.35, 0.6)
        for v, lab, c in zip(ax, ("x", "y", "z"), ("#111", "#1e8449", "#7d3c98")):
            e = [mid[i] + v[i] * span for i in range(3)]
            fig.add_trace(go.Scatter3d(x=[mid[0], e[0]], y=[mid[1], e[1]], z=[mid[2], e[2]], mode="lines+text",
                                       line=dict(color=c, width=6), text=["", f"{lab} local"],
                                       textfont=dict(color=c, size=14), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Cone(x=[e[0]], y=[e[1]], z=[e[2]], u=[v[0]], v=[v[1]], w=[v[2]], sizemode="absolute",
                                  sizeref=span * 0.25, anchor="tip", colorscale=[[0, c], [1, c]], showscale=False,
                                  hoverinfo="skip"))
    J = {j: _m(p) for j, p in model.joints.items()}
    fig.add_trace(go.Scatter3d(x=[p[0] for p in J.values()], y=[p[1] for p in J.values()],
                               z=[p[2] for p in J.values()], mode="markers+text" if joint_ids else "markers",
                               marker=dict(size=2.5, color="#333"), text=[f"N{j}" for j in J],
                               textfont=dict(size=10, color="#666"), name="joint",
                               hovertext=[f"joint {j}<br>({p[0]:g}, {p[1]:g}, {p[2]:g}) m" for j, p in J.items()],
                               hoverinfo="text"))
    if model.supports:
        S = [J[j] for j in model.supports if j in J]
        fig.add_trace(go.Scatter3d(x=[p[0] for p in S], y=[p[1] for p in S], z=[p[2] for p in S],
                                   mode="markers", marker=dict(size=7, symbol="square", color="#7f8c8d"),
                                   name="ฐานรองรับ", hovertext=[f"{model.supports[j]} @ N{j}" for j in model.supports],
                                   hoverinfo="text"))
    if member_ids:
        mids = {m: [(J[a][i] + J[b][i]) / 2 for i in range(3)] for m, (a, b) in model.members.items()}
        fig.add_trace(go.Scatter3d(x=[p[0] for p in mids.values()], y=[p[1] for p in mids.values()],
                                   z=[p[2] for p in mids.values()], mode="text", text=[str(m) for m in mids],
                                   textfont=dict(size=11, color=[COL if m in cols else BEAM for m in mids]),
                                   showlegend=False, hoverinfo="skip"))
    if load is not None and load in model.loads:
        _draw_load(fig, model, load, J)
    xs = [p[0] for p in J.values()]
    ys = [p[1] for p in J.values()]
    zs = [p[2] for p in J.values()]
    rng = [max(v) - min(v) or 1.0 for v in (xs, ys, zs)]
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.02, x=0),
        scene=dict(aspectmode="manual", aspectratio=dict(x=rng[0] / max(rng), y=max(rng[1] / max(rng), 0.25),
                                                           z=rng[2] / max(rng)),
                   xaxis_title="X (m)", yaxis_title="Y (m) ขึ้น", zaxis_title="Z (m)",
                   camera=dict(up=dict(x=0, y=1, z=0), eye=dict(x=0.75, y=0.55, z=0.95), center=dict(x=0, y=-0.1, z=0))))
    return fig


def _draw_load(fig, model, lid, J):
    """วาดน้ำหนักบรรทุกของ primary load (combo: วาดทุก primary ที่อยู่ใน combo)"""
    lc = model.loads[lid]
    prim = [lid] if lc.kind == "primary" else [k for k in model.expand(lid) if k in model.loads]
    X = [p[0] for p in J.values()]
    Z = [p[2] for p in J.values()]
    for k in prim:
        for it in model.loads[k].items:
            if it["type"] == "floor":
                r = it["range"]
                x0, x1 = (max(min(X), r["X"][0] / 1000), min(max(X), r["X"][1] / 1000)) if "X" in r else (min(X), max(X))
                z0, z1 = (max(min(Z), r["Z"][0] / 1000), min(max(Z), r["Z"][1] / 1000)) if "Z" in r else (min(Z), max(Z))
                y = sum(r["Y"]) / 2000 if "Y" in r else max(p[1] for p in J.values())
                w = abs(it["w"]) * 1e3      # N/mm² → kN/m²
                fig.add_trace(go.Mesh3d(x=[x0, x1, x1, x0], y=[y + 0.02] * 4, z=[z0, z0, z1, z1], i=[0, 0], j=[1, 2],
                                        k=[2, 3], color="#27ae60", opacity=0.25, name=f"LC{k} floor",
                                        hovertext=f"LOAD {k}: FLOOR LOAD {w:.3f} kN/m²", hoverinfo="text"))
                fig.add_trace(go.Scatter3d(x=[(x0 + x1) / 2], y=[y + 0.15], z=[(z0 + z1) / 2], mode="text",
                                           text=[f"LC{k}: {w:.2f} kN/m²"], textfont=dict(size=14, color="#1e8449"),
                                           showlegend=False, hoverinfo="skip"))
            elif it["type"] == "member" and it["member"] in model.members:
                a, b = model.members[it["member"]]
                pa, pb = J[a], J[b]
                d = {"GX": (1, 0, 0), "GY": (0, 1, 0), "GZ": (0, 0, 1), "PX": (1, 0, 0), "PY": (0, 1, 0),
                     "PZ": (0, 0, 1)}.get(it["dir"])
                if d is None:
                    continue
                sg = 1 if it["w"] >= 0 else -1
                pts = [[pa[i] + (pb[i] - pa[i]) * t for i in range(3)] for t in (0.2, 0.5, 0.8)]
                fig.add_trace(go.Cone(x=[p[0] for p in pts], y=[p[1] for p in pts], z=[p[2] for p in pts],
                                      u=[sg * d[0]] * 3, v=[sg * d[1]] * 3, w=[sg * d[2]] * 3, anchor="tip",
                                      sizemode="absolute", sizeref=0.35, showscale=False,
                                      colorscale=[[0, "#8e44ad"], [1, "#8e44ad"]],
                                      hovertext=f"LC{k} member {it['member']} {it['kind']} {it['dir']} "
                                                f"{it['w']:.3g} N/mm", hoverinfo="text"))
            elif it["type"] == "joint" and it["joint"] in J:
                p = J[it["joint"]]
                for c, d in (("FX", (1, 0, 0)), ("FY", (0, 1, 0)), ("FZ", (0, 0, 1))):
                    if it.get(c):
                        sg = 1 if it[c] > 0 else -1
                        fig.add_trace(go.Cone(x=[p[0]], y=[p[1]], z=[p[2]], u=[sg * d[0]], v=[sg * d[1]],
                                              w=[sg * d[2]], anchor="tip", sizemode="absolute", sizeref=0.5,
                                              showscale=False, colorscale=[[0, "#d35400"], [1, "#d35400"]],
                                              hovertext=f"LC{k} joint {it['joint']} {c} = {it[c] / 1e3:.3g} kN",
                                              hoverinfo="text"))


def column_level(model, m):
    """ระดับตีนเสา (mm) — ใช้แยกชั้นในผัง"""
    return round(model.joints[model.bottom_top(m)[0]][1], 1)


def plan_figure(model, highlight=None, height=460, level=None):
    """ผังมองจากด้านบน (ลงทิศ −Y): X ไปขวา, Z ลงล่าง — หน้าตัดเสาตามขนาดจริงและทิศ YD / ZD

    level: ระดับตีนเสา (mm) ของชั้นที่จะแสดง (None = ชั้นล่างสุด) — คานที่แสดงคือคานที่ระดับหัวเสาชั้นนั้น
    เสาแต่ละต้นมีจุดคลิกได้ (customdata = เลข member) สำหรับเลือกเสาด้วย st.plotly_chart(on_select=...)
    """
    fig = go.Figure()
    cols = model.columns()
    if not cols:
        return fig
    if level is None:
        level = min(column_level(model, m) for m in cols)
    here = [m for m in cols if abs(column_level(model, m) - level) < 1.0]
    tops = {round(model.joints[model.bottom_top(m)[1]][1], 1) for m in here}
    for m, (a, b) in model.members.items():
        if m in set(cols):
            continue
        pa, pb = model.joints[a], model.joints[b]
        if abs(pa[1] - pb[1]) > 1e-6 or not any(abs(pa[1] - t) < 1.0 for t in tops):
            continue                                   # ชิ้นส่วนเอียง หรือคานคนละชั้น
        pa, pb = _m(pa), _m(pb)
        # hoverinfo="skip": เส้นคานผ่านศูนย์กลางเสา ถ้าคลิกได้จะแย่งการคลิกเลือกเสา
        fig.add_trace(go.Scatter(x=[pa[0], pb[0]], y=[pa[2], pb[2]], mode="lines", line=dict(color=BEAM, width=2),
                                 hoverinfo="skip", showlegend=False))
        fig.add_annotation(x=(pa[0] + pb[0]) / 2, y=(pa[2] + pb[2]) / 2, text=str(m), showarrow=False,
                           font=dict(color=BEAM, size=11), bgcolor="white")
    xs, zs, ids, tips = [], [], [], []
    for m in sorted(here):
        lo, _ = model.bottom_top(m)
        x, _, z = _m(model.joints[lo])
        YD, ZD = (v / 1000 for v in model.prism.get(m, (300, 300)))
        _, yv, _ = local_axes(model, m)
        along_x = abs(yv[0]) >= abs(yv[2])            # YD ขนานแกนโลก X หรือ Z
        hx, hz = (YD / 2, ZD / 2) if along_x else (ZD / 2, YD / 2)
        hl = m == highlight
        fig.add_shape(type="rect", x0=x - hx, x1=x + hx, y0=z - hz, y1=z + hz,
                      fillcolor=HL if hl else "#f5b7b1", line=dict(color=COL, width=3 if hl else 1))
        fig.add_annotation(x=x + hx, y=z - hz, text=f"<b>{m}</b>", showarrow=False, xanchor="left",
                           yanchor="bottom", font=dict(color=COL, size=13))
        xs.append(x); zs.append(z); ids.append(m)
        tips.append(f"เสา {m} (คลิกเพื่อเลือก)<br>YD {YD * 1000:.0f} mm ขนาน {'X' if along_x else 'Z'}, "
                    f"ZD {ZD * 1000:.0f} mm")
    fig.add_trace(go.Scatter(x=xs, y=zs, mode="markers", customdata=ids, hovertext=tips, hoverinfo="text",
                             marker=dict(size=22, color=COL, opacity=0.15, symbol="square"), showlegend=False,
                             name="เสา"))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white",
                      xaxis=dict(title="X (m)", scaleanchor="y", showgrid=False, zeroline=False),
                      yaxis=dict(title="Z (m) (ลงล่าง)", autorange="reversed", showgrid=False, zeroline=False))
    return fig
