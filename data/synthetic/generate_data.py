"""
CancerCare360 - Générateur de données synthétiques
Phase 0 - Génère des patients fictifs et leur chronologie d'événements
de parcours de soin, rattachés à de vrais centres d'oncologie marocains.

Usage:
    python data/synthetic/generate_data.py
"""

import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

fake = Faker("fr_FR")
random.seed(42)  # reproductibilité : mêmes données générées à chaque exécution

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NB_PATIENTS = 200
CURRENT_DIR = Path(__file__).parent
CENTERS_FILE = CURRENT_DIR / "care_centers.json"
OUTPUT_PATIENTS_FILE = CURRENT_DIR / "patients.json"
OUTPUT_EVENTS_FILE = CURRENT_DIR / "events.json"

EVENT_TYPES = ["appointment", "lab_result", "treatment", "hospitalization", "discharge", "followup"]
STATUSES = ["scheduled", "completed", "missed", "cancelled"]
SOURCE_SYSTEMS = ["hospital_api", "patient_app", "lab_csv"]

# Poids réalistes : la majorité des événements sont complétés, une minorité manquée/annulée
STATUS_WEIGHTS = [0.15, 0.65, 0.12, 0.08]  # scheduled, completed, missed, cancelled


def load_care_centers():
    """Charge la liste réelle des centres d'oncologie marocains."""
    with open(CENTERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_patient(index, centers):
    """
    Génère un patient fictif.
    Le nom/prénom généré par Faker n'est utilisé QUE pour la génération interne
    (simuler une source de données réaliste) : il n'est jamais exporté tel quel.
    Seul l'identifiant pseudonymisé est conservé dans le fichier de sortie,
    conformément au principe de pseudonymisation dès l'ingestion (section 14 du CDC).
    """
    patient_id = f"P-{10000 + index}"
    home_center = random.choice(centers)

    return {
        "patient_id": patient_id,
        "age": random.randint(28, 85),
        "gender": random.choice(["M", "F"]),
        "home_city": home_center["city"],
        "primary_center_id": home_center["center_id"],
        "diagnosis_date": fake.date_between(start_date="-2y", end_date="-1m").isoformat(),
        "cancer_type": random.choice(
            ["sein", "colorectal", "poumon", "prostate", "lymphome", "leucemie", "autre"]
        ),
    }


def generate_events_for_patient(patient, centers):
    """
    Génère une chronologie réaliste d'événements pour un patient,
    conforme au schéma défini dans ingestion/event_schema.json.
    """
    events = []
    center = next(c for c in centers if c["center_id"] == patient["primary_center_id"])

    diagnosis_date = datetime.fromisoformat(patient["diagnosis_date"])
    current_date = diagnosis_date
    nb_events = random.randint(4, 12)

    for _ in range(nb_events):
        current_date += timedelta(days=random.randint(7, 45))
        if current_date > datetime.now():
            break

        event_type = random.choices(
            EVENT_TYPES,
            weights=[0.30, 0.20, 0.25, 0.10, 0.05, 0.10],
        )[0]
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        service = random.choice(center["services"])

        event = {
            "event_id": str(uuid.uuid4()),
            "patient_id": patient["patient_id"],
            "event_type": event_type,
            "event_timestamp": current_date.isoformat(),
            "service": service,
            "status": status,
            "source_system": random.choice(SOURCE_SYSTEMS),
            "metadata": {
                "center_id": center["center_id"],
                "center_name": center["name"],
            },
        }
        events.append(event)

    return events


def main():
    print("Chargement des centres de soin...")
    centers = load_care_centers()
    print(f"  -> {len(centers)} centres charges.")

    print(f"Generation de {NB_PATIENTS} patients synthetiques...")
    patients = [generate_patient(i, centers) for i in range(NB_PATIENTS)]

    print("Generation des evenements de parcours...")
    all_events = []
    for patient in patients:
        all_events.extend(generate_events_for_patient(patient, centers))

    with open(OUTPUT_PATIENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(patients, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)

    print()
    print("Termine.")
    print(f"  -> {len(patients)} patients ecrits dans {OUTPUT_PATIENTS_FILE}")
    print(f"  -> {len(all_events)} evenements ecrits dans {OUTPUT_EVENTS_FILE}")


if __name__ == "__main__":
    main()