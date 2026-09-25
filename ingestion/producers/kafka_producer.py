"""
CancerCare360 - Producteur Kafka
Phase 1 - Simule l'arrivee en continu des evenements de parcours patient
(hopital, app patient, labo) en les publiant dans un topic Kafka.

Prerequis : l'infrastructure Docker (Kafka) doit etre lancee :
    docker compose -f infra/docker/docker-compose.yml up -d

Usage:
    python ingestion/producers/kafka_producer.py
"""

import json
import time
from pathlib import Path

from confluent_kafka import Producer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
TOPIC_NAME = "patient-events"
EVENTS_FILE = Path(__file__).parent.parent.parent / "data" / "synthetic" / "events.json"
DELAY_BETWEEN_EVENTS_SECONDS = 0.05  # simulate a steady stream, not instant dump


def delivery_report(err, msg):
    """Callback appele par Kafka pour chaque message, succes ou echec."""
    if err is not None:
        print(f"  [ECHEC] Livraison impossible : {err}")
    # En cas de succes, on ne log pas chaque message pour ne pas saturer la console
    # (voir le compteur global affiche a la fin a la place)


def load_events():
    """Charge les evenements synthetiques generes en Phase 0."""
    if not EVENTS_FILE.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {EVENTS_FILE}\n"
            "Avez-vous bien execute data/synthetic/generate_data.py au prealable ?"
        )
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print(f"Connexion a Kafka ({KAFKA_BOOTSTRAP_SERVERS})...")
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})

    print("Chargement des evenements synthetiques...")
    events = load_events()
    print(f"  -> {len(events)} evenements a envoyer dans le topic '{TOPIC_NAME}'.\n")

    sent_count = 0
    for event in events:
        # La cle du message = patient_id : garantit que tous les evenements
        # d'un meme patient arrivent toujours dans le meme ordre (meme partition Kafka).
        key = event["patient_id"]
        value = json.dumps(event, ensure_ascii=False)

        producer.produce(
            topic=TOPIC_NAME,
            key=key,
            value=value,
            callback=delivery_report,
        )

        # Laisse Kafka traiter les callbacks en arriere-plan sans bloquer
        producer.poll(0)

        sent_count += 1
        if sent_count % 100 == 0:
            print(f"  ... {sent_count}/{len(events)} evenements envoyes")

        time.sleep(DELAY_BETWEEN_EVENTS_SECONDS)

    print("\nEnvoi termine, vidage du buffer (flush)...")
    producer.flush()

    print(f"\nTermine. {sent_count} evenements publies dans le topic '{TOPIC_NAME}'.")


if __name__ == "__main__":
    main()