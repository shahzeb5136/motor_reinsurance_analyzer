"""Page 3 - the Monte Carlo run itself."""
from __future__ import annotations

import math

import streamlit as st

from repricer import charts, components as C, state as S
from repricer.engine import analytic_check
from repricer.theme import num, pct, usd, usd_short

ITERATION_CHOICES = [10_000, 25_000, 50_000, 100_000, 250_000, 500_000]


def render() -> None:
    C.page_title(
        "03", "Simulation",
        "Play the underwriting year out tens of thousands of times and record what "
        "the layer pays each time.",
    )
    C.guide("simulation")

    sev = S.current_severity()
    freq = S.current_frequency()
    layer = S.current_layer()

    if sev is None:
        C.flag("danger", "Severity parameters are invalid — fix them on "
                         "<b>2 · Frequency & Severity</b> before running.")
        return

    left, right = st.columns([1, 1.25], gap="large")

    # ------------------------------------------------------------ controls
    with left:
        C.section("Run controls")
        st.select_slider(
            "Simulated years", options=ITERATION_CHOICES, key="n_iter",
            format_func=lambda v: f"{v:,}", on_change=S.invalidate_results,
            help="More years means a more precise answer. The standard error of "
                 "the expected loss falls with the square root of this number.",
        )
        a, b = st.columns([1, 1])
        with a:
            st.number_input("Random seed", key="seed", step=1, format="%d",
                            on_change=S.invalidate_results,
                            help="Fixing the seed makes the run reproducible.")
        with b:
            st.selectbox(
                "Sampling", ["tail", "full"], key="engine_mode",
                format_func=lambda m: {"tail": "Tail-thinned (fast)",
                                       "full": "Full ground-up"}[m],
                on_change=S.invalidate_results,
                help="Tail-thinned draws only the claims capable of reaching the "
                     "attachment, from the exact conditional distribution. Every "
                     "layer statistic is identical to the full run; ground-up loss "
                     "is reported from its closed form instead of simulated.",
            )

        q = float(sev.sf(layer.attachment))
        est_full = int(freq.mean * float(st.session_state["n_iter"]))
        est_tail = int(freq.mean * q * float(st.session_state["n_iter"]))
        mode = st.session_state["engine_mode"]

        draws = est_tail if mode == "tail" else est_full
        eta = draws / 27_000_000.0  # measured throughput on a typical laptop
        C.gap(small=True)
        C.ledger([
            ("Claims to draw", f"{draws:,}", "accent"),
            ("Claims avoided by thinning",
             f"{est_full - est_tail:,}" if mode == "tail" else "—",
             "good" if mode == "tail" else "muted"),
            ("Estimated run time",
             "under a second" if eta < 1 else f"about {eta:.0f}s",
             "good" if eta < 1 else "" if eta < 20 else "danger"),
        ])

        C.gap(small=True)
        run = st.button("Run pricing model", type="primary", use_container_width=True)
        slot = st.empty()

        if run:
            res = S.run_now(slot)
            if res is None:
                st.error("Could not build the severity model from these parameters.")
            else:
                st.success(
                    f"{res.n_iter:,} years simulated in {res.elapsed:.2f}s "
                    f"({res.meta.get('tail_draws', 0):,} claims drawn)."
                )

        res = S.result()
        if res is not None:
            C.gap(small=True)
            C.ledger([
                ("Last run", f"{res.n_iter:,} years · seed {res.seed}"),
                ("Elapsed", f"{res.elapsed:.2f}s"),
                ("Expected layer loss", usd_short(res.burning_cost), "accent"),
                ("95% Monte Carlo interval",
                 f"{usd_short(res.ci95[0])} – {usd_short(res.ci95[1])}"),
            ])
            if S.is_stale():
                C.flag("warn", "Assumptions have changed since this run. The results "
                               "pages are showing the earlier numbers until you run again.")

    # ------------------------------------------------------ what will run
    with right:
        C.section("What will run")
        cap = layer.aggregate_cap
        C.ledger([
            ("Frequency", freq.label),
            ("Severity", sev.label),
            ("Layer", f"{usd_short(layer.limit)} xs {usd_short(layer.attachment)}", "accent"),
            ("Aggregate cap", "unlimited" if math.isinf(cap) else usd_short(cap)),
            ("Annual aggregate deductible",
             usd_short(layer.aad) if layer.aad > 0 else "none"),
            ("P(single claim reaches layer)", f"{q:.4e}"),
        ])

        C.gap(small=True)
        C.section("Analytic control totals")
        C.note(
            "Before trusting a simulation, check it against something you can "
            "compute exactly. The expected cession per claim is the limited expected "
            "value at the top of the layer less the limited expected value at the "
            "attachment; multiplied by the expected claim count that gives the "
            "expected annual cession before any aggregate features. The simulation "
            "should land on this figure, within its own sampling error."
        )
        check = analytic_check(freq, sev, layer)
        rows = [
            ("E[cession per claim]", usd(check["per_claim_cession"])),
            ("E[claims reaching layer]", f"{check['expected_pierces']:.4f} / yr"),
            ("E[annual cession] — analytic",
             usd_short(check["expected_ceded"]), "accent"),
        ]
        if res is not None and not S.is_stale():
            sim_raw = float(res.ceded_raw.mean())
            gap_pct = (sim_raw / check["expected_ceded"] - 1.0) if check["expected_ceded"] > 0 else float("nan")
            tone = "good" if abs(gap_pct) < 0.02 else "danger" if abs(gap_pct) > 0.05 else ""
            rows += [
                ("E[annual cession] — simulated", usd_short(sim_raw)),
                ("Difference", f"{gap_pct:+.2%}" if math.isfinite(gap_pct) else "—", tone),
            ]
        C.ledger(rows)

        if res is not None and not S.is_stale():
            C.gap(small=True)
            C.chart(charts.convergence_chart(res), key="conv")
            C.note(
                "The running estimate with its 95% interval. A flat line inside a "
                "narrowing band means the answer has settled; a line still drifting "
                "at the right-hand edge means it has not, and more years are needed."
            )

    # ------------------------------------------------------------- explain
    C.exec_band([
        "There is no formula for what an excess layer costs, because the answer "
        "depends on the whole shape of the loss distribution rather than its average. "
        "So the model simulates. Each iteration draws a claim count for the year, "
        "draws that many claim sizes, applies the attachment and limit to each, adds "
        "up what the layer would have paid, and caps it at the annual maximum.",
        "Doing that hundreds of thousands of times produces a distribution of possible "
        "years. Its average is the expected cost. Its upper tail is what the capital "
        "is held against. Everything on the following pages is a read of that "
        "distribution.",
    ])
