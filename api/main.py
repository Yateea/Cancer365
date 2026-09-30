"""
CancerCare360 - API backend (FastAPI)
Phase 4 - Sert les donnees du lakehouse (couche Gold) au frontend React
du Care Command Center via une API REST simple.

Pour l'instant en lecture seule : la cloture d'un signal avec commentaire
obligatoire (RF-13) sera ajoutee dans une iteration suivante.

Usage:
    uvicorn api.main:app --reload --port 8000
"""

import hashlib
import json
import math
from pathlib import Path

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

CENTERS_FILE = Path(__file__).parent.parent / "data" / "synthetic" / "care_centers.json"

with open(CENTERS_FILE, "r", encoding="utf-8") as f:
    CARE_CENTERS = json.load(f)

DUCKDB_FILE = "cancercare.duckdb"
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"

POSTGRES_URI = "postgresql+psycopg2://airflow:airflow@127.0.0.1:5434/airflow"
WAREHOUSE_LOCATION = "s3://cancercare-lakehouse/iceberg_warehouse"
NAMESPACE = "gold"
REVIEWS_TABLE = f"{NAMESPACE}.signal_reviews"
NOTES_TABLE = f"{NAMESPACE}.patient_notes"

app = FastAPI(title="CancerCare360 API")

# Autorise le frontend React (servi par Vite sur le port 5173) a appeler cette API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",  # Care Command Center
        "http://localhost:5174", "http://127.0.0.1:5174",  # Patient Companion
        "http://localhost:5175", "http://127.0.0.1:5175",  # Patient Companion (port de secours)
    ],
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


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance a vol d'oiseau entre deux points GPS (formule de haversine)."""
    R = 6371  # rayon de la Terre en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def get_approx_home_location(patient_id: str, center_lat: float, center_lon: float):
    """
    Approxime la position du domicile du patient par un leger decalage
    deterministe autour de son centre principal (0 a environ 60 km).

    Aucune adresse reelle n'est collectee ni stockee (minimisation des
    donnees, section 14 du cahier des charges) : ce decalage est calcule
    a la volee a partir d'un hash de l'identifiant pseudonymise, uniquement
    a des fins de demonstration de la cartographie d'accessibilite.
    """
    digest = hashlib.sha256(patient_id.encode()).hexdigest()
    # Deux nombres pseudo-aleatoires stables, dans [-1, 1]
    offset_lat = (int(digest[:8], 16) / 0xFFFFFFFF) * 2 - 1
    offset_lon = (int(digest[8:16], 16) / 0xFFFFFFFF) * 2 - 1
    # ~0.5 degre max (~50-60km au Maroc), reparti sur lat/lon
    return center_lat + offset_lat * 0.5, center_lon + offset_lon * 0.5


def compute_accessibility(patient_id: str, primary_center_id: str):
    primary_center = next((c for c in CARE_CENTERS if c["center_id"] == primary_center_id), None)
    if primary_center is None:
        return None

    home_lat, home_lon = get_approx_home_location(
        patient_id, primary_center["latitude"], primary_center["longitude"]
    )

    distances = []
    for center in CARE_CENTERS:
        d = haversine_km(home_lat, home_lon, center["latitude"], center["longitude"])
        distances.append((d, center))
    distances.sort(key=lambda x: x[0])

    nearest_distance, nearest_center = distances[0]
    primary_distance = next(d for d, c in distances if c["center_id"] == primary_center_id)

    avg_speed_kmh = 50  # hypothese simple pour l'estimation du temps de trajet
    travel_time_min = round((primary_distance / avg_speed_kmh) * 60)

    accessibility_score = max(0, round(100 - 2 * primary_distance))

    return {
        "patient_id": patient_id,
        "home_latitude": round(home_lat, 5),
        "home_longitude": round(home_lon, 5),
        "primary_center": {
            "center_id": primary_center["center_id"],
            "name": primary_center["name"],
            "city": primary_center["city"],
            "latitude": primary_center["latitude"],
            "longitude": primary_center["longitude"],
            "distance_km": round(primary_distance, 1),
        },
        "nearest_center": {
            "center_id": nearest_center["center_id"],
            "name": nearest_center["name"],
            "city": nearest_center["city"],
            "latitude": nearest_center["latitude"],
            "longitude": nearest_center["longitude"],
            "distance_km": round(nearest_distance, 1),
        },
        "travel_time_min": travel_time_min,
        "accessibility_score": accessibility_score,
        "uses_nearest_center": nearest_center["center_id"] == primary_center_id,
    }



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


class NoteRequest(BaseModel):
    text: str


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


@app.get("/api/centers")
def get_centers():
    """Liste des centres de soin avec un taux de fiabilite approxime
    (RF-10) : proportion des rendez-vous non manques/annules sur ce centre."""
    con = get_connection()
    df = con.execute(
        """
        SELECT center_name,
               COUNT(*) FILTER (WHERE event_type = 'appointment') as total_appointments,
               COUNT(*) FILTER (WHERE event_type = 'appointment' AND status = 'completed') as completed
        FROM main_silver.stg_events
        GROUP BY center_name
        """
    ).fetchdf()
    reliability = {
        row["center_name"]: (
            round(100 * row["completed"] / row["total_appointments"])
            if row["total_appointments"] else None
        )
        for _, row in df.iterrows()
    }

    centers = []
    for c in CARE_CENTERS:
        centers.append({
            **c,
            "reliability_pct": reliability.get(c["name"]),
        })
    return clean(centers)


@app.get("/api/patient/{patient_id}/accessibility")
def get_patient_accessibility(patient_id: str):
    con = get_connection()
    df = con.execute(
        "SELECT primary_center_id FROM main_silver.stg_patients WHERE patient_id = ?",
        [patient_id],
    ).fetchdf()
    if df.empty:
        raise HTTPException(status_code=404, detail="Patient introuvable.")

    result = compute_accessibility(patient_id, df.iloc[0]["primary_center_id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Centre principal introuvable.")
    return clean(result)


@app.get("/api/patient-ids")
def get_patient_ids():
    """Liste des patients disponibles (pas d'authentification dans ce prototype :
    l'utilisateur choisit un patient a consulter, comme sur un poste partage)."""
    con = get_connection()
    df = con.execute(
        "SELECT patient_id FROM main_gold.patient_summary ORDER BY patient_id"
    ).fetchdf()
    return clean(df["patient_id"].tolist())


@app.get("/api/patient/{patient_id}/journey")
def get_patient_journey(patient_id: str):
    """Chronologie complete des evenements d'un patient (template T1)."""
    con = get_connection()
    df = con.execute(
        """
        SELECT event_id, event_type, event_timestamp, service, status, center_name
        FROM main_silver.stg_events
        WHERE patient_id = ?
        ORDER BY event_timestamp ASC
        """,
        [patient_id],
    ).fetchdf()
    if "event_timestamp" in df.columns:
        df["event_timestamp"] = df["event_timestamp"].astype(str)
    return clean(df.to_dict(orient="records"))


@app.get("/api/patient/{patient_id}/notes")
def get_patient_notes(patient_id: str):
    """Carnet de questions du patient (RF-16) : notes libres, jamais interpretees."""
    catalog = get_iceberg_catalog()
    try:
        table = catalog.load_table(NOTES_TABLE)
        df = table.scan().to_arrow().to_pandas()
    except NoSuchTableError:
        return []

    df = df[df["patient_id"] == patient_id].sort_values("created_at", ascending=False)
    return clean(df.to_dict(orient="records"))


@app.post("/api/patient/{patient_id}/notes")
def add_patient_note(patient_id: str, note: NoteRequest):
    """RF-16 : le patient ajoute une note libre (question, symptome a discuter).
    Aucune interpretation automatique n'est faite de ce contenu."""
    text = note.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="La note ne peut pas etre vide.")

    created_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    row = pa.table({
        "patient_id": [patient_id],
        "text": [text],
        "created_at": [created_at],
    })

    catalog = get_iceberg_catalog()
    try:
        table = catalog.load_table(NOTES_TABLE)
        table.append(row)
    except NoSuchTableError:
        table = catalog.create_table(NOTES_TABLE, schema=row.schema)
        table.append(row)

    return {"status": "saved", "patient_id": patient_id, "created_at": created_at}


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