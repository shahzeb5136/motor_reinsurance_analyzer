"""Page 6 - what breaks the price."""
from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from repricer import charts, components as C, narrative, state as S
from repricer.distributions import mixture
from repricer.engine import run_simulation
from repricer.pricing import price_layer
from repricer.theme import mult, pct, signed_pct, usd, usd_short


def render() -> None:
    C.page_title(
        "06", "What-if & sensitivity",
        "Every number in this model rests on assumptions. This page moves them and "
        "measures the damage.",
    )
    C.guide("whatif")

    res = S.result()
    if res is None:
        C.needs_run()
        return

    loadings = S.current_loadings()
    share = float(st.session_state["share"]) / 100.0
    base_quote = price_layer(res, loadings, share=share)

    # ------------------------------------------------------------- tornado
    C.section("Sensitivity of the technical premium")
    with st.spinner("Re-pricing under each driver…"):
        rows = _tornado_rows(res, loadings, share)
    if rows:
        a, b = st.columns([1.35, 1], gap="large")
        with a:
            C.chart(charts.tornado(rows, base_quote.technical_premium), key="tornado")
        with b:
            st.dataframe(_tornado_table(rows, base_quote.technical_premium),
                         use_container_width=True, hide_index=True, height=300)
        C.note(
            "Each driver moved on its own, holding everything else fixed. The bar "
            "length is what that assumption is worth to the price. Anything short is "
            "not worth arguing about; anything long deserves evidence."
        )
        top = max(rows, key=lambda r: abs(r[2] - r[1]))
        swing = abs(top[2] - top[1])
        base_premium = base_quote.technical_premium
        # Deliberately not called `share` - that name holds the signed line here.
        swing_share = (f" — {pct(swing / base_premium)} of the quoted number"
                       if base_premium > 0 else "")
        C.exec_band([
            f"The price of this layer is most sensitive to <b>{top[0].lower()}</b>. "
            f"Moving it across the range tested changes the technical premium by "
            f"<b>{usd_short(swing)}</b>{swing_share}. Everything else on this chart is "
            f"secondary. If there is one assumption to spend time validating before "
            f"binding, that is it."
        ], eyebrow="What this tells you")

    # ---------------------------------------------------------- stress run
    C.gap()
    C.section("Full stressed scenario")
    left, right = st.columns([1, 1.6], gap="large")

    with left:
        C.note(
            "Move several assumptions together and re-simulate the whole year. Same "
            "seed and same number of years as the base run, so the comparison is "
            "like for like."
        )
        st.slider("Claims inflation on severity (%)", key="stress_severity",
                  min_value=-25.0, max_value=75.0, step=1.0, format="%+.0f%%",
                  help="Scales every claim. Excess layers amplify this: inflation "
                       "pushes claims across the attachment as well as enlarging "
                       "the ones already above it.")
        st.slider("Change in claim frequency (%)", key="stress_frequency",
                  min_value=-25.0, max_value=75.0, step=1.0, format="%+.0f%%",
                  help="Scales the expected claim count, holding the contagion "
                       "parameter fixed.")
        st.slider("Uplift to the large-loss share (%)", key="stress_p_extreme_uplift",
                  min_value=-50.0, max_value=300.0, step=5.0, format="%+.0f%%",
                  help=f"Applied to the base share of {pct(S.extreme_share(), 2)}, so "
                       f"the lever always means 'more large claims than assumed'. "
                       f"Social inflation and litigation trends move the rate of "
                       f"large claims independently of average claim size.")
        uplifted = min(S.extreme_share() * (1 + float(st.session_state[
            "stress_p_extreme_uplift"]) / 100.0), 1.0)
        C.note(f"Large-loss share moves from <b>{pct(S.extreme_share(), 2)}</b> to "
               f"<b>{pct(uplifted, 2)}</b> of claims.")
        C.gap(small=True)
        go = st.button("Run stressed scenario", type="primary", use_container_width=True)
        slot = st.empty()
        if go:
            stressed = S.run_stress(slot)
            if stressed is None:
                st.error("Could not build the stressed severity model.")

    stressed = S.stress_result()

    with right:
        if stressed is None:
            C.flag("info", "Set the levers and press <b>Run stressed scenario</b>. "
                           "The comparison appears here.")
        else:
            stress_quote = price_layer(stressed, loadings, share=share)
            C.kpi_row([
                dict(label="Stressed expected loss",
                     value=usd_short(stressed.burning_cost), tone="danger",
                     delta=signed_pct(stressed.burning_cost / res.burning_cost - 1)
                     if res.burning_cost > 0 else "",
                     delta_dir="up" if stressed.burning_cost > res.burning_cost else "down",
                     sub=f"base {usd_short(res.burning_cost)}"),
                dict(label="Stressed technical premium",
                     value=usd_short(stress_quote.technical_premium), tone="accent",
                     delta=signed_pct(stress_quote.technical_premium
                                      / base_quote.technical_premium - 1)
                     if base_quote.technical_premium > 0 else "",
                     delta_dir="up" if stress_quote.technical_premium
                     > base_quote.technical_premium else "down",
                     sub=f"base {usd_short(base_quote.technical_premium)}"),
                dict(label="Stressed rate on line",
                     value=pct(stress_quote.rate_on_line), tone="",
                     sub=f"base {pct(base_quote.rate_on_line)}"),
            ])
            C.gap(small=True)
            C.chart(charts.stress_ecdf(res, stressed), key="stress_ecdf")

    if stressed is not None:
        C.gap()
        a, b = st.columns([1.2, 1], gap="large")
        with a:
            C.section("Base against stressed")
            st.dataframe(_comparison(res, stressed, base_quote,
                                     price_layer(stressed, loadings, share=share)),
                         use_container_width=True, hide_index=True, height=330)
        with b:
            C.section("Exceedance curves")
            C.chart(charts.ep_curve(res, compare=stressed), key="stress_ep")

        C.gap(small=True)
        levers = stressed.meta.get("levers", {})
        C.exec_band(narrative.stress_summary(
            S.build_context(res, base_quote), res, stressed, levers))


# ---------------------------------------------------------------------------
def _tornado_rows(res, loadings, share) -> list[tuple[str, float, float]]:
    """Re-price under a low and high setting for each driver.

    Structural drivers need a fresh simulation; loading drivers do not, so
    only the ones that change the loss distribution pay the simulation cost.
    """
    body = S.current_body()
    ext = S.current_extreme()
    p = S.extreme_share()
    freq = res.frequency
    layer = res.layer
    n = min(res.n_iter, 50_000)

    def sim_price(severity, frequency, sev_factor=1.0) -> float:
        sim = run_simulation(frequency, severity, layer, n, res.seed,
                             mode="tail", severity_factor=sev_factor)
        return price_layer(sim, loadings, share=share).technical_premium

    rows: list[tuple[str, float, float]] = []

    sev = res.severity
    rows.append(("Claims inflation ±15%",
                 sim_price(sev, freq, 0.85), sim_price(sev, freq, 1.15)))
    rows.append(("Claim frequency ±20%",
                 sim_price(sev, freq.scaled(0.8)), sim_price(sev, freq.scaled(1.2))))

    if ext is not None and p > 0:
        lo = mixture(body, ext, p * 0.6)
        hi = mixture(body, ext, p * 1.4)
        rows.append(("Large-loss share ±40%", sim_price(lo, freq), sim_price(hi, freq)))

        from repricer.distributions import build_severity
        alpha = float(st.session_state["ext_alpha"])
        soft = build_severity("Pareto", {"alpha": alpha + 0.3,
                                         "theta": float(st.session_state["ext_theta"])})
        hard = build_severity("Pareto", {"alpha": max(alpha - 0.3, 0.25),
                                         "theta": float(st.session_state["ext_theta"])})
        rows.append(("Tail shape alpha ±0.3",
                     sim_price(mixture(body, soft, p), freq),
                     sim_price(mixture(body, hard, p), freq)))

    # Loading drivers reuse the base simulation - no re-run needed.
    from repricer.pricing import Loadings
    base_l = loadings
    for label, lo_l, hi_l in (
        ("Cost of capital ±3pp",
         Loadings(**{**base_l.__dict__, "cost_of_capital": max(base_l.cost_of_capital - 0.03, 0)}),
         Loadings(**{**base_l.__dict__, "cost_of_capital": base_l.cost_of_capital + 0.03})),
        ("Diversification credit ±15pp",
         Loadings(**{**base_l.__dict__, "diversification": min(base_l.diversification + 0.15, 1.0)}),
         Loadings(**{**base_l.__dict__, "diversification": max(base_l.diversification - 0.15, 0.05)})),
    ):
        rows.append((label,
                     price_layer(res, lo_l, share=share).technical_premium,
                     price_layer(res, hi_l, share=share).technical_premium))
    return rows


def _tornado_table(rows, base: float) -> pd.DataFrame:
    out = []
    for label, lo, hi in sorted(rows, key=lambda r: -abs(r[2] - r[1])):
        out.append({
            "Driver": label,
            "Low": usd_short(lo),
            "High": usd_short(hi),
            "Swing": usd_short(abs(hi - lo)),
            "% of price": pct(abs(hi - lo) / base) if base > 0 else "—",
        })
    return pd.DataFrame(out)


def _comparison(base, stressed, base_quote, stress_quote) -> pd.DataFrame:
    def pp(a: float, b: float) -> str:
        return f"{(b - a) * 100:+.2f} pp"

    def rel(a: float, b: float) -> str:
        return f"{(b / a - 1) * 100:+.1f}%" if a > 0 else "—"

    rows = [
        ("Expected annual loss", usd_short(base.burning_cost),
         usd_short(stressed.burning_cost), rel(base.burning_cost, stressed.burning_cost)),
        ("Technical premium", usd_short(base_quote.technical_premium),
         usd_short(stress_quote.technical_premium),
         rel(base_quote.technical_premium, stress_quote.technical_premium)),
        ("Rate on line", pct(base_quote.rate_on_line), pct(stress_quote.rate_on_line),
         pp(base_quote.rate_on_line, stress_quote.rate_on_line)),
        ("P(layer pays)", pct(base.p_pay), pct(stressed.p_pay),
         pp(base.p_pay, stressed.p_pay)),
        ("P(exhaustion)", pct(base.p_exhaust), pct(stressed.p_exhaust),
         pp(base.p_exhaust, stressed.p_exhaust)),
        ("Claims reaching layer", f"{base.expected_claims_to_layer:.3f}",
         f"{stressed.expected_claims_to_layer:.3f}",
         rel(base.expected_claims_to_layer, stressed.expected_claims_to_layer)),
        ("1-in-100 year", usd_short(base.rp(100)), usd_short(stressed.rp(100)),
         rel(base.rp(100), stressed.rp(100))),
        ("1-in-250 year", usd_short(base.rp(250)), usd_short(stressed.rp(250)),
         rel(base.rp(250), stressed.rp(250))),
    ]
    return pd.DataFrame(rows, columns=["Measure", "Base", "Stressed", "Change"])
