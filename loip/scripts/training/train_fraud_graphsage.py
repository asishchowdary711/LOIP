"""Train the GraphSAGE fraud-ring classifier on synthetic graph features.

A simplified message-passing approximation: an MLP classifier over
graph-derived features (pan_match_count, aadhaar_match_count, total_degree)
substitutes for a full GraphSAGE model (no Neo4j / torch-geometric dependency).

Run with: .venv-ml/bin/python -m scripts.training.train_fraud_graphsage
"""

from __future__ import annotations

import csv
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

from loip.models.graphsage_wrapper import CHECKPOINT_DIR, CHECKPOINT_PATH, FEATURE_ORDER

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "training" / "fraud_synthetic.csv"


def main() -> None:
    with open(DATA_PATH) as f:
        rows = list(csv.DictReader(f))

    X = np.array([[float(row[name]) for name in FEATURE_ORDER] for row in rows])
    y = np.array([int(row["label"]) for row in rows])

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )

    clf = MLPClassifier(
        hidden_layer_sizes=(8,), max_iter=500, random_state=42,
    )
    clf.fit(X_train, y_train)

    preds = clf.predict_proba(X_val)[:, 1]
    auc = roc_auc_score(y_val, preds)
    print(f"[fraud_graphsage] val ROC-AUC: {auc:.4f} (n_val={len(y_val)}, positives={y_val.sum()})")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, CHECKPOINT_PATH)
    print(f"Saved checkpoint to {CHECKPOINT_PATH}")


if __name__ == "__main__":
    main()
