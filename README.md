# RE:PRICER — Reinsurance Layer Pricing Workbench

`RE:PRICER` is a high-performance Monte Carlo excess-of-loss (XoL) pricing engine designed for reinsurance actuaries. It simulates synthetic underwriting years to evaluate layer losses, burning costs, and tail volatility under customizable frequency, severity, and macro stress assumptions.

## Features

- **Ground-Up Portfolio Baseline:** Seed models using Gross Earned Premium (GEP), expected loss ratios, and claim counts.
- **Flexible Distribution Models:**
  - *Frequency:* Poisson, Negative Binomial (for overdispersion).
  - *Severity:* Lognormal, Gamma, Pareto (Type II/Lomax), Burr.
- **Blended Tail Modeling:** Piecewise mixture modeling that splits ordinary-claim bodies from heavy-tailed extreme Pareto populations.
- **Interactive Risk Analysis:** Generates Exceedance Probability (EP) curves, return-period/tail tables (up to 1-in-250 years), and visualizes ground-up vs. layer loss profiles.
- **What-If Stress Testing:** Real-time sensitivity adjustments for social/economic inflation, frequency spikes, and tail-share expansion using synchronized random seeds.
- **Executive Summaries:** Automated generation of technical pricing notes, Rates on Line (RoL), and volatility metrics.

## Requirements

The application runs on base R but enhances performance and distribution accuracy if `actuar` is available.

```r
install.packages(c("shiny", "bslib", "ggplot2", "scales", "DT"))
install.packages("actuar") # Optional, enables advanced Burr distribution features
```
