"""Publication-time events, distinct from retrieval or inferred supervision time."""
from datetime import date


def publication_time(work):
    year = work['publication_year']
    raw = work.get('publication_date')
    parsed = None
    if isinstance(raw, str):
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            pass
    # A supplied date may be normalized by the source; do not claim day-level accuracy.
    consistent = parsed is not None and parsed.year == year
    return {'year': year, 'date': parsed.isoformat() if consistent else None,
            'source_date': raw, 'precision': 'source_day_unverified' if consistent else 'year',
            'date_year_conflict': bool(parsed and parsed.year != year),
            'interval_start': parsed.isoformat() if consistent else f'{year:04d}-01-01',
            'interval_end': parsed.isoformat() if consistent else f'{year:04d}-12-31',
            'time_basis': 'publication', 'source': 'input_publication_metadata'}


def summarize_events(events):
    buckets = {}
    for e in events:
        row = buckets.setdefault(e['year'], {'year': e['year'], 'weight_raw': 0,
                                             'weight_fractional': 0.0, 'work_ids': []})
        row['weight_raw'] += 1
        row['weight_fractional'] += e['weight_fractional']
        row['work_ids'].append(e['work_id'])
    years = sorted(buckets)
    return {'first_observed_year': years[0] if years else None,
            'last_observed_year': years[-1] if years else None,
            'active_years': years, 'yearly_weights': [buckets[y] for y in years],
            'continuity_assumed': False}
