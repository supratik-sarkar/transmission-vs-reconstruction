"""The CausalRelay surplus predictor.

    s_hat(z, X) ~ E[ Delta^bu_z | pre-treatment source features ]

fitted on DEVELOPMENT documents only. The fitted artefact is frozen before the
final test and its hash enters the test freeze record.

Model family (proposed, frozen before fit):
  * primary:  HistGradientBoostingRegressor
  * ablation: Ridge (interpretable linear comparison)

Hyperparameters are chosen by GROUPED cross-validation BY DOCUMENT. Atom-level
folds would place atoms from the same document on both sides of the split; since
atoms within a document share one relay realisation and heavy local context,
that leaks and inflates apparent skill.

A dependency-free exact Ridge is always available so the pipeline and its tests
run without scikit-learn; the gradient-boosted primary requires it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

PRIMARY_FAMILY = "HistGradientBoostingRegressor"
ABLATION_FAMILY = "Ridge"

#: Frozen grids. Selected before fit; never widened after seeing test results.
PRIMARY_GRID: tuple[dict[str, Any], ...] = (
    {"max_depth": 3, "learning_rate": 0.05, "max_iter": 200, "min_samples_leaf": 20},
    {"max_depth": 3, "learning_rate": 0.10, "max_iter": 200, "min_samples_leaf": 20},
    {"max_depth": 5, "learning_rate": 0.05, "max_iter": 300, "min_samples_leaf": 10},
)
ABLATION_GRID: tuple[dict[str, Any], ...] = (
    {"alpha": 0.1},
    {"alpha": 1.0},
    {"alpha": 10.0},
)


class LabelLeakError(AssertionError):
    pass


@dataclass(slots=True)
class RidgeRegressor:
    """Exact ridge by normal equations. Deterministic; no RNG."""

    alpha: float = 1.0
    coef_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    intercept_: float = 0.0

    def fit(self, x: np.ndarray, y: np.ndarray) -> RidgeRegressor:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        xm = x.mean(axis=0)
        ym = float(y.mean())
        xc = x - xm
        p = xc.shape[1]
        gram = xc.T @ xc + self.alpha * np.eye(p)
        self.coef_ = np.linalg.solve(gram, xc.T @ (y - ym))
        self.intercept_ = ym - float(xm @ self.coef_)
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(x, dtype=float) @ self.coef_ + self.intercept_


def grouped_folds(groups: Sequence[str], n_splits: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    """Deterministic grouped K-fold. Documents are assigned to folds by sorted
    order, so no atom from one document appears in two folds."""
    unique = sorted(set(groups))
    if len(unique) < n_splits:
        n_splits = max(2, len(unique))
    assignment = {doc: i % n_splits for i, doc in enumerate(unique)}
    g = np.asarray([assignment[d] for d in groups])
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(n_splits):
        test = np.flatnonzero(g == k)
        train = np.flatnonzero(g != k)
        if test.size and train.size:
            folds.append((train, test))
    return folds


def _build(family: str, params: dict[str, Any], seed: int):
    if family == ABLATION_FAMILY:
        return RidgeRegressor(alpha=float(params.get("alpha", 1.0)))
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "scikit-learn is required for the HistGradientBoostingRegressor primary "
            "family. Install the 'ml' extra, or fit the Ridge ablation."
        ) from exc
    return HistGradientBoostingRegressor(random_state=seed, **params)


@dataclass(frozen=True, slots=True)
class FittedPolicy:
    family: str
    params: dict[str, Any]
    feature_names: tuple[str, ...]
    feature_schema_hash: str
    cv_mse: float
    n_train_atoms: int
    n_train_documents: int
    seed: int
    estimator: Any = None

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.estimator is None:
            raise RuntimeError("policy carries no fitted estimator")
        return np.asarray(self.estimator.predict(np.asarray(x, dtype=float)), dtype=float)

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "family": self.family,
                "params": self.params,
                "features": list(self.feature_names),
                "schema": self.feature_schema_hash,
                "seed": self.seed,
                "n_train_atoms": self.n_train_atoms,
                "n_train_documents": self.n_train_documents,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fit_policy(
    x: np.ndarray,
    y: np.ndarray,
    groups: Sequence[str],
    *,
    feature_names: Sequence[str],
    feature_schema_hash: str,
    family: str = PRIMARY_FAMILY,
    grid: Sequence[dict[str, Any]] | None = None,
    seed: int = 20260907,
    n_splits: int = 5,
    split_name: str = "stage2_dev",
) -> FittedPolicy:
    """Fit on development atoms only.

    ``split_name`` must be a development split. Fitting on test labels is a hard
    error, not a warning, because it is the single failure that would invalidate
    the whole benchmark.
    """
    if "test" in split_name and "dev" not in split_name:
        raise LabelLeakError(
            f"refusing to fit CausalRelay on split {split_name!r}: development labels only"
        )
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape[0] != y.shape[0] or x.shape[0] != len(groups):
        raise ValueError("feature matrix, labels and groups must align")
    if x.shape[0] == 0:
        raise ValueError("no training rows")

    candidates = (
        tuple(grid)
        if grid is not None
        else (PRIMARY_GRID if family == PRIMARY_FAMILY else ABLATION_GRID)
    )
    folds = grouped_folds(groups, n_splits=n_splits)
    best: tuple[float, dict[str, Any]] | None = None
    for params in candidates:
        errs: list[float] = []
        for train_idx, test_idx in folds:
            est = _build(family, params, seed)
            est.fit(x[train_idx], y[train_idx])
            pred = np.asarray(est.predict(x[test_idx]), dtype=float)
            errs.append(float(np.mean((pred - y[test_idx]) ** 2)))
        score = float(np.mean(errs)) if errs else float("inf")
        if best is None or score < best[0]:
            best = (score, dict(params))
    assert best is not None

    final = _build(family, best[1], seed)
    final.fit(x, y)
    return FittedPolicy(
        family=family,
        params=best[1],
        feature_names=tuple(feature_names),
        feature_schema_hash=feature_schema_hash,
        cv_mse=best[0],
        n_train_atoms=int(x.shape[0]),
        n_train_documents=len(set(groups)),
        seed=seed,
        estimator=final,
    )
