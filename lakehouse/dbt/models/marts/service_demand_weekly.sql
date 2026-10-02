-- Volume d'evenements agrege par semaine, base du Modele C
-- (prevision de la demande, module M9 du cahier des charges).

select
    date_trunc('week', event_timestamp) as week_start,
    count(*) as event_count

from {{ ref('stg_events') }}
group by 1
order by 1