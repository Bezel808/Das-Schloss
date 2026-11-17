"""Evidence-linked group-entry cohorts; no inferred student or supervisor labels.

Team assembly reference: Guimera et al., Science 2005, 10.1126/science.1106340.
The operational thresholds below are declared choices, not learned identities.
"""
from collections import Counter, defaultdict
from itertools import combinations
import hashlib
import json
import networkx as nx
from .analytics import clean_works

VERSION='group-cohorts-2'


def people(work):
    return {a['author']['id']:a for a in work.get('authorships',[]) if a.get('author',{}).get('id')}


def institution_ids(entry):
    return {i['id'] for i in entry.get('institutions',[]) if i.get('id')}


def ratio(n,d):
    return n/d if d else None


def portrait(corpora, focal, coverage, names=None, start=2016, end=2025,
             scope='shared_institution', window=5, early_years=3, prior_papers=5,
             early_papers=5, followup=2, incumbent_papers=2, max_team=50):
    if not 1000<=start<=end<=9999 or end-start>30:
        raise ValueError('请选择最多31年的范围')
    if scope not in {'shared_institution','all_collaborators'}:
        raise ValueError('未知合作圈口径')
    if not (1<=window<=10 and 1<=early_years<=5 and 0<=prior_papers<=20 and
            1<=early_papers<=20 and 1<=followup<=5 and 1<=incumbent_papers<=10 and 2<=max_team<=200):
        raise ValueError('观察参数超出范围')
    if not coverage.get(focal,{}).get('complete'):
        raise ValueError('请先完成目标学者的论文采集')
    names=dict(names or {})
    raw=[w for aid in sorted(corpora) for w in corpora[aid]
         if isinstance(w.get('publication_year'),int) and w['publication_year']<=end]
    works,excluded=clean_works(raw)
    by_id={w['id']:w for w in raw if w.get('id')};by_author=defaultdict(list)
    by_id.update({w['id']:w for w in works})
    for w in works:
        for aid,a in people(w).items():
            by_author[aid].append(w)
            names.setdefault(aid,a.get('author',{}).get('display_name') or aid.rsplit('/',1)[-1])
    for aa in by_author.values():aa.sort(key=lambda w:(w['publication_year'],w['id']))
    own=by_author[focal];qualifying=defaultdict(list);boundary=Counter()
    for w in own:
        aa=people(w)
        if len(aa)>max_team:boundary['large_team_papers']+=1;continue
        for aid,entry in aa.items():
            if aid==focal:continue
            fi,mi=institution_ids(aa[focal]),institution_ids(entry)
            if not fi or not mi:boundary['unknown_institution_pairs']+=1
            elif not fi&mi:boundary['different_institution_pairs']+=1
            if scope=='shared_institution' and (not fi or not mi or not fi&mi):continue
            qualifying[aid].append(w)
    # Publication onset is computed only from that author's completed source
    # history. A neighbor seen in somebody else's papers has unknown onset.
    def career(aid,year):
        status=coverage.get(aid,{})
        if not status.get('complete'):return None,None,('history_incomplete' if corpora.get(aid) else 'history_not_collected')
        raw_history=[w for w in corpora.get(aid,[]) if not isinstance(w.get('publication_year'),int) or w['publication_year']<=year]
        if any(aid not in people(w) for w in raw_history):return None,None,'author_mismatch'
        if any(not isinstance(w.get('publication_year'),int) or isinstance(w.get('publication_year'),bool)
               or not 1000<=w['publication_year']<=9999 or aid not in people(w) for w in raw_history):
            return None,None,'undated_source_record'
        earlier=[w for w in raw_history if w['publication_year']<=year]
        if not earlier:return None,None,'no_dated_history_at_entry'
        first=min(w['publication_year'] for w in earlier)
        # IDs, not author positions, define authors. Count unique source records
        # before the entry YEAR; within-year order is not invented.
        before=len({(w.get('doi') or w['id']).lower().removeprefix('https://doi.org/') for w in earlier if w['publication_year']<year})
        return first,before,None

    members=[];cohorts=[];peer_support=defaultdict(lambda:{'newcomers':set(),'works':set(),'persistent_newcomers':set()})
    evidence_ids=set()
    for aid,shared in sorted(qualifying.items()):
        entry_year=min(w['publication_year'] for w in shared)
        first,before,missing=career(aid,entry_year)
        category=('unknown' if missing else 'early_career' if entry_year-first<early_years and before<=prior_papers else 'experienced')
        history_issue=missing
        basis='complete_history' if not missing else 'insufficient_history'
        observed=[w for w in by_author[aid] if w['publication_year']<=entry_year]
        # Positive evidence of a long career survives missing records; absence
        # of older evidence does NOT prove a short career. Identity conflicts abstain.
        if missing and missing!='author_mismatch' and observed:
            earliest=min(w['publication_year'] for w in observed)
            previous=sum(w['publication_year']<entry_year for w in observed)
            if entry_year-earliest>=early_years or previous>prior_papers:
                first,before,category,missing=earliest,previous,'experienced',None
                basis='observed_lower_bound'
        status=coverage.get(aid,{})
        career_ids=sorted({w['id'] for w in corpora.get(aid,[]) if first is not None and
                           isinstance(w.get('publication_year'),int) and w['publication_year']<=entry_year
                           and w.get('id') in by_id})
        if basis=='observed_lower_bound':career_ids=[w['id'] for w in observed]
        member={'id':aid,'name':names.get(aid,aid),'entry_year':entry_year,'first_observed_publication_year':first,
                'papers_before_entry_year':before,'category':category,'missing_reason':missing,'history_issue':history_issue,'classification_basis':basis,
                'history_complete':bool(status.get('complete')),'coverage_through':status.get('through'),
                'qualifying_papers':len(shared),'qualifying_years':sorted({w['publication_year'] for w in shared}),
                'entry_work_ids':[w['id'] for w in shared if w['publication_year']==entry_year],
                'qualifying_work_ids':[w['id'] for w in shared],'career_evidence_work_ids':career_ids}
        members.append(member);evidence_ids.update(member['qualifying_work_ids']+career_ids)
        if not start<=entry_year<=end:continue
        prior={a for a,papers in qualifying.items() if a!=aid and
               sum(entry_year-window<=w['publication_year']<entry_year for w in papers)>=incumbent_papers}
        cohort=dict(member,incumbents=sorted(prior),
                    incumbent_evidence={a:[w['id'] for w in qualifying[a] if entry_year-window<=w['publication_year']<entry_year] for a in sorted(prior)},
                    followup_year=entry_year+followup,
                    assessment='not_early_career',early_work_ids=[],focal_work_ids=[],peer_work_ids=[],
                    persistent_peer_ids=[],independent_peer_work_ids=[],followup_work_ids=[],
                    circle_followup_work_ids=[],early_large_team_omitted=0,
                    focal_share=None,peer_supported=None,persistent_peer_supported=None,
                    publication_continuation=None,circle_continuation=None)
        if category=='unknown':cohort['assessment']='unknown_career_history'
        elif category=='early_career':
            horizon=status.get('through')
            if horizon is None:
                cohort['assessment']='coverage_date_unknown'
            elif entry_year+followup>min(end,horizon):
                cohort['assessment']='right_censored'
            else:
                batch=[w for w in by_author[aid] if entry_year<=w['publication_year']<=entry_year+followup]
                boundary_year=batch[min(early_papers,len(batch))-1]['publication_year'] if batch else None
                early=[w for w in batch if w['publication_year']<=boundary_year] if batch else []
                cohort['early_large_team_omitted']=sum(len(people(w))>max_team for w in early)
                early=[w for w in early if len(people(w))<=max_team]
                cohort['early_work_ids']=[w['id'] for w in early]
                cohort['focal_work_ids']=[w['id'] for w in early if focal in people(w)]
                peer_papers=defaultdict(list)
                for w in early:
                    for a in (set(people(w))&prior)-{focal}:peer_papers[a].append(w)
                cohort['peer_work_ids']=sorted({w['id'] for pp in peer_papers.values() for w in pp})
                cohort['persistent_peer_ids']=sorted(a for a,pp in peer_papers.items() if len(pp)>=2 and len({w['publication_year'] for w in pp})>=2)
                cohort['independent_peer_work_ids']=[w['id'] for w in early if focal not in people(w) and set(people(w))&prior]
                later=[w for w in by_author[aid] if w['publication_year']==entry_year+followup]
                cohort['followup_work_ids']=[w['id'] for w in later]
                cohort['circle_followup_work_ids']=[w['id'] for w in later if len(people(w))<=max_team and set(people(w))&(prior|{focal})]
                if not early:cohort['assessment']='no_eligible_early_papers'
                else:
                    cohort.update(assessment='assessed',focal_share=len(cohort['focal_work_ids'])/len(early),
                                  peer_supported=bool(peer_papers),persistent_peer_supported=bool(cohort['persistent_peer_ids']),
                                  publication_continuation=bool(later),circle_continuation=bool(cohort['circle_followup_work_ids']))
                    for a,pp in peer_papers.items():
                        peer_support[a]['newcomers'].add(aid);peer_support[a]['works'].update(w['id'] for w in pp)
                        if a in cohort['persistent_peer_ids']:peer_support[a]['persistent_newcomers'].add(aid)
                evidence_ids.update(cohort['early_work_ids']+cohort['followup_work_ids'])
        cohorts.append(cohort)

    def summarize(rows):
        counts=Counter(r['category'] for r in rows);assessed=[r for r in rows if r['assessment']=='assessed']
        n=len(assessed)
        return {'entrants':len(rows),'early_career':counts['early_career'],'experienced':counts['experienced'],'unknown':counts['unknown'],
                'age_classification_coverage':ratio(counts['early_career']+counts['experienced'],len(rows)),
                'early_career_share_of_classified':ratio(counts['early_career'],counts['early_career']+counts['experienced']),
                'early_career_count_bounds':[counts['early_career'],counts['early_career']+counts['unknown']],
                'assessed':n,'right_censored':sum(r['assessment']=='right_censored' for r in rows),
                'assessment_counts':dict(Counter(r['assessment'] for r in rows)),
                'unknown_reasons':dict(Counter(r['missing_reason'] for r in rows if r['category']=='unknown')),
                'focal_mean_share':sum(r['focal_share'] for r in assessed)/n if n else None,
                'peer_supported_count':sum(r['peer_supported'] for r in assessed),
                'peer_supported_rate':ratio(sum(r['peer_supported'] for r in assessed),n),
                'persistent_peer_count':sum(r['persistent_peer_supported'] for r in assessed),
                'persistent_peer_rate':ratio(sum(r['persistent_peer_supported'] for r in assessed),n),
                'circle_continuation_count':sum(r['circle_continuation'] for r in assessed),
                'circle_continuation_rate':ratio(sum(r['circle_continuation'] for r in assessed),n),
                'publication_continuation_count':sum(r['publication_continuation'] for r in assessed),
                'publication_continuation_rate':ratio(sum(r['publication_continuation'] for r in assessed),n)}
    annual=[]
    for year in range(start,end+1):
        row=summarize([r for r in cohorts if r['entry_year']==year])
        row.update(year=year,active_circle_members=sum(any(year-window+1<=w['publication_year']<=year for w in pp) for pp in qualifying.values()))
        annual.append(row)
    # Evidence of independent collaboration excludes every focal-authored paper.
    # An edge in a focal paper's projected clique cannot prove such independence.
    active={a for a,pp in qualifying.items() if any(end-window+1<=w['publication_year']<=end for w in pp)}
    entry_years={a:min(w['publication_year'] for w in pp) for a,pp in qualifying.items()}
    graph=nx.Graph();graph.add_nodes_from(sorted(active));independent_ids=[]
    for w in works:
        aa=set(people(w))
        if focal in aa or len(aa)>max_team or not end-window+1<=w['publication_year']<=end:continue
        local=sorted(a for a in aa&active if entry_years[a]<=w['publication_year'])
        if len(local)<2:continue
        independent_ids.append(w['id']);evidence_ids.add(w['id'])
        for a,b in combinations(local,2):
            old=graph.get_edge_data(a,b,{})
            graph.add_edge(a,b,weight=old.get('weight',0)+1/(len(aa)-1),work_ids=old.get('work_ids',[])+[w['id']])
    groups=nx.community.louvain_communities(graph,seed=42,weight='weight') if graph.number_of_edges() else [{a} for a in sorted(active)]
    groups=sorted(groups,key=lambda g:(-len(g),sorted(g)))
    subgroups=[{'members':sorted(g),'names':[names.get(a,a) for a in sorted(g)]} for g in groups if len(g)>1]
    membership={a:i for i,g in enumerate(groups) for a in g}
    structure={'window_start':end-window+1,'window_end':end,'active_members':len(active),
               'complete_member_histories':sum(coverage.get(a,{}).get('complete',False) for a in active),
               'history_coverage':ratio(sum(coverage.get(a,{}).get('complete',False) for a in active),len(active)),
               'independent_papers':len(independent_ids),'independent_work_ids':independent_ids,
               'observed_subgroups':subgroups,'isolates':sum(graph.degree(a)==0 for a in active),
               'nodes':[{'id':a,'name':names.get(a,a),'community':membership[a],
                         'complete':coverage.get(a,{}).get('complete',False)} for a in sorted(active)],
               'edges':[{'source':a,'target':b,**d} for a,b,d in graph.edges(data=True)],
               'formal_hierarchy_inferred':False}
    evidence={wid:{'id':wid,'title':by_id[wid].get('title') or by_id[wid].get('display_name') or wid,
                   'year':by_id[wid]['publication_year'],'is_retracted':bool(by_id[wid].get('is_retracted')),
                   'is_paratext':bool(by_id[wid].get('is_paratext')),
                   'authors':[{'id':a,'name':names.get(a,a)} for a in people(by_id[wid])],
                   'institutions':{a:sorted(institution_ids(entry)) for a,entry in people(by_id[wid]).items()}}
              for wid in sorted(evidence_ids)}
    parameters={'start':start,'end':end,'scope':scope,'window':window,'early_years':early_years,'prior_papers':prior_papers,
                'early_papers':early_papers,'followup':followup,'incumbent_papers':incumbent_papers,'max_team':max_team}
    support=[{'id':a,'name':names.get(a,a),'newcomer_ids':sorted(v['newcomers']),
              'persistent_newcomer_ids':sorted(v['persistent_newcomers']),'work_ids':sorted(v['works'])} for a,v in peer_support.items()]
    return {'version':VERSION,'focal':focal,'name':names.get(focal,focal),'parameters':parameters,
            'summary':summarize(cohorts),'annual':annual,'members':members,'cohorts':cohorts,'structure':structure,
            'peer_support':sorted(support,key=lambda x:(-len(x['newcomer_ids']),x['id'])),'evidence':evidence,
            'coverage':{'source_histories':coverage,'excluded_records':excluded,'boundary_exclusions':dict(boundary)},
            'input_sha256':hashlib.sha256(json.dumps({'corpora':{a:[w for w in ws if not isinstance(w.get('publication_year'),int) or w['publication_year']<=end] for a,ws in corpora.items()},'coverage':coverage,'parameters':parameters},sort_keys=True).encode()).hexdigest(),
            'interpretation':{'unit':'Observed publication-based collaboration circle, not a verified lab roster.',
                              'entry':'First qualifying coauthored publication year, not enrollment or joining date.',
                              'newcomer':'Early observed publication career; student status and degrees are unknown.',
                              'followup':'Publication/coauthorship observed in entry year + horizon; absence is not dropout.',
                              'inference':'Descriptive counts, not admission willingness, supervision intensity or formal senior/junior PI classification.',
                              'selection':'Initial qualifying work necessarily includes the focal author. Mean participation uses complete member histories including non-focal papers.',
                              'peer':'Previously established circle member, excluding focal; not verified senior student or mentor.',
                              'missingness':'Collection prioritizes mature cohorts and frequent collaborators. Classified members are not a random sample; their rates cannot be extrapolated to all members.',
                              'historical':'Current source snapshot reconstructed by publication year; not a database captured in that year.'},
            'references':['https://doi.org/10.1126/science.1106340','https://doi.org/10.1038/s41562-025-02114-8']}
