"""
CancerCare360 - Consommateur Kafka -> MinIO (couche Bronze du lakehouse)
Phase 1 - Lit les evenements du topic Kafka 'patient-events', les regroupe
par lots, verifie l'absence de donnees identifiantes (garde-fou de
pseudonymisation, section 14 du cahier des charges), puis les ecrit en
fichiers Parquet dans le bucket MinIO 'cancercare-lakehouse'.

Prerequis :
    - L'infrastructure Docker doit tourner (Kafka + MinIO)
    - Le producteur (kafka_producer.py) doit avoir deja publie des evenements

Usage:
    python ingestion/consumer_to_minio.py
"""

import io
import json
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
from confluent_kafka import Consumer, KafkaError
from minio import Minio

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
TOPIC_NAME = "patient-events"
CONSUMER_GROUP_ID = "cancercare-bronze-writer"

MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"
MINIO_BUCKET = "cancercare-lakehouse"
MINIO_SECURE = False  # True uniquement si HTTPS est configure

BATCH_SIZE = 200          # nombre d'evenements par fichier Parquet
POLL_TIMEOUT_SECONDS = 5.0  # temps d'attente max sans nouveau message avant d'arreter

# Champs qui NE DOIVENT JAMAIS apparaitre dans les donnees analytiques
# (garde-fou de pseudonymisation, section 14 du cahier des charges).
FORBIDDEN_FIELDS = {"name", "nom", "prenom", "first_name", "last_name",
                     "phone", "telephone", "address", "adresse", "email"}


def check_no_identifying_data(event: dict) -> None:
    """
    Verifie qu'aucun champ directement identifiant ne se trouve dans
    l'evenement, y compris a l'interieur de 'metadata'. Leve une exception
    si une fuite potentielle est detectee, plutot que de l'ecrire en silence.
    """
    flat_keys = set(event.keys())
    if "metadata" in event and isinstance(event["metadata"], dict):
        flat_keys |= set(event["metadata"].keys())

    leaked = flat_keys & FORBIDDEN_FIELDS
    if leaked:
        raise ValueError(
            f"ALERTE PRIVACY BY DESIGN : champ(s) potentiellement identifiant(s) "
            f"detecte(s) dans un evenement : {leaked}. Ecriture bloquee."
        )


def ensure_bucket_exists(client: Minio, bucket_name: str) -> None:
    """Cree le bucket MinIO s'il n'existe pas deja."""
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        print(f"  -> Bucket '{bucket_name}' cree.")
    else:
        print(f"  -> Bucket '{bucket_name}' deja existant.")


def write_batch_to_minio(client: Minio, events: list[dict], batch_number: int) -> None:
    """
    Convertit un lot d'evenements en table PyArrow, l'ecrit en Parquet
    en memoire, puis l'envoie dans MinIO sous la couche 'bronze'.
    """
    table = pa.Table.from_pylist(events)

    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    buffer.seek(0)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_name = f"bronze/events/batch_{timestamp}_{batch_number:04d}.parquet"

    client.put_object(
        bucket_name=MINIO_BUCKET,
        object_name=object_name,
        data=buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream",
    )
    print(f"  -> Lot {batch_number} ecrit : {len(events)} evenements -> {object_name}")


def main():
    print(f"Connexion a MinIO ({MINIO_ENDPOINT})...")
    minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )
    ensure_bucket_exists(minio_client, MINIO_BUCKET)

    print(f"\nConnexion a Kafka ({KAFKA_BOOTSTRAP_SERVERS})...")
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": CONSUMER_GROUP_ID,
        "auto.offset.reset": "earliest",  # lire depuis le debut du topic
    })
    consumer.subscribe([TOPIC_NAME])

    print(f"Lecture du topic '{TOPIC_NAME}' (arret automatique apres "
          f"{POLL_TIMEOUT_SECONDS:.0f}s sans nouveau message)...\n")

    buffer_events = []
    batch_number = 1
    total_consumed = 0

    try:
        while True:
            msg = consumer.poll(timeout=POLL_TIMEOUT_SECONDS)

            if msg is None:
                # Plus aucun message disponible : on ecrit ce qu'il reste et on arrete
                break

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    print(f"  [ERREUR KAFKA] {msg.error()}")
                    continue

            event = json.loads(msg.value().decode("utf-8"))

            # Garde-fou Privacy by Design : on verifie AVANT d'ecrire quoi que ce soit
            check_no_identifying_data(event)

            buffer_events.append(event)
            total_consumed += 1

            if len(buffer_events) >= BATCH_SIZE:
                write_batch_to_minio(minio_client, buffer_events, batch_number)
                batch_number += 1
                buffer_events = []

    finally:
        # Ecrire le dernier lot partiel s'il en reste
        if buffer_events:
            write_batch_to_minio(minio_client, buffer_events, batch_number)

        consumer.close()

    print(f"\nTermine. {total_consumed} evenements consommes et ecrits dans "
          f"MinIO (bucket '{MINIO_BUCKET}', prefixe 'bronze/events/').")


if __name__ == "__main__":
    main()