-- Table de features pour le Modele B (prediction de non-presentation).
-- Grain : un rendez-vous = une ligne (contrairement a ml_features_patient
-- qui etait au grain patient). Les variables de comportement passe
-- (prior_missed_count, days_since_prev_appointment) sont calculees
-- strictement a partir de l'historique ANTERIEUR a chaque rendez-vous,
-- pour eviter toute fuite d'information du futur vers le passe.

with events as (

    select * from {{ ref('stg_events') }}

),

patients as (

    select * from {{ ref('stg_patients') }}

),

appointment_events as (

    select * from events where event_type = 'appointment'

),

enriched as (

    select
        *,
        row_number() over (
            partition by patient_id order by event_timestamp
        ) as appointment_sequence,

        sum(case when status = 'missed' then 1 else 0 end) over (
            partition by patient_id order by event_timestamp
            rows between unbounded preceding and 1 preceding
        ) as prior_missed_count,

        lag(event_timestamp) over (
            partition by patient_id order by event_timestamp
        ) as prev_appointment_timestamp,

        dayofweek(event_timestamp) as day_of_week,
        month(event_timestamp) as month_of_year

    from appointment_events

)

select
    e.event_id,
    e.patient_id,
    p.age,
    p.gender,
    p.cancer_type,
    e.service,
    e.day_of_week,
    e.month_of_year,
    e.appointment_sequence,
    coalesce(e.prior_missed_count, 0) as prior_missed_count,
    coalesce(
        date_diff('day', e.prev_appointment_timestamp, e.event_timestamp), 0
    ) as days_since_prev_appointment,
    case when e.status = 'missed' then 1 else 0 end as is_no_show

from enriched e
join patients p on e.patient_id = p.patient_id
where e.status in ('completed', 'missed')