"""
CancerCare360 - Modele B : Probabilite de non-presentation (no-show)
Phase 5 - Entraine un classifieur predisant si un rendez-vous donne sera
manque, a partir du comportement passe du patient (rendez-vous manques
precedents, delai depuis le dernier rendez-vous) et du contexte
(jour de la semaine, service, demographie).

Usage:
    python ml_models/train_model_b.py
"""

import sys
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

sys.path.insert(0, str(Path(__file__).parent.parent / "lakehouse"))
from query_lakehouse import get_connection

CATEGORICAL_FEATURES = ["gender", "cancer_type", "service", "day_of_week", "month_of_year"]
NUMERIC_FEATURES = ["age", "appointment_sequence", "prior_missed_count", "days_since_prev_appointment"]
TARGET = "is_no_show"

MODEL_OUTPUT_PATH = Path(__file__).parent / "model_b_no_show.pkl"


def load_data() -> pd.DataFrame:
    con = get_connection()
    return con.execute("SELECT * FROM main_gold.ml_features_appointment").fetchdf()


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ],
        remainder="passthrough",
    )
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=5,
        random_state=42,
        class_weight="balanced",  # compense le desequilibre (~16% de no-show)
    )
    return Pipeline([("preprocessor", preprocessor), ("classifier", model)])


def get_feature_names(pipeline: Pipeline) -> list:
    cat_names = pipeline.named_steps["preprocessor"] \
        .named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES)
    return list(cat_names) + NUMERIC_FEATURES


def main():
    print("Chargement des donnees...")
    df = load_data()
    print(f"  -> {len(df)} rendez-vous charges. Repartition du label :")
    print(df[TARGET].value_counts().to_string())

    X = df[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    mlflow.set_experiment("cancercare360_model_b_no_show")

    with mlflow.start_run():
        pipeline = build_pipeline()

        print("\nEntrainement du modele...")
        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        y_proba = pipeline.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),
            "recall": recall_score(y_test, y_pred, zero_division=0),
            "f1": f1_score(y_test, y_pred, zero_division=0),
            "roc_auc": roc_auc_score(y_test, y_proba),
        }

        print("\nMetriques d'evaluation (jeu de test) :")
        for name, value in metrics.items():
            print(f"  {name:10s} : {value:.3f}")

        print("\nRapport de classification detaille :")
        print(classification_report(
            y_test, y_pred, target_names=["Presente", "No-show"], zero_division=0
        ))

        print("Matrice de confusion :")
        print(confusion_matrix(y_test, y_pred))

        feature_names = get_feature_names(pipeline)
        importances = pipeline.named_steps["classifier"].feature_importances_
        importance_df = pd.DataFrame({
            "feature": feature_names, "importance": importances
        }).sort_values("importance", ascending=False)

        print("\nTop 10 des variables les plus importantes (explicabilite RF-20) :")
        print(importance_df.head(10).to_string(index=False))

        mlflow.log_params({
            "model_type": "RandomForestClassifier",
            "n_estimators": 200,
            "max_depth": 5,
            "class_weight": "balanced",
            "n_train_samples": len(X_train),
            "n_test_samples": len(X_test),
        })
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(pipeline, "model")

        joblib.dump(pipeline, MODEL_OUTPUT_PATH)
        print(f"\nModele sauvegarde : {MODEL_OUTPUT_PATH}")


if __name__ == "__main__":
    main()