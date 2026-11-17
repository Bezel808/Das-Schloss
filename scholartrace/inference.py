"""Temporal relationship inference and evidence-linked genealogy motifs."""
import hashlib
import json
from pathlib import Path
from itertools import combinations

import networkx as nx

FEATURES = ['age_gap', 'early_dependency', 'dependency_asymmetry', 'entry_delay',
            'role_support', 'institution_overlap', 'joint_active_years', 'joint_span', 'neighbor_jaccard']


def author_profile(aid, works):
    # A first-year cohort is retained as a whole rather than inventing ordering within a year.
    unique = {}
    for w in works:
        entries = {a.get('author', {}).get('id'): a for a in w.get('authorships', [])}
        if aid in entries and isinstance(w.get('publication_year'), int) and w['publication_year'] > 0:
            key = (w.get('doi') or w['id']).lower().removeprefix('https://doi.org/')
            unique.setdefault(key, w)
    ordered = sorted(unique.values(), key=lambda w: (w['publication_year'], w['id']))
    if not ordered:
        return None
    first = ordered[0]['publication_year']
    cutoff = min(first + 2, ordered[min(4, len(ordered)-1)]['publication_year'])
    early = [w for w in ordered if w['publication_year'] <= cutoff]
    neighbors = {a['author']['id'] for w in ordered for a in w.get('authorships', []) if a.get('author', {}).get('id')} - {aid}
    return {'id': aid, 'works': ordered, 'first': first, 'early': early, 'neighbors': neighbors}


def entry(work, aid):
    return next((a for a in work['authorships'] if a.get('author', {}).get('id') == aid), {})


def pair_features(senior, junior):
    sid, jid = senior['id'], junior['id']
    joint = [w for w in junior['works'] if entry(w, sid)]
    if not joint:
        return None
    early = [w for w in junior['early'] if entry(w, sid)]
    year = min(w['publication_year'] for w in joint)
    early_end = max(w['publication_year'] for w in junior['early'])
    senior_period = [w for w in senior['works'] if junior['first'] <= w['publication_year'] <= early_end]
    dependency = len(early)/len(junior['early'])
    reverse_dependency = sum(bool(entry(w,jid)) for w in senior_period)/max(1,len(senior_period))
    role, role_known, shared_inst, inst_known = 0, 0, 0, 0
    for w in early:
        s,j = entry(w,sid),entry(w,jid)
        if s.get('author_position') and j.get('author_position'):
            role_known += 1
            role += j.get('author_position') == 'first' and (s.get('author_position') == 'last' or s.get('is_corresponding') is True)
        si = {i['id'] for i in s.get('institutions', [])}
        ji = {i['id'] for i in j.get('institutions', [])}
        if si and ji:
            inst_known += 1
            shared_inst += bool(si & ji)
    years = sorted({w['publication_year'] for w in joint})
    union = senior['neighbors'] | junior['neighbors']
    values = [junior['first']-senior['first'], dependency, dependency-reverse_dependency,
              year-junior['first'], role/role_known if role_known else 0,
              shared_inst/inst_known if inst_known else 0, len(years), years[-1]-years[0]+1,
              len(senior['neighbors'] & junior['neighbors'])/max(1,len(union))]
    return {'source':sid, 'target':jid, 'features':dict(zip(FEATURES,values)), 'work_ids':[w['id'] for w in joint],
            'early_work_ids':[w['id'] for w in early], 'early_total':len(junior['early']),
            'period':[years[0],years[-1]], 'missing':(['role_information'] if not role_known else [])+(['institution_information'] if not inst_known else [])}


def infer(corpora, names=None, cutoff=None):
    names=names or {}
    if cutoff is not None:
        if not isinstance(cutoff, int) or not 1000 <= cutoff <= 9999:
            raise ValueError('Invalid analysis cutoff')
        corpora = {a: [w for w in works if isinstance(w.get('publication_year'), int)
                      and w['publication_year'] <= cutoff] for a, works in corpora.items()}
    profiles={a:p for a,works in corpora.items() if (p:=author_profile(a,works))}
    pairs=[]
    for a,b in combinations(sorted(profiles),2):
        pa,pb=profiles[a],profiles[b]
        if pa['first']==pb['first']:
            continue
        senior,junior=sorted([pa,pb],key=lambda p:p['first'])
        item=pair_features(senior,junior)
        if item:pairs.append(item)
    from .tpfg import rank
    ranked, model = rank(profiles)
    validation_path = Path(__file__).parent / 'validation' / (model['version'] + '.json')
    model['validation'] = json.loads(validation_path.read_text()) if validation_path.exists() else {
        'status': 'not_evaluated', 'message': '此版本尚无真实数据验收结果。'}
    # No identity labels or derived genealogy from a model that failed real-data
    # validation. Preserve its numeric audit evidence, not a second decision path.
    model['relation_labels_enabled'] = model['validation'].get('status') == 'validated_for_identification'
    model['n_dyads'] = len(pairs)
    dag=nx.DiGraph();dag.add_nodes_from(profiles)
    for p in pairs:
        p['source_name']=names.get(p['source'],p['source']);p['target_name']=names.get(p['target'],p['target'])
        evidence = ranked.get((p['source'], p['target']), {})
        p['temporal_model'] = evidence
        p['ranking_score'] = evidence.get('ranking_score')
        p['supervised'] = None
        p['prediction'] = ('possible_advisor' if model['relation_labels_enabled'] and evidence.get('map_selected') and
                           evidence.get('ranking_score', 0) > evidence.get('null_score', 1)
                           else 'unresolved')
        p['provenance']='prediction';p['calibrated_probability']=None
        if p['prediction']=='possible_advisor':
            dag.add_edge(p['source'],p['target'],support=p['ranking_score'])
    # Display the jointly consistent MAP forest. Alternative advisor rankings remain in the export.
    motifs=[]
    for mentor in sorted(dag):
        students=sorted(dag.successors(mentor))
        for a,b in combinations(students,2):
            joint=[w for w in profiles[a]['works'] if entry(w,b)]
            years={w['publication_year'] for w in joint}
            persistent=len(joint)>=4 and len(years)>=3 and max(years)-min(years)>=4
            motifs.append({'type':'possible_academic_siblings', 'nodes':[mentor,a,b], 'names':[names.get(n,n) for n in [mentor,a,b]],
                           'long_term_collaboration':persistent, 'work_ids':[w['id'] for w in joint],
                           'support_lower_edge_score':min(dag[mentor][a]['support'],dag[mentor][b]['support']), 'probability':None})
        for child in students:
            for grandchild in sorted(dag.successors(child)):
                first=next(p for p in pairs if p['source']==mentor and p['target']==child)['period'][0]
                second=next(p for p in pairs if p['source']==child and p['target']==grandchild)['period'][0]
                if second<first:continue
                motifs.append({'type':'possible_two_generation_chain','nodes':[mentor,child,grandchild],
                               'names':[names.get(n,n) for n in [mentor,child,grandchild]],'probability':None})
    return {'schema_version':2, 'model':model, 'cutoff':cutoff,
            'coverage':{'complete_author_corpora':len(profiles)},
            'relationships':sorted(pairs,key=lambda p:-(p.get('ranking_score') or 0)), 'motifs':motifs,
            'capabilities': {'degree_prediction': False, 'career_transition_prediction': False},
            'input_sha256':hashlib.sha256(json.dumps(corpora,sort_keys=True).encode()).hexdigest(),
            'graph_constraints':'TPFG primary-advisor MAP forest, strict career order and non-overlapping training constraints; alternatives are rankings, not simultaneous co-supervisors.'}
