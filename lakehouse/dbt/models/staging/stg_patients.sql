-- Couche Silver : donnees de reference patient (dimension), nettoyees.
-- Alimente la Healthcare Accessibility Map (module M3).

with source as (

    select * from {{ source('bronze', 'patients') }}

)

select
    patient_id,
    age,
    gender,
    home_city,
    primary_center_id,
    cast(diagnosis_date as date) as diagnosis_date,
    cancer_type

from source