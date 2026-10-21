"""Phase 8: fits edge(TC) = intercept + slope*TC from a BatteryResult's
by_true_count buckets. Fit PER RuleSet+system -- never hardcode "+0.5% per true
count" (deck count and penetration both materially move the fit; see
.agents/skills/counting_systems_conventions/SKILL.md).

Sign convention: `edge` is the PLAYER's expected return per unit wagered
(negative = house edge, positive = player advantage) -- matching the build
plan's own worked example (intercept ~ -0.005, slope ~ +0.005, break-even near
TC +1), NOT test_house_edge.py's "house edge is a positive number" convention.
metrics.py shares this same convention; do not mix the two without converting.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Tuple

import numpy as np

from src.simulation.simulator import BatteryResult

DEFAULT_BASELINE_PATH = Path("data/baselines/edge_model_baseline.json")
BASELINE_DIR = DEFAULT_BASELINE_PATH.parent
# Be honest about extrapolating past this range in any UI/report that uses predict_edge --
# the build plan's own Phase 8 section: "the relationship is very slightly convex at high
# counts... thin sample past TC +6".
TRUSTED_TC_RANGE: Tuple[int, int] = (-3, 6)


@dataclass
class BucketFit:
    tc: int
    n: int
    edge: float
    stderr: float


@dataclass
class EdgeModel:
    ruleset_key: str
    system_name: str
    use_deviations: bool
    n_hands: int
    intercept: float
    slope: float
    r_squared: float
    fit_tc_range: Tuple[int, int]          # min/max TC actually used in the regression
    buckets: List[BucketFit] = field(default_factory=list)


def fit_edge_model(result: BatteryResult, min_bucket_n: int = 200) -> EdgeModel:
    """Weighted least squares of edge(TC) = intercept + slope*TC over the
    per-bucket means, weighted by each bucket's own sample size -- a bucket
    with 50 hands shouldn't move the fit as much as one with 500,000. Buckets
    with fewer than min_bucket_n hands are excluded from the FIT (too noisy to
    trust) but still reported in `buckets` for transparency."""
    buckets = [
        BucketFit(tc=tc, n=b.n, edge=b.mean, stderr=b.stderr)
        for tc, b in sorted(result.by_true_count.items())
    ]
    fit = [(b.tc, b.edge, b.n) for b in buckets if b.n >= min_bucket_n]
    if len(fit) < 2:
        raise ValueError(
            f"Only {len(fit)} TC bucket(s) have >= {min_bucket_n} hands -- run more hands before fitting"
        )

    tcs = np.array([f[0] for f in fit], dtype=float)
    edges = np.array([f[1] for f in fit], dtype=float)
    weights = np.array([f[2] for f in fit], dtype=float)

    w_sum = weights.sum()
    x_bar = float((weights * tcs).sum() / w_sum)
    y_bar = float((weights * edges).sum() / w_sum)
    sxx = float((weights * (tcs - x_bar) ** 2).sum())
    sxy = float((weights * (tcs - x_bar) * (edges - y_bar)).sum())
    slope = sxy / sxx
    intercept = y_bar - slope * x_bar

    predicted = intercept + slope * tcs
    ss_res = float((weights * (edges - predicted) ** 2).sum())
    ss_tot = float((weights * (edges - y_bar) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    return EdgeModel(
        ruleset_key=result.ruleset_key,
        system_name=result.system_name,
        use_deviations=result.use_deviations,
        n_hands=result.n_hands,
        intercept=float(intercept),
        slope=float(slope),
        r_squared=float(r_squared),
        fit_tc_range=(int(tcs.min()), int(tcs.max())),
        buckets=buckets,
    )


def predict_edge(model: EdgeModel, tc: float) -> float:
    """edge(TC) from the fitted line. Does not itself warn on extrapolation --
    callers (UI, reports) must check is_extrapolating() and say so, per the
    build plan's own insistence on being honest about the thin-sample tail."""
    return model.intercept + model.slope * tc


def is_extrapolating(tc: float) -> bool:
    lo, hi = TRUSTED_TC_RANGE
    return tc < lo or tc > hi


def keyed_baseline_path(ruleset_key: str, system_slug: str) -> Path:
    """data/baselines/edge_model__{ruleset_key}__{system_slug}.json -- matches
    the grid/index cache's own per-ruleset(+system) file-per-config convention
    (Phase 4/7), so app.py (Phase 10) can discover every locked edge model by
    scanning BASELINE_DIR rather than assuming one is available for every
    shipped ruleset (only ever run for the ones someone actually generated)."""
    return BASELINE_DIR / f"edge_model__{ruleset_key}__{system_slug}.json"


def save_baseline(model: EdgeModel, path: Path = DEFAULT_BASELINE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(model), f, indent=2)


def load_baseline(path: Path = DEFAULT_BASELINE_PATH) -> EdgeModel:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["buckets"] = [BucketFit(**b) for b in data["buckets"]]
    data["fit_tc_range"] = tuple(data["fit_tc_range"])
    return EdgeModel(**data)
