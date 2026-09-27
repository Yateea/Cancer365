"""
CancerCare360 - API backend (FastAPI)
Phase 4 - Sert les donnees du lakehouse (couche Gold) au frontend React
du Care Command Center via une API REST simple.

Pour l'instant en lecture seule : la cloture d'un signal avec commentaire
obligatoire (RF-13) sera ajoutee dans une iteration suivante.

Usage:
    uvicorn api.main:app --reload --port 8000
"""

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.exceptions import NoSuchTableError

DUCKDB_FILE = "cancercare.duckdb"
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"

POSTGRES_URI = "postgresql+psycopg2://airflow:airflow@127.0.0.1:5434/airflow"
WAREHOUSE_LOCATION = "s3://cancercare-lakehouse/iceberg_warehouse"
NAMESPACE = "gold"
REVIEWS_TABLE = f"{NAMESPACE}.signal_reviews"

app = FastAPI(title="CancerCare360 API")

# Autorise le frontend React (servi par Vite sur le port 5173) a appeler cette API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection():
    """Ouvre une connexion DuckDB configuree pour lire MinIO (S3-compatible)."""
    con = duckdb.connect(DUCKDB_FILE, read_only=True)
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"SET s3_endpoint='{MINIO_ENDPOINT}'")
    con.execute(f"SET s3_access_key_id='{MINIO_ACCESS_KEY}'")
    con.execute(f"SET s3_secret_access_key='{MINIO_SECRET_KEY}'")
    con.execute("SET s3_use_ssl=false")
    con.execute("SET s3_url_style='path'")
    con.execute("SET s3_region='us-east-1'")
    return con


def get_iceberg_catalog():
    """Catalogue Iceberg : metadonnees dans Postgres, donnees dans MinIO
    (meme configuration que lakehouse/sync_to_iceberg.py)."""
    return SqlCatalog(
        "cancercare360",
        **{
            "uri": POSTGRES_URI,
            "warehouse": WAREHOUSE_LOCATION,
            "s3.endpoint": f"http://{MINIO_ENDPOINT}",
            "s3.access-key-id": MINIO_ACCESS_KEY,
            "s3.secret-access-key": MINIO_SECRET_KEY,
            "s3.path-style-access": "true",
            "s3.region": "us-east-1",
        },
    )


def get_reviews_df() -> pd.DataFrame:
    """Charge les revues deja enregistrees (table Iceberg gold.signal_reviews).
    Renvoie un DataFrame vide si la table n'existe pas encore (aucune revue)."""
    catalog = get_iceberg_catalog()
    try:
        table = catalog.load_table(REVIEWS_TABLE)
        return table.scan().to_arrow().to_pandas()
    except NoSuchTableError:
        return pd.DataFrame(columns=["patient_id", "comment", "reviewed_at"])


class ReviewRequest(BaseModel):
    comment: str


def clean(obj):
    """Convertit recursivement les types numpy/pandas en types Python natifs
    (int64, float64, ndarray...), sinon FastAPI echoue a serialiser le JSON."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, np.ndarray)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/patients")
def get_patients():
    con = get_connection()
    df = con.execute("SELECT * FROM main_gold.patient_summary").fetchdf()
    if "last_event_date" in df.columns:
        df["last_event_date"] = df["last_event_date"].astype(str)
    return clean(df.to_dict(orient="records"))


@app.get("/api/signals")
def get_signals():
    con = get_connection()
    df = con.execute("SELECT * FROM main_gold.care_signals").fetchdf()
    for col in ("last_event_date", "generated_at"):
        if col in df.columns:
            df[col] = df[col].astype(str)

    reviews_df = get_reviews_df()
    reviews_map = (
        {r["patient_id"]: r for r in reviews_df.to_dict(orient="records")}
        if len(reviews_df) else {}
    )

    records = df.to_dict(orient="records")
    for rec in records:
        review = reviews_map.get(rec["patient_id"])
        if review:
            rec["status"] = "closed"
            rec["comment"] = review.get("comment")
            rec["reviewed_at"] = str(review.get("reviewed_at"))
        else:
            rec["comment"] = None
            rec["reviewed_at"] = None

    return clean(records)


@app.post("/api/signals/{patient_id}/review")
def review_signal(patient_id: str, review: ReviewRequest):
    """RF-13 : cloture un signal apres revue humaine, commentaire obligatoire."""
    comment = review.comment.strip()
    if not comment:
        raise HTTPException(
            status_code=400,
            detail="Un commentaire est obligatoire pour cloturer un signal (RF-13).",
        )

    # Stocke en chaine de caracteres (pas en timestamp) pour eviter le probleme
    # de fuseau horaire nomme rencontre lors de la Phase 2 (Africa/Casablanca
    # non supporte par Iceberg).
    reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    row = pa.table({
        "patient_id": [patient_id],
        "comment": [comment],
        "reviewed_at": [reviewed_at],
    })

    catalog = get_iceberg_catalog()
    try:
        table = catalog.load_table(REVIEWS_TABLE)
        table.append(row)
    except NoSuchTableError:
        table = catalog.create_table(REVIEWS_TABLE, schema=row.schema)
        table.append(row)

    return {"status": "reviewed", "patient_id": patient_id, "reviewed_at": reviewed_at}