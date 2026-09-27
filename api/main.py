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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

DUCKDB_FILE = "cancercare.duckdb"
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"

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
    return clean(df.to_dict(orient="records"))