"""Auditable count/size comparisons; independently implemented published formulas.

These are observed-corpus rankings, not reproductions of CSRankings/AllRankings:
no faculty roster, curated conference eligibility or OSR venue tiers are inferred.
"""
from collections import Counter, defaultdict
import math

import numpy as np
from scipy.optimize import brentq
from scipy.special import softmax

from .analytics import clean_works

VERSION = 'observed-rankings-2'


def size_adjusted(counts, sizes):
    """Poisson working-score / quasi-likelihood fit for fractional output and positive exposure."""
    c = np.asarray(counts, dtype=float); a = np.asarray(sizes, dtype=float)
    if len(a) != len(c) or np.any(a <= 0) or np.any(c < 0) or not np.isfinite(a).all() or not np.isfinite(c).all():
        raise ValueError('Counts must be nonnegative and sizes finite and positive')
    if not len(a) or c.sum() <= 0:
        return {'status':'no_output', 'beta':None, 'expected': [0.] * len(a)}
    x = np.log(a); target = float(c @ x / c.sum())
    if float(np.ptp(x)) < 1e-12:
        return {'status':'equal_sizes_beta_unidentified', 'beta':None, 'expected': [float(c.sum()/len(a))] * len(a)}
    def equation(beta): return float(softmax(beta*x) @ x - target)
    bound = 1.
    while equation(-bound) * equation(bound) >= 0 and bound < 1024: bound *= 2
    if equation(-bound) * equation(bound) >= 0:
        return {'status':'no_finite_mle', 'beta':None, 'expected':None}
    beta = float(brentq(equation, -bound, bound, xtol=1e-12))
    return {'status':'fitted', 'beta':beta, 'expected': (c.sum()*softmax(beta*x)).tolist()}


def compare_rankings(raw_works, start, end, selected_fields=None, selected_sources=None):
    if not 1000 <= start <= end <= 9999: raise ValueError('Invalid year range')
    works, omitted = clean_works([w for w in raw_works if isinstance(w.get('publication_year'),int) and start <= w['publication_year'] <= end])
    fields = {}; source_options = {}; names = {}; person_papers = defaultdict(list)
    for w in works:
        topic = w.get('primary_topic') or next(iter(w.get('topics', [])), {})
        field = topic.get('field') or {'id':'unknown','display_name':'领域缺失'}
        fields[field['id']] = field.get('display_name',field['id'])
        w = dict(w, _field=field['id'])
        source = (w.get('primary_location') or {}).get('source') or {}
        w['_source'] = source.get('id', 'unknown')
        source_options[w['_source']] = source.get('display_name', '来源缺失')
        for entry in w['authorships']:
            institutions = {i['id']:i.get('display_name',i['id']) for i in entry.get('institutions', []) if i.get('id')}
            names.update(institutions)
            # A partially populated ORCID must not split one source author ID
            # into two people. Identity reconciliation is a separate operation.
            person = entry['author']['id']
            if institutions: person_papers[person,w['publication_year']].append((w,institutions))
    selected_fields = set(fields) if selected_fields is None else set(selected_fields)
    if not selected_fields <= fields.keys(): raise ValueError('Unknown selected field')
    if selected_sources is not None and not set(selected_sources) <= source_options.keys(): raise ValueError('Unknown selected venue')
    count = defaultdict(float); size = defaultdict(float); area_count = defaultdict(lambda:defaultdict(float))
    full = defaultdict(set); evidence = defaultdict(dict)
    # Each person-year is shared across all their papers with known affiliation;
    # venue filters restrict output but not the exposure denominator.
    for (_, year), pp in person_papers.items():
        for w, institutions in pp:
            if w['_field'] not in selected_fields: continue
            for inst in institutions:
                size[inst] += 1/len(pp)/len(institutions)/(end-start+1)
                if selected_sources is not None and w['_source'] not in selected_sources: continue
                credit = 1/len(w['authorships'])/len(institutions)
                count[inst] += credit; area_count[inst][w['_field']] += credit
                full[inst].add(w['id']); evidence[inst][w['id']] = evidence[inst].get(w['id'],0.) + credit
    ids = sorted(size)
    fit = size_adjusted([count[i] for i in ids],[size[i] for i in ids])
    rows = []
    for j, inst in enumerate(ids):
        expected = fit['expected'][j] if fit['expected'] is not None else None
        rows.append({'id':inst,'name':names[inst], 'full_papers':len(full[inst]), 'fractional_papers':count[inst],
                     'annual_author_equivalents':size[inst], 'per_author':count[inst]/size[inst],
                     'area_geometric_mean': math.exp(sum(math.log1p(area_count[inst][f]) for f in selected_fields)/len(selected_fields)) if selected_fields else None,
                     'expected':expected,'excess':count[inst]-expected if expected is not None else None,
                     'field_counts':dict(area_count[inst]), 'work_credit':evidence[inst]})
    for key in ['full_papers','fractional_papers','per_author','area_geometric_mean','excess']:
        frequencies = Counter(r[key] for r in rows if r[key] is not None)
        ranks = {}; offset = 1
        for score in sorted(frequencies, reverse=True):
            ranks[score] = offset; offset += frequencies[score]
        for row in rows:
            row[key+'_rank'] = ranks.get(row[key])
    return {'version':VERSION, 'start':start,'end':end,'rows':sorted(rows,key=lambda r:-(r['excess'] or 0)),
            'fit':fit,'fields':fields,'sources':source_options,'selected_fields':sorted(selected_fields),
            'selected_sources':selected_sources, 'corpus_papers':len(works), 'omitted':omitted,
            'allocated_paper_credit':sum(count.values()),
            'scope':'Observed cached corpus only; not a university-wide or global ranking.',
            'field_policy':'Primary OpenAlex field, not reference-derived topic shares.',
            'identity_policy':'Stable source author ID; partial byline ORCID values do not change person identity.',
            'venue_policy':'User-selected source IDs, no assumed CSRankings eligibility or OSR tier.',
            'references':['https://csrankings.org/faq.html','https://ar.clarelab.moe/en/about/']}
