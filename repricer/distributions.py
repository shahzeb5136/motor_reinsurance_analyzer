"""
Frequency and severity models.

Every severity model exposes the same surface - ``sample``, ``cdf``, ``sf``,
``quantile``, ``mean`` - so the rest of the engine never has to know whether
it is holding a lognormal, a Burr, or a two-component mixture.

Parameterisations are chosen to be the ones underwriters actually quote:
severities by mean and standard deviation where possible, frequency by mean
and a variance-to-mean (contagion) factor rather than the (size, prob) pair
that numpy and R expose.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy import special

Array = np.ndarray

SEVERITY_FAMILIES = ["Lognormal", "Gamma", "Weibull", "Pareto", "Burr"]
FREQUENCY_FAMILIES = ["Poisson", "Negative Binomial"]


# ===========================================================================
#  Severity
# ===========================================================================
@dataclass
class Severity:
    """A claim-size distribution."""

    family: str
    label: str
    params: dict
    _sample: Callable[[int, np.random.Generator], Array]
    _cdf: Callable[[Array], Array]
    _quantile: Callable[[Array], Array]
    _isf: Callable[[Array], Array]
    mean: float
    variance: float = float("nan")
    components: dict = field(default_factory=dict)

    # -- core surface ------------------------------------------------------
    def sample(self, n: int, rng: np.random.Generator) -> Array:
        if n <= 0:
            return np.empty(0)
        return self._sample(int(n), rng)

    def cdf(self, x):
        return self._cdf(np.asarray(x, dtype=float))

    def sf(self, x):
        """Survival function - P(X > x). The number that decides whether a
        layer ever sees a claim."""
        return 1.0 - self.cdf(x)

    def quantile(self, p):
        q = np.asarray(self._quantile(np.asarray(p, dtype=float)))
        return float(q) if q.ndim == 0 else q

    def isf(self, s):
        """Inverse survival function: the x with P(X > x) = s.

        Expressed in terms of the survival probability rather than as
        ``quantile(1 - s)`` so it keeps full precision far out in the tail,
        where ``1 - s`` rounds away to nothing.
        """
        q = np.asarray(self._isf(np.asarray(s, dtype=float)))
        return float(q) if q.ndim == 0 else q

    def excess_sampler(self, threshold: float):
        """Return ``(q, sampler)`` for the distribution of X given X > D.

        ``q`` is P(X > D); ``sampler(n, rng)`` draws n claims from the
        conditional distribution. This is exact rather than an approximation
        - simulating only the claims that can reach the layer gives the same
        answer as simulating every claim, at a small fraction of the cost.
        """
        q = float(self.sf(threshold))
        if q <= 0.0:
            return 0.0, (lambda n, rng: np.empty(0))

        if self.components:
            body, ext = self.components["body"], self.components["extreme"]
            p = self.components["p"]
            w_ext = p * float(ext.sf(threshold)) / q
            _, body_smp = body.excess_sampler(threshold)
            _, ext_smp = ext.excess_sampler(threshold)

            def smp(n, rng):
                if n <= 0:
                    return np.empty(0)
                is_ext = rng.random(n) < w_ext
                k = int(is_ext.sum())
                out = np.empty(n)
                if k:
                    out[is_ext] = ext_smp(k, rng)
                if n - k:
                    out[~is_ext] = body_smp(n - k, rng)
                return out

            return q, smp

        def smp(n, rng):
            if n <= 0:
                return np.empty(0)
            # Given X > D, the survival probability S(X) is uniform on (0, q).
            return np.asarray(self._isf(rng.random(n) * q))

        return q, smp

    def truncated_moments(self, cap: float, n: int = 100_000) -> tuple[float, float]:
        """Mean and variance of X given X <= cap - the attritional layer."""
        f = float(self.cdf(cap))
        if f <= 0:
            return 0.0, 0.0
        u = (np.arange(n) + 0.5) / n * f
        x = np.asarray(self.quantile(u))
        return float(x.mean()), float(x.var())

    # -- derived -----------------------------------------------------------
    @property
    def sd(self) -> float:
        if math.isnan(self.variance) or math.isinf(self.variance):
            return self.variance
        return math.sqrt(self.variance)

    @property
    def cv(self) -> float:
        """Coefficient of variation - the cleanest single read on spread."""
        s = self.sd
        if math.isnan(s) or math.isinf(s) or not self.mean:
            return float(s if isinstance(s, float) else "nan")
        return s / self.mean

    def median(self) -> float:
        return float(self.quantile(0.5))

    def _survival_integral(self, lo: float, hi: float, n: int = 40_000) -> float:
        """Integral of the survival function over [lo, hi].

        Uses the identity E[min(max(X-a,0), b-a)] = integral of S(x) from a to
        b. Integrating the survival function directly - on a log-spaced grid,
        so the far tail is resolved as finely as the body - is far more
        accurate than averaging quantiles, where only a handful of sample
        points would land above a high attachment in the first place.
        """
        if hi <= lo:
            return 0.0
        if lo <= 0:
            # Split: a linear piece near zero, log-spaced above it.
            pivot = min(hi, max(hi * 1e-6, 1e-9))
            head = np.linspace(0.0, pivot, 256)
            tail = np.geomspace(pivot, hi, n)
            xs = np.concatenate([head[:-1], tail])
        else:
            xs = np.geomspace(lo, hi, n)
        return float(np.trapezoid(np.asarray(self.sf(xs), dtype=float), xs))

    def limited_mean(self, cap: float) -> float:
        """E[min(X, cap)] - the limited expected value."""
        if cap <= 0:
            return 0.0
        if math.isinf(cap):
            return self.mean
        return self._survival_integral(0.0, cap)

    def layer_mean(self, attachment: float, limit: float) -> float:
        """E[min(max(X - D, 0), L)] - the expected cession of a single claim
        to the layer. Equals LEV(D+L) - LEV(D), and is the analytic control
        total the Monte Carlo result is checked against."""
        if limit <= 0:
            return 0.0
        return max(self._survival_integral(attachment, attachment + limit), 0.0)


def _lognormal(mean: float, sd: float) -> Severity | None:
    if mean <= 0 or sd <= 0:
        return None
    sig2 = math.log1p((sd * sd) / (mean * mean))
    mu = math.log(mean) - sig2 / 2.0
    sigma = math.sqrt(sig2)

    def smp(n, rng):
        return rng.lognormal(mu, sigma, n)

    def cdf(x):
        out = np.zeros_like(x, dtype=float)
        pos = x > 0
        out[pos] = 0.5 * special.erfc(-(np.log(x[pos]) - mu) / (sigma * math.sqrt(2.0)))
        return out

    def qtl(p):
        return np.exp(mu + sigma * math.sqrt(2.0) * special.erfinv(2.0 * np.clip(p, 1e-15, 1 - 1e-15) - 1.0))

    def isf(sv):
        return np.exp(mu + sigma * math.sqrt(2.0) * special.erfcinv(2.0 * np.clip(sv, 1e-300, 1.0)))

    return Severity(
        family="Lognormal",
        label=f"Lognormal(mu={mu:.3f}, sigma={sigma:.3f})",
        params={"mean": mean, "sd": sd, "mu": mu, "sigma": sigma},
        _sample=smp, _cdf=cdf, _quantile=qtl, _isf=isf,
        mean=mean, variance=sd * sd,
    )


def _gamma(mean: float, sd: float) -> Severity | None:
    if mean <= 0 or sd <= 0:
        return None
    shape = (mean / sd) ** 2
    scale = (sd * sd) / mean

    def smp(n, rng):
        return rng.gamma(shape, scale, n)

    def cdf(x):
        return special.gammainc(shape, np.clip(x, 0, None) / scale)

    def qtl(p):
        return scale * special.gammaincinv(shape, np.clip(p, 0.0, 1 - 1e-15))

    def isf(sv):
        return scale * special.gammainccinv(shape, np.clip(sv, 1e-300, 1.0))

    return Severity(
        family="Gamma",
        label=f"Gamma(shape={shape:.3f}, scale={scale:,.0f})",
        params={"mean": mean, "sd": sd, "shape": shape, "scale": scale},
        _sample=smp, _cdf=cdf, _quantile=qtl, _isf=isf,
        mean=mean, variance=sd * sd,
    )


def _weibull(scale: float, shape: float) -> Severity | None:
    """Weibull(k=shape, lambda=scale). shape < 1 gives a fatter tail than
    exponential; shape > 1 a thinner one."""
    if scale <= 0 or shape <= 0:
        return None
    m = scale * math.gamma(1.0 + 1.0 / shape)
    v = scale ** 2 * (math.gamma(1.0 + 2.0 / shape) - math.gamma(1.0 + 1.0 / shape) ** 2)

    def smp(n, rng):
        return scale * rng.weibull(shape, n)

    def cdf(x):
        return 1.0 - np.exp(-((np.clip(x, 0, None) / scale) ** shape))

    def qtl(p):
        return scale * (-np.log1p(-np.clip(p, 0.0, 1 - 1e-15))) ** (1.0 / shape)

    def isf(sv):
        return scale * (-np.log(np.clip(sv, 1e-300, 1.0))) ** (1.0 / shape)

    return Severity(
        family="Weibull",
        label=f"Weibull(k={shape:.3f}, scale={scale:,.0f})",
        params={"shape": shape, "scale": scale},
        _sample=smp, _cdf=cdf, _quantile=qtl, _isf=isf,
        mean=m, variance=v,
    )


def _pareto(alpha: float, theta: float) -> Severity | None:
    """Pareto type II (Lomax): S(x) = (1 + x/theta)^-alpha."""
    if alpha <= 0 or theta <= 0:
        return None
    mean = theta / (alpha - 1.0) if alpha > 1 else float("inf")
    if alpha > 2:
        var = (theta ** 2 * alpha) / ((alpha - 1.0) ** 2 * (alpha - 2.0))
    else:
        var = float("inf")

    def smp(n, rng):
        return theta * ((1.0 - rng.random(n)) ** (-1.0 / alpha) - 1.0)

    def cdf(x):
        return 1.0 - (1.0 + np.clip(x, 0, None) / theta) ** (-alpha)

    def qtl(p):
        return theta * ((1.0 - np.clip(p, 0.0, 1 - 1e-15)) ** (-1.0 / alpha) - 1.0)

    def isf(sv):
        return theta * (np.clip(sv, 1e-300, 1.0) ** (-1.0 / alpha) - 1.0)

    return Severity(
        family="Pareto",
        label=f"Pareto II(alpha={alpha:.3f}, theta={theta:,.0f})",
        params={"alpha": alpha, "theta": theta},
        _sample=smp, _cdf=cdf, _quantile=qtl, _isf=isf,
        mean=mean, variance=var,
    )


def _burr(alpha: float, gamma_: float, theta: float) -> Severity | None:
    """Burr XII: S(x) = (1 + (x/theta)^gamma)^-alpha. Moments exist only up
    to order alpha*gamma."""
    if alpha <= 0 or gamma_ <= 0 or theta <= 0:
        return None

    def moment(k: float) -> float:
        if alpha * gamma_ <= k:
            return float("inf")
        return theta ** k * special.gamma(1.0 + k / gamma_) * special.gamma(alpha - k / gamma_) / special.gamma(alpha)

    m1 = moment(1.0)
    m2 = moment(2.0)
    var = float("inf") if math.isinf(m2) or math.isinf(m1) else m2 - m1 ** 2

    def smp(n, rng):
        u = rng.random(n)
        return theta * ((1.0 - u) ** (-1.0 / alpha) - 1.0) ** (1.0 / gamma_)

    def cdf(x):
        return 1.0 - (1.0 + (np.clip(x, 0, None) / theta) ** gamma_) ** (-alpha)

    def qtl(p):
        return theta * ((1.0 - np.clip(p, 0.0, 1 - 1e-15)) ** (-1.0 / alpha) - 1.0) ** (1.0 / gamma_)

    def isf(sv):
        return theta * (np.clip(sv, 1e-300, 1.0) ** (-1.0 / alpha) - 1.0) ** (1.0 / gamma_)

    return Severity(
        family="Burr",
        label=f"Burr XII(alpha={alpha:.2f}, gamma={gamma_:.2f}, theta={theta:,.0f})",
        params={"alpha": alpha, "gamma": gamma_, "theta": theta},
        _sample=smp, _cdf=cdf, _quantile=qtl, _isf=isf,
        mean=m1, variance=var,
    )


def build_severity(family: str, p: dict) -> Severity | None:
    """Factory keyed on the family name used in the UI."""
    if family == "Lognormal":
        return _lognormal(p.get("mean", 0.0), p.get("sd", 0.0))
    if family == "Gamma":
        return _gamma(p.get("mean", 0.0), p.get("sd", 0.0))
    if family == "Weibull":
        return _weibull(p.get("scale", 0.0), p.get("shape", 0.0))
    if family == "Pareto":
        return _pareto(p.get("alpha", 0.0), p.get("theta", 0.0))
    if family == "Burr":
        return _burr(p.get("alpha", 0.0), p.get("gamma", 0.0), p.get("theta", 0.0))
    return None


# ---------------------------------------------------------------------------
#  Two-component mixture: ordinary body + heavy-tailed extreme population
# ---------------------------------------------------------------------------
def mixture(body: Severity | None, extreme: Severity | None, p: float) -> Severity | None:
    """Body with probability (1-p), extreme with probability p.

    Unlike a sampled approximation, the mixture CDF is exact and the quantile
    is obtained by inverting it numerically - so the reported percentiles do
    not jitter between reruns.
    """
    if body is None:
        return None
    if extreme is None or p <= 0:
        return body
    p = float(min(max(p, 0.0), 1.0))
    if p >= 1.0:
        return extreme

    def smp(n, rng):
        u = rng.random(n)
        is_ext = u < p
        n_ext = int(is_ext.sum())
        out = np.empty(n)
        if n_ext:
            out[is_ext] = extreme.sample(n_ext, rng)
        if n - n_ext:
            out[~is_ext] = body.sample(n - n_ext, rng)
        return out

    def cdf(x):
        return (1.0 - p) * body.cdf(x) + p * extreme.cdf(x)

    # The mixture quantile has no closed form. Rather than re-sampling (which
    # makes every reported percentile jitter between reruns), invert the exact
    # CDF once on a log-spaced grid and interpolate. Deterministic and fast
    # enough to be called with hundreds of thousands of probabilities.
    grid: dict = {}

    def _grid():
        if "x" not in grid:
            lo = max(min(float(body.quantile(1e-7)), float(extreme.quantile(1e-7))), 1e-9)
            hi = max(float(body.quantile(1 - 1e-9)), float(extreme.quantile(1 - 1e-9)), lo * 10.0)
            xs = np.geomspace(lo, hi, 60_000)
            fs = cdf(xs)
            fs, keep = np.unique(fs, return_index=True)
            grid["x"] = np.log(xs[keep])
            grid["f"] = fs
        return grid["f"], grid["x"]

    def qtl(prob):
        fs, log_xs = _grid()
        pr = np.clip(np.asarray(prob, dtype=float), 1e-12, 1 - 1e-12)
        out = np.exp(np.interp(pr, fs, log_xs))
        return out if out.ndim else float(out)

    def isf(sv):
        # Headline readouts only; conditional tail sampling goes through the
        # components directly, where it stays exact.
        return qtl(1.0 - np.asarray(sv, dtype=float))

    m_body, m_ext = body.mean, extreme.mean
    m = float("inf") if math.isinf(m_ext) else (1.0 - p) * m_body + p * m_ext

    return Severity(
        family="Mixture",
        label=f"{100 * (1 - p):g}% {body.label}  +  {100 * p:g}% {extreme.label}",
        params={"p": p},
        _sample=smp, _cdf=cdf, _quantile=qtl, _isf=isf,
        mean=m, variance=float("nan"),
        components={"body": body, "extreme": extreme, "p": p},
    )


# ===========================================================================
#  Frequency
# ===========================================================================
@dataclass
class Frequency:
    family: str
    label: str
    params: dict
    _sample: Callable[[int, np.random.Generator], Array]
    mean: float
    variance: float

    def sample(self, n: int, rng: np.random.Generator) -> Array:
        return self._sample(int(n), rng)

    @property
    def sd(self) -> float:
        return math.sqrt(self.variance)

    @property
    def dispersion(self) -> float:
        """Variance-to-mean ratio. 1.0 is Poisson; above 1 is contagion."""
        return self.variance / self.mean if self.mean else float("nan")

    def scaled(self, factor: float) -> "Frequency":
        """Same shape, mean multiplied by ``factor`` - used by the stress run.

        For the negative binomial this holds the contagion parameter r fixed,
        which is the standard way to spike frequency without also changing
        how clustered the claims are.
        """
        if factor == 1.0:
            return self
        if self.family == "Poisson":
            return build_frequency("Poisson", {"lam": self.mean * factor})
        return build_frequency(
            "Negative Binomial",
            {"mean": self.mean * factor, "r": self.params["r"], "by_r": True},
        )


def build_frequency(family: str, p: dict) -> Frequency:
    if family == "Poisson":
        lam = max(float(p.get("lam", 0.0)), 0.0)

        def smp(n, rng):
            return rng.poisson(lam, n)

        return Frequency("Poisson", f"Poisson(lambda={lam:,.0f})",
                         {"lam": lam}, smp, lam, lam)

    # Negative binomial. Preferred UI parameterisation is (mean, dispersion);
    # (mean, r) is available for users who think in contagion terms.
    m = max(float(p.get("mean", 0.0)), 1e-9)
    if p.get("by_r"):
        r = max(float(p.get("r", 1.0)), 1e-6)
        var = m + m * m / r
    else:
        disp = max(float(p.get("dispersion", 1.05)), 1.0000001)
        var = disp * m
        r = m * m / (var - m)
    prob = r / (r + m)

    def smp(n, rng):
        return rng.negative_binomial(r, prob, n)

    return Frequency(
        "Negative Binomial",
        f"NegBin(r={r:,.2f}, p={prob:.5f})",
        {"mean": m, "r": r, "prob": prob, "dispersion": var / m},
        smp, m, var,
    )


def frequency_pmf(freq: Frequency, k: Array) -> Array:
    """Probability mass over a grid, for the distribution preview chart."""
    k = np.asarray(k, dtype=float)
    if freq.family == "Poisson":
        lam = freq.params["lam"]
        if lam <= 0:
            return np.where(k == 0, 1.0, 0.0)
        return np.exp(k * math.log(lam) - lam - special.gammaln(k + 1.0))
    r, prob = freq.params["r"], freq.params["prob"]
    return np.exp(
        special.gammaln(k + r) - special.gammaln(r) - special.gammaln(k + 1.0)
        + r * math.log(prob) + k * math.log1p(-prob)
    )
