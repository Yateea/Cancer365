-- Couche Gold : une ligne par patient, avec les metriques de parcours
-- necessaires a la detection de signaux de rupture de suivi
-- (RF-04, RF-05, RF-06 du cahier des charges).

with events as (

    select * from {{ ref('stg_events') }}

),

aggregated as (

    select
        patient_id,

        count(*) as total_events,

        max(event_timestamp) as last_event_date,

        -- RF-04 : delai depuis le dernier contact (en jours)
        date_diff('day', max(event_timestamp), current_timestamp) as days_since_last_contact,

        -- RF-06 : nombre de rendez-vous manques
        count(*) filter (where event_type = 'appointment' and status = 'missed')
            as missed_appointments_count,

        -- RF-05 : existence d'un rendez-vous futur planifie
        max(
            case
                when event_type = 'appointment'
                     and status = 'scheduled'
                     and event_timestamp > current_timestamp
                then 1
                else 0
            end
        ) as has_future_appointment

    from events
    group by patient_id

)

select * from aggregated