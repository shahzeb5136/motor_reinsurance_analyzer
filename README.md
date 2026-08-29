# RE:PRICER

**A Monte Carlo excess-of-loss pricing workbench for motor reinsurance.**

Prices an XoL layer from first principles — frequency and severity assumptions in,
simulated loss distribution and a defensible technical premium out — and explains
the answer twice: once for the actuary reviewing the work, and once for the person
who has to sign it off.

Built with Streamlit, NumPy, SciPy and Plotly. Optional AI commentary via Google Gemini.

---

## Running it

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

The app opens on **1 · Portfolio & Layer**. Press **Run pricing model** on page 3 and
everything downstream populates — a 100,000-year simulation takes about
two hundredths of a second.

### AI commentary (optional)

The app is fully functional without a key: every narrative on every page is generated
by the model itself, deterministically. The AI pass is an extra, independent read of
finished results.

To enable it, supply a [Google AI Studio key](https://aistudio.google.com/apikey) by
any of:

- pasting it into the sidebar (kept in the browser session only),
- setting `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the environment,
- creating `.streamlit/secrets.toml` with `GEMINI_API_KEY = "..."`.

---

## What it does

**Seven pages, each doing one job.**

| | |
|---|---|
| **1 · Portfolio & Layer** | The book being protected and the shape of the layer — attachment, limit, reinstatements, aggregate deductible, signed share. |
| **2 · Frequency & Severity** | Poisson or negative binomial claim counts; lognormal, gamma, Weibull, Pareto or Burr claim sizes, blended with a heavy-tailed large-loss population. |
| **3 · Simulation** | The Monte Carlo run, with analytic control totals and a convergence trace. |
| **4 · Results** | Loss distribution, exceedance curve, return periods, and the ten worst simulated years. |
| **5 · Pricing** | Expected loss → capital charge → expenses → reinstatement income → technical premium, plus a layer ladder showing how rate on line decays with attachment. |
| **6 · What-if** | A tornado over every driver, and a full stressed re-simulation. |
| **7 · Summary** | A self-contained pricing note, exportable to Markdown, with AI commentary. |

---

## How the engine works

### Tail-thinned sampling

A motor book produces thousands of claims a year and essentially none of them reach an
excess layer. Simulating 100,000 years of a 4,200-claim book means drawing 420 million
claims to learn about the twenty-odd that matter.

The default engine draws only the claims capable of reaching the attachment. This is
**exact, not an approximation**:

- each claim independently exceeds the attachment with probability `q = S(D)`, so the
  number that do is `Binomial(N, q)`;
- those claims are drawn from the exact conditional distribution `X | X > D`, by
  inverting the survival function — `S(X)` is uniform on `(0, q)` given `X > D`;
- for the two-component mixture, the conditional distribution is itself a mixture of the
  components conditioned above `D`, weighted by their survival at `D`.

Every layer statistic is identical to a full run. Ground-up loss, which depends on the
attritional claims that are deliberately not drawn, is reported at its closed form
`E[N] × E[X]`. Switch to **Full ground-up** sampling on page 3 to simulate every claim
and get the ground-up distribution too.

The speed-up is roughly 180×: 100,000 years in ~0.02s rather than ~7s.

### Validation

The simulation is checked against closed-form control totals, not just eyeballed:

```
E[annual cession]  =  E[N] × ( LEV(D+L) − LEV(D) )
```

where the limited expected values come from integrating the survival function directly,
which is accurate to machine precision against the Pareto closed form. Page 3 shows the
analytic total, the simulated total, and the gap between them. `tests/test_app.py`
asserts the gap stays inside the Monte Carlo standard error.

### Pricing

The premium equation solved is

```
P × (1 + c·k − e − b)  =  LC + rc × K
```

| | |
|---|---|
| `P` | deposit premium |
| `LC` | expected loss to the layer |
| `c` | reinstatement cost as a fraction of `P` |
| `k` | expected number of limits reinstated in a year |
| `e`, `b` | internal expense and brokerage ratios |
| `K` | allocated capital: `(TVaR_p − LC)` × diversification credit |
| `rc` | cost of capital |

Reinstatement premium is genuine income and reduces the deposit premium — which is why a
low-attaching layer with three reinstatements can price below its own expected loss, and
why the app flags that when it happens.

---

## Layout

```
app.py                  navigation, sidebar, masthead
repricer/
  distributions.py      severity and frequency models, exact mixtures
  engine.py             the Monte Carlo, both sampling modes
  pricing.py            loadings, reinstatements, diagnostics, classification
  charts.py             every figure
  narrative.py          deterministic executive summaries and the exported note
  ai.py                 Gemini client, brief construction, markdown rendering
  components.py         KPI tiles, ledgers, callouts, the plain-English bands
  state.py              session state, presets, model builders
  theme.py              palette, Plotly template, CSS
views/                  one module per page
tests/                  engine validation and page-render checks
```

---

## Tests

```bash
python tests/test_app.py
```

Eighteen checks covering distribution correctness against closed forms and empirical
samples, agreement between the two sampling modes, convergence to analytic control
totals, the premium equation balancing, and every page rendering in four states —
cold, tail-mode result, full-mode result with a stress, and a layer that never attaches.

Pages are exercised through `tests/page_harness.py` rather than `AppTest.switch_page`,
which only understands file-backed pages; this app builds its navigation from callables.

---

## Notes and limitations

- Figures are **technical estimates before market adjustment** — not a bound quotation.
- The large-loss tail parameter dominates the price. It deserves exposure analysis and
  market benchmarks, not a fit to attritional experience. The what-if page quantifies
  exactly how much it is worth.
- Claims are assumed independent within a year, with no clash or accumulation across
  risks, and no allowance for reporting delay or reserve development.
- Currency is a display setting only; no conversion is applied.
- Deep-linking straight to a page URL (`/pricing`) shows a spurious "Page not found"
  toast on Streamlit 1.38 before rendering correctly. Navigating from the sidebar is
  unaffected.

---

*Rebuilt in Python from an earlier R/Shiny prototype.*
