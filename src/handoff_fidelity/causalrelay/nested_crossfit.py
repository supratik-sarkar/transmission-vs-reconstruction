"""Nested grouped outer cross-fitting runner for CausalRelay and learned controls.

Ensures strict independence of held-out test document evaluations:
- Outer partition: K-fold grouped split by document ID.
- Inner loop: Hyperparameter & family selection strictly within outer training documents.
- Pretreatment features only: predicts Delta_budget from source-only representations.
- Leakage prevention: held-out documents are strictly quarantined from inner CV and training.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from handoff_fidelity.causalrelay.families import PredictorFamily
from handoff_fidelity.causalrelay.model import RidgeRegressor, grouped_folds


class LeakageError(AssertionError):
    """Raised when held-out test data leaks into training or model selection."""


@dataclass(frozen=True, slots=True)
class CrossFitFoldResult:
    fold_index: int
    train_document_ids: list[str]
    test_document_ids: list[str]
    selected_family: str
    selected_params: dict[str, Any]
    inner_cv_mse: float
    model_artifact_sha256: str


@dataclass
class NestedCrossFitReport:
    n_documents: int
    n_outer_folds: int
    n_inner_folds: int
    fold_results: list[CrossFitFoldResult]
    predictions: dict[str, float]
    feature_names: list[str]
    target_name: str


def _fit_candidate(family: str, params: dict[str, Any], x: np.ndarray, y: np.ndarray, seed: int):
    """Instantiate and fit a candidate regressor."""
    if family == PredictorFamily.RIDGE:
        alpha = float(params.get("alpha", 1.0))
        return RidgeRegressor(alpha=alpha).fit(x, y)
    if family == PredictorFamily.HIST_GRADIENT_BOOSTING:
        from sklearn.ensemble import HistGradientBoostingRegressor

        reg = HistGradientBoostingRegressor(
            max_depth=params.get("max_depth", 3),
            learning_rate=params.get("learning_rate", 0.05),
            max_iter=params.get("max_iter", 200),
            min_samples_leaf=params.get("min_samples_leaf", 20),
            random_state=seed,
        )
        return reg.fit(x, y)
    if family == PredictorFamily.EXTRA_TREES:
        from sklearn.ensemble import ExtraTreesRegressor

        reg = ExtraTreesRegressor(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth", 5),
            min_samples_leaf=params.get("min_samples_leaf", 10),
            random_state=seed,
        )
        return reg.fit(x, y)
    raise ValueError(f"Unknown learner family: {family}")


def _predict_candidate(model: Any, x: np.ndarray) -> np.ndarray:
    """Predict using fitted model."""
    if hasattr(model, "predict"):
        return np.asarray(model.predict(x), dtype=float)
    raise ValueError(f"Model {type(model)} lacks predict method")


def run_nested_grouped_crossfit(
    *,
    document_ids: Sequence[str],
    features: np.ndarray,
    targets: np.ndarray,
    feature_names: Sequence[str] | None = None,
    target_name: str = "Delta_budget",
    n_outer_folds: int = 5,
    n_inner_folds: int = 4,
    candidate_families: Sequence[str] = (
        PredictorFamily.HIST_GRADIENT_BOOSTING,
        PredictorFamily.RIDGE,
        PredictorFamily.EXTRA_TREES,
    ),
    seed: int = 42,
) -> NestedCrossFitReport:
    """Execute leakage-safe nested grouped outer cross-fitting.

    Outer folds are grouped strictly by document_id. For each fold:
    1. Inner CV is performed solely on outer-training documents.
    2. The best-performing family and hyperparameter config is selected.
    3. The winner is fit on all outer-training documents.
    4. Predictions are made on outer-test documents and recorded.
    """
    doc_arr = np.asarray(document_ids, dtype=str)
    x_arr = np.asarray(features, dtype=float)
    y_arr = np.asarray(targets, dtype=float)

    n_samples = len(doc_arr)
    if len(x_arr) != n_samples or len(y_arr) != n_samples:
        raise ValueError(f"Length mismatch: docs={n_samples}, X={len(x_arr)}, y={len(y_arr)}")

    unique_docs = sorted(set(doc_arr))
    n_unique = len(unique_docs)
    if n_unique < n_outer_folds:
        raise ValueError(f"Fewer unique documents ({n_unique}) than outer folds ({n_outer_folds})")

    outer_folds = grouped_folds(doc_arr, n_splits=n_outer_folds)
    fold_results: list[CrossFitFoldResult] = []
    predictions: dict[str, float] = {}

    # Define hyperparameter grid per candidate family
    grid_by_family: dict[str, list[dict[str, Any]]] = {
        PredictorFamily.HIST_GRADIENT_BOOSTING: [
            {"max_depth": 3, "learning_rate": 0.05, "max_iter": 100},
            {"max_depth": 5, "learning_rate": 0.05, "max_iter": 100},
        ],
        PredictorFamily.RIDGE: [
            {"alpha": 0.1},
            {"alpha": 1.0},
            {"alpha": 10.0},
        ],
        PredictorFamily.EXTRA_TREES: [
            {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 10},
            {"n_estimators": 100, "max_depth": 5, "min_samples_leaf": 10},
        ],
    }

    for fold_idx, (train_idx, test_idx) in enumerate(outer_folds):
        train_docs = set(doc_arr[train_idx])
        test_docs = set(doc_arr[test_idx])

        # Strict leakage assertion
        overlap = train_docs & test_docs
        if overlap:
            raise LeakageError(
                f"Fold {fold_idx}: Outer test documents leaked into outer train: {overlap}"
            )

        x_train, y_train = x_arr[train_idx], y_arr[train_idx]
        x_test = x_arr[test_idx]
        train_doc_arr = doc_arr[train_idx]

        # Inner grouped CV to select best family & params
        inner_folds = grouped_folds(train_doc_arr, n_splits=n_inner_folds)
        best_mse = float("inf")
        best_family = str(candidate_families[0])
        best_params: dict[str, Any] = {}

        for fam in candidate_families:
            for p_cand in grid_by_family.get(fam, [{}]):
                inner_errors: list[float] = []
                for in_tr_idx, in_val_idx in inner_folds:
                    in_tr_docs = set(train_doc_arr[in_tr_idx])
                    in_val_docs = set(train_doc_arr[in_val_idx])
                    if in_tr_docs & in_val_docs:
                        raise LeakageError(
                            f"Inner CV leakage in fold {fold_idx}: {in_tr_docs & in_val_docs}"
                        )

                    m_cand = _fit_candidate(
                        fam, p_cand, x_train[in_tr_idx], y_train[in_tr_idx], seed
                    )
                    y_pred_val = _predict_candidate(m_cand, x_train[in_val_idx])
                    mse = float(np.mean((y_train[in_val_idx] - y_pred_val) ** 2))
                    inner_errors.append(mse)

                mean_inner_mse = float(np.mean(inner_errors))
                if mean_inner_mse < best_mse:
                    best_mse = mean_inner_mse
                    best_family = fam
                    best_params = p_cand

        # Fit winning candidate on all outer training data
        fitted_model = _fit_candidate(best_family, best_params, x_train, y_train, seed)
        preds_test = _predict_candidate(fitted_model, x_test)

        # Hash model parameters for lineage
        model_repr = f"{best_family}:{json.dumps(best_params, sort_keys=True)}:{len(train_idx)}"
        model_sha = hashlib.sha256(model_repr.encode("utf-8")).hexdigest()

        for d_id, pred_val in zip(doc_arr[test_idx], preds_test, strict=True):
            predictions[str(d_id)] = float(pred_val)

        fold_results.append(
            CrossFitFoldResult(
                fold_index=fold_idx,
                train_document_ids=sorted(train_docs),
                test_document_ids=sorted(test_docs),
                selected_family=best_family,
                selected_params=best_params,
                inner_cv_mse=best_mse,
                model_artifact_sha256=model_sha,
            )
        )

    return NestedCrossFitReport(
        n_documents=n_unique,
        n_outer_folds=n_outer_folds,
        n_inner_folds=n_inner_folds,
        fold_results=fold_results,
        predictions=predictions,
        feature_names=list(feature_names or []),
        target_name=target_name,
    )
