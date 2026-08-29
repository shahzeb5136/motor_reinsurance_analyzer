"""
AI commentary on a priced layer, via Google Gemini.

Design rules this module follows:

* The app is fully functional without a key. AI commentary is an extra pass
  over results that already have a deterministic narrative attached.
* The model is handed the computed figures, never asked to compute. It reads
  a structured brief and writes about it; every number in the brief comes
  from the simulation.
* Output is cached against a fingerprint of the run, so navigating between
  pages does not re-bill the same question.
"""
from __future__ import annotations

import json
import math
import os
import re

import requests

from .pricing import Quote, classify_layer, premium_build_up, quote_diagnostics
from .theme import mult, num, pct, usd, usd_short

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT = 90

MODELS = {
    "gemini-2.5-flash": "Fast, inexpensive - good for iterating during a session",
    "gemini-2.5-pro": "Strongest reasoning - best for the final written note",
    "gemini-2.0-flash": "Previous generation, lowest latency",
}

PERSONAS: dict[str, str] = {
    "Underwriter's review": (
        "You are a senior treaty underwriter at a major reinsurer reviewing this "
        "submission before quoting. You care about whether the price is adequate, where "
        "the model is most likely to be wrong, and what you would push back on in "
        "negotiation. You are commercially minded and direct."
    ),
    "Actuarial peer review": (
        "You are a qualified pricing actuary performing peer review on a colleague's "
        "technical pricing. You care about parameter selection, model risk, whether the "
        "simulation is converged, whether the capital basis is appropriate for this "
        "layer's remoteness, and whether the stated assumptions are internally "
        "consistent. You are precise and constructively critical."
    ),
    "Broker / client-facing note": (
        "You are a reinsurance broker explaining this analysis to the cedant's finance "
        "director, who is intelligent but not an actuary. You avoid jargon, explain any "
        "technical term you must use, and focus on what the numbers mean for the "
        "cedant's business and what choices they have."
    ),
    "Capital & risk view": (
        "You are a risk officer assessing what this layer does to the portfolio's "
        "capital position and tail risk. You care about the volatility of the result, "
        "the adequacy of the capital charge, accumulation and correlation with the rest "
        "of the book, and what could make this layer behave far worse than modelled."
    ),
}

DEFAULT_PERSONA = "Underwriter's review"


# ---------------------------------------------------------------------------
#  Key handling
# ---------------------------------------------------------------------------
KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def _from_secrets() -> str:
    """Read secrets.toml, but only if one actually exists.

    Touching ``st.secrets`` with no secrets file makes Streamlit surface a
    'No secrets found' error in the app itself, which is noise for the large
    majority of users who supply the key another way.
    """
    import pathlib

    paths = (
        pathlib.Path.cwd() / ".streamlit" / "secrets.toml",
        pathlib.Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml",
        pathlib.Path.home() / ".streamlit" / "secrets.toml",
    )
    if not any(p.is_file() for p in paths):
        return ""
    try:
        import streamlit as st

        for name in KEY_NAMES:
            if name in st.secrets:
                return str(st.secrets[name]).strip()
    except Exception:
        pass
    return ""


def resolve_key(explicit: str = "") -> str:
    """Find an API key: what the user typed, then secrets, then environment."""
    if explicit and explicit.strip():
        return explicit.strip()
    found = _from_secrets()
    if found:
        return found
    for name in KEY_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


# ---------------------------------------------------------------------------
#  The brief - the model reads facts, it does not invent them
# ---------------------------------------------------------------------------
def _tail_moments(ctx: dict) -> str:
    """State which moments of the tail exist.

    Left unsaid, a reviewer reaches for the rule of thumb that a Pareto tail
    is heavy and asserts infinite variance regardless of the parameter. The
    threshold is alpha = 2, so give the fact rather than invite the guess.
    """
    ext = ctx.get("extreme")
    if ext is None:
        return "Tail moments: no separate large-loss component."
    alpha = float(ext.params.get("alpha", float("nan")))
    if math.isnan(alpha):
        return "Tail moments: not characterised."
    if alpha <= 1:
        state = ("neither the mean nor the variance exists (alpha <= 1). Expected "
                 "values of the underlying claim size are undefined")
    elif alpha <= 2:
        state = ("the mean exists but the variance does not (1 < alpha <= 2). The "
                 "average large claim understates the exposure")
    else:
        state = ("both the mean and the variance exist (alpha > 2). This is a heavy "
                 "tail but not an infinite-variance one")
    return (f"Tail moment properties: for the Pareto II large-loss component with "
            f"alpha = {alpha:.3f}, {state}. Moments of order k exist only for "
            f"k < alpha. Do not assert otherwise.")


def build_brief(ctx: dict) -> str:
    res = ctx["result"]
    quote: Quote = ctx["quote"]
    layer = ctx["layer"]
    load = ctx["loadings"]
    sev = ctx["severity"]
    freq = ctx["frequency"]
    _, kind, headline, _ = classify_layer(res)

    reinst = ("unlimited" if math.isinf(layer.reinstatements)
              else f"{layer.reinstatements:g} at {pct(layer.reinstatement_cost, 0)} pro rata")

    lines = [
        "## SUBMISSION",
        f"Cedant: {ctx['cedant']}",
        f"Programme: {ctx['programme']}",
        f"Class: motor excess of loss",
        f"Subject gross earned premium: {usd(ctx['gep'])}",
        f"Assumed ground-up loss ratio: {ctx['loss_ratio']:.1f}%",
        f"Expected ground-up loss: {usd(ctx['expected_gu'])}",
        f"Expected annual claim count: {num(ctx['n_claims'])}",
        "",
        "## STRUCTURE",
        f"Layer: {usd(layer.limit)} excess of {usd(layer.attachment)}",
        f"The limit is PER OCCURRENCE: any single claim cedes at most "
        f"{usd(layer.limit)}, and a claim larger than {usd(layer.top)} still cedes only "
        f"{usd(layer.limit)}.",
        f"Reinstatements: {reinst}",
        f"Annual aggregate cap: {usd(layer.aggregate_cap)} - the most the layer can pay "
        f"across a whole year. Several qualifying claims in one year can therefore take "
        f"the annual loss above the per-occurrence limit of {usd(layer.limit)}, which is "
        f"why tail statistics exceed it.",
        f"'Exhausted' below means the annual aggregate cap of {usd(layer.aggregate_cap)} "
        f"was reached, not that one full limit was used.",
        f"Annual aggregate deductible: {usd(layer.aad)}",
        f"Signed share: {pct(layer.share, 0)}",
        "",
        "## MODEL ASSUMPTIONS",
        f"Frequency: {freq.label}; mean {num(freq.mean)}, "
        f"variance-to-mean ratio {freq.dispersion:.2f}",
        f"Severity - attritional body: "
        f"{sev.components['body'].label if sev.components else sev.label}",
        f"Severity - large-loss tail: "
        f"{ctx['extreme'].label if ctx['extreme'] else 'none'}"
        + (f", applied to {pct(ctx['p_extreme'], 3)} of claims" if ctx["extreme"] else ""),
        f"Blended average claim: {usd(sev.mean)}",
        _tail_moments(ctx),
        f"P(a single claim exceeds the attachment): {float(sev.sf(layer.attachment)):.4e} "
        f"(one claim in {1 / max(float(sev.sf(layer.attachment)), 1e-15):,.0f})",
        f"Simulation: {res.n_iter:,} underwriting years, seed {res.seed}, "
        f"{'tail-thinned exact sampling' if res.mode == 'tail' else 'full ground-up sampling'}",
        "",
        "## SIMULATED RESULT (100% of layer)",
        f"Expected annual loss to layer: {usd(res.burning_cost)}",
        f"Monte Carlo standard error: {usd(res.std_error)} "
        f"({pct(res.rel_error, 3)} of the estimate)",
        f"Standard deviation of annual loss: {usd(res.volatility)} "
        f"(coefficient of variation {res.cv:.2f})",
        f"P(layer attaches): {pct(res.p_attach, 3)}",
        f"P(layer pays): {pct(res.p_pay, 3)}",
        f"P(at least one full per-occurrence limit consumed in a year): "
        f"{pct(res.p_full_limit, 3)}",
        f"P(annual aggregate cap reached, i.e. layer exhausted): {pct(res.p_exhaust, 3)}",
        f"Expected claims reaching the layer: {res.expected_claims_to_layer:.4f} per year",
        f"Average loss in a year that pays: {usd(res.mean_severity_to_layer)}",
        f"Share of gross cessions removed by aggregate features: {pct(res.cap_bite)}",
        f"Expected limits reinstated per year: {res.expected_reinstatements_used:.3f}",
        "",
        "## TAIL",
    ]
    for rp in (10, 25, 50, 100, 250):
        lines.append(f"1-in-{rp} year: VaR {usd(res.rp(rp))}, TVaR {usd(res.rp_tvar(rp))}")

    lines += [
        "",
        "## PRICING",
        f"Loadings: expense {pct(load.expense_ratio, 1)}, brokerage {pct(load.brokerage, 1)}, "
        f"cost of capital {pct(load.cost_of_capital, 1)}",
        f"Capital basis: TVaR {pct(load.capital_percentile, 2)} less expected loss, "
        f"{pct(load.diversification, 0)} allocated after diversification credit",
        f"Standalone capital: {usd(quote.standalone_capital)}; "
        f"allocated {usd(quote.capital)}; charge {usd(quote.capital_charge)}",
        f"Expected reinstatement income: {usd(quote.reinstatement_income)}",
        f"TECHNICAL PREMIUM (100%): {usd(quote.technical_premium)}",
        f"Rate on line: {pct(quote.rate_on_line)}",
        f"Loss on line: {pct(quote.loss_on_line)}",
        f"Expected loss ratio (on total income): {pct(quote.expected_loss_ratio)}",
        f"Premium as multiple of expected loss: {mult(quote.premium_to_loss)}",
        f"Payback period: {quote.payback_years:.1f} years",
        f"Premium as a rate on subject GEP: {pct(quote.subject_premium_rate, 3)}",
        f"Signed premium at {pct(layer.share, 0)}: {usd(quote.signed_premium)}",
        "",
        "## PREMIUM BUILD-UP",
    ]
    for label, amount, _kind in premium_build_up(quote):
        lines.append(f"{label}: {usd(amount)}")

    lines += ["", "## MODEL CLASSIFICATION", f"{kind} - {headline}"]

    diags = quote_diagnostics(res, quote, load)
    if diags:
        lines += ["", "## AUTOMATED DIAGNOSTICS ALREADY RAISED"]
        lines += [f"[{level}] {msg}" for level, msg in diags]

    stress = ctx.get("stress")
    if stress is not None:
        delta = ((stress.burning_cost / res.burning_cost - 1)
                 if res.burning_cost > 0 else float("nan"))
        lines += [
            "",
            "## STRESS SCENARIO RUN",
            f"Stressed expected annual loss: {usd(stress.burning_cost)} "
            f"({delta:+.1%} vs base)" if math.isfinite(delta)
            else f"Stressed expected annual loss: {usd(stress.burning_cost)}",
            f"Stressed P(exhaustion): {pct(stress.p_exhaust, 3)} "
            f"(base {pct(res.p_exhaust, 3)})",
            f"Stressed 1-in-100: {usd(stress.rp(100))} (base {usd(res.rp(100))})",
            f"Stressed 1-in-250: {usd(stress.rp(250))} (base {usd(res.rp(250))})",
            f"Levers: {stress.meta.get('lever_note', 'see app')}",
        ]

    return "\n".join(lines)


SYSTEM_RULES = """
You are commenting on the output of a Monte Carlo excess-of-loss pricing model.

RULES
1. Every figure you cite must come from the brief. Do not compute new numbers,
   do not estimate, and do not introduce market data, benchmarks or rates you
   were not given. If something you would want is missing, say it is missing.
2. Be specific. "The tail assumption is important" is worthless; "at alpha 2.3
   the tail drives 80% of a premium that is 4x expected loss, so a move to 2.0
   would be material" is useful.
3. Lead with the thing that matters most. Do not restate the brief back.
4. Where the automated diagnostics have already raised a point, either add
   something to it or leave it alone - do not simply repeat it.
5. No preamble, no sign-off, no "as an AI". Start with the substance.
6. British English. Reproduce currency amounts exactly as written in the brief,
   symbol included; never name a currency (no "pounds", no "dollars").
7. Read the STRUCTURE section carefully before calling anything inconsistent.
   Per-occurrence limits, annual aggregate caps and reinstatements interact, and
   an annual figure above the per-occurrence limit is normal, not an error.

FORMAT
Use these four sections as markdown level-4 headings, in this order:

#### Read
Two or three sentences: what this layer actually is and what the price says
about it.

#### Watch
The two or three assumptions or model choices that most affect the answer, and
what would happen if each were wrong. Be concrete about direction and rough
size.

#### Challenge
The strongest specific question you would put to whoever produced this, or the
weakest link in the analysis. One paragraph.

#### Next
Two to four concrete actions, as a bullet list. Each one a thing someone could
actually do this week.

Keep the whole response under 400 words.
""".strip()


# ---------------------------------------------------------------------------
#  Call
# ---------------------------------------------------------------------------
class AIError(RuntimeError):
    pass


def generate(ctx: dict, api_key: str, model: str = "gemini-2.5-flash",
             persona: str = DEFAULT_PERSONA,
             extra_question: str = "") -> tuple[str, dict]:
    """Ask Gemini for commentary. Returns (markdown, metadata)."""
    key = resolve_key(api_key)
    if not key:
        raise AIError("No Gemini API key configured.")

    brief = build_brief(ctx)
    persona_text = PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA])

    prompt = f"{persona_text}\n\n{SYSTEM_RULES}\n\n---\n\n{brief}"
    if extra_question.strip():
        prompt += (f"\n\n---\n\nThe reviewer has also asked specifically: "
                   f"{extra_question.strip()}\nAddress this within the format above, "
                   f"giving it priority in the 'Read' section.")

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "maxOutputTokens": 4096,
        },
    }

    url = f"{API_ROOT}/{model}:generateContent"
    try:
        resp = requests.post(
            url, params={"key": key},
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload), timeout=TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise AIError(f"Gemini did not respond within {TIMEOUT}s. Try again, or "
                      f"switch to a faster model.")
    except requests.exceptions.RequestException as exc:
        raise AIError(f"Could not reach Gemini: {exc}")

    if resp.status_code != 200:
        raise AIError(_explain_http_error(resp))

    try:
        data = resp.json()
    except ValueError:
        raise AIError("Gemini returned a response that was not JSON.")

    candidates = data.get("candidates") or []
    if not candidates:
        blocked = (data.get("promptFeedback") or {}).get("blockReason")
        raise AIError(f"Gemini returned no content{f' (blocked: {blocked})' if blocked else ''}.")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        reason = candidates[0].get("finishReason", "unknown")
        raise AIError(f"Gemini returned an empty response (finish reason: {reason}).")

    usage = data.get("usageMetadata") or {}
    meta = {
        "model": model,
        "persona": persona,
        "prompt_tokens": usage.get("promptTokenCount"),
        "output_tokens": usage.get("candidatesTokenCount"),
        "total_tokens": usage.get("totalTokenCount"),
    }
    return text, meta


def _explain_http_error(resp) -> str:
    """Turn Google's error payloads into something actionable."""
    try:
        err = (resp.json() or {}).get("error", {})
        message = err.get("message", "").strip()
        status = err.get("status", "")
    except ValueError:
        message, status = resp.text[:300], ""

    if resp.status_code in (400, 403) and ("API key" in message or "API_KEY" in status):
        return ("Gemini rejected the API key. Check it was copied in full from "
                "aistudio.google.com/apikey and that the Generative Language API is "
                "enabled for the project.")
    if resp.status_code == 404:
        return (f"Model not found. '{status or message}'. Try gemini-2.5-flash, which is "
                f"available on every key.")
    if resp.status_code == 429:
        return ("Rate limit or quota exhausted on this key. Wait a moment, or switch to "
                "gemini-2.5-flash which has a more generous free tier.")
    if resp.status_code >= 500:
        return f"Gemini is having trouble (HTTP {resp.status_code}). Try again shortly."
    return f"Gemini returned HTTP {resp.status_code}: {message or 'no detail given'}"


def verify_key(api_key: str) -> tuple[bool, str]:
    """Cheap round-trip to confirm a key works before the user relies on it."""
    key = resolve_key(api_key)
    if not key:
        return False, "No key provided."
    try:
        resp = requests.get(API_ROOT, params={"key": key}, timeout=20)
    except requests.exceptions.RequestException as exc:
        return False, f"Could not reach Gemini: {exc}"
    if resp.status_code == 200:
        try:
            names = [m.get("name", "").split("/")[-1] for m in resp.json().get("models", [])]
            gen = [n for n in names if n.startswith("gemini")]
            return True, f"Key valid - {len(gen)} Gemini models available."
        except ValueError:
            return True, "Key valid."
    return False, _explain_http_error(resp)


# ---------------------------------------------------------------------------
#  Rendering
# ---------------------------------------------------------------------------
def to_html(markdown_text: str) -> str:
    """Minimal, safe markdown to HTML for the commentary panel.

    Deliberately small: the model is instructed to emit headings, paragraphs,
    bold and bullets, and nothing else is rendered as markup.
    """
    text = markdown_text.replace("\r\n", "\n")
    text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    html: list[str] = []
    in_list = False
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            if in_list:
                html.append("</ul>")
                in_list = False
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            if in_list:
                html.append("</ul>")
                in_list = False
            level = min(len(heading.group(1)) + 1, 4)
            html.append(f"<h{max(level, 3)}>{heading.group(2)}</h{max(level, 3)}>")
            continue

        bullet = re.match(r"^[-*+]\s+(.*)$", line)
        if bullet:
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{bullet.group(1)}</li>")
            continue

        numbered = re.match(r"^\d+[.)]\s+(.*)$", line)
        if numbered:
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{numbered.group(1)}</li>")
            continue

        if in_list:
            html.append("</ul>")
            in_list = False
        html.append(f"<p>{line}</p>")

    if in_list:
        html.append("</ul>")
    return "\n".join(html)
