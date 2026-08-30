"""
Turning a loss distribution into a price.

The simulation gives the expected loss to the layer. Everything between that
and a quotable number lives here: reinstatement premium income, acquisition
and internal expense, and the profit load that pays for the capital the tail
of the layer consumes.

The premium equation solved below is

    P x (1 + c*k - e - b)  =  LC + rc x K

where P is the deposit premium, LC the expected layer loss, c the
reinstatement cost as a fraction of P, k the expected number of limits
reinstated, e and b the internal-expense and brokerage ratios, K the capital
the layer absorbs and rc the cost of that capital.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .engine import SimResult


@dataclass(frozen=True)
class Loadings:
    """Everything loaded on top of the expected loss."""

    expense_ratio: float = 0.055       # reinsurer's internal expense, share of premium
    brokerage: float = 0.10            # ceding commission / broker fee, share of premium
    cost_of_capital: float = 0.10      # required return on capital absorbed
    capital_percentile: float = 0.995  # TVaR level defining absorbed capital
    diversification: float = 0.45      # share of standalone capital actually allocated
    target_margin: float = 0.0         # optional flat margin on top, share of premium

    @property
    def total_expense(self) -> float:
        return self.expense_ratio + self.brokerage + self.target_margin


@dataclass
class Quote:
    """A priced layer."""

    # volumes (100% of the layer unless noted)
    expected_loss: float
    standalone_capital: float
    capital: float
    capital_charge: float
    reinstatement_income: float
    expense: float
    brokerage: float
    margin: float
    technical_premium: float

    # our participation
    share: float
    signed_premium: float
    signed_expected_loss: float

    # ratios
    rate_on_line: float
    loss_on_line: float
    expected_loss_ratio: float
    premium_to_loss: float
    payback_years: float
    reinstatements_used: float
    subject_premium_rate: float

    feasible: bool = True
    note: str = ""

    @property
    def expected_profit(self) -> float:
        return self.technical_premium + self.reinstatement_income \
            - self.expected_loss - self.expense - self.brokerage

    @property
    def total_income(self) -> float:
        return self.technical_premium + self.reinstatement_income


def price_layer(result: SimResult, loadings: Loadings,
                subject_premium: float = 0.0,
                share: float | None = None) -> Quote:
    """Price ``result``'s layer under ``loadings``.

    ``share`` overrides the participation stored on the simulated layer. The
    simulation is always run on a 100% basis, so the signed line can be moved
    without re-simulating anything.
    """
    layer = result.layer
    limit = float(layer.limit)

    lc = result.burning_cost                       # expected loss, 100% basis
    k = result.expected_reinstatements_used        # expected limits reinstated
    c = float(layer.reinstatement_cost)
    e = float(loadings.expense_ratio)
    b = float(loadings.brokerage)
    m = float(loadings.target_margin)

    # Standalone capital is the tail loss in excess of the expected loss. A
    # single layer never consumes that much inside a portfolio, so only a
    # diversified share of it is charged for.
    standalone_capital = max(result.tvar(loadings.capital_percentile) - lc, 0.0)
    capital = standalone_capital * float(loadings.diversification)
    capital_charge = capital * float(loadings.cost_of_capital)

    denom = 1.0 + c * k - e - b - m
    feasible = denom > 0.05
    note = ""
    if not feasible:
        # Expenses have eaten the whole premium: no finite price balances.
        note = ("Expense and margin loadings exceed the premium they are charged "
                "on - no finite technical premium balances. Reduce the loadings.")
        denom = max(denom, 0.05)

    premium = (lc + capital_charge) / denom

    reinstatement_income = c * k * premium
    expense = e * premium
    brokerage = b * premium
    margin = m * premium

    total_income = premium + reinstatement_income
    share = float(layer.share if share is None else share)

    return Quote(
        expected_loss=lc,
        standalone_capital=standalone_capital,
        capital=capital,
        capital_charge=capital_charge,
        reinstatement_income=reinstatement_income,
        expense=expense,
        brokerage=brokerage,
        margin=margin,
        technical_premium=premium,
        share=share,
        signed_premium=premium * share,
        signed_expected_loss=lc * share,
        rate_on_line=premium / limit if limit > 0 else float("nan"),
        loss_on_line=lc / limit if limit > 0 else float("nan"),
        expected_loss_ratio=lc / total_income if total_income > 0 else float("nan"),
        premium_to_loss=premium / lc if lc > 0 else float("inf"),
        payback_years=limit / premium if premium > 0 else float("inf"),
        reinstatements_used=k,
        subject_premium_rate=(premium / subject_premium) if subject_premium > 0 else float("nan"),
        feasible=feasible,
        note=note,
    )


def quote_diagnostics(result: SimResult, quote: Quote,
                      loadings: Loadings) -> list[tuple[str, str]]:
    """Model-integrity checks on the priced result.

    Each entry is (level, message) with level in {"danger", "warn", "info"}.
    These are the things that quietly make a technical price wrong, so they
    are surfaced rather than left for the reviewer to notice.
    """
    out: list[tuple[str, str]] = []

    if not quote.feasible:
        out.append(("danger", quote.note))

    # A capital percentile inside the non-attaching mass measures nothing.
    tail_prob = 1.0 - loadings.capital_percentile
    if result.p_attach > 0 and tail_prob > result.p_attach:
        out.append((
            "warn",
            f"Capital is measured at TVaR {loadings.capital_percentile:.1%}, but the layer only "
            f"attaches in {result.p_attach:.2%} of years. The worst {tail_prob:.1%} of years is "
            f"mostly zeros, so the capital figure is diluted and the price understated. Move the "
            f"capital percentile above {1 - result.p_attach:.3%}."))

    # Deposit premium below expected loss: the layer leans on reinstatements.
    if quote.technical_premium < quote.expected_loss and quote.reinstatement_income > 0:
        out.append((
            "warn",
            f"The deposit premium sits below the expected loss. The structure only balances "
            f"because reinstatement premium adds a further "
            f"{quote.reinstatement_income / max(quote.technical_premium, 1e-9):.1f}x on top. "
            f"That income only arrives once losses have already been paid, so the cash-flow and "
            f"credit profile is far worse than the headline rate suggests."))

    # Monte Carlo precision on the number being quoted.
    if result.rel_error > 0.02:
        out.append((
            "warn",
            f"Monte Carlo standard error on the expected loss is {result.rel_error:.1%} of the "
            f"estimate. Increase the iteration count before relying on this price."))

    # Tail quantiles resting on a handful of simulated years.
    tail_years = int(round(result.n_iter * tail_prob))
    if 0 < tail_years < 200:
        out.append((
            "info",
            f"The capital figure is an average over just {tail_years:,} simulated years. "
            f"Expect it to move between runs at this iteration count."))

    # Aggregate features biting hard.
    if result.cap_bite > 0.25:
        out.append((
            "info",
            f"The aggregate cap and any annual deductible remove {result.cap_bite:.0%} of gross "
            f"cessions. The cedant retains materially more than the per-claim structure implies."))

    if math.isinf(result.severity.mean):
        out.append((
            "danger",
            "The severity distribution has an infinite mean (Pareto alpha <= 1). Expected values "
            "are not defined for the underlying claim size, and simulated averages will keep "
            "drifting upward with more iterations rather than converging."))

    return out


def premium_build_up(quote: Quote) -> list[tuple[str, float, str]]:
    """Waterfall steps from expected loss to technical premium.

    Returns (label, signed amount, kind) with kind in
    {"start", "add", "sub", "total"}.
    """
    steps = [
        ("Expected annual layer loss", quote.expected_loss, "start"),
        ("Capital charge", quote.capital_charge, "add"),
        ("Internal expense", quote.expense, "add"),
        ("Brokerage / commission", quote.brokerage, "add"),
    ]
    if quote.margin > 0:
        steps.append(("Target margin", quote.margin, "add"))
    if quote.reinstatement_income > 0:
        steps.append(("Reinstatement income", -quote.reinstatement_income, "sub"))
    steps.append(("Technical premium", quote.technical_premium, "total"))
    return steps


# ---------------------------------------------------------------------------
#  Risk-adjusted alternatives, for context around the technical number
# ---------------------------------------------------------------------------
def alternative_prices(result: SimResult, loadings: Loadings) -> dict[str, float]:
    """Other standard premium principles, to sanity-check the technical price.

    None of these are the quote; they bracket it. If the technical premium
    sits far outside this range, the loadings deserve a second look.
    """
    lc = result.burning_cost
    sd = result.volatility
    return {
        "Expected annual loss (burning cost)": lc,
        "Standard deviation principle (EL + 0.25 sd)": lc + 0.25 * sd,
        "Variance principle": lc + (0.5 * sd * sd / max(result.tvar(0.995), 1.0)),
        "TVaR 99% principle": 0.85 * lc + 0.15 * result.tvar(0.99),
        "Proportional hazard (r=0.9)": _ph_premium(result, 0.9),
    }


def _ph_premium(result: SimResult, r: float, points: int = 400) -> float:
    """Wang's proportional-hazard transform: reprice by raising the survival
    curve to the power r < 1, which fattens the tail before taking a mean."""
    import numpy as np

    x = np.sort(result.layer_loss)
    n = x.size
    s = 1.0 - (np.arange(1, n + 1) / n)
    idx = np.unique(np.linspace(0, n - 1, points).astype(int))
    xs, ss = x[idx], s[idx] ** r
    return float(np.trapezoid(ss, xs)) if hasattr(np, "trapezoid") else float(np.trapz(ss, xs))


def classify_layer(result: SimResult) -> tuple[str, str, str, str]:
    """Describe how the layer behaves, in the terms an underwriter would use.

    Returns (level, name, headline, explanation). ``level`` drives the badge
    colour: high / elev / mod / none.

    The classification is driven by how often the layer attaches and how often
    it burns through, not by the ratio of the tail to the mean. A remote layer
    naturally has a huge 1-in-250-to-average ratio; that is the nature of the
    product, not a warning sign.
    """
    p_attach = result.p_attach
    p_exh = result.p_exhaust
    p_full = result.p_full_limit

    if p_attach < 0.002 or result.burning_cost <= 0:
        return ("none", "Non-attaching",
                "Layer effectively never attaches",
                "No simulated year produced a claim large enough to breach the "
                "retention. Either the attachment sits well above the plausible "
                "loss range, or the severity assumptions understate the tail. "
                "As priced there is nothing to charge for.")

    if p_exh > 0.35:
        return ("high", "Swing layer",
                "Near-certain erosion of the limit",
                "The layer is exhausted in more than a third of years. It is "
                "functioning as a financing arrangement rather than risk "
                "transfer: the cedant is largely paying its own losses back "
                "through premium and reinstatements. Expect the price to sit "
                "close to the limit, and consider raising the attachment.")

    if p_exh > 0.10 or p_attach > 0.80:
        return ("elev", "Working layer",
                "Attaches most years, real erosion",
                "The layer is hit in most years and fully consumed in a "
                "meaningful share of them. This is a working layer: the premium "
                "is doing genuine work covering expected losses, and the "
                "reinstatement provision matters materially to the economics.")

    if p_attach < 0.15:
        return ("mod", "Remote tail cover",
                "Quiet most years, priced for the shock",
                "The layer attaches in only a small minority of years and is "
                "rarely consumed. The premium is compensation for infrequent but "
                "severe hits, so the capital load rather than the expected loss "
                "drives the price. Results are inherently volatile and the "
                "burning cost alone would badly underprice it.")

    return ("mod", "Tail cover",
            "Losses reasonably contained",
            "The layer attaches in a minority of years and is seldom exhausted. "
            "It behaves as intended for an excess layer: quiet in most years, "
            "with the premium compensating for occasional significant hits.")


def risk_verdict(result: SimResult) -> tuple[str, str, str]:
    """Backwards-compatible three-tuple form of :func:`classify_layer`."""
    level, _name, headline, explanation = classify_layer(result)
    return level, headline, explanation
