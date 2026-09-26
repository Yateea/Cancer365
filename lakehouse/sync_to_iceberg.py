"""
CancerCare360 - Synchronisation Lakehouse -> Apache Iceberg
Phase 2 (complement) - Lit les tables Gold (patient_summary, care_signals)
depuis DuckDB et les ecrit comme de VRAIES tables Iceberg : catalogue SQL
stocke dans Postgres, donnees stockees dans MinIO (S3-compatible).

Cela apporte le versioning (time travel), les transactions ACID et
l'evolution de schema decrits section 8 du cahier des charges, sans
deployer un serveur Apache Polaris complet (choix documente dans
docs/architecture.md).

Prerequis :
    - L'infrastructure Docker doit tourner (MinIO + Postgres)
    - dbt run doit avoir deja ete execute (tables Gold presentes)

Usage:
    python lakehouse/sync_to_iceberg.py
"""

import duckdb
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.exceptions import NoSuchTableError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DUCKDB_FILE = "cancercare.duckdb"

MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"

POSTGRES_URI = "postgresql+psycopg2://airflow:airflow@127.0.0.1:5434/airflow"
WAREHOUSE_LOCATION = "s3://cancercare-lakehouse/iceberg_warehouse"

NAMESPACE = "gold"
TABLES_TO_SYNC = ["patient_summary", "care_signals"]


def get_duckdb_connection():
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


def get_iceberg_catalog():
    """Catalogue Iceberg : metadonnees dans Postgres, donnees dans MinIO."""
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


def sync_table(catalog, con, table_name: str):
    """Lit une table Gold depuis DuckDB et l'ecrit (ou la remplace) dans Iceberg."""
    print(f"\nLecture de main_{NAMESPACE}.{table_name} depuis DuckDB...")
    arrow_table = con.execute(f"SELECT * FROM main_{NAMESPACE}.{table_name}").fetch_arrow_table()
    print(f"  -> {arrow_table.num_rows} lignes lues.")

    identifier = f"{NAMESPACE}.{table_name}"

    try:
        iceberg_table = catalog.load_table(identifier)
        print(f"  -> Table Iceberg '{identifier}' existante, remplacement des donnees...")
        iceberg_table.overwrite(arrow_table)
    except NoSuchTableError:
        print(f"  -> Creation de la table Iceberg '{identifier}'...")
        iceberg_table = catalog.create_table(identifier, schema=arrow_table.schema)
        iceberg_table.append(arrow_table)

    print(f"  -> OK : {len(iceberg_table.scan().to_arrow())} lignes dans la table Iceberg.")


def main():
    print("Connexion au catalogue Iceberg (Postgres + MinIO)...")
    catalog = get_iceberg_catalog()

    if NAMESPACE not in [ns[0] for ns in catalog.list_namespaces()]:
        catalog.create_namespace(NAMESPACE)
        print(f"  -> Namespace '{NAMESPACE}' cree.")
    else:
        print(f"  -> Namespace '{NAMESPACE}' deja existant.")

    con = get_duckdb_connection()

    for table_name in TABLES_TO_SYNC:
        sync_table(catalog, con, table_name)

    print("\nTermine. Tables Iceberg synchronisees :")
    for table_name in TABLES_TO_SYNC:
        print(f"  - {NAMESPACE}.{table_name}")


if __name__ == "__main__":
    main()