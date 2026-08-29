"""
RE:PRICER - an excess-of-loss reinsurance pricing workbench.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import math

import streamlit as st

st.set_page_config(
    page_title="RE:PRICER — XoL pricing workbench",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"about": "RE:PRICER — excess-of-loss reinsurance pricing workbench."},
)

from repricer import ai, components as C, state as S  # noqa: E402
from repricer.pricing import price_layer  # noqa: E402
from repricer.theme import apply_theme, pct, usd_short  # noqa: E402
from views import (distributions, portfolio, pricing, results, simulation,  # noqa: E402
                   summary, whatif)

apply_theme()
S.init_state()


# ---------------------------------------------------------------------------
#  Sidebar
# ---------------------------------------------------------------------------
def sidebar() -> None:
    with st.sidebar:
        st.markdown(
            '<div style="font-family:\'Space Grotesk\';font-size:19px;font-weight:700;'
            'letter-spacing:.4px;color:#E9EFF6;padding:2px 6px 10px">'
            'RE:<span style="color:#E8A33D">PRICER</span></div>',
            unsafe_allow_html=True,
        )

        # -- the deal, always visible ------------------------------------
        layer = S.current_layer()
        res = S.result()
        rows = [
            ("Layer", f"{usd_short(layer.limit)} xs {usd_short(layer.attachment)}", "accent"),
            ("Cedant", st.session_state["cedant_name"]),
        ]
        if res is not None:
            quote = price_layer(res, S.current_loadings(),
                                subject_premium=float(st.session_state["gep"]),
                                share=float(st.session_state["share"]) / 100.0)
            rows += [
                ("Expected loss", usd_short(res.burning_cost)),
                ("Technical premium", usd_short(quote.technical_premium), "accent"),
                ("Rate on line", pct(quote.rate_on_line)),
            ]
        else:
            rows.append(("Status", "not yet priced", "muted"))
        C.ledger(rows)

        if S.is_stale():
            st.markdown(
                '<div class="rp-flag warn" style="margin:10px 0 4px;font-size:12px">'
                '<span class="ic">!</span><span>Assumptions changed since the last '
                'run.</span></div>', unsafe_allow_html=True)
            if st.button("Recalculate", use_container_width=True, key="sb_recalc"):
                S.run_now(st.empty())
                st.rerun()

        st.divider()

        # -- presets -----------------------------------------------------
        st.markdown('<div class="rp-sec" style="margin-top:0">Scenario</div>',
                    unsafe_allow_html=True)
        names = list(S.PRESETS)
        choice = st.selectbox("Load a worked example", names,
                              index=names.index(st.session_state.get("active_preset"))
                              if st.session_state.get("active_preset") in names else 1,
                              label_visibility="collapsed")
        note = S.PRESETS[choice].get("_note", "")
        if note:
            st.markdown(f'<div class="rp-note" style="margin:-2px 0 8px">{note}</div>',
                        unsafe_allow_html=True)
        if st.button("Load scenario", use_container_width=True):
            S.apply_preset(choice)
            st.rerun()

        st.divider()

        # -- display -----------------------------------------------------
        st.markdown('<div class="rp-sec" style="margin-top:0">Display</div>',
                    unsafe_allow_html=True)
        st.toggle("Plain-English panels", key="show_plain_english",
                  help="The amber bands that translate each page for a "
                       "non-specialist audience.")
        st.selectbox("Currency", ["$", "£", "€"], key="currency_symbol",
                     help="Display only — no conversion is applied.")

        st.divider()

        # -- AI ----------------------------------------------------------
        st.markdown('<div class="rp-sec" style="margin-top:0">AI commentary</div>',
                    unsafe_allow_html=True)
        configured = ai.resolve_key(st.session_state.get("gemini_key", ""))
        st.text_input("Gemini API key", key="gemini_key", type="password",
                      placeholder="AIza…" if not configured else "configured",
                      help="Stored in this browser session only. Also read from "
                           "GEMINI_API_KEY in the environment or .streamlit/secrets.toml.")
        cols = st.columns([1, 1])
        with cols[0]:
            if st.button("Test key", use_container_width=True, disabled=not configured):
                ok, message = ai.verify_key(st.session_state.get("gemini_key", ""))
                (st.success if ok else st.error)(message)
        with cols[1]:
            st.link_button("Get a key", "https://aistudio.google.com/apikey",
                           use_container_width=True)
        if configured:
            st.markdown('<div class="rp-note">Key detected. Commentary is generated '
                        'on the <b>Summary</b> page.</div>', unsafe_allow_html=True)

        st.divider()
        st.markdown(
            '<div class="rp-note" style="font-size:11px;line-height:1.6">'
            'Monte Carlo excess-of-loss pricing. Technical estimates only — '
            'not a bound quotation.</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
#  Masthead chips
# ---------------------------------------------------------------------------
def chips() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    layer = S.current_layer()
    out.append((f"{usd_short(layer.limit)} xs {usd_short(layer.attachment)}", "on"))

    res = S.result()
    if res is None:
        out.append(("not priced", ""))
    elif S.is_stale():
        out.append(("stale — recalculate", ""))
    else:
        out.append((f"{res.n_iter:,} yrs · {res.elapsed:.2f}s", "live"))

    out.append(("gemini connected" if ai.resolve_key(
        st.session_state.get("gemini_key", "")) else "gemini offline", ""))
    return out


# ---------------------------------------------------------------------------
#  Navigation
# ---------------------------------------------------------------------------
PAGES = [
    st.Page(portfolio.render, title="1 · Portfolio & Layer", url_path="portfolio",
            default=True),
    st.Page(distributions.render, title="2 · Frequency & Severity",
            url_path="distributions"),
    st.Page(simulation.render, title="3 · Simulation", url_path="simulation"),
    st.Page(results.render, title="4 · Results", url_path="results"),
    st.Page(pricing.render, title="5 · Pricing", url_path="pricing"),
    st.Page(whatif.render, title="6 · What-if", url_path="what-if"),
    st.Page(summary.render, title="7 · Summary", url_path="summary"),
]

nav = st.navigation(PAGES)
sidebar()
C.masthead(chips())
nav.run()
