"""Reproducible, bounded-network validation on independently recorded mentorship.

This is a retrospective retrieval benchmark, NOT a binary accuracy estimate or
population validation. AFT's original identity linking partly used mentorship;
this dependence and the restricted candidate universe are reported explicitly.
Only publication identifiers and years enter TPFG. No degree dates enter features.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import getpass
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

import httpx
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scholartrace.inference import author_profile
from scholartrace.tpfg import rank, VERSION

ROOT = PROJECT / 'data/research/aft'


def repair_ids():
    """Archive the official legacy merge ledger and resolve relevant ID chains."""
    ns = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}
    response = httpx.get('https://openalex.s3.amazonaws.com/',
                         params={'list-type': '2', 'prefix': 'legacy-data/merged_ids/works/',
                                 'max-keys': 1000}, timeout=60)
    response.raise_for_status()
    listing = ET.fromstring(response.content)
    if listing.find('s:IsTruncated', ns).text != 'false':
        raise ValueError('Merge listing requires pagination; refusing an incomplete ledger')
    files = [{'key': e.find('s:Key', ns).text, 'bytes': int(e.find('s:Size', ns).text)}
             for e in listing.findall('s:Contents', ns)]
    (ROOT / 'merge-manifest.json').write_text(json.dumps(files, indent=2))
    folder = ROOT / 'merges'; folder.mkdir(exist_ok=True)
    def download(item):
        path = folder / Path(item['key']).name
        if path.exists() and path.stat().st_size == item['bytes']:
            return
        with httpx.stream('GET', 'https://openalex.s3.amazonaws.com/' + item['key'], timeout=120) as r:
            r.raise_for_status()
            with path.with_suffix('.part').open('wb') as f:
                for chunk in r.iter_bytes(): f.write(chunk)
        if path.with_suffix('.part').stat().st_size != item['bytes']:
            raise ValueError('Merge ledger download is truncated')
        path.with_suffix('.part').replace(path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download, files))
    cohort = json.loads((ROOT / 'cohort.json').read_text())
    needed = {w for pubs in cohort['publications'].values() for w in pubs}
    mapping = {}; frontier = needed
    # Multiple passes retain only relevant chains instead of a huge global map.
    while frontier:
        found = {}
        for item in files:
            with gzip.open(folder / Path(item['key']).name, 'rt') as f:
                for row in csv.DictReader(f):
                    old = row['id'].split('/W')[-1].removeprefix('W')
                    if old in frontier:
                        found[old] = row['merge_into_id'].split('/W')[-1].removeprefix('W')
        mapping.update(found)
        frontier = set(found.values()) - needed - mapping.keys()
        needed.update(frontier)
    aliases = {}
    for old in mapping:
        new = old; seen = set()
        while new in mapping:
            if new in seen: raise ValueError('Cyclic merge ledger')
            seen.add(new); new = mapping[new]
        aliases[old] = new
    (ROOT / 'aliases.json').write_text(json.dumps(aliases, sort_keys=True, indent=2))
    print('resolved aliases', len(aliases), flush=True)


def order(value):
    return hashlib.sha256(('das-schloss-aft-v1:' + value).encode()).hexdigest()


def records(filename):
    with gzip.open(ROOT / filename, 'rt') as source:
        yield from csv.DictReader(source)


def prepare(labs):
    researchers = {r['PID']: r for r in records('researcher.csv.gz') if r['MAGAuthorID']}
    by_mentor = defaultdict(set); all_labels = defaultdict(set)
    for r in records('mentorship.csv.gz'):
        student, mentor = r['MenteeID'], r['MentorID']
        if student not in researchers or mentor not in researchers or student == mentor:
            continue
        # Report the raw category instead of asserting a degree based on its code.
        if r['MentorshipType'] != '1':
            continue
        all_labels[student].add(mentor)
        if r['StopYear'].isdigit() and 1995 <= int(r['StopYear']) <= 2015:
            by_mentor[mentor].add(student)
    mentors = sorted((p for p, kids in by_mentor.items() if len(kids) >= 3), key=order)[:labs]
    targets = sorted({kid for p in mentors for kid in sorted(by_mentor[p], key=order)[:3]}, key=order)
    # Candidate selection uses publication overlap, never the gold mentor ID.
    # Match the application's bounded expansion (12 strongest collaborators).
    target_set = set(targets)
    paper_targets = defaultdict(set)
    for row in records('authorship.csv.gz'):
        if row['PID'] in target_set:
            paper_targets[row['MAGPaperID']].add(row['PID'])
    print('target papers', len(paper_targets), flush=True)
    overlaps = defaultdict(Counter)
    for row in records('authorship.csv.gz'):
        other = row['PID']
        if other not in researchers:
            continue
        for target in paper_targets.get(row['MAGPaperID'], ()):
            if other != target:
                overlaps[target][other] += 1
    candidates = {p: [a for a, _ in sorted(overlaps[p].items(), key=lambda x: (-x[1], x[0]))[:12]] for p in targets}
    people = target_set | {a for aa in candidates.values() for a in aa}
    print('expanded people', len(people), flush=True)
    mag_counts = Counter(researchers[p]['MAGAuthorID'] for p in people)
    duplicates = {p for p in people if mag_counts[researchers[p]['MAGAuthorID']] > 1}
    people -= duplicates
    publications = defaultdict(set)
    for row in records('authorship.csv.gz'):
        if row['PID'] in people:
            publications[row['PID']].add(row['MAGPaperID'])
    data = {'version': 2, 'seed': 'das-schloss-aft-v1', 'labs_requested': labs,
            'targets': [p for p in targets if p in people],
            'labels': {p: sorted(all_labels[p]) for p in targets if p in people},
            'candidate_ids': candidates,
            'candidate_sampling': 'top 12 AFT-indexed coauthors by shared papers; gold labels never inserted',
            'lab_groups': {p: sorted(by_mentor[p] & set(targets)) for p in mentors},
            'duplicate_identity_exclusions': sorted(duplicates),
            'names': {p: ' '.join(researchers[p][k] for k in ['FirstName', 'MiddleName', 'LastName']).strip() for p in people},
            'publications': {p: sorted(publications[p], key=int) for p in sorted(people)},
            'source': 'https://doi.org/10.5281/zenodo.4917086', 'license': 'CC BY 4.0',
            'raw_mentorship_category': '1', 'feature_cutoff': 2020}
    (ROOT / 'cohort.json').write_text(json.dumps(data, indent=2))
    print(json.dumps({'people': len(people), 'targets': len(data['targets']),
                      'unique_papers': len(set().union(*publications.values()))}), flush=True)


def fetch_years():
    cohort = json.loads((ROOT / 'cohort.json').read_text())
    papers = sorted({p for pubs in cohort['publications'].values() for p in pubs}, key=int)
    aliases_path = ROOT / 'aliases.json'
    if aliases_path.exists():
        papers = sorted(set(papers) | set(json.loads(aliases_path.read_text()).values()), key=int)
    cache = ROOT / 'years'; cache.mkdir(exist_ok=True)
    completed = set()
    for path in cache.glob('*.json'):
        completed.update(json.loads(path.read_text())['requested'])
    missing = [p for p in papers if p not in completed]
    batches = [missing[i:i + 100] for i in range(0, len(missing), 100)]
    key = getpass.getpass('OpenAlex key (memory only): ')
    headers = {'Authorization': 'Bearer ' + key} if key else {}
    def fetch(batch):
        identity = hashlib.sha256('|'.join(batch).encode()).hexdigest()
        dest = cache / (identity + '.json')
        if dest.exists():
            return
        for attempt in range(4):
            try:
                response = httpx.get('https://api.openalex.org/works', headers=headers,
                                     params={'filter': 'openalex_id:' + '|'.join('W' + p for p in batch),
                                             'per_page': 100, 'select': 'id,publication_year'}, timeout=60)
                if response.status_code in (401, 403):
                    raise RuntimeError('OpenAlex authentication failed')
                if response.status_code == 429 or response.status_code >= 500:
                    time.sleep(2 ** attempt); continue
                response.raise_for_status()
                payload = {'requested': batch, 'results': response.json()['results'],
                           'retrieved_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
                dest.with_suffix('.tmp').write_text(json.dumps(payload))
                dest.with_suffix('.tmp').replace(dest)
                return
            except httpx.HTTPError:
                if attempt == 3:
                    raise RuntimeError('OpenAlex request failed; completed batches are cached') from None
                time.sleep(2 ** attempt)
        raise RuntimeError('OpenAlex rate limit; completed batches are cached')
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, _ in enumerate(pool.map(fetch, batches), 1):
            if i % 20 == 0 or i == len(batches):
                print('year batches', i, '/', len(batches), flush=True)


def evaluate():
    cohort = json.loads((ROOT / 'cohort.json').read_text())
    years = {}; requested = set()
    for path in sorted((ROOT / 'years').glob('*.json')):
        cache = json.loads(path.read_text()); requested.update(cache['requested'])
        for w in cache['results']:
            if isinstance(w.get('publication_year'), int):
                years[w['id'].split('/W')[-1]] = w['publication_year']
    original_pubs = cohort['publications']
    needed = {w for ids in original_pubs.values() for w in ids}
    if needed - requested:
        raise ValueError('Metadata fetching is incomplete; finish fetch-years first')
    aliases_path = ROOT / 'aliases.json'
    legacy_aliases = json.loads(aliases_path.read_text()) if aliases_path.exists() else {}
    # A legacy ledger is not current truth: IDs can be restored. A current exact
    # API result takes precedence over old merges. Only dated survivors repair gaps.
    aliases = {old: new for old, new in legacy_aliases.items() if old not in years and new in years}
    # Canonicalize and deduplicate before constructing either histories or edges.
    pubs = {p: sorted({aliases.get(w, w) for w in ids}) for p, ids in original_pubs.items()}
    coverage = {p: sum(w in years for w in ids) / len(ids) if ids else 0 for p, ids in pubs.items()}
    retained = {p for p in pubs if coverage[p] >= .95}
    authors = defaultdict(list)
    for p in retained:
        for w in pubs[p]:
            if w in years and years[w] <= cohort['feature_cutoff']:
                authors[w].append(p)
    works = {w: {'id': 'https://openalex.org/W' + w, 'publication_year': years[w],
                 'authorships': [{'author': {'id': p}} for p in sorted(people)]}
             for w, people in authors.items()}
    profiles = {p: profile for p in sorted(retained)
                if (profile := author_profile(p, [works[w] for w in pubs[p] if w in works]))}
    evidence, model = rank(profiles, seconds=180, candidate_ids=cohort['candidate_ids'])
    if model['status'] != 'optimal':
        raise ValueError('Solver has not certified the evaluation; no final metrics written')
    rows = []
    for student in cohort['targets']:
        gold = set(cohort['labels'][student])
        candidates = [(a, e) for (a, s), e in evidence.items() if s == student and e['eligible']
                      and a in cohort['candidate_ids'][student]]
        local = sorted(candidates, key=lambda item: (-item[1]['local_potential'], item[0]))
        tpfg = sorted(candidates, key=lambda item: (-item[1]['ranking_score'], item[0]))
        frequency = sorted(candidates, key=lambda item: (-item[1]['annual_evidence'][-1]['joint_papers'], item[0]))
        row = {'student': student, 'gold': sorted(gold), 'feature_coverage': coverage.get(student, 0),
               'n_candidates': len(candidates), 'gold_in_candidates': bool(gold & {a for a, _ in candidates}),
               'predicted_primary': next((a for a, e in candidates if e['map_selected']), None)}
        for name, ranking in [('tpfg', tpfg), ('independent_local', local), ('most_coauthored', frequency)]:
            positions = [i + 1 for i, (a, _) in enumerate(ranking) if a in gold]
            row[name + '_rank'] = min(positions) if positions else None
        rows.append(row)
    # Fixed denominator includes missing candidate mentors; conditional metrics
    # are reported separately so retrieval failures cannot disappear silently.
    def metrics(subset):
        result = {'n': len(subset)}
        for name in ['tpfg', 'independent_local', 'most_coauthored']:
            ranks = [r[name + '_rank'] for r in subset]
            result[name] = {'recall_at_1': sum(x == 1 for x in ranks) / max(1, len(ranks)),
                            'recall_at_2': sum(x is not None and x <= 2 for x in ranks) / max(1, len(ranks)),
                            'mrr': sum(1 / x if x else 0 for x in ranks) / max(1, len(ranks))}
        return result
    challenging = [r for r in rows if r['gold_in_candidates'] and r['n_candidates'] >= 3]
    # Cluster resampling at the sampled mentor-group level, not individual dyads.
    # A repeated student is counted once per sampled group occurrence.
    row_by_person = {r['student']: r for r in rows}
    groups = [[row_by_person[p] for p in members if p in row_by_person]
              for members in cohort['lab_groups'].values()]
    groups = [g for g in groups if g]
    rng = np.random.default_rng(42)
    deltas = []
    for _ in range(2000):
        sample = [r for k in rng.integers(0, len(groups), len(groups)) for r in groups[k]]
        deltas.append(np.mean([int(r['tpfg_rank'] == 1) - int(r['most_coauthored_rank'] == 1) for r in sample]))
    report = {'model_version': VERSION, 'model': model, 'cohort_sha256': hashlib.sha256((ROOT / 'cohort.json').read_bytes()).hexdigest(),
              'metadata_sha256': hashlib.sha256(json.dumps(years,sort_keys=True).encode()).hexdigest(),
              'aliases_sha256': hashlib.sha256(json.dumps(aliases,sort_keys=True).encode()).hexdigest(),
              'source': cohort['source'], 'feature_cutoff': cohort['feature_cutoff'],
              'candidate_sampling': cohort['candidate_sampling'],
              'counts': {'profiles_retained': len(profiles), 'profiles_rejected_for_metadata_coverage': len(pubs) - len(profiles),
                         'requested_papers': len(needed), 'dated_papers': len(needed & years.keys()),
                         'resolved_legacy_aliases': len(needed & aliases.keys()),
                         'papers_with_year_after_alias_repair': sum(aliases.get(w,w) in years for w in needed),
                         'canonical_unique_papers': len({w for ids in pubs.values() for w in ids}),
                         'known_mentors_in_candidates': sum(r['gold_in_candidates'] for r in rows)},
              'all_targets': metrics(rows), 'at_least_three_candidates_with_known_mentor': metrics(challenging),
              'tpfg_minus_frequency_recall_at_1_cluster_bootstrap_95': np.quantile(deltas, [.025, .975]).tolist(),
              'limitations': ['Restricted AFT researcher cohort, not a complete global collaborator candidate universe.',
                             'AFT-to-MAG identity matching partly used mentor coauthorship; validation is not fully independent of identity resolution.',
                             'Missing mentorship labels are not negative labels; metrics evaluate retrieval of recorded mentors only.',
                             'Year metadata reconstructed from current OpenAlex; source publication lists are from the AFT-MAG snapshot.',
                             'Official legacy merge ledger ends in 2025; later merges or deletions may still leave missing metadata.',
                             'No extrapolation of bioscience-dominated results to computer science or degree identification.'],
              'rows': rows}
    dest = PROJECT / 'research/aft-validation.json'
    dest.write_text(json.dumps(report, indent=2) + '\n')
    # Ship the exact measured results alongside the runtime, without personal rows.
    summary = {k: v for k, v in report.items() if k not in {'rows', 'model'}}
    summary['status'] = 'insufficient_evidence_for_reliable_identification'
    summary['message'] = '真实数据验收未支持可靠师生识别；以下为待核实候选，不能作为学位、任职或晋升的事实依据。'
    summary['comparison'] = '未证明优于合作次数基线' if np.quantile(deltas, .025) <= 0 else '该受限队列上优于合作次数基线；仍不等于总体可靠性'
    packaged = PROJECT / 'scholartrace/validation'
    packaged.mkdir(exist_ok=True)
    (packaged / (VERSION + '.json')).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['counts', 'all_targets', 'at_least_three_candidates_with_known_mentor']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'fetch-years', 'repair-ids', 'evaluate'])
    parser.add_argument('--labs', type=int, default=40)
    args = parser.parse_args()
    if args.stage == 'prepare': prepare(args.labs)
    elif args.stage == 'fetch-years': fetch_years()
    elif args.stage == 'repair-ids': repair_ids()
    else: evaluate()
