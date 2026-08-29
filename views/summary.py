"""Page 7 - the pricing note, and the AI commentary on it."""
from __future__ import annotations

import datetime as dt
import math

import streamlit as st

from repricer import ai, charts, components as C, narrative, state as S
from repricer.pricing import classify_layer, premium_build_up, price_layer
from repricer.theme import mult, num, pct, usd, usd_short


def render() -> None:
    res = S.result()
    if res is None:
        C.page_title("07", "Executive summary",
                     "The whole deal on one page, in language a non-actuary can act on.")
        C.needs_run()
        return

    loadings = S.current_loadings()
    share = float(st.session_state["share"]) / 100.0
    quote = price_layer(res, loadings, subject_premium=float(st.session_state["gep"]),
                        share=share)
    ctx = S.build_context(res, quote)
    layer = res.layer
    level, kind, headline, explanation = classify_layer(res)

    # ------------------------------------------------------------- masthead
    st.markdown(
        f'<div class="rp-title"><span class="n">07</span>'
        f'<span class="t">{layer.limit and usd_short(layer.limit)} xs '
        f'{usd_short(layer.attachment)} excess of loss</span></div>'
        f'<p class="rp-lede" style="margin-bottom:6px">'
        f'<b style="color:#E9EFF6">{ctx["cedant"]}</b> · {ctx["programme"]} · '
        f'subject premium {usd_short(ctx["gep"])} · priced '
        f'{dt.date.today().strftime("%d %B %Y")}</p>',
        unsafe_allow_html=True,
    )
    C.guide("summary")

    # ------------------------------------------------------------- headline
    C.kpi_row([
        dict(label="Technical premium", value=usd_short(quote.technical_premium),
             tone="accent", sub=f"{pct(quote.rate_on_line)} rate on line"),
        dict(label="Expected annual loss", value=usd_short(res.burning_cost),
             tone="teal", sub=f"{pct(quote.loss_on_line)} loss on line"),
        dict(label="1-in-100 year", value=usd_short(res.rp(100)), tone="",
             sub=f"1-in-250: {usd_short(res.rp(250))}"),
        dict(label="Probability it pays", value=pct(res.p_pay), tone="danger",
             sub=f"a full {usd_short(layer.limit)} limit goes in "
                 f"{pct(res.p_full_limit)} of years"),
    ])

    C.gap()
    left, right = st.columns([1.45, 1], gap="large")

    with left:
        C.section("The deal, in plain terms")
        C.prose(narrative.executive_summary(ctx))

        C.gap(small=True)
        C.section("Loss profile")
        C.chart(charts.loss_histogram(res, height=280), key="sum_hist")

    with right:
        C.section("Verdict")
        C.verdict_badge(level, kind)
        C.gap(small=True)
        C.note(explanation)

        C.gap(small=True)
        C.section("Basis of pricing")
        body = ctx["severity"].components.get("body") if ctx["severity"].components else None
        C.ledger([
            ("Subject gross earned premium", usd_short(ctx["gep"])),
            ("Ground-up loss ratio", f"{ctx['loss_ratio']:.1f}%"),
            ("Expected claim count", num(ctx["n_claims"])),
            ("Layer", f"{usd_short(layer.limit)} xs {usd_short(layer.attachment)}", "accent"),
            ("Reinstatements",
             "unlimited" if math.isinf(layer.reinstatements)
             else f"{layer.reinstatements:g} @ {pct(layer.reinstatement_cost, 0)}"),
            ("Aggregate cap",
             "unlimited" if math.isinf(layer.aggregate_cap)
             else usd_short(layer.aggregate_cap)),
            ("Frequency model", ctx["frequency"].label),
            ("Severity — body", body.label if body else ctx["severity"].label),
            ("Severity — large-loss tail",
             ctx["extreme"].label if ctx["extreme"] else "none"),
            ("Large-loss share", pct(ctx["p_extreme"], 2)),
            ("Blended average claim", usd(ctx["severity"].mean)),
            ("Simulation", f"{res.n_iter:,} years · seed {res.seed}"),
        ])

        C.gap(small=True)
        C.section("Price build-up")
        C.ledger([(label, usd_short(amount),
                   "total" if kind_ == "total" else ("good" if amount < 0 else ""))
                  for label, amount, kind_ in premium_build_up(quote)])

    # ------------------------------------------------------------ AI panel
    C.gap()
    _ai_section(ctx)

    # ----------------------------------------------------------- technical
    C.gap()
    with st.expander("Technical note — for the actuary reviewing this"):
        C.prose(narrative.technical_note(ctx), lead_first=False)

    if ctx.get("stress") is not None:
        with st.expander("Sensitivity note"):
            levers = ctx["stress"].meta.get("levers", {})
            C.prose(narrative.stress_summary(ctx, res, ctx["stress"], levers),
                    lead_first=False)

    # -------------------------------------------------------------- export
    C.gap()
    C.section("Export")
    a, b, c = st.columns([1, 1, 2])
    with a:
        st.download_button(
            "Download pricing note (.md)",
            data=narrative.markdown_report(ctx),
            file_name=f"{_slug(ctx['programme'])}-pricing-note.md",
            mime="text/markdown", use_container_width=True,
        )
    with b:
        st.download_button(
            "Download loss distribution (.csv)",
            data=_csv(res),
            file_name=f"{_slug(ctx['programme'])}-simulated-losses.csv",
            mime="text/csv", use_container_width=True,
        )

    C.footer(
        "Figures are simulated technical estimates before market adjustment. "
        "Not a bound quotation.<br>"
        "RE:PRICER · excess-of-loss pricing workbench"
    )


# ---------------------------------------------------------------------------
#  AI commentary
# ---------------------------------------------------------------------------
def _ai_section(ctx: dict) -> None:
    C.section("AI commentary")

    key = ai.resolve_key(st.session_state.get("gemini_key", ""))
    res = ctx["result"]
    persona = st.session_state.get("ai_persona", ai.DEFAULT_PERSONA)
    model = st.session_state.get("gemini_model", "gemini-2.5-flash")

    a, b, c = st.columns([1.3, 1.1, 1], gap="medium")
    with a:
        st.selectbox("Reviewer", list(ai.PERSONAS), key="ai_persona",
                     help="Changes who the commentary is written for and what it "
                          "chooses to comment on.")
    with b:
        st.selectbox("Model", list(ai.MODELS), key="gemini_model",
                     format_func=lambda m: m, help=" · ".join(
                         f"{k}: {v}" for k, v in ai.MODELS.items()))
    with c:
        C.gap(small=True)
        go = st.button("Generate commentary", type="primary",
                       use_container_width=True, disabled=not key)

    question = st.text_input(
        "Specific question (optional)", key="ai_question",
        placeholder="e.g. Is the capital basis appropriate for a layer this remote?",
    )

    if not key:
        C.flag("info",
               "Add a Gemini API key in the sidebar to generate commentary. "
               "Everything else on this page works without one — the written "
               "summary above is produced by the model itself, not by an LLM. "
               "Get a free key at <a href='https://aistudio.google.com/apikey' "
               "target='_blank'>aistudio.google.com/apikey</a>.")
        return

    cache = st.session_state.setdefault("ai_cache", {})
    cache_key = f"{res.fingerprint()}|{persona}|{model}|{question.strip()}"

    if go:
        with st.spinner(f"Asking {model}…"):
            try:
                text, meta = ai.generate(ctx, key, model=model, persona=persona,
                                         extra_question=question)
                cache[cache_key] = (text, meta)
            except ai.AIError as exc:
                C.flag("danger", str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - surface anything unexpected
                C.flag("danger", f"Unexpected error calling Gemini: {exc}")
                return

    entry = cache.get(cache_key)
    if entry is None:
        C.flag("info", "Press <b>Generate commentary</b> for an independent read of "
                       "these results. The model is given the computed figures and "
                       "asked to comment; it is not asked to calculate anything.")
        return

    text, meta = entry
    tokens = ""
    if meta.get("total_tokens"):
        tokens = f"{meta['total_tokens']:,} tokens"
    C.ai_panel(ai.to_html(text), model=meta.get("model", model),
               tokens=tokens, persona=meta.get("persona", persona))

    with st.expander("What the model was given"):
        st.code(ai.build_brief(ctx), language="text")


# ---------------------------------------------------------------------------
def _slug(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "layer"


def _csv(res) -> str:
    import io

    import numpy as np
    import pandas as pd

    df = pd.DataFrame({
        "year": np.arange(1, res.n_iter + 1),
        "claims_in_year": res.n_claims,
        "claims_above_attachment": res.n_pierce,
        "largest_claim": np.round(res.largest, 2),
        "ceded_before_annual_features": np.round(res.ceded_raw, 2),
        "loss_to_layer": np.round(res.layer_loss, 2),
    })
    if res.has_gu_distribution:
        df.insert(2, "ground_up_loss", np.round(res.gu_loss, 2))
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()
