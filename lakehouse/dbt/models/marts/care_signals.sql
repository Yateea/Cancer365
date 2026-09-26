-- Care Signal Engine (module M2 du cahier des charges).
-- Applique des regles simples et EXPLICABLES sur les metriques patient
-- pour detecter un risque de rupture de suivi.
--
-- Principe directeur (section 1.2) : Patient -> Data -> Intelligence -> Human action.
-- Ce modele ne pose JAMAIS de diagnostic. Chaque signal est accompagne de ses
-- facteurs contributifs (RF-07) et marque comme necessitant une revue humaine (RF-08).

with patient_metrics as (

    select * from {{ ref('patient_summary') }}

),

evaluated as (

    select
        patient_id,

        -- RF-05 : absence de rendez-vous futur planifie
        (has_future_appointment = 0) as no_future_appointment,

        -- RF-04 : delai depuis le dernier contact
        (days_since_last_contact >= 90) as long_delay_since_contact,

        -- RF-06 : rendez-vous manques precedents
        (missed_appointments_count >= 2) as repeated_missed_appointments,

        days_since_last_contact,
        missed_appointments_count,
        last_event_date

    from patient_metrics

),

signals as (

    select
        patient_id,
        'follow_up_risk' as signal_type,

        -- RF-07 : liste des facteurs contributifs, jamais un signal "boite noire"
        list_filter(
            [
                case when no_future_appointment
                    then 'Aucun rendez-vous futur planifie'
                end,
                case when long_delay_since_contact
                    then 'Delai de ' || days_since_last_contact || ' jours depuis le dernier contact'
                end,
                case when repeated_missed_appointments
                    then missed_appointments_count || ' rendez-vous manques precedemment'
                end
            ],
            x -> x is not null
        ) as contributing_factors,

        last_event_date,

        'open' as status,

        -- RF-08 : jamais presente comme un diagnostic, toujours soumis a revue humaine
        true as requires_human_review,

        cast(current_timestamp as timestamp) as generated_at

    from evaluated
    where no_future_appointment
      and (long_delay_since_contact or repeated_missed_appointments)

)

select * from signals