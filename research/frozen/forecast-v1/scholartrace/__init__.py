"""Evidence-linked personal publication histories."""
from collections import defaultdict
from itertools import combinations
from .temporal import publication_time, summarize_events


def analyze(focal, works):
    """Project only focal-authored works; never infer employment or mentorship."""
    years, edges, nodes, seen = {}, {}, {focal: focal}, set()
    excluded = defaultdict(int)
    for work in works:
        wid = work.get('id')
        if not wid:
            raise ValueError('Every work must have an id')
        if wid in seen:
            continue
        seen.add(wid)
        authorships = work.get('authorships', [])
        if work.get('authors_count', len(authorships)) > len(authorships):
            raise ValueError('Incomplete authorships for ' + wid + '; fetch the individual work first')
        authors = {a['author']['id']: a for a in authorships if a.get('author', {}).get('id')}
        if len(authors) != len(authorships):
            raise ValueError('Missing or duplicate author identities for ' + wid)
        if focal not in authors:
            excluded['not_focal'] += 1
            continue
        year = work.get('publication_year')
        if not isinstance(year, int) or isinstance(year, bool):
            raise ValueError('Missing or invalid publication year for ' + wid)
        event_time = publication_time(work)
        row = years.setdefault(year, {'year': year, 'works': [], 'roles': {}, 'institutions': {}, 'topics': {}})
        target = authors[focal]
        row['works'].append({'id': wid, 'title': work.get('title'), 'doi': work.get('doi'),
                             'abstract_available': bool(work.get('abstract_inverted_index')), 'publication_time': event_time})
        roles = [target.get('author_position', 'unknown')]
        if target.get('is_corresponding') is True:
            roles.append('corresponding')
        for role in roles:
            row['roles'].setdefault(role, []).append(wid)
        for institution in target.get('institutions', []):
            key = institution['id']
            item = row['institutions'].setdefault(key, {'name': institution.get('display_name'), 'work_ids': []})
            if wid not in item['work_ids']:
                item['work_ids'].append(wid)
        for topic in work.get('topics', []):
            item = row['topics'].setdefault(topic['id'], {'name': topic.get('display_name'), 'work_ids': []})
            if wid not in item['work_ids']:
                item['work_ids'].append(wid)
        for aid, entry in authors.items():
            nodes[aid] = entry['author'].get('display_name') or aid
        for left, right in combinations(sorted(authors), 2):
            edge = edges.setdefault((left, right), {'source': left, 'target': right, 'weight_raw': 0,
                                                   'weight_fractional': 0.0, 'work_ids': [], 'events': []})
            edge['weight_raw'] += 1
            edge['weight_fractional'] += 1 / (len(authors) - 1)
            edge['work_ids'].append(wid)
            edge['events'].append(dict(event_time, work_id=wid, weight_fractional=1 / (len(authors)-1)))
    for edge in edges.values():
        edge['events'].sort(key=lambda e: (e['year'], e['date'] or '', e['work_id']))
        edge.update(summarize_events(edge['events']))
    timeline = [years[y] for y in sorted(years)]
    for row in timeline:
        row['work_count'] = len(row['works'])
        row['abstract_available_rate'] = sum(w['abstract_available'] for w in row['works']) / row['work_count']
    return {'schema_version': 2, 'focal_author_id': focal, 'timeline': timeline,
            'graph': {'temporal_schema_version': 1, 'time_basis': 'publication', 'scope': 'coauthorship projection of focal-authored works only',
                      'nodes': [{'id': k, 'name': v} for k, v in sorted(nodes.items())],
                      'edges': [edges[k] for k in sorted(edges)]},
            'excluded': dict(excluded),
            'interpretation': ['Institutions are publication affiliations, not employment records.',
                               'Author positions do not establish mentorship or seniority.',
                               'Topics are source labels, not extracted research objects.',
                               'Collaborator edges omit papers without the focal author.']}
