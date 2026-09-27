"""
CancerCare360 - Care Command Center
Phase 4 - Interface professionnelle (module M7) affichant les KPIs globaux
et la liste des signaux de rupture de suivi generes par le Care Signal
Engine, avec leurs facteurs contributifs (jamais un signal "boite noire").

Usage:
    streamlit run frontend/command_center/app.py
"""

import duckdb
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DUCKDB_FILE = "cancercare.duckdb"
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"

st.set_page_config(
    page_title="CancerCare360 - Care Command Center",
    page_icon="🩺",
    layout="wide",
)


@st.cache_resource
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


@st.cache_data(ttl=60)
def load_patient_summary() -> pd.DataFrame:
    con = get_connection()
    return con.execute("SELECT * FROM main_gold.patient_summary").fetchdf()


@st.cache_data(ttl=60)
def load_care_signals() -> pd.DataFrame:
    con = get_connection()
    return con.execute("SELECT * FROM main_gold.care_signals").fetchdf()


# ---------------------------------------------------------------------------
# En-tete
# ---------------------------------------------------------------------------
st.title("🩺 Care Command Center")
st.caption(
    "CancerCare360 — Vue professionnelle du parcours patient. "
    "Aucun signal ci-dessous n'est un diagnostic : chaque signal necessite "
    "une revue humaine (voir facteurs contributifs)."
)

patients = load_patient_summary()
signals = load_care_signals()

# ---------------------------------------------------------------------------
# KPIs globaux (template T4)
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Patients actifs", len(patients))

with col2:
    open_signals = signals[signals["status"] == "open"]
    st.metric("Signaux ouverts", len(open_signals))

with col3:
    pct = round(100 * len(signals) / len(patients), 1) if len(patients) else 0
    st.metric("Taux de signal", f"{pct}%")

with col4:
    avg_delay = round(patients["days_since_last_contact"].mean(), 0) if len(patients) else 0
    st.metric("Delai moyen depuis dernier contact", f"{avg_delay:.0f} j")

st.divider()

# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------
st.subheader("Signaux de rupture de suivi")

col_filter1, col_filter2 = st.columns([1, 2])

with col_filter1:
    status_filter = st.selectbox(
        "Statut du signal",
        options=["Tous"] + sorted(signals["status"].unique().tolist()),
    )

with col_filter2:
    min_missed = st.slider(
        "Nombre minimum de rendez-vous manques",
        min_value=0,
        max_value=int(patients["missed_appointments_count"].max()) if len(patients) else 0,
        value=0,
    )

filtered = signals.copy()
if status_filter != "Tous":
    filtered = filtered[filtered["status"] == status_filter]

filtered = filtered.merge(
    patients[["patient_id", "missed_appointments_count"]],
    on="patient_id",
    how="left",
)
filtered = filtered[filtered["missed_appointments_count"] >= min_missed]
filtered = filtered.sort_values("days_since_last_contact", ascending=False) \
    if "days_since_last_contact" in filtered.columns else filtered

st.write(f"**{len(filtered)} signal(aux)** correspondant aux filtres.")

# ---------------------------------------------------------------------------
# Liste des signaux, chacun avec ses facteurs contributifs (template T2)
# ---------------------------------------------------------------------------
for _, row in filtered.iterrows():
    factors = row["contributing_factors"]
    factors_text = " • ".join(factors) if isinstance(factors, (list,)) else str(factors)

    with st.expander(
        f"🟠 {row['patient_id']} — {row['signal_type']} "
        f"(dernier contact : {row['last_event_date']})"
    ):
        st.markdown("**Facteurs contributifs :**")
        st.markdown(f"- {factors_text.replace(' • ', chr(10) + '- ')}")
        st.markdown(f"**Statut :** `{row['status']}`")
        st.markdown("⚠️ *Ce signal necessite une revue humaine avant toute action.*")
        st.button("Marquer comme revu (a venir)", key=f"review_{row['patient_id']}", disabled=True)

if len(filtered) == 0:
    st.info("Aucun signal ne correspond aux filtres selectionnes.")