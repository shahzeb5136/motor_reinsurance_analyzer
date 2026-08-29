"""
Plain-English writing about the numbers.

Everything here is deterministic: the same run always produces the same
words. That matters for two reasons. It means the app tells a coherent story
with no API key attached, and it means the AI commentary in :mod:`ai` has a
factual baseline to be checked against rather than being the only prose on
the page.
"""
from __future__ import annotations

import math

from .pricing import Quote, classify_layer
from .theme import mult, num, pct, usd, usd_short, years


def _n(text: str) -> str:
    return f'<span class="num">{text}</span>'


def _one_in(p: float) -> str:
    """Turn a probability into the 'one year in N' phrasing non-specialists
    read far more easily than a percentage."""
    if p <= 0:
        return "never"
    if p >= 0.995:
        return "effectively every year"
    period = 1.0 / p
    if period < 1.5:
        return "most years"
    if period < 25:
        return f"about one year in {period:.0f}"
    if period < 500:
        return f"about one year in {round(period / 5) * 5:.0f}"
    return f"about one year in {round(period / 50) * 50:,.0f}"


def _frequency_phrase(rate: float) -> str:
    """Describe an annual event rate the way a person would say it aloud.

    Phrased to complete the sentence "a claim big enough ... happens ...".
    """
    if rate <= 0:
        return "never, on these assumptions"
    if rate >= 2:
        return f"around {rate:.1f} times a year"
    if rate >= 0.6:
        return f"roughly {rate:.1f} times a year, so most years see one"
    if rate >= 0.02:
        return f"about once every {1 / rate:,.0f} years"
    return f"about once every {round(1 / rate / 10) * 10:,.0f} years"


# ===========================================================================
#  Headline
# ===========================================================================
def headline(ctx: dict) -> dict:
    """The four numbers that lead the executive summary."""
    res, quote = ctx["result"], ctx["quote"]
    return {
        "premium": quote.technical_premium,
        "rate_on_line": quote.rate_on_line,
        "expected_loss": res.burning_cost,
        "rp250": res.rp(250),
        "verdict": classify_layer(res),
    }


# ===========================================================================
#  The executive summary - written for someone who does not price reinsurance
# ===========================================================================
def executive_summary(ctx: dict) -> list[str]:
    res: object = ctx["result"]
    quote: Quote = ctx["quote"]
    layer = ctx["layer"]
    level, kind, headline_txt, explanation = classify_layer(res)

    limit_s = usd_short(layer.limit)
    attach_s = usd_short(layer.attachment)
    paras: list[str] = []

    # --- what is being bought -------------------------------------------
    paras.append(
        f"<b>{ctx['cedant']}</b> is buying protection against unusually large motor "
        f"claims. The cover pays the part of any single claim above "
        f"{_n(attach_s)}, up to a further {_n(limit_s)}. Anything below "
        f"{_n(attach_s)} stays with the insurer; anything above "
        f"{_n(usd_short(layer.top))} on a single claim falls outside this layer."
    )

    # --- how often it bites ----------------------------------------------
    pierce_rate = res.expected_claims_to_layer
    paras.append(
        f"On the assumptions modelled here, a claim big enough to reach this cover "
        f"happens {_n(_frequency_phrase(pierce_rate))}. The cover therefore pays out in "
        f"{_n(_one_in(res.p_pay))}. In the years it does pay, the average amount is "
        f"{_n(usd_short(res.mean_severity_to_layer))}."
    )

    # --- the price and what drives it ------------------------------------
    el_share = quote.expected_loss / quote.technical_premium if quote.technical_premium > 0 else 0
    driver = ("expected claims" if el_share > 0.6
              else "the cost of holding capital against a bad year" if el_share < 0.35
              else "a roughly even split between expected claims and the cost of capital")
    iters = _n(format(int(ctx["n_iter"]), ","))
    paras.append(
        f"Averaged over {iters} simulated years, the claims cost of this "
        f"cover is {_n(usd_short(res.burning_cost))} a year. Adding the cost of the capital "
        f"the reinsurer must hold, its expenses and brokerage - and crediting the "
        f"reinstatement premium the contract earns back - gives a technical premium of "
        f"<b>{_n(usd_short(quote.technical_premium))}</b>, or "
        f"{_n(pct(quote.rate_on_line))} of the limit on offer. The price is driven mainly by "
        f"{driver}."
    )

    # --- the bad year ------------------------------------------------------
    rp100, rp250 = res.rp(100), res.rp(250)
    if rp250 > 0:
        paras.append(
            f"A bad year matters more than an average one. A one-in-100 year costs this "
            f"layer {_n(usd_short(rp100))} and a one-in-250 year "
            f"{_n(usd_short(rp250))} - "
            f"{_n(mult(rp250 / res.burning_cost) if res.burning_cost > 0 else '-')} "
            f"the average. That gap is what the premium above the pure claims cost is "
            f"paying for."
        )

    # --- verdict ------------------------------------------------------------
    paras.append(f"<b>{headline_txt}.</b> {explanation}")

    return paras


# ===========================================================================
#  The technical note - written for the actuary reviewing the work
# ===========================================================================
def technical_note(ctx: dict) -> list[str]:
    res = ctx["result"]
    quote: Quote = ctx["quote"]
    layer = ctx["layer"]
    sev = ctx["severity"]
    freq = ctx["frequency"]
    load = ctx["loadings"]

    paras: list[str] = []

    tail_txt = (
        f"a two-component mixture in which {_n(pct(ctx['p_extreme'], 2))} of claims are drawn "
        f"from a heavy-tailed {ctx['extreme'].label}"
        if ctx["extreme"] is not None else "a single severity distribution"
    )
    paras.append(
        f"Claim frequency is modelled as <b>{freq.label}</b> (variance-to-mean "
        f"{_n(f'{freq.dispersion:.2f}')}) and severity as {tail_txt}, giving a blended "
        f"average claim of {_n(usd(sev.mean))}. The probability that any single claim "
        f"breaches the {_n(usd_short(layer.attachment))} attachment is "
        f"{_n(f'{float(sev.sf(layer.attachment)):.3e}')} - one claim in "
        f"{_n(f'{1 / max(float(sev.sf(layer.attachment)), 1e-15):,.0f}')}."
    )

    ci_lo, ci_hi = res.ci95
    mode_txt = ("tail-thinned sampling, which draws only the claims capable of reaching "
                "the attachment from the exact conditional distribution"
                if res.mode == "tail" else
                "full ground-up sampling of every claim in every year")
    paras.append(
        f"The layer was simulated over {_n(f'{res.n_iter:,}')} underwriting years using "
        f"{mode_txt} (seed {_n(str(res.seed))}, {_n(f'{res.elapsed:.2f}s')}). The expected "
        f"annual loss to the layer is {_n(usd(res.burning_cost))} with a 95% Monte Carlo "
        f"interval of {_n(usd_short(ci_lo))} to {_n(usd_short(ci_hi))}, a relative standard "
        f"error of {_n(pct(res.rel_error, 2))}. The coefficient of variation of the annual "
        f"layer loss is {_n(f'{res.cv:.2f}')}."
    )

    cap_txt = ""
    if res.cap_bite > 0.01:
        cap_txt = (
            f" The aggregate cap of {_n(usd_short(layer.aggregate_cap))} and any annual "
            f"deductible remove {_n(pct(res.cap_bite))} of gross cessions, so the layer pays "
            f"materially less than a per-claim view alone would suggest.")
    paras.append(
        f"Gross cessions before annual features average "
        f"{_n(usd(float(res.ceded_raw.mean())))} against an analytic control total of "
        f"{_n(usd(freq.mean * sev.layer_mean(layer.attachment, layer.limit)))} "
        f"(E[N] x (LEV(D+L) - LEV(D))).{cap_txt}"
    )

    paras.append(
        f"Capital is measured as TVaR at {_n(pct(load.capital_percentile, 1))} in excess of "
        f"the expected loss - {_n(usd_short(quote.standalone_capital))} standalone, of which "
        f"{_n(pct(load.diversification, 0))} is allocated after diversification credit, "
        f"charged at {_n(pct(load.cost_of_capital, 0))}. With an expense ratio of "
        f"{_n(pct(load.expense_ratio, 1))}, brokerage of {_n(pct(load.brokerage, 1))} and "
        f"expected reinstatement income of {_n(usd_short(quote.reinstatement_income))} "
        f"({_n(f'{quote.reinstatements_used:.2f}')} limits reinstated on average), the "
        f"technical premium solves to {_n(usd(quote.technical_premium))}: a rate on line of "
        f"{_n(pct(quote.rate_on_line))} against a loss on line of "
        f"{_n(pct(quote.loss_on_line))}, an expected loss ratio of "
        f"{_n(pct(quote.expected_loss_ratio))} and a payback period of "
        f"{_n(years(quote.payback_years))}."
    )

    return paras


# ===========================================================================
#  Stress commentary
# ===========================================================================
def stress_summary(ctx: dict, base, stressed, levers: dict) -> list[str]:
    base_bc, str_bc = base.burning_cost, stressed.burning_cost
    delta = (str_bc - base_bc) / base_bc if base_bc > 0 else float("nan")

    sev_k = levers.get("severity", 0.0)
    frq_k = levers.get("frequency", 0.0)
    p0, p1 = levers.get("p_base", 0.0), levers.get("p_stress", 0.0)

    moves = []
    if abs(sev_k) > 1e-9:
        moves.append(f"claim sizes {sev_k:+.0f}%")
    if abs(frq_k) > 1e-9:
        moves.append(f"claim numbers {frq_k:+.0f}%")
    if abs(p1 - p0) > 1e-9:
        moves.append(f"the large-loss share from {pct(p0, 2)} to {pct(p1, 2)}")
    if not moves:
        move_txt = "no change to the assumptions"
    elif len(moves) == 1:
        move_txt = moves[0]
    else:
        move_txt = ", ".join(moves[:-1]) + f" and {moves[-1]}"

    paras = [
        f"Moving {move_txt} takes the expected annual cost of this layer from "
        f"{_n(usd_short(base_bc))} to <b>{_n(usd_short(str_bc))}</b>"
        + (f", a change of {_n(f'{delta:+.0%}')}." if math.isfinite(delta) else ".")
    ]

    # The leverage claim is only honest when severity moved on its own; with
    # several levers running together the change cannot be attributed to one.
    severity_alone = (abs(sev_k) > 1e-9 and abs(frq_k) < 1e-9
                      and abs(p1 - p0) < 1e-12)
    if math.isfinite(delta) and severity_alone:
        leverage = delta / (sev_k / 100.0)
        if math.isfinite(leverage) and leverage > 1.3:
            paras.append(
                f"Note the leverage: a {_n(f'{sev_k:+.0f}%')} move in claim sizes alone "
                f"produces a {_n(f'{delta:+.0%}')} move in the cost of this layer - roughly "
                f"{_n(mult(abs(leverage)))} the effect. Excess layers amplify severity trend, "
                f"because inflation pushes claims across the attachment that previously fell "
                f"below it as well as enlarging the ones already there. This is the single "
                f"most important sensitivity in the pricing."
            )
    elif math.isfinite(delta) and len(moves) > 1 and abs(delta) > abs(sev_k / 100.0):
        paras.append(
            f"The levers moved together here, so the change cannot be attributed to any one "
            f"of them - but note that the total move of {_n(f'{delta:+.0%}')} is far larger "
            f"than any of the individual inputs. Excess layers amplify their drivers: "
            f"inflation pushes claims across the attachment that previously fell below it as "
            f"well as enlarging the ones already there. Use the tornado above to see what "
            f"each assumption is worth on its own."
        )

    d_exh = stressed.p_exhaust - base.p_exhaust
    if d_exh > 0.02:
        paras.append(
            f"Exhaustion frequency rises from {_n(pct(base.p_exhaust))} to "
            f"{_n(pct(stressed.p_exhaust))} of years. Once the limit is regularly consumed the "
            f"cover stops absorbing the marginal loss, so the cedant - not the reinsurer - "
            f"takes the next increment of deterioration."
        )

    d100 = stressed.rp(100) - base.rp(100)
    if abs(d100) > 0:
        paras.append(
            f"The one-in-100 year moves from {_n(usd_short(base.rp(100)))} to "
            f"{_n(usd_short(stressed.rp(100)))}, and the one-in-250 from "
            f"{_n(usd_short(base.rp(250)))} to {_n(usd_short(stressed.rp(250)))}. "
            f"Read the whole exercise as a measure of how much the price depends on "
            f"assumptions that are themselves uncertain."
        )
    return paras


# ===========================================================================
#  Page-level plain-English guides
# ===========================================================================
GUIDES: dict[str, tuple[str, str]] = {
    "portfolio": (
        "What this page does",
        "An excess-of-loss reinsurance contract is a deductible on the insurer's own "
        "losses. The insurer pays every claim up to the <b>attachment</b>; the reinsurer "
        "pays the next slice up to the <b>limit</b>. This page sets the size of the book "
        "being protected and the shape of that slice. Everything after it is arithmetic "
        "about how often, and how hard, that slice gets hit."),
    "distributions": (
        "What this page does",
        "Pricing a layer means knowing two things: how many claims arrive in a year, and "
        "how big each one is. This page sets both. The critical judgement is the "
        "<b>large-loss tail</b> - a small share of claims drawn from a much heavier "
        "distribution. Ordinary motor claims are far too small to reach an excess layer, "
        "so almost the entire price of the contract comes from that handful of severe "
        "claims. Change the tail and you change the price."),
    "simulation": (
        "What this page does",
        "There is no closed-form answer for what an excess layer costs, so the model plays "
        "out the year many thousands of times. Each simulated year draws a claim count, "
        "draws that many claim sizes, and works out what the layer would have paid. The "
        "spread of those answers is the risk; their average is the expected cost."),
    "results": (
        "How to read this page",
        "The headline number is the <b>expected annual loss</b> - what the layer costs in "
        "an average year. But no year is average. The <b>return-period</b> figures show "
        "the bad ones: a one-in-100 year is the level exceeded in 1% of simulated years. "
        "The gap between the average and the tail is what the premium above expected loss "
        "is paying for."),
    "pricing": (
        "How the price is built",
        "Start with what the layer is expected to cost in claims. Add the return the "
        "reinsurer needs on the capital it must hold against a bad year, plus its expenses "
        "and the broker's commission. Then credit back the reinstatement premium the "
        "contract earns when losses restore the limit. What is left is the technical "
        "premium - the floor below which the deal destroys value."),
    "whatif": (
        "Why this page matters",
        "Every number in this model rests on assumptions about a future that has not "
        "happened. This page moves those assumptions and shows what breaks. Excess layers "
        "are unusually sensitive to claims inflation, because rising claim sizes push "
        "losses across the attachment that previously fell below it - so a 10% move in "
        "claim sizes rarely means a 10% move in the price."),
    "summary": (
        "About this document",
        "A self-contained pricing note: what is being bought, what it is expected to cost, "
        "what a bad year looks like, and what the answer depends on. The figures are "
        "technical estimates from a simulation model, not a bound quotation."),
}


# ===========================================================================
#  Export
# ===========================================================================
def markdown_report(ctx: dict) -> str:
    """A complete pricing note in Markdown, for download."""
    import datetime as _dt
    import re

    res = ctx["result"]
    quote: Quote = ctx["quote"]
    layer = ctx["layer"]
    load = ctx["loadings"]
    level, kind, headline_txt, explanation = classify_layer(res)

    def strip(html: str) -> str:
        return re.sub(r"<[^>]+>", "", html)

    today = _dt.date.today().strftime("%d %B %Y")
    lines = [
        f"# {ctx['programme']}",
        f"### {usd_short(layer.limit)} xs {usd_short(layer.attachment)} excess of loss",
        "",
        f"**Cedant:** {ctx['cedant']}  ",
        f"**Priced:** {today}  ",
        f"**Basis:** {res.n_iter:,} simulated underwriting years, seed {res.seed}",
        "",
        "---",
        "",
        "## Headline",
        "",
        "| | |",
        "|---|---|",
        f"| Technical premium (100%) | **{usd(quote.technical_premium)}** |",
        f"| Rate on line | **{pct(quote.rate_on_line)}** |",
        f"| Expected annual loss | {usd(res.burning_cost)} |",
        f"| Loss on line | {pct(quote.loss_on_line)} |",
        f"| Expected loss ratio | {pct(quote.expected_loss_ratio)} |",
        f"| Premium to expected loss | {mult(quote.premium_to_loss)} |",
        f"| Payback period | {years(quote.payback_years)} |",
        f"| Verdict | {kind} - {headline_txt} |",
        "",
        "## Executive summary",
        "",
    ]
    lines += [strip(p) + "\n" for p in executive_summary(ctx)]

    lines += [
        "## Structure",
        "",
        "| Term | Value |",
        "|---|---|",
        f"| Attachment | {usd(layer.attachment)} |",
        f"| Limit | {usd(layer.limit)} |",
        f"| Exhaustion point | {usd(layer.top)} |",
        f"| Reinstatements | {'unlimited' if math.isinf(layer.reinstatements) else f'{layer.reinstatements:g}'} "
        f"@ {pct(layer.reinstatement_cost, 0)} pro rata |",
        f"| Aggregate cap | {usd(layer.aggregate_cap)} |",
        f"| Annual aggregate deductible | {usd(layer.aad)} |",
        f"| Signed share | {pct(layer.share, 0)} |",
        "",
        "## Basis of pricing",
        "",
        "| Assumption | Value |",
        "|---|---|",
        f"| Subject gross earned premium | {usd(ctx['gep'])} |",
        f"| Ground-up loss ratio | {ctx['loss_ratio']:.1f}% |",
        f"| Expected claim count | {num(ctx['n_claims'])} |",
        f"| Frequency model | {ctx['frequency'].label} |",
        f"| Severity - attritional body | {ctx['severity'].components.get('body').label if ctx['severity'].components else ctx['severity'].label} |",
        f"| Severity - large-loss tail | {ctx['extreme'].label if ctx['extreme'] else 'none'} "
        f"({pct(ctx['p_extreme'], 2)} of claims) |",
        f"| Blended average claim | {usd(ctx['severity'].mean)} |",
        f"| Expense ratio | {pct(load.expense_ratio, 1)} |",
        f"| Brokerage | {pct(load.brokerage, 1)} |",
        f"| Cost of capital | {pct(load.cost_of_capital, 1)} |",
        f"| Capital basis | TVaR {pct(load.capital_percentile, 1)}, "
        f"{pct(load.diversification, 0)} diversification credit |",
        "",
        "## Risk profile",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Probability the layer attaches | {pct(res.p_attach)} |",
        f"| Probability the layer pays | {pct(res.p_pay)} |",
        f"| Probability of exhaustion | {pct(res.p_exhaust)} |",
        f"| Expected claims reaching the layer | {res.expected_claims_to_layer:.3f} per year |",
        f"| Average loss in a year that pays | {usd(res.mean_severity_to_layer)} |",
        "",
        "### Return periods",
        "",
        "| Return period | Exceedance probability | Layer loss | Tail VaR |",
        "|---|---|---|---|",
    ]
    for rp in (5, 10, 25, 50, 100, 200, 250):
        lines.append(f"| 1-in-{rp} | {pct(1 / rp, 2)} | {usd(res.rp(rp))} | {usd(res.rp_tvar(rp))} |")

    lines += ["", "## Premium build-up", "", "| Component | Amount |", "|---|---|"]
    from .pricing import premium_build_up
    for label, amount, kind_ in premium_build_up(quote):
        prefix = "**" if kind_ == "total" else ""
        lines.append(f"| {prefix}{label}{prefix} | {prefix}{usd(amount)}{prefix} |")

    lines += ["", "## Technical note", ""]
    lines += [strip(p) + "\n" for p in technical_note(ctx)]

    if ctx.get("stress") is not None:
        lines += ["## Sensitivity", ""]
        st_res = ctx["stress"]
        lines += [
            "| Measure | Base | Stressed | Change |",
            "|---|---|---|---|",
            f"| Expected annual loss | {usd(res.burning_cost)} | {usd(st_res.burning_cost)} | "
            f"{(st_res.burning_cost / res.burning_cost - 1) * 100:+.1f}% |"
            if res.burning_cost > 0 else "",
            f"| Probability of attaching | {pct(res.p_attach)} | {pct(st_res.p_attach)} | "
            f"{(st_res.p_attach - res.p_attach) * 100:+.1f} pp |",
            f"| Probability of exhaustion | {pct(res.p_exhaust)} | {pct(st_res.p_exhaust)} | "
            f"{(st_res.p_exhaust - res.p_exhaust) * 100:+.1f} pp |",
            f"| 1-in-100 year | {usd(res.rp(100))} | {usd(st_res.rp(100))} | "
            f"{usd(st_res.rp(100) - res.rp(100))} |",
            f"| 1-in-250 year | {usd(res.rp(250))} | {usd(st_res.rp(250))} | "
            f"{usd(st_res.rp(250) - res.rp(250))} |",
            "",
        ]

    lines += [
        "---",
        "",
        "*Figures are simulated technical estimates before any market adjustment. "
        "They do not constitute a bound quotation. Model output depends entirely on the "
        "frequency and severity assumptions recorded above; the large-loss tail parameter "
        "is the dominant driver and should be supported by exposure analysis and market "
        "benchmarks rather than fitted to attritional experience alone.*",
        "",
        f"*Generated by RE:PRICER on {today}.*",
    ]
    return "\n".join(str(x) for x in lines if x != "")
