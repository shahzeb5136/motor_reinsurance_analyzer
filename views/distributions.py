"""Page 2 - how many claims, and how big."""
from __future__ import annotations

import math

import streamlit as st

from repricer import charts, components as C, state as S
from repricer.distributions import SEVERITY_FAMILIES
from repricer.theme import num, pct, usd, usd_short


def render() -> None:
    C.page_title(
        "02", "Frequency & Severity",
        "Two assumptions decide the price of an excess layer: how many claims arrive, "
        "and how the largest of them behave. The second matters far more.",
    )
    C.guide("distributions")

    layer = S.current_layer()
    freq = S.current_frequency()

    left, right = st.columns([1, 1], gap="large")

    # ----------------------------------------------------------- frequency
    with left:
        C.section("A — Claim frequency")
        st.selectbox(
            "Distribution", ["Poisson", "Negative Binomial"], key="freq_family",
            on_change=S.invalidate_results,
            help="Poisson assumes claims arrive independently at a steady rate. "
                 "Negative Binomial allows the rate itself to vary year to year - "
                 "weather, legal environment, an unusually bad book of business.",
        )
        a, b = st.columns(2)
        with a:
            st.number_input(
                "Expected claims per year", key="freq_mean", min_value=0.0,
                step=50.0, format="%.0f", on_change=S.invalidate_results,
            )
        with b:
            if st.session_state["freq_family"] == "Negative Binomial":
                st.number_input(
                    "Variance-to-mean ratio", key="freq_dispersion",
                    min_value=1.001, max_value=50.0, step=0.1,
                    on_change=S.invalidate_results,
                    help="1.0 is Poisson. Above that the claim count is more "
                         "volatile than pure randomness would give - contagion.",
                )

        C.gap(small=True)
        C.ledger([
            ("Mean count", num(freq.mean)),
            ("Standard deviation", num(freq.sd, 1)),
            ("Variance / mean", f"{freq.dispersion:.2f}", "accent"),
            ("Parameters", freq.label, "muted"),
        ])
        C.chart(charts.frequency_chart(freq), key="freq")

        if st.session_state["freq_family"] == "Negative Binomial":
            C.note(
                "Contagion in the total claim count matters much less to an excess "
                "layer than it looks. What reaches the layer is the number of "
                "<b>large</b> claims, and thinning a volatile count by a very small "
                "probability leaves something close to Poisson again. Severity is "
                "where the money is."
            )

    # ------------------------------------------------------------ severity
    with right:
        C.section("B — Claim severity")
        fam = st.selectbox(
            "Attritional body distribution", SEVERITY_FAMILIES, key="sev_family",
            on_change=S.invalidate_results,
            help="The shape of an ordinary claim. This governs the bulk of the "
                 "book but rarely reaches an excess layer on its own.",
        )
        if fam in ("Lognormal", "Gamma"):
            a, b = st.columns(2)
            with a:
                st.number_input("Mean claim", key="sev_mean", min_value=1.0,
                                step=100.0, format="%.0f", on_change=S.invalidate_results)
            with b:
                st.number_input("Standard deviation", key="sev_sd", min_value=1.0,
                                step=500.0, format="%.0f", on_change=S.invalidate_results)
        elif fam == "Weibull":
            a, b = st.columns(2)
            with a:
                st.number_input("Scale", key="wb_scale", min_value=1.0, step=100.0,
                                format="%.0f", on_change=S.invalidate_results)
            with b:
                st.number_input("Shape (k)", key="wb_shape", min_value=0.05,
                                step=0.05, on_change=S.invalidate_results,
                                help="Below 1 the tail is heavier than exponential.")
        elif fam == "Pareto":
            a, b = st.columns(2)
            with a:
                st.number_input("Shape (alpha)", key="par_alpha", min_value=0.05,
                                step=0.1, on_change=S.invalidate_results)
            with b:
                st.number_input("Scale (theta)", key="par_theta", min_value=1.0,
                                step=500.0, format="%.0f", on_change=S.invalidate_results)
        else:
            a, b, c = st.columns(3)
            with a:
                st.number_input("alpha", key="burr_alpha", min_value=0.05, step=0.1,
                                on_change=S.invalidate_results)
            with b:
                st.number_input("gamma", key="burr_gamma", min_value=0.05, step=0.1,
                                on_change=S.invalidate_results)
            with c:
                st.number_input("theta", key="burr_theta", min_value=1.0, step=500.0,
                                format="%.0f", on_change=S.invalidate_results)

        C.section("C — Large-loss tail")
        C.note(
            "A small share of claims behaves nothing like the rest. Bodily injury, "
            "periodical payment orders, catastrophic liability: rare, and orders of "
            "magnitude larger. <b>These are the only claims that reach the layer</b>, "
            "so this block sets the price."
        )
        st.slider(
            "Share of claims drawn from the large-loss population (%)",
            key="p_extreme", min_value=0.0, max_value=5.0, step=0.05,
            format="%.2f%%", on_change=S.invalidate_results,
        )
        if float(st.session_state["p_extreme"]) > 0:
            a, b = st.columns(2)
            with a:
                st.number_input(
                    "Tail shape (alpha)", key="ext_alpha", min_value=0.2, step=0.05,
                    on_change=S.invalidate_results,
                    help="The single most important number in the model. Lower means "
                         "a heavier tail. Below 2 the variance is infinite; below 1 "
                         "even the mean does not exist.",
                )
            with b:
                st.number_input(
                    "Tail scale (theta)", key="ext_theta", min_value=1.0,
                    step=10_000.0, format="%.0f", on_change=S.invalidate_results,
                )

    # ------------------------------------------------------------- readout
    sev = S.current_severity()
    if sev is None:
        C.flag("danger", "Severity parameters are invalid. Every parameter must be "
                         "greater than zero.")
        return

    ext = S.current_extreme()
    p_pierce = float(sev.sf(layer.attachment))
    expected_pierce = freq.mean * p_pierce

    C.section("What the assumptions imply")
    C.kpi_row([
        dict(label="Blended average claim", value=usd(sev.mean), tone="",
             sub="across every claim the book produces"),
        dict(label="Claims reaching the layer", value=f"{expected_pierce:.2f}",
             tone="accent", sub="expected per year"),
        dict(label="One claim in", value=f"{1 / p_pierce:,.0f}" if p_pierce > 0 else "never",
             tone="", sub=f"breaches {usd_short(layer.attachment)}"),
        dict(label="99.9th percentile claim", value=usd_short(float(sev.quantile(0.999))),
             tone="teal", sub="1 in 1,000 claims exceeds this"),
    ])

    C.gap()
    a, b = st.columns([1.15, 1], gap="large")
    with a:
        C.chart(charts.severity_chart(sev, layer.attachment, layer.top), key="sev")
        C.note(
            "Log scale on both the axis and the argument: the claims that matter are "
            "hundreds of times larger than a typical one, and a linear axis would "
            "compress them into the origin. The shaded band is the layer."
        )
    with b:
        C.chart(charts.exceedance_by_claim(sev, layer.attachment, layer.top), key="sevx")
        rows = [
            ("Median claim", usd(sev.median())),
            ("99th percentile", usd(float(sev.quantile(0.99)))),
            ("99.9th percentile", usd(float(sev.quantile(0.999)))),
            ("P(claim > attachment)", f"{p_pierce:.3e}", "accent"),
        ]
        if ext is not None:
            rows += [
                ("Mean large-loss claim",
                 "undefined (alpha <= 1)" if math.isinf(ext.mean) else usd(ext.mean),
                 "danger" if math.isinf(ext.mean) else ""),
                ("P(large loss > attachment)", f"{float(ext.sf(layer.attachment)):.3e}"),
            ]
        C.ledger(rows)

    # ------------------------------------------------------------ warnings
    warns = [w for w in S.model_warnings() if "attachment" in w[1] or "alpha" in w[1]
             or "modelled average" in w[1]]
    if warns:
        C.gap(small=True)
        C.flags(warns)

    # ------------------------------------------------------- executive band
    if ext is not None and float(st.session_state["p_extreme"]) > 0:
        p_ext = S.extreme_share()
        share_of_mean = (p_ext * ext.mean / sev.mean) if math.isfinite(ext.mean) and sev.mean else float("nan")
        tail_sentence = (
            f"Those {pct(p_ext, 2)} of claims account for roughly "
            f"<b>{pct(share_of_mean)}</b> of the book's total claims cost, and for "
            f"essentially <b>100%</b> of what this layer will ever pay."
            if math.isfinite(share_of_mean) else
            "The large-loss population has no finite mean, so it dominates the "
            "book's cost without bound."
        )
        if expected_pierce <= 0:
            cadence = " — which is to say, never, on these assumptions"
        elif expected_pierce < 1:
            cadence = f" — roughly one every {1 / expected_pierce:,.1f} years"
        else:
            cadence = " — so a typical year sees more than one"

        C.exec_band([
            f"The model splits claims into two populations. "
            f"<b>{pct(1 - p_ext, 2)}</b> are ordinary claims averaging "
            f"{usd(S.current_body().mean)}. The remaining <b>{pct(p_ext, 2)}</b> come "
            f"from a heavy-tailed population that is far larger and far less "
            f"predictable. {tail_sentence}",
            f"On these assumptions a claim large enough to reach "
            f"{usd_short(layer.attachment)} arrives "
            f"<b>{expected_pierce:.2f} times a year</b> on average{cadence}. "
            f"If the true rate is half that, the layer is worth about half as much. "
            f"This is the number to argue about with the cedant, and it deserves "
            f"exposure analysis rather than a fit to attritional data.",
        ])
