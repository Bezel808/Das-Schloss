"""Community analysis on focal-publication co-links, independent of rendering."""
from collections import Counter, defaultdict
import networkx as nx


def decorate_graph(graph, works, focal, metadata=None, resolution=1.0):
    metadata = metadata or {}
    by_work = {w['id']: {a['author']['id']: {i['id'] for i in a.get('institutions', []) if i.get('id')}
                        for a in w.get('authorships', [])} for w in works}
    for edge in graph['edges']:
        evidence = {'shared': [], 'disjoint': [], 'unknown': []}
        for wid in edge['work_ids']:
            authors = by_work.get(wid, {})
            left, right = authors.get(edge['source'], set()), authors.get(edge['target'], set())
            kind = 'unknown' if not left or not right else 'shared' if left & right else 'disjoint'
            evidence[kind].append(wid)
        edge['semantics'] = {
            'kind': 'focal_coauthor' if focal in (edge['source'], edge['target']) else 'coauthors_on_focal_papers',
            'evidence_level': 'observed_coauthorship', 'directed': False,
            'institution_work_ids': evidence,
            'institution_scope': 'Contemporaneous byline institution IDs; disjoint does not establish external employment.',
            'relation_inference': None,
        }
    co = nx.Graph()
    co.add_nodes_from(n['id'] for n in graph['nodes'] if n['id'] != focal)
    for e in graph['edges']:
        if focal not in (e['source'], e['target']):
            co.add_edge(e['source'], e['target'], weight=e['weight_fractional'])
    if co.number_of_edges():
        groups = nx.community.louvain_communities(co, weight='weight', resolution=resolution, seed=42)
    else:
        groups = [{n} for n in sorted(co)]
    groups = sorted(groups, key=lambda g: (-len(g), sorted(g)))
    membership = {a: i for i, group in enumerate(groups) for a in group}
    observed = defaultdict(lambda: {'works': set(), 'topics': Counter(), 'institutions': {}, 'first': 9999, 'last': 0, 'years': set()})
    for w in works:
        for a in w.get('authorships', []):
            aid = a['author']['id']
            obs = observed[aid]
            obs['works'].add(w['id'])
            obs['years'].add(w['publication_year'])
            obs['first'] = min(obs['first'], w['publication_year'])
            obs['last'] = max(obs['last'], w['publication_year'])
            for t in w.get('topics', [])[:1]:
                obs['topics'][t['display_name']] += 1
            for i in a.get('institutions', []):
                obs['institutions'][i['id']] = i.get('display_name')
    communities = []
    for index, group in enumerate(groups):
        topics = Counter()
        for aid in group:
            topics.update(observed[aid]['topics'])
        communities.append({'id': index, 'size': len(group), 'label': topics.most_common(1)[0][0] if topics else '无主题标签'})
    for n in graph['nodes']:
        aid = n['id']
        obs = observed[aid]
        meta = metadata.get(aid, {})
        n.update(community=membership.get(aid, -1), shared_count=len(obs['works']),
                 active_years=sorted(obs['years']), first_shared_year=obs['first'] if obs['works'] else None,
                 last_shared_year=obs['last'] or None, work_ids=sorted(obs['works']),
                 institutions=obs['institutions'], cited_by_count=meta.get('cited_by_count'),
                 orcid=meta.get('orcid'), latest_institutions=meta.get('last_known_institutions', []))
    graph.update(communities=communities, algorithm='Louvain on collaborator co-links (focal node removed)',
                 seed=42, resolution=resolution,
                 modularity=nx.community.modularity(co, groups, weight='weight', resolution=resolution) if co.number_of_edges() else None)
    return graph
