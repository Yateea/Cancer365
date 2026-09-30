"""
CancerCare360 - Ingestion des donnees demographiques patient
Phase 4 (complement) - Les evenements de parcours sont deja dans le
lakehouse depuis la Phase 1, mais les donnees de reference du patient
(ville, centre principal, type de cancer) generees en Phase 0 n'avaient
jamais ete integrees. Necessaire pour la Healthcare Accessibility Map
(module M3).

Ces donnees sont statiques (pas de flux), donc ecrites directement en
Parquet dans MinIO plutot que transitant par Kafka (choix architectural
justifie : Kafka sert les evenements, pas les tables de reference).

Usage:
    python ingestion/ingest_patients_dimension.py
"""

import io
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio

PATIENTS_FILE = Path(__file__).parent.parent / "data" / "synthetic" / "patients.json"

MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"
MINIO_BUCKET = "cancercare-lakehouse"
OBJECT_NAME = "bronze/patients/patients.parquet"


def main():
    print("Chargement des donnees patient (reference Phase 0)...")
    with open(PATIENTS_FILE, "r", encoding="utf-8") as f:
        patients = json.load(f)
    print(f"  -> {len(patients)} patients charges.")

    df = pd.DataFrame(patients)
    table = pa.Table.from_pandas(df)

    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)

    print("Connexion a MinIO...")
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )

    client.put_object(
        bucket_name=MINIO_BUCKET,
        object_name=OBJECT_NAME,
        data=buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream",
    )

    print(f"\nTermine. {len(patients)} patients ecrits dans "
          f"s3://{MINIO_BUCKET}/{OBJECT_NAME}")


if __name__ == "__main__":
    main()