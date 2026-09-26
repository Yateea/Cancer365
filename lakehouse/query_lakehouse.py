"""
CancerCare360 - Utilitaire de requete sur le lakehouse
Configure la connexion DuckDB -> MinIO (memes reglages que profiles.yml)
puis execute une requete SQL donnee. A utiliser pour explorer les
donnees en dehors de dbt.

Usage:
    python lakehouse/query_lakehouse.py "SELECT * FROM main_silver.stg_events LIMIT 5"
"""

import sys

import duckdb
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

DUCKDB_FILE = "cancercare.duckdb"

MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"


def get_connection():
    """Ouvre une connexion DuckDB configuree pour lire MinIO (S3-compatible)."""
    con = duckdb.connect(DUCKDB_FILE)
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"SET s3_endpoint='{MINIO_ENDPOINT}'")
    con.execute(f"SET s3_access_key_id='{MINIO_ACCESS_KEY}'")
    con.execute(f"SET s3_secret_access_key='{MINIO_SECRET_KEY}'")
    con.execute("SET s3_use_ssl=false")
    con.execute("SET s3_url_style='path'")
    con.execute("SET s3_region='us-east-1'")
    return con


def main():
    if len(sys.argv) < 2:
        query = "SELECT * FROM main_silver.stg_events LIMIT 5"
        print(f"Aucune requete fournie, utilisation de la requete par defaut :\n  {query}\n")
    else:
        query = sys.argv[1]

    con = get_connection()
    result = con.execute(query).fetchdf()
    print(result)


if __name__ == "__main__":
    main()