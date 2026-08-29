"""
Visual identity for RE:PRICER.

A single place for the palette, the Plotly template and the CSS that turns
Streamlit's default chrome into something that reads like an actuarial
workbench rather than a dashboard toy.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---------------------------------------------------------------------------
#  Palette - deep slate, ledger ink, a single amber accent
# ---------------------------------------------------------------------------
INK = "#0B0E13"        # page background
PANEL = "#12171F"      # card surface
PANEL_2 = "#1A212B"    # raised surface
PANEL_3 = "#212A36"    # input surface
LINE = "#28323F"       # hairline rules
LINE_SOFT = "#1F2733"  # very quiet divider

MUTED = "#8A96A6"      # secondary text
TEXT_DIM = "#B7C2CF"   # body text
TEXT = "#E9EFF6"       # primary text

ACCENT = "#E8A33D"     # amber - the one accent
ACCENT_HI = "#F6BC64"
TEAL = "#4CB5AE"       # secondary series
VIOLET = "#8E7CE8"     # tertiary series
DANGER = "#E5646E"     # stress / tail
GOOD = "#4FBF87"       # favourable

RETAIN = "#3E4C5E"     # cedant retention block
LAYER = ACCENT         # reinsurance layer block
XS_BAND = "#5A6878"    # excess of layer block

SERIES = [ACCENT, TEAL, VIOLET, DANGER, GOOD, XS_BAND]

FONT_SANS = "'Inter', 'Segoe UI', system-ui, sans-serif"
FONT_HEAD = "'Space Grotesk', 'Inter', system-ui, sans-serif"
FONT_MONO = "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace"


# ---------------------------------------------------------------------------
#  Number formatting
# ---------------------------------------------------------------------------
def _cur() -> str:
    """Currency symbol. Falls back to '$' outside a Streamlit run so the
    formatters stay usable from scripts and the report exporter."""
    try:
        return st.session_state.get("currency_symbol", "$")
    except Exception:
        return "$"


def usd(x, dp: int = 0) -> str:
    """Full-precision currency, e.g. $1,240,000."""
    if x is None:
        return "-"
    x = float(x)
    if math.isnan(x):
        return "-"
    if math.isinf(x):
        return "unbounded"
    return f"{_cur()}{x:,.{dp}f}"


def usd_short(x, dp: int = 2) -> str:
    """Short-scale currency, e.g. $1.24m, $840k, $2.10bn."""
    if x is None:
        return "-"
    x = float(x)
    if math.isnan(x):
        return "-"
    if math.isinf(x):
        return "unbounded"
    sign = "-" if x < 0 else ""
    a = abs(x)
    if a >= 1e9:
        return f"{sign}{_cur()}{a / 1e9:,.{dp}f}bn"
    if a >= 1e6:
        return f"{sign}{_cur()}{a / 1e6:,.{dp}f}m"
    if a >= 1e3:
        return f"{sign}{_cur()}{a / 1e3:,.0f}k"
    return f"{sign}{_cur()}{a:,.0f}"


def pct(x, dp: int = 1) -> str:
    if x is None:
        return "-"
    x = float(x)
    if math.isnan(x):
        return "-"
    return f"{x * 100:,.{dp}f}%"


def num(x, dp: int = 0) -> str:
    if x is None:
        return "-"
    x = float(x)
    if math.isnan(x):
        return "-"
    if math.isinf(x):
        return "inf"
    return f"{x:,.{dp}f}"


def mult(x, dp: int = 1) -> str:
    if x is None:
        return "-"
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return "-"
    return f"{x:,.{dp}f}x"


def years(x, dp: int = 1) -> str:
    """A period in years. Unbounded when the premium is zero, which happens
    for a layer nothing can reach."""
    if x is None:
        return "-"
    x = float(x)
    if math.isnan(x) or math.isinf(x) or x > 10_000:
        return "never"
    return f"{x:,.{dp}f} years"


def signed_pct(x, dp: int = 1) -> str:
    if x is None:
        return "-"
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return "-"
    return f"{x * 100:+,.{dp}f}%"


# ---------------------------------------------------------------------------
#  Plotly template
# ---------------------------------------------------------------------------
def register_template() -> None:
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_SANS, size=12.5, color=TEXT_DIM),
        title=dict(font=dict(family=FONT_HEAD, size=15, color=TEXT), x=0, xanchor="left"),
        margin=dict(l=10, r=16, t=46, b=10),
        colorway=SERIES,
        hoverlabel=dict(
            bgcolor=PANEL_2,
            bordercolor=LINE,
            font=dict(family=FONT_MONO, size=12, color=TEXT),
        ),
        xaxis=dict(
            gridcolor=LINE_SOFT, zerolinecolor=LINE, linecolor=LINE,
            tickfont=dict(size=11, color=MUTED),
            title=dict(font=dict(size=11.5, color=MUTED)),
            showline=True, ticks="outside", tickcolor=LINE, ticklen=4,
        ),
        yaxis=dict(
            gridcolor=LINE_SOFT, zerolinecolor=LINE, linecolor=LINE,
            tickfont=dict(size=11, color=MUTED),
            title=dict(font=dict(size=11.5, color=MUTED)),
            showline=False, ticks="",
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
            font=dict(size=11.5, color=MUTED),
            orientation="h", y=1.06, x=0, xanchor="left", yanchor="bottom",
        ),
        bargap=0.04,
    )
    pio.templates["repricer"] = tpl
    pio.templates.default = "repricer"


PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "lasso2d", "select2d", "autoScale2d", "toggleSpikelines",
        "hoverClosestCartesian", "hoverCompareCartesian",
    ],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


# ---------------------------------------------------------------------------
#  CSS
# ---------------------------------------------------------------------------
def _css() -> str:
    return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --ink:__INK__; --panel:__PANEL__; --panel2:__PANEL_2__; --panel3:__PANEL_3__;
  --line:__LINE__; --line-soft:__LINE_SOFT__;
  --muted:__MUTED__; --dim:__TEXT_DIM__; --text:__TEXT__;
  --accent:__ACCENT__; --accent-hi:__ACCENT_HI__; --teal:__TEAL__;
  --danger:__DANGER__; --good:__GOOD__; --violet:__VIOLET__;
  --mono:__FONT_MONO__; --head:__FONT_HEAD__; --sans:__FONT_SANS__;
}

/* ---------- shell ---------- */
.stApp {
  background:
    radial-gradient(1200px 600px at 12% -10%, #17202B 0%, rgba(23,32,43,0) 60%),
    radial-gradient(900px 500px at 100% 0%, #1A1710 0%, rgba(26,23,16,0) 55%),
    __INK__;
  color: __TEXT_DIM__;
  font-family: __FONT_SANS__;
}
html, body, [class*="css"] { font-family: __FONT_SANS__; letter-spacing:.1px; }

.block-container { padding-top: 2.4rem; padding-bottom: 3.5rem; max-width: 1580px; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stDecoration"] { display:none; }

/* Streamlit's own header is an opaque fixed bar that sits on top of the first
   rows of the page. Left alone it clips the masthead. Collapse it to nothing
   and keep only the toolbar floating above the content. */
header[data-testid="stHeader"] {
  background: transparent !important;
  height: 0 !important;
  min-height: 0 !important;
  z-index: 90;
}
header[data-testid="stHeader"]::before,
header[data-testid="stHeader"]::after { display: none !important; }
[data-testid="stToolbar"] { right: .75rem; top: .35rem; z-index: 95; }
[data-testid="stStatusWidget"] { z-index: 95; }
/* the sidebar collapse control must stay clickable above the masthead */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] { top: .5rem; z-index: 95; }

h1,h2,h3,h4,h5 { font-family:__FONT_HEAD__ !important; color:__TEXT__ !important;
  letter-spacing:-.2px; font-weight:600; }
a { color: __ACCENT__; text-decoration: none; }
a:hover { color: __ACCENT_HI__; }
hr { border-color:__LINE__ !important; margin:.9rem 0 !important; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background:__PANEL__; border-right:1px solid __LINE__; }
[data-testid="stSidebar"] .block-container { padding-top: .8rem; }
[data-testid="stSidebarNav"] { padding-top:.2rem; }
[data-testid="stSidebarNav"] a { border-radius:6px; margin:1px 6px; padding:5px 10px !important; }
[data-testid="stSidebarNav"] a span { font-family:__FONT_MONO__ !important; font-size:12px !important;
  letter-spacing:.4px; color:__MUTED__ !important; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background:__PANEL_3__ !important;
  box-shadow: inset 2px 0 0 __ACCENT__; }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color:__TEXT__ !important; }

/* ---------- masthead ---------- */
.rp-head { display:flex; align-items:center; gap:16px; padding:10px 18px 12px;
  border-bottom:1px solid __LINE__; margin:0 0 18px;
  background:linear-gradient(90deg, rgba(232,163,61,.055), rgba(232,163,61,0) 55%); }
.rp-mark { font-family:__FONT_HEAD__; font-weight:700; font-size:22px; letter-spacing:.5px;
  color:__TEXT__; line-height:1; white-space:nowrap; }
.rp-mark b { color:__ACCENT__; }
.rp-rule { width:1px; height:26px; background:__LINE__; }
.rp-tag { font-family:__FONT_MONO__; font-size:10.5px; letter-spacing:2.2px;
  text-transform:uppercase; color:__MUTED__; }
.rp-spacer { flex:1; }
.rp-chip { font-family:__FONT_MONO__; font-size:10.5px; letter-spacing:1px; text-transform:uppercase;
  color:__MUTED__; background:__PANEL_2__; border:1px solid __LINE__; border-radius:999px;
  padding:4px 11px; white-space:nowrap; }
.rp-chip.on { color:__INK__; background:__ACCENT__; border-color:__ACCENT__; font-weight:600; }
.rp-chip.live { color:__GOOD__; border-color:#2C4A3C; background:#131E19; }

/* ---------- page title ---------- */
.rp-title { display:flex; align-items:baseline; gap:14px; margin:2px 0 4px; }
.rp-title .n { font-family:__FONT_MONO__; font-size:11px; color:__ACCENT__; letter-spacing:2px; }
.rp-title .t { font-family:__FONT_HEAD__; font-size:25px; font-weight:600; color:__TEXT__;
  letter-spacing:-.3px; }
.rp-lede { color:__MUTED__; font-size:13.5px; line-height:1.6; max-width:96ch; margin:0 0 14px; }

/* ---------- section label ---------- */
.rp-sec { font-family:__FONT_MONO__; font-size:10.5px; letter-spacing:2px; text-transform:uppercase;
  color:__MUTED__; margin:18px 0 8px; display:flex; align-items:center; gap:10px; }
.rp-sec::after { content:""; flex:1; height:1px; background:__LINE__; }

/* ---------- cards ---------- */
.rp-card { background:__PANEL__; border:1px solid __LINE__; border-radius:9px; overflow:hidden; }
.rp-card > .hd { font-family:__FONT_MONO__; font-size:10.5px; letter-spacing:1.6px;
  text-transform:uppercase; color:__MUTED__; padding:10px 15px; background:__PANEL_2__;
  border-bottom:1px solid __LINE__; }
.rp-card > .bd { padding:14px 15px; }

/* ---------- KPI tiles ---------- */
.rp-kpi { background:linear-gradient(160deg,__PANEL_2__ 0%, __PANEL__ 100%);
  border:1px solid __LINE__; border-radius:9px; padding:13px 15px 14px; height:100%;
  position:relative; overflow:hidden; }
.rp-kpi::before { content:""; position:absolute; left:0; top:0; bottom:0; width:2px;
  background:__LINE__; }
.rp-kpi.accent::before { background:__ACCENT__; }
.rp-kpi.teal::before { background:__TEAL__; }
.rp-kpi.danger::before { background:__DANGER__; }
.rp-kpi.good::before { background:__GOOD__; }
.rp-kpi .lbl { font-family:__FONT_MONO__; font-size:9.8px; letter-spacing:1.4px;
  text-transform:uppercase; color:__MUTED__; line-height:1.4; }
.rp-kpi .val { font-family:__FONT_HEAD__; font-size:27px; font-weight:700; color:__TEXT__;
  line-height:1.12; margin-top:6px; letter-spacing:-.6px; }
.rp-kpi.accent .val { color:__ACCENT__; }
.rp-kpi.danger .val { color:__DANGER__; }
.rp-kpi.teal .val { color:__TEAL__; }
.rp-kpi.good .val { color:__GOOD__; }
.rp-kpi .sub { font-size:11.5px; color:__MUTED__; margin-top:5px; line-height:1.45; }
.rp-kpi .dlt { font-family:__FONT_MONO__; font-size:11px; margin-top:5px; }
.rp-kpi .dlt.up { color:__DANGER__; }
.rp-kpi .dlt.down { color:__GOOD__; }
.rp-kpi .dlt.flat { color:__MUTED__; }

/* ---------- ledger rows ---------- */
.rp-ledger { font-family:__FONT_MONO__; font-size:12.5px; }
.rp-ledger .r { display:flex; justify-content:space-between; gap:16px; padding:7px 0;
  border-bottom:1px dashed __LINE__; }
.rp-ledger .r:last-child { border-bottom:none; }
.rp-ledger .k { color:__MUTED__; }
.rp-ledger .v { color:__TEXT__; text-align:right; white-space:nowrap; }
.rp-ledger .v.accent { color:__ACCENT__; }
.rp-ledger .v.danger { color:__DANGER__; }
.rp-ledger .v.good { color:__GOOD__; }
.rp-ledger .v.muted { color:__MUTED__; }
.rp-ledger .r.total { border-top:1px solid __LINE__; border-bottom:none; margin-top:4px;
  padding-top:10px; }
.rp-ledger .r.total .k { color:__TEXT__; font-weight:600; }
.rp-ledger .r.total .v { color:__ACCENT__; font-weight:600; font-size:14px; }

/* ---------- executive band ---------- */
.rp-exec { background:linear-gradient(90deg, rgba(232,163,61,.075), rgba(232,163,61,.015) 70%);
  border:1px solid #33291A; border-left:3px solid __ACCENT__; border-radius:8px;
  padding:14px 18px 15px; margin:2px 0 16px; }
.rp-exec .eyebrow { font-family:__FONT_MONO__; font-size:10px; letter-spacing:2px;
  text-transform:uppercase; color:__ACCENT__; margin-bottom:7px; }
.rp-exec p { color:__TEXT_DIM__; font-size:14px; line-height:1.68; margin:0 0 9px; }
.rp-exec p:last-child { margin-bottom:0; }
.rp-exec b { color:__TEXT__; font-weight:600; }
.rp-exec .num { font-family:__FONT_MONO__; color:__ACCENT__; font-weight:500; }

/* ---------- prose ---------- */
.rp-prose p { color:__TEXT_DIM__; font-size:14px; line-height:1.72; margin:0 0 12px; }
.rp-prose p.lead { font-size:15.5px; color:__TEXT__; }
.rp-prose b { color:__TEXT__; font-weight:600; }
.rp-prose .num { font-family:__FONT_MONO__; color:__ACCENT__; }
.rp-note { color:__MUTED__; font-size:12.5px; line-height:1.62; }
.rp-note b { color:__TEXT_DIM__; }

/* ---------- callouts ---------- */
.rp-flag { border-radius:7px; padding:10px 14px; font-size:13px; line-height:1.6;
  margin:8px 0; border:1px solid; display:flex; gap:10px; align-items:flex-start; }
.rp-flag .ic { font-family:__FONT_MONO__; font-weight:600; flex:0 0 auto; }
.rp-flag.warn { background:#1F1809; border-color:#4A3A16; color:#E9C583; }
.rp-flag.warn .ic { color:__ACCENT__; }
.rp-flag.danger { background:#1F1113; border-color:#4A2429; color:#EFA5AB; }
.rp-flag.danger .ic { color:__DANGER__; }
.rp-flag.info { background:#0F1A1A; border-color:#204442; color:#9FD6D1; }
.rp-flag.info .ic { color:__TEAL__; }
.rp-flag.good { background:#101D16; border-color:#22452F; color:#9BD9B6; }
.rp-flag.good .ic { color:__GOOD__; }

/* ---------- verdict badge ---------- */
.rp-verdict { display:inline-flex; align-items:center; gap:9px; border-radius:999px;
  padding:6px 15px 6px 12px; font-family:__FONT_HEAD__; font-weight:600; font-size:13.5px;
  border:1px solid; }
.rp-verdict .dot { width:8px; height:8px; border-radius:50%; }
.rp-verdict.high { color:__DANGER__; border-color:#4A2429; background:#1C1013; }
.rp-verdict.high .dot { background:__DANGER__; box-shadow:0 0 9px __DANGER__; }
.rp-verdict.elev { color:__ACCENT__; border-color:#463618; background:#1C1710; }
.rp-verdict.elev .dot { background:__ACCENT__; box-shadow:0 0 9px __ACCENT__; }
.rp-verdict.mod { color:__TEAL__; border-color:#204442; background:#101A1A; }
.rp-verdict.mod .dot { background:__TEAL__; box-shadow:0 0 9px __TEAL__; }
.rp-verdict.none { color:__MUTED__; border-color:__LINE__; background:__PANEL_2__; }
.rp-verdict.none .dot { background:__MUTED__; }

/* ---------- AI panel ---------- */
.rp-ai { background:linear-gradient(150deg, #141A22 0%, #12161D 100%);
  border:1px solid #263243; border-radius:9px; overflow:hidden; }
.rp-ai .hd { display:flex; align-items:center; gap:9px; padding:9px 15px;
  background:linear-gradient(90deg, rgba(142,124,232,.13), rgba(76,181,174,.06));
  border-bottom:1px solid #263243; }
.rp-ai .hd .t { font-family:__FONT_MONO__; font-size:10.5px; letter-spacing:1.8px;
  text-transform:uppercase; color:#B9AEF3; }
.rp-ai .hd .m { font-family:__FONT_MONO__; font-size:10px; color:__MUTED__; margin-left:auto; }
.rp-ai .bd { padding:14px 17px 15px; }
.rp-ai .bd p { color:__TEXT_DIM__; font-size:13.8px; line-height:1.7; margin:0 0 11px; }
.rp-ai .bd p:last-child { margin-bottom:0; }
.rp-ai .bd b, .rp-ai .bd strong { color:__TEXT__; font-weight:600; }
.rp-ai .bd h3, .rp-ai .bd h4 { font-family:__FONT_MONO__ !important; font-size:11px !important;
  letter-spacing:1.5px; text-transform:uppercase; color:#B9AEF3 !important;
  margin:15px 0 7px !important; font-weight:600 !important; }
.rp-ai .bd ul, .rp-ai .bd ol { margin:0 0 11px; padding-left:19px; }
.rp-ai .bd li { color:__TEXT_DIM__; font-size:13.6px; line-height:1.62; margin-bottom:5px; }
.rp-ai .bd em { color:__MUTED__; }
.rp-ai .bd table { width:100%; border-collapse:collapse; font-family:__FONT_MONO__;
  font-size:12.2px; margin:4px 0 12px; }
.rp-ai .bd th { text-align:left; color:__MUTED__; border-bottom:1px solid #263243;
  padding:5px 8px; font-weight:500; }
.rp-ai .bd td { padding:5px 8px; border-bottom:1px dashed #1E2530; color:__TEXT_DIM__; }
.rp-ai .ft { font-family:__FONT_MONO__; font-size:9.8px; color:__MUTED__; padding:8px 17px 11px;
  border-top:1px solid #1E2530; letter-spacing:.4px; }

/* ---------- inputs ---------- */
[data-testid="stSidebar"] label, .stTextInput label, .stNumberInput label,
.stSelectbox label, .stSlider label, .stRadio label, .stCheckbox label {
  font-size:12px !important; color:__MUTED__ !important; font-weight:500 !important; }
.stNumberInput input, .stTextInput input, .stTextArea textarea {
  background:__PANEL_3__ !important; color:__TEXT__ !important; border:1px solid __LINE__ !important;
  font-family:__FONT_MONO__ !important; font-size:13px !important; border-radius:6px !important; }
.stNumberInput input:focus, .stTextInput input:focus { border-color:__ACCENT__ !important;
  box-shadow:0 0 0 2px rgba(232,163,61,.16) !important; }
[data-baseweb="select"] > div { background:__PANEL_3__ !important; border-color:__LINE__ !important;
  font-family:__FONT_MONO__ !important; font-size:13px !important; border-radius:6px !important; }
[data-baseweb="popover"] li { font-family:__FONT_MONO__ !important; font-size:12.5px !important; }
[data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {
  background:__PANEL_3__ !important; border-color:__LINE__ !important; }

/* sliders */
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
  background:__ACCENT__ !important; border-color:__ACCENT__ !important; }
[data-testid="stTickBar"] { font-family:__FONT_MONO__; font-size:10px; color:__MUTED__; }
[data-testid="stThumbValue"] { font-family:__FONT_MONO__ !important; font-size:11.5px !important;
  color:__ACCENT__ !important; }

/* buttons */
.stButton > button, .stDownloadButton > button {
  font-family:__FONT_MONO__ !important; font-size:11.5px !important; font-weight:600 !important;
  letter-spacing:1.1px; text-transform:uppercase; border-radius:6px !important;
  border:1px solid __LINE__ !important; background:__PANEL_3__ !important;
  color:__TEXT_DIM__ !important; transition:all .13s ease; padding:.5rem 1rem !important; }
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color:__ACCENT__ !important; color:__ACCENT__ !important; background:__PANEL_2__ !important; }
.stButton > button[kind="primary"] { background:__ACCENT__ !important; color:__INK__ !important;
  border-color:__ACCENT__ !important; }
.stButton > button[kind="primary"]:hover { background:__ACCENT_HI__ !important;
  color:__INK__ !important; }

/* tabs */
.stTabs [data-baseweb="tab-list"] { gap:2px; border-bottom:1px solid __LINE__; }
.stTabs [data-baseweb="tab"] { font-family:__FONT_MONO__; font-size:11.5px; letter-spacing:.9px;
  text-transform:uppercase; color:__MUTED__; background:transparent; padding:9px 15px;
  border-radius:6px 6px 0 0; }
.stTabs [aria-selected="true"] { color:__ACCENT__ !important; background:__PANEL__ !important;
  box-shadow: inset 0 -2px 0 __ACCENT__; }
.stTabs [data-baseweb="tab-highlight"] { background:transparent !important; }

/* expander */
[data-testid="stExpander"] { border:1px solid __LINE__ !important; border-radius:8px !important;
  background:__PANEL__ !important; }
[data-testid="stExpander"] summary { font-family:__FONT_MONO__ !important;
  font-size:11.5px !important; letter-spacing:.9px; color:__MUTED__ !important; }
[data-testid="stExpander"] summary:hover { color:__ACCENT__ !important; }

/* dataframe */
[data-testid="stDataFrame"] { border:1px solid __LINE__; border-radius:8px; }
[data-testid="stDataFrame"] * { font-family:__FONT_MONO__ !important; font-size:12.3px !important; }

/* metrics / progress */
[data-testid="stMetricValue"] { font-family:__FONT_HEAD__ !important; color:__TEXT__ !important; }
.stProgress > div > div > div { background:__ACCENT__ !important; }

/* alerts */
[data-testid="stAlert"] { border-radius:7px; font-size:13px; }

/* plotly */
.js-plotly-plot .plotly .modebar { background:transparent !important; }
.js-plotly-plot .plotly .modebar-btn path { fill:__MUTED__ !important; }

/* misc */
.rp-mono { font-family:__FONT_MONO__; font-size:12px; color:__MUTED__; }
.rp-foot { font-family:__FONT_MONO__; font-size:10px; color:__MUTED__; text-align:center;
  padding:26px 0 8px; letter-spacing:.5px; line-height:1.8; border-top:1px solid __LINE_SOFT__;
  margin-top:34px; }
.rp-gap { height:14px; }
.rp-gap-s { height:7px; }
</style>
"""


_TOKENS = {
    "__INK__": INK, "__PANEL__": PANEL, "__PANEL_2__": PANEL_2, "__PANEL_3__": PANEL_3,
    "__LINE__": LINE, "__LINE_SOFT__": LINE_SOFT, "__MUTED__": MUTED,
    "__TEXT_DIM__": TEXT_DIM, "__TEXT__": TEXT, "__ACCENT_HI__": ACCENT_HI,
    "__ACCENT__": ACCENT, "__TEAL__": TEAL, "__DANGER__": DANGER, "__GOOD__": GOOD,
    "__VIOLET__": VIOLET, "__FONT_MONO__": FONT_MONO, "__FONT_HEAD__": FONT_HEAD,
    "__FONT_SANS__": FONT_SANS,
}


def apply_theme() -> None:
    """Inject CSS and register the Plotly template. Call once per rerun."""
    css = _css()
    for token, value in _TOKENS.items():
        css = css.replace(token, value)
    st.markdown(css, unsafe_allow_html=True)
    register_template()
