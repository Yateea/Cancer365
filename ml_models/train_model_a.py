"""
CancerCare360 - Modele A : Signal d'attention de suivi (follow-up risk)
Phase 5 - Entraine un classifieur predisant si un patient est susceptible
de declencher un signal de rupture de suivi, a partir de son profil
(demographie, repartition des types d'evenements) - PAS a partir des
variables utilisees par les regles du Care Signal Engine (voir le modele
dbt ml_features_patient pour la justification de ce choix).

Conforme a la section 12.4 du cahier des charges : aucun modele n'est
deploye sans evaluation documentee. Chaque prediction est accompagnee
d'un score de confiance et d'une explication (RF-19, RF-20).

Usage:
    python ml_models/train_model_a.py
"""

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

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "lakehouse"))
from query_lakehouse import get_connection  # reutilise la config S3/DuckDB existante

CATEGORICAL_FEATURES = ["gender", "cancer_type", "primary_center_id"]
NUMERIC_FEATURES = [
    "age", "days_since_diagnosis", "lab_result_count", "treatment_count",
    "hospitalization_count", "discharge_count", "followup_count", "total_events",
]
TARGET = "is_at_risk"

MODEL_OUTPUT_PATH = Path(__file__).parent / "model_a_follow_up_risk.pkl"


def load_data() -> pd.DataFrame:
    con = get_connection()
    return con.execute("SELECT * FROM main_gold.ml_features_patient").fetchdf()


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ],
        remainder="passthrough",  # laisse passer les variables numeriques telles quelles
    )
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=5,  # profondeur limitee : modele volontairement simple et interpretable
        random_state=42,
        class_weight="balanced",
    )
    return Pipeline([("preprocessor", preprocessor), ("classifier", model)])


def get_feature_names(pipeline: Pipeline) -> list:
    """Recupere les noms de colonnes apres one-hot encoding, pour l'explicabilite."""
    cat_names = pipeline.named_steps["preprocessor"] \
        .named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES)
    return list(cat_names) + NUMERIC_FEATURES


def main():
    print("Chargement des donnees...")
    df = load_data()
    print(f"  -> {len(df)} patients charges. Repartition du label :")
    print(df[TARGET].value_counts().to_string())

    X = df[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    mlflow.set_experiment("cancercare360_model_a_follow_up_risk")

    with mlflow.start_run():
        pipeline = build_pipeline()

        print("\nEntrainement du modele...")
        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        y_proba = pipeline.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred),
            "recall": recall_score(y_test, y_pred),
            "f1": f1_score(y_test, y_pred),
            "roc_auc": roc_auc_score(y_test, y_proba),
        }

        print("\nMetriques d'evaluation (jeu de test) :")
        for name, value in metrics.items():
            print(f"  {name:10s} : {value:.3f}")

        print("\nRapport de classification detaille :")
        print(classification_report(y_test, y_pred, target_names=["Non a risque", "A risque"]))

        print("Matrice de confusion :")
        print(confusion_matrix(y_test, y_pred))

        # Explicabilite (RF-20) : importance de chaque variable dans la decision
        feature_names = get_feature_names(pipeline)
        importances = pipeline.named_steps["classifier"].feature_importances_
        importance_df = pd.DataFrame({
            "feature": feature_names, "importance": importances
        }).sort_values("importance", ascending=False)

        print("\nTop 10 des variables les plus importantes (explicabilite RF-20) :")
        print(importance_df.head(10).to_string(index=False))

        # Suivi MLflow
        mlflow.log_params({
            "model_type": "RandomForestClassifier",
            "n_estimators": 200,
            "max_depth": 5,
            "n_train_samples": len(X_train),
            "n_test_samples": len(X_test),
        })
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(pipeline, "model")

        # Sauvegarde locale pour utilisation par l'API (Phase 5, etape suivante)
        joblib.dump(pipeline, MODEL_OUTPUT_PATH)
        print(f"\nModele sauvegarde : {MODEL_OUTPUT_PATH}")
        print("Suivi de l'experimentation enregistre dans MLflow (dossier mlruns/).")


if __name__ == "__main__":
    main()