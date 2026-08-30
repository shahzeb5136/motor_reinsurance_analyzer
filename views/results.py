"""Page 4 - the loss distribution the simulation produced."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import streamlit as st

from repricer import charts, components as C, state as S
from repricer.pricing import classify_layer
from repricer.theme import mult, num, pct, usd, usd_short


def render() -> None:
    C.page_title(
        "04", "Results",
        "What the layer costs in an average year, and what it costs in the years that "
        "matter.",
    )
    C.guide("results")

    res = S.result()
    if res is None:
        C.needs_run()
        return
    if S.is_stale():
        _stale_banner()

    layer = res.layer
    level, kind, headline, explanation = classify_layer(res)

    # --------------------------------------------------------------- KPIs
    lo, hi = res.ci95
    C.kpi_row([
        dict(label="Expected annual loss", value=usd_short(res.burning_cost),
             tone="accent", sub=f"95% interval {usd_short(lo)} – {usd_short(hi)}"),
        dict(label="Probability the layer pays", value=pct(res.p_pay),
             tone="", sub=f"{res.expected_claims_to_layer:.2f} qualifying claims a year"),
        dict(label="1-in-100 year", value=usd_short(res.rp(100)),
             tone="teal", sub=f"{mult(res.rp(100) / res.burning_cost) if res.burning_cost else '—'} the average"),
        dict(label="1-in-250 year", value=usd_short(res.rp(250)),
             tone="danger", sub=f"TVaR {usd_short(res.rp_tvar(250))}"),
    ])

    C.gap()
    a, b = st.columns([1, 1], gap="large")
    with a:
        C.section("Distribution of the annual loss")
        C.chart(charts.loss_histogram(res), key="hist")
        C.note(_histogram_note(res))
    with b:
        C.section("Exceedance probability")
        C.chart(charts.ep_curve(res), key="ep")
        C.note(
            "Read it as: what is the chance of losing at least this much in a year. "
            "The vertical axis is logarithmic, so a straight line means the tail "
            "decays at a constant rate - the signature of a heavy-tailed severity."
        )

    # ----------------------------------------------------------- tail table
    C.gap()
    a, b = st.columns([1.15, 1], gap="large")
    with a:
        C.section("Return periods")
        st.dataframe(_tail_table(res), use_container_width=True, hide_index=True,
                     height=320)
        C.note(
            "<b>VaR</b> is the loss at that return period. <b>TVaR</b> is the average "
            "loss given you are that deep in the tail or worse - always the larger "
            "number, and the more useful one for capital, because it accounts for "
            "how bad things get beyond the threshold rather than stopping at it."
        )
    with b:
        C.section("Where the ground-up loss goes")
        C.chart(charts.loss_waterfall(res), key="wf")
        rows = [
            ("Expected ground-up loss", usd_short(res.gu_mean)),
            ("Retained below attachment", usd_short(max(res.gu_mean - float(res.ceded_raw.mean()), 0))),
            ("Ceded to this layer", usd_short(res.burning_cost), "accent"),
            ("Share of ground-up ceded",
             pct(res.burning_cost / res.gu_mean) if res.gu_mean > 0 else "—"),
        ]
        if res.cap_bite > 0.005:
            rows.insert(3, ("Cut off by annual cap / AAD",
                            usd_short(float(res.ceded_raw.mean()) - res.burning_cost),
                            "danger"))
        C.ledger(rows)
        if res.mode == "tail":
            C.note(
                "Ground-up loss is shown at its closed-form expectation "
                "(E[claims] × E[claim size]). Attritional claims are deliberately "
                "not simulated in tail-thinned mode because none of them can reach "
                "the layer. Switch to full sampling on page 3 to simulate them."
            )

    # --------------------------------------------------------- worst years
    C.gap()
    a, b = st.columns([1.3, 1], gap="large")
    with a:
        C.section("The ten worst simulated years")
        st.dataframe(_worst_years(res), use_container_width=True, hide_index=True,
                     height=330)
        C.note(
            "Each row is a single simulated underwriting year. They show what a bad "
            "year is actually made of - usually one very large claim rather than an "
            "unlucky accumulation of medium ones."
        )
    with b:
        C.section("Behaviour")
        C.verdict_badge(level, kind)
        C.gap(small=True)
        C.ledger([
            ("Probability of attaching", pct(res.p_attach)),
            ("Probability of paying", pct(res.p_pay)),
            (f"Probability a full {usd_short(res.layer.limit)} limit goes",
             pct(res.p_full_limit)),
            ("Probability of exhausting the annual cap", pct(res.p_exhaust),
             "danger" if res.p_exhaust > 0.15 else ""),
            ("Average loss when it pays", usd_short(res.mean_severity_to_layer)),
            ("Volatility (std dev)", usd_short(res.volatility)),
            ("Coefficient of variation", f"{res.cv:.2f}"),
            ("Limits reinstated per year", f"{res.expected_reinstatements_used:.2f}"),
        ])
        C.gap(small=True)
        C.note(explanation)

    # -------------------------------------------------------- exec summary
    C.gap()
    _exec_band(res)


def _histogram_note(res) -> str:
    """Explain the two features of this chart people reliably misread: the
    pile-up exactly on one limit, and the years sitting beyond it."""
    layer = res.layer
    limit, cap = layer.limit, layer.aggregate_cap
    at_limit = float((np.isclose(res.layer_loss, limit, atol=1.0)).mean())
    beyond = float((res.layer_loss > limit + 1.0).mean())

    note = (
        "Each bar is one simulated <b>year</b>, totalled across every claim in it. "
        "Only years in which the layer paid are plotted; the clean years would "
        "otherwise be a single bar swamping everything else."
    )
    if at_limit > 0.0005:
        note += (
            f" The spike on <b>{usd_short(limit)}</b> is the per-occurrence limit "
            f"biting: every claim above {usd_short(layer.top)} cedes exactly one "
            f"full limit and no more, however large it is, so the whole upper tail "
            f"of claim sizes lands on that one value ({pct(at_limit)} of years)."
        )
    if beyond > 0.0005 and math.isfinite(cap):
        note += (
            f" Years further right had <b>two or more</b> qualifying claims — the "
            f"limit is per claim, not per year, and the reinstatements let it be "
            f"restored and used again up to the {usd_short(cap)} annual cap "
            f"({pct(beyond)} of years)."
        )
    return note


def _stale_banner() -> None:
    C.flag("warn",
           "Assumptions have changed since this simulation ran. These figures are "
           "from the previous parameters.")
    if st.button("Recalculate now", type="primary", key="restale_results"):
        S.run_now(st.empty())
        st.rerun()


def _tail_table(res) -> pd.DataFrame:
    cap = res.layer.aggregate_cap
    rows = []
    for rp in (2, 5, 10, 20, 25, 50, 100, 200, 250, 500):
        if rp > res.n_iter / 20:
            continue
        var = res.rp(rp)
        rows.append({
            "Return period": f"1-in-{rp}",
            "Exceedance": pct(1 / rp, 2),
            "Layer loss (VaR)": usd_short(var),
            "Tail VaR": usd_short(res.rp_tvar(rp)),
            "% of aggregate cap": pct(var / cap) if math.isfinite(cap) and cap > 0 else "—",
        })
    return pd.DataFrame(rows)


def _worst_years(res) -> pd.DataFrame:
    order, loss, counts, pierces, largest, gu = res.worst_years(10)
    data = {
        "Sim year": [f"#{i + 1:,}" for i in order],
        "Loss to layer": [usd_short(v) for v in loss],
        "Claims > attachment": [int(v) for v in pierces],
        "Largest single claim": [usd_short(v) for v in largest],
    }
    if res.has_gu_distribution:
        data["Ground-up loss"] = [usd_short(v) for v in gu]
    else:
        data["Claims in year"] = [f"{int(v):,}" for v in counts]
    return pd.DataFrame(data)


def _exec_band(res) -> None:
    layer = res.layer
    bc = res.burning_cost
    rp100, rp250 = res.rp(100), res.rp(250)
    quiet = 1.0 - res.p_pay

    lines = [
        f"In an average year this layer costs <b>{usd_short(bc)}</b>. But that average "
        f"is misleading on its own, because <b>{pct(quiet)}</b> of years cost nothing "
        f"at all and the rest cost a great deal. When the layer does pay, the average "
        f"payment is <b>{usd_short(res.mean_severity_to_layer)}</b> — "
        f"{mult(res.mean_severity_to_layer / bc) if bc > 0 else '—'} the headline "
        f"average.",
    ]
    if rp250 > 0:
        lines.append(
            f"One year in a hundred costs at least <b>{usd_short(rp100)}</b>; one year "
            f"in 250 at least <b>{usd_short(rp250)}</b>. The reinsurer has to be able "
            f"to pay that in the year it happens, not on average across a career. "
            f"Holding capital against it is expensive, and that cost is a large part "
            f"of what separates the premium from the expected loss."
        )
    if res.p_exhaust > 0.05:
        lines.append(
            f"The limit is completely used up in <b>{pct(res.p_exhaust)}</b> of years. "
            f"Above that point the cover stops responding and the cedant is back on "
            f"risk — worth checking that is understood, because it is exactly when "
            f"they can least afford it."
        )
    C.exec_band(lines)
