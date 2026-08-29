"""Page 1 - the book being protected and the shape of the layer."""
from __future__ import annotations

import math

import streamlit as st

from repricer import charts, components as C, state as S
from repricer.theme import num, pct, usd, usd_short


def render() -> None:
    C.page_title(
        "01", "Portfolio & Layer",
        "Set the size of the book being reinsured and the slice of it this contract "
        "takes. Every figure downstream is anchored here.",
    )
    C.guide("portfolio")

    left, right = st.columns([1, 1], gap="large")

    # ---------------------------------------------------------------- book
    with left:
        C.section("The cedant's book")
        a, b = st.columns(2)
        with a:
            st.text_input("Cedant", key="cedant_name")
        with b:
            st.text_input("Programme", key="programme_name")

        C.money_m(
            "Gross earned premium", "gep", step=1.0,
            help="The subject premium the reinsurance applies to - the size of the "
                 "book being protected.",
        )
        a, b = st.columns(2)
        with a:
            st.number_input(
                "Expected ground-up loss ratio (%)", key="loss_ratio",
                min_value=0.0, max_value=400.0, step=1.0,
                help="Expected claims as a percentage of gross earned premium, "
                     "before any reinsurance.",
            )
        with b:
            st.number_input(
                "Expected claim count", key="n_claims", min_value=1.0, step=50.0,
                format="%.0f",
                help="How many claims the book is expected to produce in a year.",
            )

        gu = S.ground_up_loss()
        avg = S.implied_average_claim()
        C.gap(small=True)
        C.ledger([
            ("Expected ground-up loss", usd_short(gu), "accent"),
            ("Implied average claim", usd(avg), ""),
            ("Premium per claim", usd(float(st.session_state["gep"]) /
                                      max(float(st.session_state["n_claims"]), 1.0)), ""),
        ])

    # --------------------------------------------------------------- layer
    with right:
        C.section("Layer structure")
        a, b = st.columns(2)
        with a:
            C.money_m(
                "Attachment / retention", "attachment", step=0.25,
                on_change=S.invalidate_results,
                help="The cedant pays every claim up to this point. The layer only "
                     "responds above it.",
            )
        with b:
            C.money_m(
                "Limit", "limit", step=0.25, min_value=1.0,
                on_change=S.invalidate_results,
                help="The most the layer pays on any single claim, above the "
                     "attachment.",
            )

        a, b = st.columns(2)
        with a:
            st.number_input(
                "Reinstatements", key="reinstatements", min_value=0, max_value=20,
                step=1, on_change=S.invalidate_results,
                disabled=bool(st.session_state.get("unlimited_reinstatements")),
                help="How many times the limit is restored after being used up. "
                     "This caps what the layer can pay in a single year.",
            )
        with b:
            st.number_input(
                "Reinstatement cost (% pro rata)", key="reinstatement_cost",
                min_value=0.0, max_value=400.0, step=25.0,
                help="Additional premium charged when a reinstatement is used, as a "
                     "percentage of the deposit premium, pro rata to the amount "
                     "reinstated. 100% is the market standard.",
            )
        st.checkbox(
            "Unlimited reinstatements", key="unlimited_reinstatements",
            on_change=S.invalidate_results,
            help="No annual cap - the layer responds to every qualifying claim, "
                 "however many there are.",
        )

        with st.expander("Advanced structure — aggregate deductible, signed share"):
            a, b = st.columns(2)
            with a:
                C.money_m(
                    "Annual aggregate deductible", "aad", step=0.25,
                    on_change=S.invalidate_results,
                    help="An annual excess sitting on top of the per-claim "
                         "attachment. Ceded losses accumulate against it before "
                         "the layer pays anything.",
                )
            with b:
                st.number_input(
                    "Signed share (%)", key="share", min_value=0.0, max_value=100.0,
                    step=5.0,
                    help="The participation being written. The model always runs on "
                         "a 100% basis; this scales the result.",
                )

        layer = S.current_layer()
        cap = layer.aggregate_cap
        C.gap(small=True)
        C.ledger([
            ("Layer", f"{usd_short(layer.limit)} xs {usd_short(layer.attachment)}", "accent"),
            ("Exhausts at", usd_short(layer.top), ""),
            ("Annual aggregate cap",
             "unlimited" if math.isinf(cap) else usd_short(cap), ""),
            ("Maximum annual recovery at share",
             "unlimited" if math.isinf(cap) else usd_short(cap * layer.share), ""),
        ])

    # -------------------------------------------------------------- tower
    C.section("The risk tower")
    sev = S.current_severity()
    reference = None
    if sev is not None:
        try:
            reference = float(sev.quantile(1.0 - 1.0 / max(S.current_frequency().mean * 250, 2)))
        except Exception:
            reference = None

    fig = charts.risk_tower(S.current_layer(), reference=reference)
    C.chart(fig, key="tower")

    layer = S.current_layer()
    C.exec_band([
        f"Of every claim this book produces, the cedant absorbs the first "
        f"<b>{usd_short(layer.attachment)}</b>. This contract then pays the next "
        f"<b>{usd_short(layer.limit)}</b>, and stops. A claim of "
        f"{usd_short(layer.top * 1.25)} would see the reinsurer pay its full "
        f"{usd_short(layer.limit)} and the cedant pick up both the "
        f"{usd_short(layer.attachment)} underneath and the "
        f"{usd_short(layer.top * 0.25)} above.",
        f"Because ordinary motor claims average around <b>{usd(S.implied_average_claim())}</b>, "
        f"almost none of them come anywhere near the attachment. That is the point: "
        f"this contract is not buying protection against the everyday cost of claims, "
        f"it is buying protection against the rare severe one. Which means the price "
        f"depends almost entirely on how the rare severe claim is modelled - the "
        f"subject of the next page.",
    ])

    warnings = S.model_warnings()
    if warnings:
        C.section("Consistency checks")
        C.flags(warnings)
        if any(k == "warn" and "modelled average claim" in v for k, v in warnings):
            if st.button("Reconcile severity to the book", key="reconcile"):
                if S.reconcile_body_mean():
                    st.rerun()
                else:
                    st.warning("Reconciliation only applies to Lognormal and Gamma "
                               "bodies with a finite tail mean.")
