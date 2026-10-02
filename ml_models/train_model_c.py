"""
CancerCare360 - Modele C : Prevision de la demande (time series)
Phase 5 - Predit le volume hebdomadaire d'evenements a partir de
l'historique recent (valeurs des semaines precedentes, moyenne mobile).

IMPORTANT - methodologie serie temporelle : contrairement aux Modeles A
et B (classification), le decoupage train/test se fait ICI de maniere
chronologique (les dernieres semaines servent de test), jamais aleatoire,
pour eviter toute fuite d'information du futur vers le passe.

Usage:
    python ml_models/train_model_c.py
"""

import sys
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, str(Path(__file__).parent.parent / "lakehouse"))
from query_lakehouse import get_connection

N_LAGS = 4
TEST_SIZE_WEEKS = 15  # ~15% des 103 semaines disponibles
FORECAST_HORIZON_WEEKS = 4  # horizon parametrable (RF-18)

MODEL_OUTPUT_PATH = Path(__file__).parent / "model_c_demand_forecast.pkl"


def load_data() -> pd.DataFrame:
    con = get_connection()
    df = con.execute(
        "SELECT * FROM main_gold.service_demand_weekly ORDER BY week_start"
    ).fetchdf()
    df["week_start"] = pd.to_datetime(df["week_start"])
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cree les variables de decalage (lags) et la moyenne mobile."""
    df = df.copy()
    for lag in range(1, N_LAGS + 1):
        df[f"lag_{lag}"] = df["event_count"].shift(lag)
    df["rolling_mean_4"] = df["event_count"].shift(1).rolling(window=4).mean()
    return df.dropna().reset_index(drop=True)


def main():
    print("Chargement de la serie hebdomadaire...")
    raw = load_data()
    print(f"  -> {len(raw)} semaines chargees ({raw['week_start'].min().date()} "
          f"a {raw['week_start'].max().date()})")

    df = build_features(raw)
    feature_cols = [f"lag_{i}" for i in range(1, N_LAGS + 1)] + ["rolling_mean_4"]

    # Decoupage CHRONOLOGIQUE (pas aleatoire) : les dernieres semaines = test
    train = df.iloc[:-TEST_SIZE_WEEKS]
    test = df.iloc[-TEST_SIZE_WEEKS:]
    print(f"  -> Entrainement : {len(train)} semaines, Test : {len(test)} semaines "
          f"(les plus recentes)")

    X_train, y_train = train[feature_cols], train["event_count"]
    X_test, y_test = test[feature_cols], test["event_count"]

    mlflow.set_experiment("cancercare360_model_c_demand_forecast")

    with mlflow.start_run():
        model = RandomForestRegressor(n_estimators=200, max_depth=4, random_state=42)

        print("\nEntrainement du modele...")
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)

        metrics = {
            "mae": mean_absolute_error(y_test, y_pred),
            "rmse": mean_squared_error(y_test, y_pred) ** 0.5,
            "r2": r2_score(y_test, y_pred),
        }

        print("\nMetriques d'evaluation (semaines les plus recentes, jamais vues) :")
        for name, value in metrics.items():
            print(f"  {name:6s} : {value:.2f}")

        baseline_pred = test["lag_1"]  # "ca ne change pas par rapport a la semaine d'avant"
        baseline_mae = mean_absolute_error(y_test, baseline_pred)
        print(f"\nPour comparaison, un modele naif ('identique a la semaine "
              f"precedente') obtient un MAE de {baseline_mae:.2f}")
        print("(un bon modele doit faire mieux que cette base naive)")

        importance_df = pd.DataFrame({
            "feature": feature_cols, "importance": model.feature_importances_
        }).sort_values("importance", ascending=False)
        print("\nImportance des variables (explicabilite RF-20) :")
        print(importance_df.to_string(index=False))

        mlflow.log_params({
            "model_type": "RandomForestRegressor",
            "n_estimators": 200,
            "max_depth": 4,
            "n_lags": N_LAGS,
            "test_size_weeks": TEST_SIZE_WEEKS,
        })
        mlflow.log_metrics(metrics)
        mlflow.log_metric("baseline_mae", baseline_mae)
        mlflow.sklearn.log_model(model, "model")

        joblib.dump(model, MODEL_OUTPUT_PATH)

        # Prevision future (horizon parametrable - RF-18)
        print(f"\nPrevision pour les {FORECAST_HORIZON_WEEKS} prochaines semaines :")
        history = list(df["event_count"].values)
        last_date = raw["week_start"].max()

        for i in range(FORECAST_HORIZON_WEEKS):
            lags = {f"lag_{lag}": history[-lag] for lag in range(1, N_LAGS + 1)}
            lags["rolling_mean_4"] = sum(history[-4:]) / 4
            next_features = pd.DataFrame([lags])[feature_cols]
            next_pred = model.predict(next_features)[0]

            next_date = last_date + pd.Timedelta(weeks=i + 1)
            print(f"  Semaine du {next_date.date()} : {next_pred:.0f} evenements estimes")
            history.append(next_pred)

        print(f"\nModele sauvegarde : {MODEL_OUTPUT_PATH}")


if __name__ == "__main__":
    main()