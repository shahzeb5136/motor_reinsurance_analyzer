"""
Session state: the single source of truth for what is being priced.

Widgets bind to the keys defined here. Everything downstream - the engine,
the narrative, the AI commentary, the export - reads models built by the
``current_*`` helpers rather than poking at raw widget values, so there is
one place where inputs become a model.
"""
from __future__ import annotations

import math

import streamlit as st

from .distributions import Frequency, Severity, build_frequency, build_severity, mixture
from .engine import Layer, SimResult
from .pricing import Loadings

# ---------------------------------------------------------------------------
#  Defaults
# ---------------------------------------------------------------------------
DEFAULTS: dict = {
    # presentation
    "currency_symbol": "$",
    "cedant_name": "Meridian Motor Insurance",
    "programme_name": "2026 Motor Excess of Loss",
    "show_plain_english": True,

    # portfolio
    "gep": 50_000_000.0,
    "loss_ratio": 62.0,
    "n_claims": 4_200.0,

    # layer
    "attachment": 2_000_000.0,
    "limit": 6_000_000.0,
    "reinstatements": 2,
    "unlimited_reinstatements": False,
    "reinstatement_cost": 100.0,
    "aad": 0.0,
    "share": 100.0,

    # frequency
    "freq_family": "Poisson",
    "freq_mean": 4_200.0,
    "freq_dispersion": 1.6,

    # severity body
    "sev_family": "Lognormal",
    "sev_mean": 5_800.0,
    "sev_sd": 18_000.0,
    "wb_scale": 4_600.0,
    "wb_shape": 0.85,
    "par_alpha": 2.4,
    "par_theta": 8_100.0,
    "burr_alpha": 3.0,
    "burr_gamma": 1.6,
    "burr_theta": 6_300.0,

    # large-loss tail
    "p_extreme": 0.80,
    "ext_alpha": 2.30,
    "ext_theta": 260_000.0,

    # simulation
    "n_iter": 100_000,
    "seed": 42,
    "engine_mode": "tail",

    # loadings
    "expense_ratio": 5.5,
    "brokerage": 10.0,
    "cost_of_capital": 10.0,
    "capital_percentile": 99.5,
    "diversification": 45.0,

    # stress levers
    "stress_severity": 12.0,
    "stress_frequency": 8.0,
    "stress_p_extreme_uplift": 50.0,

    # AI
    "gemini_key": "",
    "gemini_model": "gemini-2.5-flash",
    "ai_persona": "Underwriter's review",
}

RESULT_KEYS = ("sim_result", "stress_result", "ai_cache")


# ---------------------------------------------------------------------------
#  Presets - realistic starting points for a demonstration
# ---------------------------------------------------------------------------
_MOTOR_BOOK = {
    "cedant_name": "Meridian Motor Insurance",
    "gep": 50_000_000.0, "loss_ratio": 62.0, "n_claims": 4_200.0,
    "freq_family": "Poisson", "freq_mean": 4_200.0, "freq_dispersion": 1.6,
    "sev_family": "Lognormal", "sev_mean": 5_800.0, "sev_sd": 18_000.0,
    "p_extreme": 0.80, "ext_alpha": 2.30, "ext_theta": 260_000.0,
    "aad": 0.0, "share": 100.0, "reinstatement_cost": 100.0,
}

PRESETS: dict[str, dict] = {
    "Layer 1 — working layer": {
        **_MOTOR_BOOK,
        "_note": "Attaches in almost every year and is hit several times over. "
                 "Frequency drives the price, reinstatement income does most of "
                 "the work, and the loss ratio is high by design.",
        "programme_name": "2026 Motor XoL — Layer 1",
        "attachment": 500_000.0, "limit": 1_500_000.0, "reinstatements": 3,
    },
    "Layer 2 — mid excess": {
        **_MOTOR_BOOK,
        "_note": "The classic middle layer: attaches in roughly one year in "
                 "five, rarely exhausts, and the capital load starts to carry "
                 "as much of the price as the expected loss.",
        "programme_name": "2026 Motor XoL — Layer 2",
        "attachment": 2_000_000.0, "limit": 6_000_000.0, "reinstatements": 2,
    },
    "Layer 3 — high excess, PPO exposed": {
        **_MOTOR_BOOK,
        "_note": "A periodical-payment-order exposed top layer. Barely one year "
                 "in a hundred sees a claim reach it, so almost the entire "
                 "premium is compensation for tail risk rather than expected "
                 "loss. The tail parameter is the whole argument.",
        "programme_name": "2026 Motor XoL — Layer 3",
        "attachment": 8_000_000.0, "limit": 22_000_000.0, "reinstatements": 1,
    },
    "Commercial fleet — small volatile book": {
        "_note": "A smaller book with genuine claim-count contagion. Worth "
                 "noting how little the overdispersed frequency moves an excess "
                 "layer: what matters is the number of large claims, not the "
                 "volatility of the attritional count.",
        "cedant_name": "Northgate Fleet & Haulage",
        "programme_name": "2026 Fleet XoL",
        "gep": 18_000_000.0, "loss_ratio": 71.0, "n_claims": 900.0,
        "attachment": 1_500_000.0, "limit": 5_000_000.0,
        "reinstatements": 2, "reinstatement_cost": 100.0, "aad": 0.0, "share": 100.0,
        "freq_family": "Negative Binomial", "freq_mean": 900.0, "freq_dispersion": 3.5,
        "sev_family": "Lognormal", "sev_mean": 11_700.0, "sev_sd": 42_000.0,
        "p_extreme": 0.90, "ext_alpha": 2.05, "ext_theta": 300_000.0,
    },
}


# ---------------------------------------------------------------------------
#  Lifecycle
# ---------------------------------------------------------------------------
def init_state() -> None:
    """Seed defaults, and keep them alive across page switches.

    Streamlit only pushes a session-state value down to a widget when the key
    was *assigned during the same script run* (``is_new_state_value``). A
    plain ``setdefault`` assigns on the first run only, so a widget appearing
    for the first time on a later run - which is every widget on every page
    the user reaches by clicking rather than by loading its URL - would ignore
    the stored value and fall back to its own default, which for a numeric
    widget is ``min_value``. Re-assigning each key every run keeps the value
    in the current run's state, so widgets always open on the real figure.

    Must run before any widget is created; assigning a key after its widget
    exists is an error in Streamlit.
    """
    for key, value in DEFAULTS.items():
        st.session_state[key] = st.session_state.get(key, value)
    for key in RESULT_KEYS:
        st.session_state.setdefault(key, {} if key == "ai_cache" else None)


def apply_preset(name: str) -> None:
    preset = PRESETS.get(name)
    if not preset:
        return
    for key, value in preset.items():
        if key.startswith("_"):
            continue
        st.session_state[key] = value
    st.session_state["sim_result"] = None
    st.session_state["stress_result"] = None
    st.session_state["active_preset"] = name


def invalidate_results() -> None:
    st.session_state["sim_result"] = None
    st.session_state["stress_result"] = None
    st.session_state["sim_signature"] = None


def has_result() -> bool:
    return isinstance(st.session_state.get("sim_result"), SimResult)


def result() -> SimResult | None:
    return st.session_state.get("sim_result")


def stress_result() -> SimResult | None:
    return st.session_state.get("stress_result")


# ---------------------------------------------------------------------------
#  Staleness
# ---------------------------------------------------------------------------
#  Only inputs that change what the simulation actually does belong here.
#  Loadings and the signed share are applied to a finished result, so they can
#  move without invalidating anything - which is what makes dragging the cost
#  of capital and watching the premium respond feel instant.
SIGNATURE_KEYS = (
    "attachment", "limit", "reinstatements", "unlimited_reinstatements", "aad",
    "freq_family", "freq_mean", "freq_dispersion",
    "sev_family", "sev_mean", "sev_sd", "wb_scale", "wb_shape",
    "par_alpha", "par_theta", "burr_alpha", "burr_gamma", "burr_theta",
    "p_extreme", "ext_alpha", "ext_theta",
    "n_iter", "seed", "engine_mode",
)


def signature() -> tuple:
    return tuple(st.session_state.get(k) for k in SIGNATURE_KEYS)


def mark_run() -> None:
    st.session_state["sim_signature"] = signature()


def is_stale() -> bool:
    """True when assumptions have moved since the stored run."""
    if not has_result():
        return False
    stored = st.session_state.get("sim_signature")
    return stored is not None and stored != signature()


def touch() -> None:
    """on_change hook for widgets that alter the simulation."""
    st.session_state["stress_result"] = None


# ---------------------------------------------------------------------------
#  Running
# ---------------------------------------------------------------------------
def run_now(progress_slot=None) -> SimResult | None:
    """Run the base simulation and store it. Returns None if inputs are invalid."""
    from .engine import run_simulation

    sev = current_severity()
    if sev is None:
        return None

    bar = progress_slot.progress(0.0, text="Preparing") if progress_slot else None

    def report(frac: float, message: str) -> None:
        if bar is not None:
            bar.progress(min(frac, 1.0), text=message)

    res = run_simulation(
        current_frequency(), sev, current_layer(),
        n_iter=int(st.session_state["n_iter"]),
        seed=int(st.session_state["seed"]),
        progress=report,
        label="Base case",
        mode=st.session_state["engine_mode"],
    )
    if bar is not None:
        bar.empty()

    st.session_state["sim_result"] = res
    st.session_state["stress_result"] = None
    mark_run()
    return res


def run_stress(progress_slot=None) -> SimResult | None:
    """Re-run the layer under the stress levers, holding seed and count."""
    from .engine import run_simulation

    base = result()
    if base is None:
        return None

    s = st.session_state
    sev_k = 1.0 + float(s["stress_severity"]) / 100.0
    freq_k = 1.0 + float(s["stress_frequency"]) / 100.0
    p_stress = min(extreme_share() * (1.0 + float(s["stress_p_extreme_uplift"]) / 100.0), 1.0)

    stressed_sev = mixture(current_body(), current_extreme(), p_stress)
    if stressed_sev is None:
        return None

    bar = progress_slot.progress(0.0, text="Stressing") if progress_slot else None

    def report(frac: float, message: str) -> None:
        if bar is not None:
            bar.progress(min(frac, 1.0), text=message)

    res = run_simulation(
        current_frequency().scaled(freq_k), stressed_sev, current_layer(),
        n_iter=base.n_iter, seed=base.seed, progress=report,
        label="Stressed", severity_factor=sev_k, mode=base.mode,
    )
    if bar is not None:
        bar.empty()

    res.meta["levers"] = {
        "severity": float(s["stress_severity"]),
        "frequency": float(s["stress_frequency"]),
        "p_base": extreme_share(),
        "p_stress": p_stress,
        "p_uplift": float(s["stress_p_extreme_uplift"]),
    }
    res.meta["lever_note"] = (
        f"severity {float(s['stress_severity']):+.0f}%, "
        f"frequency {float(s['stress_frequency']):+.0f}%, "
        f"large-loss share {extreme_share() * 100:.2f}% -> {p_stress * 100:.2f}% "
        f"({float(s['stress_p_extreme_uplift']):+.0f}%)"
    )
    st.session_state["stress_result"] = res
    return res


# ---------------------------------------------------------------------------
#  Model builders
# ---------------------------------------------------------------------------
def current_frequency() -> Frequency:
    s = st.session_state
    if s["freq_family"] == "Poisson":
        return build_frequency("Poisson", {"lam": float(s["freq_mean"])})
    return build_frequency("Negative Binomial", {
        "mean": float(s["freq_mean"]),
        "dispersion": float(s["freq_dispersion"]),
    })


def current_body() -> Severity | None:
    s = st.session_state
    fam = s["sev_family"]
    params = {
        "Lognormal": {"mean": s["sev_mean"], "sd": s["sev_sd"]},
        "Gamma": {"mean": s["sev_mean"], "sd": s["sev_sd"]},
        "Weibull": {"scale": s["wb_scale"], "shape": s["wb_shape"]},
        "Pareto": {"alpha": s["par_alpha"], "theta": s["par_theta"]},
        "Burr": {"alpha": s["burr_alpha"], "gamma": s["burr_gamma"],
                 "theta": s["burr_theta"]},
    }[fam]
    return build_severity(fam, {k: float(v) for k, v in params.items()})


def current_extreme() -> Severity | None:
    s = st.session_state
    if float(s["p_extreme"]) <= 0:
        return None
    return build_severity("Pareto", {
        "alpha": float(s["ext_alpha"]),
        "theta": float(s["ext_theta"]),
    })


def extreme_share() -> float:
    return float(st.session_state["p_extreme"]) / 100.0


def current_severity() -> Severity | None:
    return mixture(current_body(), current_extreme(), extreme_share())


def current_layer() -> Layer:
    s = st.session_state
    reinst = float("inf") if s.get("unlimited_reinstatements") else float(s["reinstatements"])
    return Layer(
        attachment=float(s["attachment"]),
        limit=float(s["limit"]),
        reinstatements=reinst,
        reinstatement_cost=float(s["reinstatement_cost"]) / 100.0,
        aad=float(s["aad"]),
        share=float(s["share"]) / 100.0,
    )


def current_loadings() -> Loadings:
    s = st.session_state
    return Loadings(
        expense_ratio=float(s["expense_ratio"]) / 100.0,
        brokerage=float(s["brokerage"]) / 100.0,
        cost_of_capital=float(s["cost_of_capital"]) / 100.0,
        capital_percentile=float(s["capital_percentile"]) / 100.0,
        diversification=float(s["diversification"]) / 100.0,
    )


# ---------------------------------------------------------------------------
#  Derived portfolio figures
# ---------------------------------------------------------------------------
def ground_up_loss() -> float:
    s = st.session_state
    return float(s["gep"]) * float(s["loss_ratio"]) / 100.0


def implied_average_claim() -> float:
    n = float(st.session_state["n_claims"])
    return ground_up_loss() / n if n > 0 else float("nan")


def reconcile_body_mean() -> bool:
    """Back-solve the attritional mean so the blended severity reproduces the
    average claim implied by the portfolio figures.

    Blended mean = (1-p) x body mean + p x tail mean, so the body mean that
    ties the model back to the book is simply that rearranged. Only defined
    for the two-parameter families where the mean is an input.
    """
    s = st.session_state
    if s["sev_family"] not in ("Lognormal", "Gamma"):
        return False
    target = implied_average_claim()
    if not math.isfinite(target) or target <= 0:
        return False

    p = extreme_share()
    ext = current_extreme()
    tail_mean = ext.mean if ext is not None else 0.0
    if math.isinf(tail_mean):
        return False

    body_mean = (target - p * tail_mean) / max(1.0 - p, 1e-9)
    if body_mean <= 0:
        return False

    cv = float(s["sev_sd"]) / max(float(s["sev_mean"]), 1e-9)
    s["sev_mean"] = round(body_mean, 2)
    s["sev_sd"] = round(body_mean * cv, 2)
    invalidate_results()
    return True


def model_warnings() -> list[tuple[str, str]]:
    """Consistency checks between the portfolio figures and the fitted models.

    These catch the most common way a pricing model goes quietly wrong: the
    distributions drift away from the book they are meant to describe.
    """
    out: list[tuple[str, str]] = []
    s = st.session_state
    sev = current_severity()
    freq = current_frequency()

    if sev is None:
        out.append(("danger", "Severity parameters are invalid - every parameter "
                              "must be strictly positive."))
        return out

    implied = implied_average_claim()
    if math.isfinite(implied) and implied > 0 and math.isfinite(sev.mean):
        drift = sev.mean / implied - 1.0
        if abs(drift) > 0.10:
            out.append((
                "warn",
                f"The modelled average claim of {sev.mean:,.0f} is {abs(drift):.0%} "
                f"{'above' if drift > 0 else 'below'} the {implied:,.0f} implied by the "
                f"portfolio figures on this page. Reconcile the two before quoting - "
                f"the layer price scales directly with severity."))

    if abs(freq.mean / max(float(s["n_claims"]), 1.0) - 1.0) > 0.02:
        out.append((
            "warn",
            f"Modelled claim frequency ({freq.mean:,.0f}) differs from the expected "
            f"claim count entered for the book ({float(s['n_claims']):,.0f})."))

    ext = current_extreme()
    if ext is not None:
        alpha = float(s["ext_alpha"])
        if alpha <= 1.0:
            out.append((
                "danger",
                f"The large-loss tail is set to alpha = {alpha:.2f}. At or below 1.0 the "
                f"distribution has an infinite mean: expected values do not exist and "
                f"simulated averages will keep climbing with more iterations instead of "
                f"settling. A single claim can dwarf the entire limit."))
        elif alpha <= 2.0:
            out.append((
                "warn",
                f"The large-loss tail is set to alpha = {alpha:.2f}. Below 2.0 the "
                f"distribution has a finite mean but infinite variance, so the average "
                f"large claim badly understates what the layer is exposed to. Deliberate "
                f"for a PPO-exposed book, but it should be a choice rather than an accident."))

    layer = current_layer()
    if layer.limit <= 0:
        out.append(("danger", "The layer limit must be greater than zero."))
    if layer.aad >= layer.limit > 0:
        out.append(("warn", "The annual aggregate deductible is at least a full limit, "
                            "so the cedant absorbs a whole limit before the layer responds."))
    if math.isfinite(sev.mean) and layer.attachment > 0:
        p = float(sev.sf(layer.attachment))
        expected_pierce = freq.mean * p
        if expected_pierce < 0.01:
            out.append((
                "info",
                f"Only about {expected_pierce:.3f} claims a year are expected to breach the "
                f"attachment - roughly one every {1 / max(expected_pierce, 1e-9):,.0f} years. "
                f"Results at this remoteness rest on the tail assumption rather than on data."))
    return out


# ---------------------------------------------------------------------------
#  A single bundle for narrative / AI / export
# ---------------------------------------------------------------------------
def build_context(res: SimResult, quote) -> dict:
    """Everything the narrative, the AI prompt and the export need."""
    s = st.session_state
    layer = res.layer
    sev = res.severity
    ext = current_extreme()

    return {
        "cedant": s["cedant_name"],
        "programme": s["programme_name"],
        "currency": s["currency_symbol"],
        "gep": float(s["gep"]),
        "loss_ratio": float(s["loss_ratio"]),
        "expected_gu": ground_up_loss(),
        "n_claims": float(s["n_claims"]),

        "layer": layer,
        "attachment": layer.attachment,
        "limit": layer.limit,
        "top": layer.top,
        "aggregate_cap": layer.aggregate_cap,
        "reinstatements": layer.reinstatements,
        "reinstatement_cost": layer.reinstatement_cost,
        "aad": layer.aad,
        "share": layer.share,

        "frequency": res.frequency,
        "severity": sev,
        "extreme": ext,
        "p_extreme": extreme_share(),

        "result": res,
        "quote": quote,
        "stress": stress_result(),
        "loadings": current_loadings(),

        "n_iter": res.n_iter,
        "seed": res.seed,
        "mode": res.mode,
        "elapsed": res.elapsed,
    }
