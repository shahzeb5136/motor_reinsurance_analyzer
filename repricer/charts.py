"""
Every figure in the app.

Charts return bare Plotly figures; the pages decide where they sit. Colour
and typography come from the registered template in :mod:`theme`, so nothing
here hard-codes a style beyond the semantic use of the palette.
"""
from __future__ import annotations

import math

import numpy as np
import plotly.graph_objects as go

from . import theme as T
from .distributions import Frequency, Severity, frequency_pmf
from .engine import Layer, SimResult


def _money_axis(fig, axis: str = "x", title: str | None = None):
    fmt = dict(tickprefix=T._cur(), tickformat="~s")
    if title:
        fmt["title"] = title
    (fig.update_xaxes if axis == "x" else fig.update_yaxes)(**fmt)
    return fig


def _empty(msg: str, height: int = 260) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, x=0.5, y=0.5,
                       xref="paper", yref="paper",
                       font=dict(size=13, color=T.MUTED))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=height)
    return fig


# ===========================================================================
#  Structure
# ===========================================================================
def risk_tower(layer: Layer, reference: float | None = None,
               height: int = 300) -> go.Figure:
    """The vertical risk tower: what the cedant keeps, what the layer takes,
    and what sits above it."""
    D, L = layer.attachment, layer.limit
    top = D + L
    ceiling = max(top * 1.35, (reference or 0) * 1.1, top + L * 0.35)

    bands = [
        ("Cedant retention", 0.0, D, T.RETAIN,
         f"Every loss up to {T.usd_short(D)} stays with the cedant"),
        ("Reinsurance layer", D, top, T.ACCENT,
         f"{T.usd_short(L)} xs {T.usd_short(D)} - the layer being priced"),
        ("Above the layer", top, ceiling, T.XS_BAND,
         f"Losses above {T.usd_short(top)} fall back to the cedant or a higher layer"),
    ]

    fig = go.Figure()
    for name, lo, hi, colour, hover in bands:
        fig.add_trace(go.Bar(
            x=[hi - lo], y=[""], base=[lo], orientation="h",
            name=name, marker=dict(color=colour, line=dict(color=T.INK, width=1.5)),
            hovertemplate=f"<b>{name}</b><br>{hover}<extra></extra>",
            width=0.42,
        ))

    for value, label in ((D, "attachment"), (top, "exhaustion")):
        fig.add_vline(x=value, line=dict(color=T.MUTED, width=1, dash="dot"))
        fig.add_annotation(
            x=value, y=0.62, yref="paper", text=f"<b>{T.usd_short(value)}</b><br>{label}",
            showarrow=False, font=dict(family=T.FONT_MONO, size=10.5, color=T.TEXT_DIM),
            bgcolor="rgba(11,14,19,.72)", borderpad=3, yanchor="bottom",
        )

    if reference:
        fig.add_vline(x=reference, line=dict(color=T.TEAL, width=1.4, dash="dash"))
        fig.add_annotation(
            x=reference, y=0.06, yref="paper",
            text=f"largest modelled claim<br><b>{T.usd_short(reference)}</b>",
            showarrow=False, font=dict(family=T.FONT_MONO, size=10, color=T.TEAL),
            bgcolor="rgba(11,14,19,.72)", borderpad=3, yanchor="bottom",
        )

    fig.update_layout(
        barmode="stack", height=height, showlegend=True,
        margin=dict(l=10, r=20, t=52, b=34),
    )
    fig.update_yaxes(showticklabels=False, showgrid=False)
    _money_axis(fig, "x", "Loss arising from a single claim")
    fig.update_xaxes(range=[0, ceiling])
    return fig


# ===========================================================================
#  Distributions
# ===========================================================================
def frequency_chart(freq: Frequency, height: int = 230) -> go.Figure:
    lo = max(0, int(freq.mean - 4.2 * freq.sd))
    hi = int(freq.mean + 4.2 * freq.sd) + 2
    step = max(1, (hi - lo) // 420)
    k = np.arange(lo, hi, step, dtype=float)
    pmf = frequency_pmf(freq, k)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=k, y=pmf, mode="lines", fill="tozeroy",
        line=dict(color=T.TEAL, width=2),
        fillcolor="rgba(76,181,174,.16)",
        hovertemplate="%{x:,.0f} claims<br>p = %{y:.5f}<extra></extra>",
        name="pmf",
    ))
    fig.add_vline(x=freq.mean, line=dict(color=T.ACCENT, width=1.2, dash="dot"))
    fig.add_annotation(
        x=freq.mean, y=1, yref="paper", yanchor="top",
        text=f"mean {freq.mean:,.0f}", showarrow=False,
        font=dict(family=T.FONT_MONO, size=10.5, color=T.ACCENT),
        bgcolor="rgba(11,14,19,.7)", borderpad=3,
    )
    fig.update_layout(height=height, showlegend=False,
                      margin=dict(l=10, r=16, t=30, b=34))
    fig.update_xaxes(title="Claims in a year", tickformat="~s")
    fig.update_yaxes(title="probability", showticklabels=False)
    return fig


def severity_chart(sev: Severity, attachment: float, top: float,
                   height: int = 300, show_components: bool = True) -> go.Figure:
    """Claim-size density on a log scale, with the layer shaded in.

    Log scale is not decoration: the whole point of an excess layer is that
    the claims that matter are orders of magnitude larger than the typical
    one, and a linear axis hides them completely.
    """
    lo = max(float(sev.quantile(0.005)), 1.0)
    hi = max(float(sev.quantile(0.9995)), top * 1.4)
    grid = np.geomspace(lo, hi, 600)

    def density(model: Severity) -> np.ndarray:
        # Density in log space: d/d(log x) F(x) = x f(x). Differencing the
        # exact CDF avoids needing a closed-form pdf for every family.
        cdf = np.asarray(model.cdf(grid), dtype=float)
        d = np.gradient(cdf, np.log(grid))
        return np.clip(d, 0, None)

    fig = go.Figure()

    comps = sev.components
    if show_components and comps:
        body, ext, p = comps["body"], comps["extreme"], comps["p"]
        fig.add_trace(go.Scatter(
            x=grid, y=(1 - p) * density(body), mode="lines",
            line=dict(color=T.RETAIN, width=1.6, dash="dot"),
            name=f"attritional body ({100 * (1 - p):.4g}%)",
            hovertemplate="%{x:$,.0f}<extra>body</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=grid, y=p * density(ext), mode="lines",
            line=dict(color=T.DANGER, width=1.6, dash="dot"),
            name=f"large-loss tail ({100 * p:.4g}%)",
            hovertemplate="%{x:$,.0f}<extra>tail</extra>",
        ))

    fig.add_trace(go.Scatter(
        x=grid, y=density(sev), mode="lines", fill="tozeroy",
        line=dict(color=T.ACCENT, width=2.2),
        fillcolor="rgba(232,163,61,.13)", name="blended severity",
        hovertemplate="claim %{x:$,.0f}<extra></extra>",
    ))

    fig.add_vrect(x0=attachment, x1=top, fillcolor="rgba(232,163,61,.09)",
                  line_width=0, layer="below")
    for value, label, colour in ((attachment, "attachment", T.DANGER),
                                 (top, "exhaustion", T.MUTED)):
        fig.add_vline(x=value, line=dict(color=colour, width=1.3, dash="dash"))
        fig.add_annotation(
            x=math.log10(max(value, 1.0)), y=1, yref="paper", yanchor="top",
            text=f"{label}<br><b>{T.usd_short(value)}</b>", showarrow=False,
            font=dict(family=T.FONT_MONO, size=10, color=colour),
            bgcolor="rgba(11,14,19,.75)", borderpad=3,
        )

    fig.update_layout(height=height, margin=dict(l=10, r=16, t=52, b=36))
    fig.update_xaxes(type="log", title="Claim size (log scale)",
                     tickprefix=T._cur(), tickformat="~s")
    fig.update_yaxes(title="relative frequency", showticklabels=False)
    return fig


def _log_density(model: Severity, grid: np.ndarray) -> np.ndarray:
    """Density with respect to log x, i.e. x·f(x).

    Differencing the exact CDF avoids needing a closed-form pdf for every
    family, and working in log space is what makes a distribution spanning
    four orders of magnitude readable at all.
    """
    cdf = np.asarray(model.cdf(grid), dtype=float)
    return np.clip(np.gradient(cdf, np.log(grid)), 0, None)


def component_density(model: Severity, colour: str, name: str,
                      attachment: float | None = None, top: float | None = None,
                      height: int = 300, subtitle: str = "") -> go.Figure:
    """One severity population plotted on its own scale.

    The blended chart necessarily shows the large-loss component scaled by its
    mixing weight, which for a share of a percent or so flattens it into the
    axis. Here it gets the full height of the panel, so its shape and its
    position relative to the layer are actually legible.
    """
    lo = max(float(model.quantile(0.002)), 1.0)
    hi = max(float(model.quantile(0.9995)), (top or 0.0) * 1.25, lo * 10)
    grid = np.geomspace(lo, hi, 600)
    dens = _log_density(model, grid)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=grid, y=dens, mode="lines", fill="tozeroy",
        line=dict(color=colour, width=2.2),
        fillcolor=_rgba(colour, 0.16), name=name,
        hovertemplate="claim %{x:$,.0f}<extra></extra>",
    ))

    if attachment is not None and top is not None and top > attachment:
        fig.add_vrect(x0=attachment, x1=top, fillcolor="rgba(232,163,61,.10)",
                      line_width=0, layer="below")
        for value, label, mark in ((attachment, "attachment", T.DANGER),
                                   (top, "exhaustion", T.MUTED)):
            if value < lo or value > hi:
                continue
            fig.add_vline(x=value, line=dict(color=mark, width=1.3, dash="dash"))
            fig.add_annotation(
                x=math.log10(max(value, 1.0)), y=1, yref="paper", yanchor="top",
                text=f"{label}<br><b>{T.usd_short(value)}</b>", showarrow=False,
                font=dict(family=T.FONT_MONO, size=10, color=mark),
                bgcolor="rgba(11,14,19,.78)", borderpad=3,
            )

    median = float(model.quantile(0.5))
    if lo <= median <= hi:
        fig.add_vline(x=median, line=dict(color=colour, width=1, dash="dot"))
        fig.add_annotation(
            x=math.log10(max(median, 1.0)), y=0.04, yref="paper", yanchor="bottom",
            text=f"median {T.usd_short(median)}", showarrow=False,
            font=dict(family=T.FONT_MONO, size=9.5, color=colour),
            bgcolor="rgba(11,14,19,.7)", borderpad=2,
        )

    fig.update_layout(
        height=height, showlegend=False, margin=dict(l=10, r=16, t=50, b=36),
        title=dict(text=subtitle or name,
                   font=dict(family=T.FONT_MONO, size=11.5, color=T.MUTED)),
    )
    fig.update_xaxes(type="log", title="Claim size (log scale)",
                     tickprefix=T._cur(), tickformat="~s")
    fig.update_yaxes(title="relative frequency", showticklabels=False)
    return fig


def _rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def claim_funnel(stages: list[tuple[str, float, str, str]],
                 height: int = 300) -> go.Figure:
    """How a year's claims narrow down to the ones the layer actually pays.

    Counts fall across several orders of magnitude, so the axis is
    logarithmic; the annotation on each bar carries the real number.
    """
    labels = [s[0] for s in stages]
    values = [max(s[1], 1e-9) for s in stages]
    colours = [s[2] for s in stages]
    notes = [s[3] for s in stages]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels[::-1], x=values[::-1], orientation="h",
        marker=dict(color=colours[::-1], line=dict(color=T.INK, width=1)),
        text=[_count_label(v) for v in values[::-1]],
        textposition="outside",
        textfont=dict(family=T.FONT_MONO, size=11.5, color=T.TEXT),
        cliponaxis=False,          # keep the top bar's label off the axis edge
        customdata=notes[::-1],
        hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
    ))
    fig.update_layout(height=height, showlegend=False,
                      margin=dict(l=10, r=96, t=42, b=38), bargap=0.32)

    # Leave a decade of headroom to the right so the outside labels have
    # somewhere to sit, and a floor below the smallest bar so it stays visible.
    lo = max(min(values), 1e-4)
    hi = max(values)
    fig.update_xaxes(type="log", title="Claims per year (log scale)",
                     range=[math.log10(lo) - 0.6, math.log10(hi) + 0.9])
    fig.update_yaxes(tickfont=dict(size=11, color=T.TEXT_DIM))
    return fig


def _count_label(v: float) -> str:
    if v >= 100:
        return f"  {v:,.0f}"
    if v >= 1:
        return f"  {v:,.1f}"
    if v >= 0.01:
        return f"  {v:.2f}  (1 in {1 / v:,.0f} yrs)"
    if v > 0:
        return f"  1 in {1 / v:,.0f} yrs"
    return "  never"


def exceedance_by_claim(sev: Severity, attachment: float, top: float,
                        height: int = 280) -> go.Figure:
    """P(a single claim exceeds x) - the curve that decides whether a layer
    is ever reached."""
    lo = max(float(sev.quantile(0.5)), 1.0)
    hi = max(top * 3.0, float(sev.quantile(0.99999)))
    grid = np.geomspace(lo, hi, 500)
    sf = np.asarray(sev.sf(grid), dtype=float)
    sf = np.clip(sf, 1e-12, 1.0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=grid, y=sf, mode="lines", line=dict(color=T.ACCENT, width=2.2),
        hovertemplate="claim > %{x:$,.0f}<br>p = %{y:.3e}<extra></extra>",
        name="P(claim > x)",
    ))
    for value, label, colour in ((attachment, "attachment", T.DANGER),
                                 (top, "exhaustion", T.MUTED)):
        fig.add_vline(x=value, line=dict(color=colour, width=1.2, dash="dash"))
    p_attach = float(sev.sf(attachment))
    fig.add_trace(go.Scatter(
        x=[attachment], y=[max(p_attach, 1e-12)], mode="markers+text",
        marker=dict(color=T.DANGER, size=9, line=dict(color=T.INK, width=1.5)),
        text=[f"  1 in {1 / p_attach:,.0f} claims" if p_attach > 0 else ""],
        textposition="middle right", textfont=dict(family=T.FONT_MONO, size=11, color=T.DANGER),
        hovertemplate=f"P(claim > attachment) = {p_attach:.3e}<extra></extra>",
        showlegend=False,
    ))
    fig.update_layout(height=height, showlegend=False,
                      margin=dict(l=10, r=16, t=34, b=36))
    fig.update_xaxes(type="log", title="Claim size (log scale)",
                     tickprefix=T._cur(), tickformat="~s")
    fig.update_yaxes(type="log", title="P(single claim exceeds)", tickformat=".0e")
    return fig


# ===========================================================================
#  Results
# ===========================================================================
def loss_histogram(result: SimResult, height: int = 320,
                   markers: bool = True) -> go.Figure:
    x = result.layer_loss
    nz = x[x > 1e-6]
    fig = go.Figure()

    if nz.size == 0:
        return _empty("The layer was never hit in any simulated year.", height)

    fig.add_trace(go.Histogram(
        x=nz, nbinsx=70, marker=dict(color=T.ACCENT, line=dict(width=0)),
        opacity=.72, name="years with a layer loss",
        hovertemplate="%{x:$,.0f}<br>%{y:,} years<extra></extra>",
    ))

    # Structural reference lines. The mass sitting exactly on one full limit,
    # and the years reaching past it, are the two things readers most often
    # misread - a per-occurrence limit does not cap the year, because the
    # reinstatements let the layer respond again to a second large claim.
    layer = result.layer
    limit, cap = layer.limit, layer.aggregate_cap
    hi = float(nz.max())
    structure = [(limit, "one full limit")]
    if math.isfinite(cap) and cap > limit * 1.001:
        structure.append((cap, "annual cap"))
    for value, label in structure:
        if value <= 0 or value > hi * 1.08:
            continue
        fig.add_vline(x=value, line=dict(color=T.XS_BAND, width=1.2, dash="dot"))
        fig.add_annotation(
            x=value, y=0.02, yref="paper", yanchor="bottom",
            text=f"{label}<br><b>{T.usd_short(value)}</b>", showarrow=False,
            font=dict(family=T.FONT_MONO, size=9.5, color=T.XS_BAND),
            bgcolor="rgba(11,14,19,.82)", borderpad=3,
        )

    if markers:
        marks = [
            (result.burning_cost, "expected", T.TEAL),
            (result.rp(100), "1-in-100", T.ACCENT_HI),
            (result.rp(250), "1-in-250", T.DANGER),
        ]
        for value, label, colour in marks:
            if value <= 0:
                continue
            fig.add_vline(x=value, line=dict(color=colour, width=1.5, dash="dash"))
            fig.add_annotation(
                x=value, y=1, yref="paper", yanchor="top",
                text=f"{label}<br><b>{T.usd_short(value)}</b>", showarrow=False,
                font=dict(family=T.FONT_MONO, size=10, color=colour),
                bgcolor="rgba(11,14,19,.78)", borderpad=3,
            )

    multi = float((result.n_pierce >= 2).mean())
    caption = (f"{T.pct(result.p_pay)} of years produce a loss to the layer"
               f"  ·  {T.pct(1.0 - result.p_pay)} are clean")
    if multi > 0.0005:
        caption += f"  ·  {T.pct(multi)} see two or more qualifying claims"

    fig.update_layout(
        height=height, showlegend=False, margin=dict(l=10, r=16, t=54, b=36),
        title=dict(text=caption,
                   font=dict(family=T.FONT_MONO, size=11.5, color=T.MUTED)),
    )
    _money_axis(fig, "x", "Total loss to the layer across the whole year")
    fig.update_yaxes(title="simulated years")
    return fig


def ep_curve(result: SimResult, height: int = 320,
             compare: SimResult | None = None) -> go.Figure:
    """Exceedance probability: how likely is a layer loss of at least x."""
    fig = go.Figure()

    def add(res: SimResult, colour: str, name: str):
        loss, ep = res.ep_curve()
        keep = loss > 0
        fig.add_trace(go.Scatter(
            x=loss[keep], y=ep[keep], mode="lines",
            line=dict(color=colour, width=2.2), name=name,
            hovertemplate="loss >= %{x:$,.0f}<br>p = %{y:.3%}<extra>" + name + "</extra>",
        ))

    add(result, T.ACCENT, result.label)
    if compare is not None:
        add(compare, T.DANGER, compare.label)

    rps = [5, 10, 25, 50, 100, 250]
    xs, ys, txt = [], [], []
    for rp in rps:
        v = result.rp(rp)
        if v > 0:
            xs.append(v)
            ys.append(1.0 / rp)
            txt.append(f" 1-in-{rp}")
    if xs:
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text", text=txt, textposition="middle right",
            marker=dict(color=T.TEXT, size=6, line=dict(color=T.INK, width=1)),
            textfont=dict(family=T.FONT_MONO, size=10, color=T.MUTED),
            showlegend=False,
            hovertemplate="%{text}: %{x:$,.0f}<extra></extra>",
        ))

    fig.update_layout(height=height, margin=dict(l=10, r=16, t=46, b=36),
                      showlegend=compare is not None)
    _money_axis(fig, "x", "Annual loss to the layer")
    # ".3~%" keeps the deep tail legible: 0.004 renders as "0.4%" rather than
    # collapsing to a column of identical "0.0%" labels.
    fig.update_yaxes(type="log", title="P(loss exceeded)", tickformat=".3~%")
    return fig


def loss_waterfall(result: SimResult, height: int = 300) -> go.Figure:
    """Where the ground-up loss ends up: retained below, ceded to the layer,
    and retained again above."""
    gu = result.gu_mean
    ceded_raw = float(result.ceded_raw.mean())
    ceded = result.burning_cost
    below = max(gu - ceded_raw, 0.0)
    clipped = max(ceded_raw - ceded, 0.0)

    rows = [
        ("Retained below attachment", below, T.RETAIN),
        ("Ceded to the layer", ceded, T.ACCENT),
        ("Cut off by aggregate cap / AAD", clipped, T.DANGER),
    ]
    rows = [r for r in rows if r[1] > 0]

    fig = go.Figure()
    for name, value, colour in rows:
        fig.add_trace(go.Bar(
            x=[value], y=["annual"], orientation="h", name=name,
            marker=dict(color=colour, line=dict(color=T.INK, width=1)),
            text=[T.usd_short(value)], textposition="inside",
            insidetextfont=dict(family=T.FONT_MONO, size=11, color=T.INK),
            hovertemplate=f"<b>{name}</b><br>%{{x:$,.0f}} per year"
                          f"<br>{value / gu:.1%} of ground-up<extra></extra>" if gu > 0 else None,
        ))

    fig.update_layout(
        barmode="stack", height=height, margin=dict(l=10, r=16, t=54, b=36),
        title=dict(text=f"Expected ground-up loss {T.usd_short(gu)} per year"
                        f"  ·  {T.pct(ceded / gu) if gu > 0 else '-'} reaches the layer",
                   font=dict(family=T.FONT_MONO, size=11.5, color=T.MUTED)),
    )
    fig.update_yaxes(showticklabels=False, showgrid=False)
    _money_axis(fig, "x", "Expected annual loss")
    return fig


def convergence_chart(result: SimResult, height: int = 260) -> go.Figure:
    """Running estimate of the expected loss with its 95% band - the honest
    answer to 'have you run enough simulations?'."""
    idx, means, half = result.convergence()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=np.concatenate([idx, idx[::-1]]),
        y=np.concatenate([means + half, (means - half)[::-1]]),
        fill="toself", fillcolor="rgba(232,163,61,.13)",
        line=dict(width=0), hoverinfo="skip", name="95% interval",
    ))
    fig.add_trace(go.Scatter(
        x=idx, y=means, mode="lines", line=dict(color=T.ACCENT, width=2),
        name="running estimate",
        hovertemplate="%{x:,} years<br>%{y:$,.0f}<extra></extra>",
    ))
    fig.add_hline(y=result.burning_cost, line=dict(color=T.TEAL, width=1.2, dash="dot"))
    fig.update_layout(height=height, margin=dict(l=10, r=16, t=44, b=36), showlegend=False)
    fig.update_xaxes(type="log", title="simulated years")
    _money_axis(fig, "y", "expected layer loss")
    return fig


def premium_waterfall(steps, height: int = 320) -> go.Figure:
    """Expected loss to technical premium, one loading at a time."""
    labels = [s[0] for s in steps]
    values = [s[1] for s in steps]
    kinds = [s[2] for s in steps]
    measures = ["absolute" if k in ("start", "total") else "relative" for k in kinds]

    fig = go.Figure(go.Waterfall(
        orientation="v", measure=measures, x=labels, y=values,
        text=[T.usd_short(v) for v in values],
        textposition="outside",
        textfont=dict(family=T.FONT_MONO, size=11, color=T.TEXT_DIM),
        connector=dict(line=dict(color=T.LINE, width=1)),
        increasing=dict(marker=dict(color=T.XS_BAND)),
        decreasing=dict(marker=dict(color=T.TEAL)),
        totals=dict(marker=dict(color=T.ACCENT)),
        hovertemplate="%{x}<br>%{y:$,.0f}<extra></extra>",
    ))
    fig.update_layout(height=height, margin=dict(l=10, r=16, t=34, b=70), showlegend=False)
    fig.update_xaxes(tickangle=-22, tickfont=dict(size=10.5))
    _money_axis(fig, "y")
    return fig


# ===========================================================================
#  What-if
# ===========================================================================
def stress_ecdf(base: SimResult, stressed: SimResult, height: int = 320) -> go.Figure:
    fig = go.Figure()
    for res, colour, name in ((base, T.TEAL, "Base case"), (stressed, T.DANGER, "Stressed")):
        x = np.sort(res.layer_loss)
        keep = np.unique(np.linspace(0, x.size - 1, 1200).astype(int))
        fig.add_trace(go.Scatter(
            x=x[keep], y=(keep + 1) / x.size, mode="lines",
            line=dict(color=colour, width=2.2), name=name,
            hovertemplate="loss <= %{x:$,.0f}<br>%{y:.1%} of years<extra>" + name + "</extra>",
        ))
    fig.update_layout(height=height, margin=dict(l=10, r=16, t=46, b=36))
    _money_axis(fig, "x", "Annual loss to the layer")
    fig.update_yaxes(title="cumulative probability", tickformat=".0%", range=[0, 1.02])
    return fig


def tornado(rows: list[tuple[str, float, float]], base: float,
            height: int = 340) -> go.Figure:
    """Sensitivity of the technical premium to each driver.

    ``rows`` is (driver, premium at low setting, premium at high setting).
    """
    rows = sorted(rows, key=lambda r: abs(r[2] - r[1]))
    labels = [r[0] for r in rows]
    lows = [r[1] - base for r in rows]
    highs = [r[2] - base for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=lows, orientation="h", name="downside",
        marker=dict(color=T.TEAL), hovertemplate="%{y}<br>%{x:+$,.0f}<extra>low</extra>",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=highs, orientation="h", name="upside",
        marker=dict(color=T.DANGER), hovertemplate="%{y}<br>%{x:+$,.0f}<extra>high</extra>",
    ))
    fig.add_vline(x=0, line=dict(color=T.MUTED, width=1.2))
    fig.update_layout(
        barmode="overlay", height=height, margin=dict(l=10, r=16, t=46, b=40),
        bargap=0.35,
    )
    fig.update_xaxes(title=f"Change in technical premium (base {T.usd_short(base)})",
                     tickprefix=T._cur(), tickformat="~s")
    fig.update_yaxes(tickfont=dict(size=11))
    return fig


def layer_ladder(rows, height: int = 330) -> go.Figure:
    """Rate on line against attachment point - how the market curve behaves
    as you move up the tower."""
    xs = [r["attachment"] for r in rows]
    rol = [r["rate_on_line"] for r in rows]
    lol = [r["loss_on_line"] for r in rows]
    sel = [r for r in rows if r.get("selected")]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=rol, mode="lines+markers", name="rate on line",
        line=dict(color=T.ACCENT, width=2.4),
        marker=dict(size=6, line=dict(color=T.INK, width=1)),
        hovertemplate="xs %{x:$,.0f}<br>ROL %{y:.2%}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=xs, y=lol, mode="lines+markers", name="loss on line",
        line=dict(color=T.TEAL, width=1.8, dash="dot"),
        marker=dict(size=5),
        hovertemplate="xs %{x:$,.0f}<br>LOL %{y:.2%}<extra></extra>",
    ))
    if sel:
        fig.add_trace(go.Scatter(
            x=[sel[0]["attachment"]], y=[sel[0]["rate_on_line"]],
            mode="markers", marker=dict(size=13, color="rgba(0,0,0,0)",
                                        line=dict(color=T.TEXT, width=2)),
            name="this layer", hovertemplate="selected layer<extra></extra>",
        ))
    fig.update_layout(height=height, margin=dict(l=10, r=16, t=46, b=40))
    _money_axis(fig, "x", "Attachment point")
    fig.update_yaxes(title="share of limit", tickformat=".0%", type="log")
    return fig
