"""
Headless checks.

Two layers of testing:

* ``test_engine_*`` verify the numbers - the tail-thinned sampler must agree
  with full sampling, and both must agree with closed-form control totals.
* ``test_pages_*`` render every page through Streamlit's AppTest harness and
  fail on any uncaught exception.

Run with:  python -m pytest tests -q      (or: python tests/test_app.py)
"""
from __future__ import annotations

import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from repricer.distributions import (build_frequency, build_severity,  # noqa: E402
                                    mixture)
from repricer.engine import Layer, analytic_check, run_simulation  # noqa: E402
from repricer.pricing import (Loadings, classify_layer, premium_build_up,  # noqa: E402
                              price_layer, quote_diagnostics)

APP = str(ROOT / "app.py")


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------
def _models():
    body = build_severity("Lognormal", {"mean": 5_800, "sd": 18_000})
    ext = build_severity("Pareto", {"alpha": 2.30, "theta": 260_000})
    sev = mixture(body, ext, 0.008)
    freq = build_frequency("Poisson", {"lam": 4_200})
    layer = Layer(attachment=2e6, limit=6e6, reinstatements=2,
                  reinstatement_cost=1.0)
    return freq, sev, layer


# ---------------------------------------------------------------------------
#  Distributions
# ---------------------------------------------------------------------------
def test_severity_families_match_their_samples():
    rng = np.random.default_rng(3)
    cases = [
        ("Lognormal", {"mean": 7_400, "sd": 22_000}),
        ("Gamma", {"mean": 7_400, "sd": 22_000}),
        ("Weibull", {"scale": 6_000, "shape": 0.8}),
        ("Pareto", {"alpha": 2.4, "theta": 9_000}),
        ("Burr", {"alpha": 3.0, "gamma": 1.6, "theta": 8_000}),
    ]
    for family, params in cases:
        sev = build_severity(family, params)
        sample = sev.sample(400_000, rng)
        assert abs(sev.median() / np.median(sample) - 1) < 0.02, family
        assert abs(float(sev.quantile(0.99)) / np.quantile(sample, 0.99) - 1) < 0.05, family
        if math.isfinite(sev.mean):
            assert abs(sev.mean / sample.mean() - 1) < 0.05, family


def test_layer_mean_matches_pareto_closed_form():
    alpha, theta, D, L = 2.3, 260_000.0, 2e6, 6e6
    par = build_severity("Pareto", {"alpha": alpha, "theta": theta})
    exact = (theta / (alpha - 1)) * ((1 + D / theta) ** (1 - alpha)
                                     - (1 + (D + L) / theta) ** (1 - alpha))
    assert abs(par.layer_mean(D, L) / exact - 1) < 1e-6


def test_mixture_is_exact_not_sampled():
    body = build_severity("Lognormal", {"mean": 5_800, "sd": 18_000})
    ext = build_severity("Pareto", {"alpha": 2.3, "theta": 260_000})
    mix = mixture(body, ext, 0.008)
    # The blended mean is a closed form, and repeated calls must not jitter.
    assert abs(mix.mean - (0.992 * body.mean + 0.008 * ext.mean)) < 1e-6
    assert float(mix.quantile(0.999)) == float(mix.quantile(0.999))
    # Survival is the weighted survival of the components.
    for x in (1e5, 1e6, 5e6):
        expected = 0.992 * float(body.sf(x)) + 0.008 * float(ext.sf(x))
        assert abs(float(mix.sf(x)) - expected) < 1e-12


def test_excess_sampler_draws_only_above_the_threshold():
    _, sev, layer = _models()
    rng = np.random.default_rng(11)
    q, sampler = sev.excess_sampler(layer.attachment)
    draws = sampler(200_000, rng)
    assert (draws > layer.attachment).all()
    assert abs(q - float(sev.sf(layer.attachment))) < 1e-12
    # Conditional distribution must match the unconditional one, restricted.
    for p in (0.25, 0.5, 0.9):
        target = float(sev.isf(q * (1 - p)))
        assert abs(np.quantile(draws, p) / target - 1) < 0.05, p


# ---------------------------------------------------------------------------
#  Engine
# ---------------------------------------------------------------------------
def test_tail_mode_agrees_with_full_mode():
    freq, sev, layer = _models()
    tail = run_simulation(freq, sev, layer, 60_000, 5, mode="tail")
    full = run_simulation(freq, sev, layer, 60_000, 5, mode="full")
    combined_se = math.hypot(tail.std_error, full.std_error)
    assert abs(tail.burning_cost - full.burning_cost) < 4 * combined_se
    assert abs(tail.p_attach - full.p_attach) < 0.01
    assert abs(tail.expected_claims_to_layer - full.expected_claims_to_layer) < 0.05


def test_simulation_converges_to_the_analytic_control_total():
    freq, sev, layer = _models()
    res = run_simulation(freq, sev, layer, 400_000, 42, mode="tail")
    control = analytic_check(freq, sev, layer)["expected_ceded"]
    simulated = float(res.ceded_raw.mean())
    se = res.ceded_raw.std(ddof=1) / math.sqrt(res.n_iter)
    assert abs(simulated - control) < 4 * se


def test_aggregate_cap_and_aad_bind():
    freq, sev, _ = _models()
    capped = Layer(attachment=2e6, limit=6e6, reinstatements=0)
    uncapped = Layer(attachment=2e6, limit=6e6, reinstatements=float("inf"))
    a = run_simulation(freq, sev, capped, 40_000, 7, mode="tail")
    b = run_simulation(freq, sev, uncapped, 40_000, 7, mode="tail")
    assert a.burning_cost <= b.burning_cost + 1e-9
    assert (a.layer_loss <= capped.aggregate_cap + 1e-6).all()

    with_aad = Layer(attachment=2e6, limit=6e6, reinstatements=2, aad=1e6)
    c = run_simulation(freq, sev, with_aad, 40_000, 7, mode="tail")
    assert c.burning_cost < a.burning_cost or c.p_pay < a.p_pay


def test_severity_trend_is_consistent_across_modes():
    freq, sev, layer = _models()
    tail = run_simulation(freq, sev, layer, 60_000, 9, mode="tail",
                          severity_factor=1.25)
    full = run_simulation(freq, sev, layer, 60_000, 9, mode="full",
                          severity_factor=1.25)
    combined_se = math.hypot(tail.std_error, full.std_error)
    assert abs(tail.burning_cost - full.burning_cost) < 4 * combined_se


# ---------------------------------------------------------------------------
#  Pricing
# ---------------------------------------------------------------------------
def test_premium_equation_balances():
    freq, sev, layer = _models()
    res = run_simulation(freq, sev, layer, 60_000, 42, mode="tail")
    load = Loadings()
    q = price_layer(res, load, subject_premium=50e6)

    income = q.technical_premium + q.reinstatement_income
    outgo = (q.expected_loss + q.expense + q.brokerage + q.margin
             + q.capital_charge)
    assert abs(income - outgo) < 1e-6 * max(income, 1.0)

    # Build-up must reconcile to the premium.
    total = sum(a for _, a, kind in premium_build_up(q) if kind != "total")
    assert abs(total - q.technical_premium) < 1e-6 * q.technical_premium


def test_share_scales_without_resimulating():
    freq, sev, layer = _models()
    res = run_simulation(freq, sev, layer, 40_000, 42, mode="tail")
    full = price_layer(res, Loadings(), share=1.0)
    quarter = price_layer(res, Loadings(), share=0.25)
    assert abs(quarter.signed_premium - 0.25 * full.technical_premium) < 1e-6
    assert full.technical_premium == quarter.technical_premium


def test_diagnostics_flag_a_capital_percentile_inside_the_zero_mass():
    freq, sev, _ = _models()
    remote = Layer(attachment=2e7, limit=1e7, reinstatements=1)
    res = run_simulation(freq, sev, remote, 60_000, 42, mode="tail")
    load = Loadings(capital_percentile=0.995)
    messages = " ".join(m for _, m in quote_diagnostics(res, price_layer(res, load), load))
    if 0 < res.p_attach < 0.005:
        assert "capital percentile" in messages.lower()


def test_classification_does_not_call_a_remote_layer_high_risk():
    freq, sev, _ = _models()
    remote = Layer(attachment=8e6, limit=22e6, reinstatements=1)
    res = run_simulation(freq, sev, remote, 60_000, 42, mode="tail")
    level, name, _, _ = classify_layer(res)
    assert res.p_exhaust < 0.05
    assert level != "high", f"remote layer classified {name}"


# ---------------------------------------------------------------------------
#  Pages
# ---------------------------------------------------------------------------
#  AppTest.switch_page only understands file-backed pages and this app builds
#  its navigation from callables, so the pages are exercised through
#  tests/page_harness.py, which wires up the same theme and state and calls one
#  view directly.
HARNESS = str(ROOT / "tests" / "page_harness.py")
PAGES = ("portfolio", "distributions", "simulation", "results", "pricing",
         "whatif", "summary")


def _harness(page: str, timeout: int = 180):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(HARNESS, default_timeout=timeout)
    at.session_state["__page__"] = page
    return at


def test_pages_render_before_any_simulation():
    """Cold start: every page must show its gate rather than fall over."""
    for page in PAGES:
        at = _harness(page)
        at.run()
        assert not at.exception, f"{page}: {[e.value for e in at.exception]}"


def test_pages_render_with_a_tail_mode_result():
    """The default engine mode leaves gu_loss unset - pages must cope."""
    freq, sev, layer = _models()
    res = run_simulation(freq, sev, layer, 20_000, 42, mode="tail",
                         label="Base case")
    assert res.gu_loss is None
    for page in PAGES:
        at = _harness(page)
        at.run()
        at.session_state["sim_result"] = res
        at.run()
        assert not at.exception, f"{page}: {[e.value for e in at.exception]}"


def test_pages_render_with_a_full_mode_result_and_a_stress():
    freq, sev, layer = _models()
    res = run_simulation(freq, sev, layer, 15_000, 42, mode="full",
                         label="Base case")
    stress = run_simulation(freq, sev, layer, 15_000, 42, mode="full",
                            label="Stressed", severity_factor=1.15)
    stress.meta["levers"] = {"severity": 15.0, "frequency": 8.0,
                             "p_base": 0.008, "p_stress": 0.012}
    assert res.gu_loss is not None
    for page in PAGES:
        at = _harness(page)
        at.run()
        at.session_state["sim_result"] = res
        at.session_state["stress_result"] = stress
        at.run()
        assert not at.exception, f"{page}: {[e.value for e in at.exception]}"


def test_pages_render_for_a_never_attaching_layer():
    """The degenerate case: an attachment nothing can reach."""
    freq, sev, _ = _models()
    remote = Layer(attachment=5e9, limit=1e9, reinstatements=1)
    res = run_simulation(freq, sev, remote, 5_000, 42, mode="tail")
    assert res.burning_cost == 0.0
    for page in ("results", "pricing", "summary", "whatif"):
        at = _harness(page)
        at.run()
        at.session_state["sim_result"] = res
        at.run()
        assert not at.exception, f"{page}: {[e.value for e in at.exception]}"


def test_severity_page_handles_every_tail_setting():
    """The large-loss section is skipped when there is no tail, and must cope
    with an infinite-mean tail and an unreachable attachment."""
    cases = [
        ("no tail", {"p_extreme": 0.0}),
        ("infinite mean", {"ext_alpha": 0.9}),
        ("burr body", {"sev_family": "Burr"}),
        ("pareto body", {"sev_family": "Pareto"}),
        ("wide tail share", {"p_extreme": 5.0}),
        ("unreachable attachment", {"attachment": 5_000_000_000.0}),
    ]
    for label, overrides in cases:
        at = _harness("distributions")
        at.run()
        for key, value in overrides.items():
            at.session_state[key] = value
        at.run()
        assert not at.exception, f"{label}: {[e.value for e in at.exception]}"


def test_widget_defaults_survive_a_page_switch():
    """Streamlit only pushes a session value to a widget when the key was
    assigned in the same run, so a plain setdefault leaves widgets on a later
    page showing min_value instead of the real figure."""
    at = _harness("pricing")
    at.run()
    freq, sev, layer = _models()
    at.session_state["sim_result"] = run_simulation(freq, sev, layer, 5_000, 42,
                                                    mode="tail")
    at.run()          # first render of the loading widgets, on a later run
    assert not at.exception, [e.value for e in at.exception]

    seen = {ni.label: ni.value for ni in at.number_input}
    assert seen.get("Internal expense (%)") == 5.5, seen
    assert seen.get("Brokerage (%)") == 10.0, seen
    assert seen.get("Cost of capital (%)") == 10.0, seen
    assert seen.get("Diversification credit (%)") == 45.0, seen
    assert at.slider[0].value == 99.5


def test_report_export_is_complete():
    """The downloadable note must carry the numbers, not just headings."""
    import streamlit as st

    from repricer.narrative import markdown_report
    from repricer.theme import usd, usd_short

    at = _harness("summary")
    at.run()
    freq, sev, layer = _models()
    res = run_simulation(freq, sev, layer, 20_000, 42, mode="tail")
    at.session_state["sim_result"] = res
    at.run()
    assert not at.exception, [e.value for e in at.exception]

    # Rebuild the same context the page hands to the exporter.
    quote = price_layer(res, Loadings(), subject_premium=50e6)
    ctx = {
        "cedant": "Test Cedant", "programme": "Test Programme",
        "gep": 50e6, "loss_ratio": 62.0, "n_claims": 4200.0,
        "expected_gu": 31e6, "layer": layer, "result": res, "quote": quote,
        "frequency": freq, "severity": sev,
        "extreme": sev.components.get("extreme"), "p_extreme": 0.008,
        "loadings": Loadings(), "stress": None,
        "n_iter": res.n_iter, "seed": res.seed, "mode": res.mode,
        "currency": "$", "attachment": layer.attachment, "limit": layer.limit,
        "top": layer.top, "aggregate_cap": layer.aggregate_cap,
        "reinstatements": layer.reinstatements,
        "reinstatement_cost": layer.reinstatement_cost,
        "aad": layer.aad, "share": layer.share, "elapsed": res.elapsed,
    }
    report = markdown_report(ctx)
    for needle in ("Executive summary", "Basis of pricing", "Return periods",
                   "Premium build-up", "Technical note",
                   usd(quote.technical_premium), usd(res.burning_cost)):
        assert needle in report, f"missing from report: {needle!r}"
    # No unformatted placeholders leaking into a client-facing document.
    # Word boundaries matter: "nan" is a substring of "dominant".
    import re
    leaked = re.findall(r"\b(?:None|nan|inf|NaN)\b", report)
    assert not leaked, f"unformatted values in report: {leaked}"
    assert len(report) > 2_500, len(report)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import traceback

    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
