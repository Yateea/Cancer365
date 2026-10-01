-- Table de features pour le Modele A (follow-up risk).
-- IMPORTANT : on exclut deliberement les variables utilisees par les regles
-- du Care Signal Engine (days_since_last_contact, missed_appointments_count,
-- has_future_appointment) pour eviter que le modele ne fasse que "reapprendre"
-- la regle elle-meme. Le but est de detecter un profil a risque a partir de
-- caracteristiques differentes (demographie, repartition des types
-- d'evenements), potentiellement plus tot que la regle ne le ferait.

with patients as (

    select * from {{ ref('stg_patients') }}

),

events as (

    select * from {{ ref('stg_events') }}

),

event_counts as (

    select
        patient_id,
        count(*) filter (where event_type = 'lab_result') as lab_result_count,
        count(*) filter (where event_type = 'treatment') as treatment_count,
        count(*) filter (where event_type = 'hospitalization') as hospitalization_count,
        count(*) filter (where event_type = 'discharge') as discharge_count,
        count(*) filter (where event_type = 'followup') as followup_count,
        count(*) as total_events

    from events
    group by patient_id

),

labels as (

    -- Label = 1 si le patient a declenche un signal de risque (Phase 3)
    select distinct patient_id, 1 as is_at_risk
    from {{ ref('care_signals') }}

)

select
    p.patient_id,
    p.age,
    p.gender,
    p.cancer_type,
    p.primary_center_id,
    date_diff('day', p.diagnosis_date, current_date) as days_since_diagnosis,
    coalesce(ec.lab_result_count, 0) as lab_result_count,
    coalesce(ec.treatment_count, 0) as treatment_count,
    coalesce(ec.hospitalization_count, 0) as hospitalization_count,
    coalesce(ec.discharge_count, 0) as discharge_count,
    coalesce(ec.followup_count, 0) as followup_count,
    coalesce(ec.total_events, 0) as total_events,
    coalesce(l.is_at_risk, 0) as is_at_risk

from patients p
left join event_counts ec on p.patient_id = ec.patient_id
left join labels l on p.patient_id = l.patient_id
