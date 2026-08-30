"""Page 5 - from expected loss to a quotable premium."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import streamlit as st

from repricer import charts, components as C, state as S
from repricer.engine import Layer, run_simulation
from repricer.pricing import (Loadings, alternative_prices, premium_build_up,
                              price_layer, quote_diagnostics)
from repricer.theme import mult, num, pct, usd, usd_short, years


def render() -> None:
    C.page_title(
        "05", "Pricing",
        "The expected loss is the floor. Capital, expenses, brokerage and "
        "reinstatement income turn it into a number you could quote.",
    )
    C.guide("pricing")

    res = S.result()
    if res is None:
        C.needs_run()
        return

    loadings = S.current_loadings()
    share = float(st.session_state["share"]) / 100.0
    quote = price_layer(res, loadings, subject_premium=float(st.session_state["gep"]),
                        share=share)
    layer = res.layer

    # ------------------------------------------------------------- headline
    C.kpi_row([
        dict(label="Technical premium (100%)", value=usd_short(quote.technical_premium),
             tone="accent", sub="per year, before market adjustment"),
        dict(label="Rate on line", value=pct(quote.rate_on_line),
             tone="", sub=f"loss on line {pct(quote.loss_on_line)}"),
        dict(label="Expected loss ratio", value=pct(quote.expected_loss_ratio),
             tone="teal", sub="claims ÷ total expected income"),
        dict(label=f"Signed premium at {pct(share, 0)}",
             value=usd_short(quote.signed_premium), tone="good",
             sub=f"expected loss {usd_short(quote.signed_expected_loss)}"),
    ])

    C.gap()
    left, right = st.columns([1, 1.35], gap="large")

    # ------------------------------------------------------------- loadings
    with left:
        C.section("Loadings")
        C.note(
            "These move the price without re-running the simulation — the loss "
            "distribution does not depend on them."
        )
        a, b = st.columns(2)
        with a:
            st.number_input("Internal expense (%)", key="expense_ratio",
                            min_value=0.0, max_value=60.0, step=0.5,
                            help="The reinsurer's own cost of writing and servicing "
                                 "the contract, as a share of premium.")
        with b:
            st.number_input("Brokerage (%)", key="brokerage", min_value=0.0,
                            max_value=60.0, step=0.5,
                            help="Broker commission and ceding commission, as a "
                                 "share of premium.")
        a, b = st.columns(2)
        with a:
            st.number_input("Cost of capital (%)", key="cost_of_capital",
                            min_value=0.0, max_value=60.0, step=0.5,
                            help="The return the reinsurer requires on the capital "
                                 "this layer ties up.")
        with b:
            st.number_input("Diversification credit (%)", key="diversification",
                            min_value=1.0, max_value=100.0, step=5.0,
                            help="Share of the layer's standalone capital that is "
                                 "actually allocated once it sits inside a "
                                 "diversified portfolio. 100% would treat the layer "
                                 "as the reinsurer's only contract.")
        st.slider("Capital measured at TVaR (%)", key="capital_percentile",
                  min_value=90.0, max_value=99.9, step=0.1, format="%.1f%%",
                  help="The tail level that defines how much capital the layer "
                       "absorbs. It should sit beyond the point at which the layer "
                       "starts attaching, or it measures mostly clean years.")

        C.gap(small=True)
        C.ledger([
            ("Standalone capital (TVaR less EL)", usd_short(quote.standalone_capital)),
            ("Allocated after diversification", usd_short(quote.capital), "accent"),
            ("Annual charge on that capital", usd_short(quote.capital_charge)),
            ("Expected reinstatement income", usd_short(quote.reinstatement_income), "good"),
            ("Limits reinstated per year", f"{quote.reinstatements_used:.2f}"),
        ])

    # -------------------------------------------------------------- buildup
    with right:
        C.section("Premium build-up")
        C.chart(charts.premium_waterfall(premium_build_up(quote)), key="pwf")
        C.note(
            f"Every figure here is <b>per year</b>, not per claim. The expected annual "
            f"loss of {usd_short(quote.expected_loss)} is what the layer costs in an "
            f"average year across all "
            f"{float(st.session_state['n_claims']):,.0f} claims — roughly "
            f"{res.expected_claims_to_layer:.2f} of them reach the layer in a year, at "
            f"about {usd_short(res.burning_cost / res.expected_claims_to_layer)} each "
            f"when they do. Added to it: the cost of capital held against a bad year, "
            f"expenses and brokerage; less the reinstatement premium the contract earns "
            f"back when losses restore the limit, which is income the reinsurer expects "
            f"to collect."
            if res.expected_claims_to_layer > 0 else
            "Expected loss, plus the cost of the capital held against a bad year, plus "
            "expenses and brokerage, less the reinstatement premium the contract earns "
            "back when losses restore the limit."
        )

    # ---------------------------------------------------------- diagnostics
    diags = quote_diagnostics(res, quote, loadings)
    if diags:
        C.gap(small=True)
        C.section("Model integrity")
        C.flags(diags)

    # ---------------------------------------------------------- the numbers
    C.gap()
    a, b, c = st.columns([1, 1, 1], gap="large")
    with a:
        C.section("Quote summary")
        cap = layer.aggregate_cap
        C.ledger([
            ("Layer", f"{usd_short(layer.limit)} xs {usd_short(layer.attachment)}"),
            ("Reinstatements",
             "unlimited" if math.isinf(layer.reinstatements)
             else f"{layer.reinstatements:g} @ {pct(layer.reinstatement_cost, 0)}"),
            ("Expected annual loss", usd_short(quote.expected_loss)),
            ("Technical premium", usd_short(quote.technical_premium), "accent"),
            ("Expected total income", usd_short(quote.total_income)),
            ("Expected underwriting profit", usd_short(quote.expected_profit), "good"),
            ("Signed premium", usd_short(quote.signed_premium), "total"),
        ])
    with b:
        C.section("Market metrics")
        C.ledger([
            ("Rate on line", pct(quote.rate_on_line), "accent"),
            ("Loss on line", pct(quote.loss_on_line)),
            ("Premium ÷ expected loss", mult(quote.premium_to_loss)),
            ("Expected loss ratio", pct(quote.expected_loss_ratio)),
            ("Payback period", years(quote.payback_years)),
            ("Rate on subject GEP", pct(quote.subject_premium_rate, 3)),
            ("Maximum annual recovery",
             "unlimited" if math.isinf(cap) else usd_short(cap)),
        ])
        C.note(
            "<b>Rate on line</b> is premium divided by limit — the market's shorthand "
            "for how expensive a layer is. <b>Payback</b> is how many years of premium "
            "it takes to fund one full limit; a layer with a 20-year payback needs to "
            "stay clean for a long time to be worth writing."
        )
    with c:
        C.section("Cross-checks")
        alts = alternative_prices(res, loadings)
        rows = [(k, usd_short(v)) for k, v in alts.items()]
        rows.append(("Technical premium (this model)",
                     usd_short(quote.technical_premium), "total"))
        C.ledger(rows)
        C.note(
            "Standard premium principles applied to the same loss distribution. They "
            "are not alternative quotes — they bracket the answer. A technical "
            "premium far outside this range usually means a loading is doing more "
            "work than intended."
        )

    # ------------------------------------------------------------ ladder
    C.gap()
    C.section("Where this layer sits on the curve")
    with st.spinner("Pricing neighbouring attachment points…"):
        ladder = _layer_ladder(res, loadings, share)
    if ladder:
        a, b = st.columns([1.3, 1], gap="large")
        with a:
            C.chart(charts.layer_ladder(ladder), key="ladder")
        with b:
            st.dataframe(_ladder_table(ladder), use_container_width=True,
                         hide_index=True, height=330)
        C.note(
            "The same book and the same limit, priced at a range of attachment "
            "points. Rate on line falls steeply as the attachment rises — but not as "
            "steeply as loss on line, because the capital load does not decay as "
            "fast as the expected loss. That widening gap is why high layers look "
            "expensive relative to their expected cost, and it is the single most "
            "common source of argument in a renewal."
        )

    # -------------------------------------------------------- exec summary
    C.gap()
    el_share = quote.expected_loss / quote.technical_premium if quote.technical_premium else 0
    C.exec_band([
        f"The claims this layer is expected to pay come to "
        f"<b>{usd_short(quote.expected_loss)}</b> a year. Nobody would write it for "
        f"that: {pct(1 - res.p_pay)} of years the layer pays nothing at all, and "
        f"occasionally it pays {usd_short(res.rp(250))} — the capital standing behind "
        f"that possibility has to earn a return. Adding "
        f"<b>{usd_short(quote.capital_charge)}</b> for capital, "
        f"<b>{usd_short(quote.expense + quote.brokerage)}</b> for expenses and "
        f"brokerage, and crediting back "
        f"<b>{usd_short(quote.reinstatement_income)}</b> of expected reinstatement "
        f"premium gives a technical premium of "
        f"<b>{usd_short(quote.technical_premium)}</b>.",
        f"That is {pct(quote.rate_on_line)} of the limit on offer, and "
        f"{mult(quote.premium_to_loss)} the expected claims cost. Roughly "
        f"<b>{pct(el_share)}</b> of the premium is paying for claims the model expects "
        f"to happen; the rest is the price of being wrong. It is a floor, not a "
        f"quote — the market clears where supply and demand put it, and this number "
        f"tells you whether the market price is worth taking.",
    ])


# ---------------------------------------------------------------------------
def _layer_ladder(res, loadings: Loadings, share: float) -> list[dict]:
    """Re-price the same limit at a spread of attachment points.

    Cheap because tail-thinned sampling means each point costs a fraction of
    a second, and it is the most informative single chart in the app.
    """
    base = res.layer
    if base.limit <= 0 or base.attachment <= 0:
        return []

    freq, sev = res.frequency, res.severity
    n = min(res.n_iter, 60_000)
    factors = (0.4, 0.6, 0.8, 1.0, 1.4, 2.0, 3.0, 4.5)
    rows: list[dict] = []

    for f in factors:
        attach = base.attachment * f
        layer = Layer(attachment=attach, limit=base.limit,
                      reinstatements=base.reinstatements,
                      reinstatement_cost=base.reinstatement_cost,
                      aad=base.aad, share=base.share)
        try:
            sim = run_simulation(freq, sev, layer, n, res.seed, mode="tail")
            q = price_layer(sim, loadings, share=share)
        except Exception:
            continue
        rows.append({
            "attachment": attach,
            "rate_on_line": q.rate_on_line,
            "loss_on_line": q.loss_on_line,
            "premium": q.technical_premium,
            "expected_loss": sim.burning_cost,
            "p_attach": sim.p_attach,
            "selected": abs(f - 1.0) < 1e-9,
        })
    return rows


def _ladder_table(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Attachment": usd_short(r["attachment"]) + ("  ←" if r["selected"] else ""),
        "P(attaches)": pct(r["p_attach"]),
        "Expected loss": usd_short(r["expected_loss"]),
        "Premium": usd_short(r["premium"]),
        "ROL": pct(r["rate_on_line"]),
    } for r in rows])
