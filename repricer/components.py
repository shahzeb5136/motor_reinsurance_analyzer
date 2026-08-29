"""
Small UI building blocks shared across the pages.

Streamlit gives you widgets; it does not give you a house style. These
helpers are that style - KPI tiles, ledgers, callouts, the executive band and
the AI panel - so no page has to hand-roll HTML.
"""
from __future__ import annotations

import html as _html

import streamlit as st

from . import theme as T

_ICONS = {"warn": "!", "danger": "!!", "info": "i", "good": "+"}


# ---------------------------------------------------------------------------
#  Page furniture
# ---------------------------------------------------------------------------
def masthead(chips: list[tuple[str, str]] | None = None) -> None:
    """The bar across the top of every page."""
    bits = [
        '<div class="rp-head">',
        '<div class="rp-mark">RE:<b>PRICER</b></div>',
        '<div class="rp-rule"></div>',
        '<div class="rp-tag">excess-of-loss pricing workbench</div>',
        '<div class="rp-spacer"></div>',
    ]
    for text, kind in (chips or []):
        bits.append(f'<div class="rp-chip {kind}">{_html.escape(text)}</div>')
    bits.append("</div>")
    st.markdown("".join(bits), unsafe_allow_html=True)


def page_title(number: str, title: str, lede: str = "") -> None:
    st.markdown(
        f'<div class="rp-title"><span class="n">{_html.escape(number)}</span>'
        f'<span class="t">{_html.escape(title)}</span></div>'
        + (f'<p class="rp-lede">{lede}</p>' if lede else ""),
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    st.markdown(f'<div class="rp-sec">{_html.escape(label)}</div>', unsafe_allow_html=True)


def gap(small: bool = False) -> None:
    st.markdown(f'<div class="rp-gap{"-s" if small else ""}"></div>', unsafe_allow_html=True)


def footer(text: str) -> None:
    st.markdown(f'<div class="rp-foot">{text}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Content blocks
# ---------------------------------------------------------------------------
def kpi(label: str, value: str, sub: str = "", tone: str = "",
        delta: str = "", delta_dir: str = "flat") -> None:
    parts = [f'<div class="rp-kpi {tone}">',
             f'<div class="lbl">{_html.escape(label)}</div>',
             f'<div class="val">{_html.escape(value)}</div>']
    if delta:
        parts.append(f'<div class="dlt {delta_dir}">{_html.escape(delta)}</div>')
    if sub:
        parts.append(f'<div class="sub">{sub}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def kpi_row(tiles: list[dict]) -> None:
    cols = st.columns(len(tiles), gap="small")
    for col, tile in zip(cols, tiles):
        with col:
            kpi(**tile)


def ledger(rows: list[tuple], title: str | None = None) -> None:
    """Key/value rows in a monospaced ledger.

    Each row is (key, value) or (key, value, css_class); a key of ``None``
    renders a total line.
    """
    parts = []
    if title:
        parts.append(f'<div class="rp-sec" style="margin-top:0">{_html.escape(title)}</div>')
    parts.append('<div class="rp-ledger">')
    for row in rows:
        key, value = row[0], row[1]
        cls = row[2] if len(row) > 2 else ""
        total = "total" if cls == "total" else ""
        vcls = "" if total else cls
        parts.append(
            f'<div class="r {total}"><span class="k">{key}</span>'
            f'<span class="v {vcls}">{value}</span></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def card(title: str, body_html: str) -> None:
    st.markdown(
        f'<div class="rp-card"><div class="hd">{_html.escape(title)}</div>'
        f'<div class="bd">{body_html}</div></div>',
        unsafe_allow_html=True,
    )


def flag(kind: str, text: str) -> None:
    st.markdown(
        f'<div class="rp-flag {kind}"><span class="ic">{_ICONS.get(kind, "i")}</span>'
        f'<span>{text}</span></div>',
        unsafe_allow_html=True,
    )


def flags(items: list[tuple[str, str]]) -> None:
    for kind, text in items:
        flag(kind, text)


def verdict_badge(level: str, text: str) -> None:
    st.markdown(
        f'<div class="rp-verdict {level}"><span class="dot"></span>'
        f'<span>{_html.escape(text)}</span></div>',
        unsafe_allow_html=True,
    )


def exec_band(paragraphs: list[str], eyebrow: str = "In plain terms") -> None:
    """The amber band that translates the technical content above it."""
    if not st.session_state.get("show_plain_english", True):
        return
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    st.markdown(
        f'<div class="rp-exec"><div class="eyebrow">{_html.escape(eyebrow)}</div>{body}</div>',
        unsafe_allow_html=True,
    )


def guide(key: str) -> None:
    """Render the page's plain-English explainer from :mod:`narrative`."""
    from .narrative import GUIDES

    entry = GUIDES.get(key)
    if entry:
        exec_band([entry[1]], eyebrow=entry[0])


def prose(paragraphs: list[str], lead_first: bool = True) -> None:
    body = []
    for i, para in enumerate(paragraphs):
        cls = ' class="lead"' if (lead_first and i == 0) else ""
        body.append(f"<p{cls}>{para}</p>")
    st.markdown(f'<div class="rp-prose">{"".join(body)}</div>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="rp-note">{text}</div>', unsafe_allow_html=True)


def ai_panel(body_html: str, model: str, tokens: str = "", persona: str = "") -> None:
    head = f'<div class="hd"><span class="t">AI commentary</span>'
    if persona:
        head += f'<span class="m">{_html.escape(persona)}</span>'
    head += "</div>"
    foot = (f'<div class="ft">Generated by {_html.escape(model)}'
            + (f" · {_html.escape(tokens)}" if tokens else "")
            + " · Commentary on model output, not independent advice. "
              "Every figure is taken from the simulation above.</div>")
    st.markdown(f'<div class="rp-ai">{head}<div class="bd">{body_html}</div>{foot}</div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Gating
# ---------------------------------------------------------------------------
def needs_run(message: str = "") -> None:
    """The placeholder shown on pages that require a simulation."""
    flag("info", message or (
        "No simulation has been run yet. Open <b>3 · Simulation</b> and press "
        "<b>Run pricing model</b> - it takes a fraction of a second."))


def chart(fig, key: str | None = None, height: int | None = None) -> None:
    from .theme import PLOTLY_CONFIG

    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, key=key)


# ---------------------------------------------------------------------------
#  Inputs
# ---------------------------------------------------------------------------
def money_m(label: str, key: str, step: float = 0.25, min_value: float = 0.0,
            on_change=None, help: str | None = None, disabled: bool = False) -> None:
    """A currency input expressed in millions.

    Layer terms are quoted in millions in every submission and slip, and a raw
    ``6000000`` in a box is genuinely harder to read than ``6.00``. State is
    still stored in absolute units; only the widget works in millions.
    """
    display_key = f"{key}__m"
    shadow_key = f"{key}__shadow"

    absolute = float(st.session_state.get(key, 0.0))
    # Re-derive the displayed value whenever the underlying figure was changed
    # from somewhere else - loading a preset, for instance.
    if display_key not in st.session_state or st.session_state.get(shadow_key) != absolute:
        st.session_state[display_key] = round(absolute / 1e6, 6)
        st.session_state[shadow_key] = absolute

    def _sync() -> None:
        value = float(st.session_state[display_key]) * 1e6
        st.session_state[key] = value
        st.session_state[shadow_key] = value
        if on_change is not None:
            on_change()

    unit = st.session_state.get("currency_symbol", "$")
    st.number_input(
        f"{label} ({unit}m)", key=display_key, min_value=min_value / 1e6,
        step=step, format="%.2f", on_change=_sync, help=help, disabled=disabled,
    )
