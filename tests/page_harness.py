"""
A one-page stand-in for app.py so the test suite can exercise each view.

``AppTest.switch_page`` only understands file-backed pages, and this app
builds its navigation from callables. Rather than test something other than
what ships, this harness sets up exactly the same theme and session state and
then calls one view directly, chosen by ``__page__`` in session state.
"""
from __future__ import annotations

import pathlib
import sys

import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="harness", layout="wide")

from repricer import components as C, state as S  # noqa: E402
from repricer.theme import apply_theme  # noqa: E402
from views import (distributions, portfolio, pricing, results, simulation,  # noqa: E402
                   summary, whatif)

apply_theme()
S.init_state()

VIEWS = {
    "portfolio": portfolio.render,
    "distributions": distributions.render,
    "simulation": simulation.render,
    "results": results.render,
    "pricing": pricing.render,
    "whatif": whatif.render,
    "summary": summary.render,
}

C.masthead([("harness", "on")])
VIEWS[st.session_state.get("__page__", "portfolio")]()
