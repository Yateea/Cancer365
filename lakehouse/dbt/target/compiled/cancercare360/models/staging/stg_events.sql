-- Couche Silver : evenements nettoyes, types, avec les champs imbriques
-- (metadata) extraits en colonnes plates pour faciliter l'analyse.

with source as (

    select * from 's3://cancercare-lakehouse/bronze/events/*.parquet'

),

renamed as (

    select
        event_id,
        patient_id,
        event_type,
        cast(event_timestamp as timestamp) as event_timestamp,
        service,
        status,
        source_system,
        metadata.center_id as center_id,
        metadata.center_name as center_name

    from source

)

select * from renamed