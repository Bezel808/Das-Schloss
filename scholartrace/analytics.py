"""Publication-time panels on an explicit, observed corpus (never global careers)."""
from collections import Counter, defaultdict
from itertools import combinations
import hashlib
import json
import math

import networkx as nx
import numpy as np

VERSION = 'observed-panel-2'


def clean_works(works):
    result = {}; seen_doi = set(); excluded = Counter()
    # Prefer the earliest observed year when duplicate records share a DOI.
    # Extending end into the future must not erase a historical publication.
    for w in sorted(works, key=lambda x: (x.get('publication_year') if isinstance(x.get('publication_year'),int) else 10000,
                                        str(x.get('id', '')))):
        wid = w.get('id'); year = w.get('publication_year')
        aa = w.get('authorships', [])
        ids = [a.get('author', {}).get('id') for a in aa]
        doi = (w.get('doi') or '').lower().removeprefix('https://doi.org/')
        reason = ('missing_id' if not wid else
                  'duplicate' if wid in result or doi and doi in seen_doi else
                  'invalid_year' if not isinstance(year, int) or isinstance(year, bool) or not 1000 <= year <= 9999 else
                  'incomplete_authorships' if not ids or None in ids or len(ids) != len(set(ids)) or w.get('authors_count', len(ids)) > len(ids) else
                  'retracted_or_paratext' if w.get('is_retracted') or w.get('is_paratext') else None)
        if reason:
            excluded[reason] += 1; continue
        result[wid] = w
        if doi: seen_doi.add(doi)
    return list(result.values()), dict(excluded)


def authors(w):
    return [a['author']['id'] for a in w['authorships']]


def projection(works, start, end, max_team=200):
    graph = nx.Graph(); excluded = 0
    for w in works:
        if not start <= w['publication_year'] <= end: continue
        aa = authors(w)
        if len(aa) > max_team:
            excluded += 1; continue
        graph.add_nodes_from(aa)
        for a, b in combinations(sorted(aa), 2):
            previous = graph.get_edge_data(a, b, {})
            graph.add_edge(a, b, weight=previous.get('weight', 0) + 1 / (len(aa) - 1),
                           count=previous.get('count', 0) + 1)
    return graph, excluded


def role_metrics(graph, focal, resolution=1.):
    """Weighted within-community z and participation; unweighted k-core/clustering."""
    base = {'nodes': len(graph), 'edges': graph.number_of_edges()}
    if focal not in graph:
        return dict(base, observed=False, degree=None, strength=None, within_module_z=None,
                    participation=None, constraint=None, effective_size=None, core=None,
                    pagerank=None, clustering=None, community_size=None)
    groups = (nx.community.louvain_communities(graph, weight='weight', seed=42, resolution=resolution)
              if graph.number_of_edges() else [{a} for a in sorted(graph)])
    membership = {a: i for i, group in enumerate(groups) for a in group}
    own_group = groups[membership[focal]]
    within = {a: sum(d['weight'] for b, d in graph[a].items() if b in own_group) for a in own_group}
    sigma = float(np.std(list(within.values())))
    strength_by_group = defaultdict(float)
    for other, data in graph[focal].items(): strength_by_group[membership[other]] += data['weight']
    strength = sum(strength_by_group.values())
    degree = graph.degree(focal)
    constraint, effective = brokerage(graph, focal)
    return dict(base, observed=True, degree=degree, strength=strength,
                within_module_z=(within[focal] - float(np.mean(list(within.values())))) / sigma if sigma > 1e-12 else None,
                participation=1 - sum((v / strength)**2 for v in strength_by_group.values()) if strength else None,
                constraint=float(constraint) if constraint is not None and math.isfinite(constraint) else None,
                effective_size=float(effective) if effective is not None and math.isfinite(effective) else None,
                core=nx.core_number(graph)[focal], pagerank=nx.pagerank(graph, weight='weight', tol=1e-10, max_iter=500)[focal],
                clustering=nx.clustering(graph, focal), community_size=len(own_group))


def brokerage(graph, focal):
    """Burt's weighted formulas on an undirected graph, without repeated row sums."""
    neighbors = set(graph[focal])
    if not neighbors: return None, None
    total = sum(d['weight'] for d in graph[focal].values())
    p = {a:d['weight']/total for a,d in graph[focal].items()}
    indirect = defaultdict(float); redundancy = defaultdict(float)
    maxima = {a:max(d['weight'] for d in graph[a].values()) for a in neighbors}
    for q in neighbors:
        q_total = sum(d['weight'] for d in graph[q].values())
        for j, d in graph[q].items():
            if j in neighbors:
                indirect[j] += p[q] * d['weight']/q_total
                redundancy[j] += p[q] * d['weight']/maxima[j]
    return sum((p[j]+indirect[j])**2 for j in neighbors), sum(1-redundancy[j] for j in neighbors)


def annual_panel(raw_works, focal, start, end, window=5, resolution=1.):
    if not 1000 <= start <= end <= 9999 or end - start > 50 or not 1 <= window <= 20:
        raise ValueError('Use at most 51 years, with a window between 1 and 20 years')
    raw_works = [w for w in raw_works if isinstance(w.get('publication_year'), int) and w['publication_year'] <= end]
    works, omitted = clean_works(raw_works)
    # Future metadata must not change the feature fingerprint or any historical row.
    works = [w for w in works if w['publication_year'] <= end]
    own = [w for w in works if focal in authors(w)]
    first = min((w['publication_year'] for w in own), default=None)
    index = {w['id']: w for w in works}
    citations = defaultdict(list)
    for w in works:
        for target in set(w.get('referenced_works', [])):
            if target in index and index[target]['publication_year'] <= w['publication_year'] and target != w['id']:
                citations[target].append(w['publication_year'])
    rows = []; previous_neighbors = None
    for year in range(start, end + 1):
        history = [w for w in own if w['publication_year'] <= year]
        current = [w for w in history if w['publication_year'] == year]
        graph, excluded = projection(works, year-window+1, year)
        metrics = role_metrics(graph, focal, resolution)
        neighbors = set(graph[focal]) if focal in graph else set()
        counts = sorted((sum(t <= year for t in citations[w['id']]) for w in history), reverse=True)
        historic_neighbors = {a for w in history if w['publication_year'] < year for a in authors(w)} - {focal}
        year_neighbors = {a for w in current for a in authors(w)} - {focal}
        rows.append(dict(year=year, graph_start=year-window+1, graph_end=year,
                         papers=len(current), fractional_papers=sum(1/len(authors(w)) for w in current),
                         cumulative_papers=len(history), observed_career_age=year-first if first is not None and first <= year else None,
                         citations_within_corpus=sum(counts), h_index_within_corpus=sum(c >= i for i, c in enumerate(counts, 1)),
                         i10_index_within_corpus=sum(c >= 10 for c in counts),
                         neighbor_retention=len(neighbors & previous_neighbors)/len(previous_neighbors) if previous_neighbors else None,
                         window_added_neighbors=len(neighbors - previous_neighbors) if previous_neighbors is not None else None,
                         first_observed_partners=len(year_neighbors - historic_neighbors),
                         graph_omitted_large_teams=excluded, **metrics))
        previous_neighbors = neighbors
    evidence = [{'id':w['id'], 'year':w['publication_year'], 'authors':authors(w),
                 'references':sorted(set(w.get('referenced_works', [])))} for w in works]
    return {'version': VERSION, 'focal': focal, 'start': start, 'end': end, 'window': window,
            'resolution': resolution, 'seed':42, 'rows':rows, 'omitted':omitted,
            'corpus_papers':len(works), 'input_sha256':hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest(),
            'scope':'union of explicitly cached author corpora; observed subgraph, not global network',
            'citation_scope':'Only dated references from citing papers in the supplied corpus; not OpenAlex or Google Scholar h-index.',
            'interpretation':'z measures within-community position; participation/constraint measure structural position, not promotion or demonstrated brokerage.',
            'community_identity':'Louvain fitted separately per historical window; community IDs are not longitudinal identities.'}
