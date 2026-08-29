"""
The Monte Carlo engine.

One iteration is one synthetic underwriting year: draw a claim count, draw
that many claim sizes, push them through the layer. The whole thing is
vectorised and processed in chunks of years, so a hundred thousand years of
a 4,000-claim book runs in seconds instead of minutes and never holds more
than a bounded slice of claims in memory.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .distributions import Frequency, Severity

EPS = 1e-6

# Keep each vectorised chunk to roughly this many individual claims. At eight
# bytes a claim and a handful of working arrays this is a few hundred MB at
# most, and it is large enough that numpy overhead is irrelevant.
CLAIMS_PER_CHUNK = 6_000_000


# ===========================================================================
#  Structure
# ===========================================================================
@dataclass(frozen=True)
class Layer:
    """An excess-of-loss layer: ``limit`` xs ``attachment``."""

    attachment: float          # D - retention below which the cedant keeps everything
    limit: float               # L - per-occurrence limit
    reinstatements: float = 2  # number of times the limit is restored (inf = unlimited)
    reinstatement_cost: float = 1.0   # as a fraction of the deposit premium, pro rata
    aad: float = 0.0           # annual aggregate deductible applied to ceded losses
    share: float = 1.0         # signed line / participation

    @property
    def top(self) -> float:
        return self.attachment + self.limit

    @property
    def aggregate_cap(self) -> float:
        """Total the layer can pay in one year: the limit plus reinstatements."""
        if math.isinf(self.reinstatements):
            return float("inf")
        return self.limit * (1.0 + self.reinstatements)

    @property
    def reinstatable(self) -> float:
        """Capacity that must be paid for through reinstatement premium."""
        if math.isinf(self.reinstatements):
            return float("inf")
        return self.limit * self.reinstatements

    def describe(self) -> str:
        from .theme import usd_short
        r = "unlimited" if math.isinf(self.reinstatements) else f"{self.reinstatements:g}"
        return f"{usd_short(self.limit)} xs {usd_short(self.attachment)} - {r} reinstatement(s)"


# ===========================================================================
#  Result
# ===========================================================================
@dataclass
class SimResult:
    """Per-year simulated outcomes plus everything derived from them.

    All loss arrays are on a 100% (whole-layer) basis; the signed share is
    applied in ``pricing`` so both views stay available.
    """

    layer_loss: np.ndarray          # ceded to layer after AAD and aggregate cap
    ceded_raw: np.ndarray           # ceded before AAD and aggregate cap
    gu_loss: np.ndarray | None      # ground-up loss (only in full mode)
    n_claims: np.ndarray            # claim count in the year
    n_pierce: np.ndarray            # claims breaching the attachment
    largest: np.ndarray             # largest single claim in the year

    layer: Layer
    frequency: Frequency
    severity: Severity
    n_iter: int
    seed: int
    elapsed: float = 0.0
    total_claims: int = 0
    label: str = "Base"
    meta: dict = field(default_factory=dict)

    # -- headline ----------------------------------------------------------
    @property
    def burning_cost(self) -> float:
        """Expected annual loss to the layer - the pure/technical loss cost."""
        return float(self.layer_loss.mean())

    @property
    def std_error(self) -> float:
        """Monte Carlo standard error of the burning cost."""
        return float(self.layer_loss.std(ddof=1) / math.sqrt(self.n_iter))

    @property
    def ci95(self) -> tuple[float, float]:
        h = 1.959964 * self.std_error
        return self.burning_cost - h, self.burning_cost + h

    @property
    def rel_error(self) -> float:
        bc = self.burning_cost
        return self.std_error / bc if bc > 0 else float("nan")

    @property
    def volatility(self) -> float:
        return float(self.layer_loss.std(ddof=1))

    @property
    def cv(self) -> float:
        bc = self.burning_cost
        return self.volatility / bc if bc > 0 else float("nan")

    # -- probabilities -----------------------------------------------------
    @property
    def p_attach(self) -> float:
        """P(at least one claim breaches the attachment)."""
        return float((self.n_pierce > 0).mean())

    @property
    def p_pay(self) -> float:
        """P(the layer actually pays) - differs from p_attach once an
        aggregate deductible is in play."""
        return float((self.layer_loss > EPS).mean())

    @property
    def p_exhaust(self) -> float:
        cap = self.layer.aggregate_cap
        if math.isinf(cap):
            return 0.0
        return float((self.layer_loss >= cap - EPS).mean())

    @property
    def p_full_limit(self) -> float:
        """P(at least one full limit consumed in the year)."""
        return float((self.layer_loss >= self.layer.limit - EPS).mean())

    @property
    def mean_severity_to_layer(self) -> float:
        hit = self.layer_loss[self.layer_loss > EPS]
        return float(hit.mean()) if hit.size else 0.0

    @property
    def expected_claims_to_layer(self) -> float:
        return float(self.n_pierce.mean())

    # -- tail --------------------------------------------------------------
    def var(self, p: float) -> float:
        """Value at Risk - the p-th percentile of the annual layer loss."""
        return float(np.quantile(self.layer_loss, p))

    def tvar(self, p: float) -> float:
        """Tail VaR - the average loss in the worst (1-p) of years."""
        threshold = self.var(p)
        tail = self.layer_loss[self.layer_loss >= threshold]
        return float(tail.mean()) if tail.size else threshold

    def rp(self, years: float) -> float:
        """Loss at a return period, e.g. rp(100) is the 1-in-100 year."""
        return self.var(1.0 - 1.0 / years)

    def rp_tvar(self, years: float) -> float:
        return self.tvar(1.0 - 1.0 / years)

    @property
    def capital(self) -> float:
        """Capital the layer consumes: TVaR(99.5%) in excess of expected loss."""
        return max(self.tvar(0.995) - self.burning_cost, 0.0)

    # -- reinstatements ----------------------------------------------------
    @property
    def expected_reinstated(self) -> float:
        """E[limit reinstated] - drives reinstatement premium income."""
        cap = self.layer.reinstatable
        if cap <= 0:
            return 0.0
        if math.isinf(cap):
            return self.burning_cost
        return float(np.minimum(self.layer_loss, cap).mean())

    @property
    def expected_reinstatements_used(self) -> float:
        """Expected number of reinstatements consumed in a year."""
        if self.layer.limit <= 0:
            return 0.0
        return self.expected_reinstated / self.layer.limit

    @property
    def cap_bite(self) -> float:
        """Share of gross cessions cut off by the aggregate cap and AAD.

        A large number means the structure's annual protection is binding -
        the cedant is retaining more than the per-claim view suggests.
        """
        raw = float(self.ceded_raw.mean())
        if raw <= 0:
            return 0.0
        return 1.0 - self.burning_cost / raw

    # -- ground up ---------------------------------------------------------
    @property
    def mode(self) -> str:
        return self.meta.get("mode", "tail")

    @property
    def has_gu_distribution(self) -> bool:
        return self.gu_loss is not None

    @property
    def gu_mean(self) -> float:
        """Expected annual ground-up loss. Simulated in full mode; taken from
        the closed form E[N] x E[X] in tail mode, where attritional claims are
        deliberately not drawn."""
        if self.gu_loss is not None:
            return float(self.gu_loss.mean())
        return float(self.meta.get("gu_mean_analytic", float("nan")))

    @property
    def retained_mean(self) -> float:
        gu = self.gu_mean
        if math.isnan(gu):
            return float("nan")
        return max(gu - self.burning_cost, 0.0)

    # -- diagnostics -------------------------------------------------------
    def convergence(self, points: int = 240) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Running mean and a 95% band, for the convergence trace."""
        n = self.n_iter
        idx = np.unique(np.geomspace(max(50, n // 500), n, points).astype(int))
        cs = np.cumsum(self.layer_loss, dtype=float)
        cs2 = np.cumsum(self.layer_loss.astype(float) ** 2)
        means = cs[idx - 1] / idx
        var = np.maximum(cs2[idx - 1] / idx - means ** 2, 0.0)
        half = 1.959964 * np.sqrt(var / idx)
        return idx, means, half

    def ep_curve(self, points: int = 900) -> tuple[np.ndarray, np.ndarray]:
        """Exceedance probability curve, thinned for plotting."""
        s = np.sort(self.layer_loss)[::-1]
        ep = np.arange(1, s.size + 1) / s.size
        keep = np.unique(np.geomspace(1, s.size, points).astype(int)) - 1
        return s[keep], ep[keep]

    def worst_years(self, k: int = 10):
        """The k costliest simulated years. Ground-up loss comes back as None
        in tail-thinned mode, where attritional claims are never drawn."""
        order = np.argsort(self.layer_loss)[::-1][:k]
        gu = self.gu_loss[order] if self.gu_loss is not None else None
        return (order, self.layer_loss[order], self.n_claims[order],
                self.n_pierce[order], self.largest[order], gu)

    def fingerprint(self) -> str:
        """Short stable id for caching AI commentary against this exact run."""
        import hashlib
        raw = (
            f"{self.n_iter}|{self.seed}|{self.layer}|{self.frequency.label}|"
            f"{self.severity.label}|{self.burning_cost:.6f}|{self.label}"
        )
        return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ===========================================================================
#  Simulation
# ===========================================================================
def _aggregate(idx, values, size):
    return np.bincount(idx, weights=values, minlength=size)


def _per_year_max(values, counts, size):
    """Largest single claim in each year. ``reduceat`` needs the start offset
    of every non-empty group; years with no claims keep their zero."""
    out = np.zeros(size)
    nonempty = counts > 0
    if nonempty.any():
        starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
        out[nonempty] = np.maximum.reduceat(values, starts[nonempty])
    return out


def run_simulation(
    frequency: Frequency,
    severity: Severity,
    layer: Layer,
    n_iter: int,
    seed: int,
    progress: Callable[[float, str], None] | None = None,
    label: str = "Base",
    severity_factor: float = 1.0,
    mode: str = "tail",
) -> SimResult:
    """Simulate ``n_iter`` underwriting years.

    ``mode`` picks how the claims are generated:

    ``"tail"``   Only claims capable of reaching the attachment are drawn,
                 from the exact conditional distribution X | X > D, with the
                 count of such claims thinned out of the annual frequency.
                 Every layer statistic is exact; ground-up loss is reported
                 at its closed-form expectation rather than simulated.

    ``"full"``   Every claim in every year is drawn. Adds the ground-up and
                 net-retained loss distributions at a much higher cost.

    ``severity_factor`` inflates every claim, which is how the what-if page
    applies severity trend without rebuilding the distribution.
    """
    import time

    t0 = time.perf_counter()
    n_iter = int(n_iter)
    rng = np.random.default_rng(seed)

    D = float(layer.attachment)
    L = float(layer.limit)
    agg_cap = layer.aggregate_cap
    aad = float(layer.aad)
    k = max(float(severity_factor), 1e-12)

    layer_loss = np.empty(n_iter)
    ceded_raw = np.empty(n_iter)
    n_pierce = np.empty(n_iter, dtype=np.int64)
    largest = np.zeros(n_iter)

    counts = frequency.sample(n_iter, rng).astype(np.int64)
    total_claims = int(counts.sum())

    # An inflated claim reaches the layer when its uninflated size exceeds
    # D / k, so the conditioning threshold moves with the trend factor.
    threshold = D / k
    q_pierce = float(severity.sf(threshold))

    if mode == "tail":
        # Thinning: each claim independently reaches the attachment with
        # probability q, so the number that do is Binomial(N, q). Exact.
        n_large = rng.binomial(counts, q_pierce).astype(np.int64)
        _, tail_sampler = severity.excess_sampler(threshold)
        draws_per_year = max(frequency.mean * q_pierce, 1e-9)
    else:
        n_large = counts
        draws_per_year = max(frequency.mean, 1.0)

    gu_loss = np.empty(n_iter) if mode == "full" else None
    chunk = int(max(1, min(n_iter, CLAIMS_PER_CHUNK / draws_per_year)))

    done = 0
    while done < n_iter:
        hi = min(done + chunk, n_iter)
        size = hi - done
        c = n_large[done:hi]
        m = int(c.sum())

        if m == 0:
            layer_loss[done:hi] = 0.0
            ceded_raw[done:hi] = 0.0
            n_pierce[done:hi] = 0
            largest[done:hi] = 0.0
            if gu_loss is not None:
                gu_loss[done:hi] = 0.0
            done = hi
            continue

        if mode == "tail":
            claims = tail_sampler(m, rng) * k
            idx = np.repeat(np.arange(size), c)
            ceded = np.minimum(claims - D, L)          # every draw exceeds D
            ceded_raw[done:hi] = _aggregate(idx, ceded, size)
            n_pierce[done:hi] = c
            largest[done:hi] = _per_year_max(claims, c, size)
        else:
            claims = severity.sample(m, rng)
            if k != 1.0:
                claims *= k
            idx = np.repeat(np.arange(size), c)
            gu_loss[done:hi] = _aggregate(idx, claims, size)
            # Only the claims above the attachment matter to the layer, and
            # there are usually very few of them - restrict before reducing.
            hit = claims > D
            if hit.any():
                ceded = np.minimum(claims[hit] - D, L)
                ceded_raw[done:hi] = _aggregate(idx[hit], ceded, size)
                n_pierce[done:hi] = np.bincount(idx[hit], minlength=size)
            else:
                ceded_raw[done:hi] = 0.0
                n_pierce[done:hi] = 0
            largest[done:hi] = _per_year_max(claims, c, size)

        raw = ceded_raw[done:hi]
        layer_loss[done:hi] = np.minimum(np.maximum(raw - aad, 0.0), agg_cap)

        done = hi
        if progress is not None:
            progress(done / n_iter, f"{done:,} of {n_iter:,} years simulated")

    return SimResult(
        layer_loss=layer_loss,
        ceded_raw=ceded_raw,
        gu_loss=gu_loss,
        n_claims=counts,
        n_pierce=n_pierce,
        largest=largest,
        layer=layer,
        frequency=frequency,
        severity=severity,
        n_iter=n_iter,
        seed=seed,
        elapsed=time.perf_counter() - t0,
        total_claims=total_claims,
        label=label,
        meta={
            "severity_factor": severity_factor,
            "mode": mode,
            "q_pierce": q_pierce,
            "gu_mean_analytic": frequency.mean * severity.mean * k,
            "tail_draws": int(n_large.sum()),
        },
    )


# ===========================================================================
#  Analytic control totals
# ===========================================================================
def analytic_check(frequency: Frequency, severity: Severity, layer: Layer) -> dict:
    """Closed-form expectations to validate the simulation against.

    E[ceded] = E[N] x (LEV(D+L) - LEV(D)), before any annual aggregate
    features. If the Monte Carlo disagrees with this by more than its own
    sampling error, something is wrong.
    """
    per_claim = severity.layer_mean(layer.attachment, layer.limit)
    sf = float(severity.sf(layer.attachment))
    return {
        "per_claim_cession": per_claim,
        "expected_ceded": frequency.mean * per_claim,
        "p_claim_pierces": sf,
        "expected_pierces": frequency.mean * sf,
        "expected_gu": frequency.mean * severity.mean,
    }
