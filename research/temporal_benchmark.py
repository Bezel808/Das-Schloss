"""Leakage-separated complete-author-query experiments on real timestamped papers.

Development runs are explicit. Validation/test stages require a frozen selection
artifact; this runner cannot silently repurpose development scores as holdout.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import fcntl
import json
from pathlib import Path
import random
import resource
import sys
import time

import numpy as np
from fetch_temporal import file_sha256
from event_data import canonical_incidence, VERSION as DATA_VERSION

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from scholartrace.acquisition import Observation, VERSION
from scholartrace.evaluation import retrieval, ranked, VERSION as METRIC_VERSION

ROOT=PROJECT/'data/research/temporal'
POLICIES=['random','observed_degree','uncertainty','neighbor_random','neighbor_degree','uniform_cover','ambiguity_cover']
BUDGETS=[0,5,10,20,40]


class TemporalCorpus:
    def __init__(self,name):
        self.name=name
        expected=json.loads((PROJECT/'research/temporal-data-manifest.json').read_text())[name]['processed_sha256']
        if file_sha256(ROOT/(name+'.npz'))!=expected:raise ValueError('Temporal source fingerprint mismatch')
        data=np.load(ROOT/(name+'.npz'))
        self.times=data['times'];self.vertices=data['vertices'];self.offsets=data['offsets']
        self.nverts=data['nverts'];self.n_nodes=int(self.vertices.max())+1
        self.vertices,self.nverts,self.offsets,self.normalization=canonical_incidence(self.vertices,self.nverts,self.offsets)
        preprocessing_sha=file_sha256(Path(__file__).with_name('event_data.py'))
        prefix=ROOT/(name+'-author-index-'+DATA_VERSION+'-'+expected[:12]+'-'+preprocessing_sha[:12])
        self.index_prefix=prefix
        manifest=prefix.with_suffix('.manifest.json')
        source_sha=json.loads((PROJECT/'research/temporal-data-manifest.json').read_text())[name]['processed_sha256']
        paths=[prefix.with_suffix('.'+part+'.npy') for part in ['indptr','events','first']]
        with prefix.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            valid=manifest.exists() and all(p.exists() for p in paths)
            if valid:
                record=json.loads(manifest.read_text())
                valid=record.get('source_sha256')==source_sha and all(p.stat().st_size==record['bytes'].get(p.name) and file_sha256(p)==record.get('sha256',{}).get(p.name) for p in paths)
            if not valid:
                event_ids=np.repeat(np.arange(len(self.times),dtype=np.int32),self.nverts)
                order=np.argsort(self.vertices,kind='stable')
                counts=np.bincount(self.vertices,minlength=self.n_nodes)
                first=np.full(self.n_nodes,10000,dtype=np.int32)
                np.minimum.at(first,self.vertices,self.times[event_ids])
                for path,array in zip(paths,[np.r_[0,np.cumsum(counts)],event_ids[order],first]):
                    with path.with_suffix('.tmp').open('wb') as f:np.save(f,array)
                    path.with_suffix('.tmp').replace(path)
                manifest.with_suffix('.tmp').write_text(json.dumps({'source_sha256':source_sha,'bytes':{p.name:p.stat().st_size for p in paths},'sha256':{p.name:file_sha256(p) for p in paths}}))
                manifest.with_suffix('.tmp').replace(manifest)
        self.indptr=np.load(prefix.with_suffix('.indptr.npy'),mmap_mode='r')
        self.events=np.load(prefix.with_suffix('.events.npy'),mmap_mode='r')
        self.first=np.load(prefix.with_suffix('.first.npy'),mmap_mode='r')
        self.query_cache={}

    def query(self,author,cutoff):
        key=(int(author),int(cutoff))
        if key not in self.query_cache:
            events=self.events[self.indptr[author]:self.indptr[author+1]]
            events=events[self.times[events]<=cutoff]
            rows=[]
            for e in events:
                people=self.vertices[self.offsets[e]:self.offsets[e+1]].tolist()
                if len(people)!=len(set(people)):
                    raise ValueError('Duplicate author in original event; inspect source before continuing')
                rows.append((int(e),int(self.times[e]),people))
            self.query_cache[key]=rows
        return self.query_cache[key]

    def neighbors(self,author,cutoff):
        return {a for _,_,people in self.query(author,cutoff) for a in people}-{author}

    def future(self,author,cutoff):
        old=self.neighbors(author,cutoff)
        next_people={a for _,year,people in self.query(author,cutoff+1) if year==cutoff+1 for a in people}-{author}
        new=next_people-old
        return {'new_seen':{a for a in new if self.first[a]<=cutoff},
                'new_cold':{a for a in new if self.first[a]>cutoff},'repeated':next_people&old}

    def cohort(self,cutoff,count,seed):
        # Current activity and past output only; never select on future positives.
        recent=(self.times>=cutoff-4)&(self.times<=cutoff)
        active_counts=np.bincount(self.vertices[np.repeat(recent,self.nverts)],minlength=self.n_nodes)
        eligible=np.flatnonzero(active_counts>=3)
        order=sorted(eligible.tolist(),key=lambda a:hashlib.sha256(f'{self.name}|{cutoff}|{seed}|{a}'.encode()).digest())
        chosen=[]
        for author in order:
            if len(self.neighbors(author,cutoff))>=2:chosen.append(author)
            if len(chosen)==count:break
        return chosen


def evaluate_state(state,truth,full_cn,policy,budget,elapsed):
    scores=state.scores()
    metrics={name:retrieval({v:r[name] for v,r in scores.items()},truth['new_seen'])
             for name in ['common_neighbors','adamic_adar','resource_allocation','preferential_attachment','edge_bank','past_joint_count']}
    # Ranking recovery is separate from forecasting: known full-past CN top10.
    full_top=set(ranked(full_cn)[:10]); observed_top=set(metrics['common_neighbors']['top10'])
    cert=state.certificate(10)
    valid_bounds=all(lo<=full_cn.get(v,0)<=hi for v,(lo,hi) in cert['bounds'].items())
    if not valid_bounds:raise AssertionError('Historical CN escaped its certified interval')
    if any(score>cert['unseen_candidate_upper'] for v,score in full_cn.items() if v not in cert['bounds']):
        raise AssertionError('Undiscovered candidate escaped its certified upper bound')
    if cert['certified'] and set(cert['members'])!=full_top:
        raise AssertionError('False top-k certificate')
    # Repetition is a different task on the exactly observed focal-neighbor set.
    repeated={}
    for name in ['past_joint_count','recent_joint_year','edge_bank']:
        values={}
        for v in state.neighbors:
            edge=tuple(sorted((state.focal,v)))
            values[v]=float(state.counts[edge] if name=='past_joint_count' else
                            state.last[edge] if name=='recent_joint_year' else 1)
        repeated[name]=retrieval(values,truth['repeated'])
    widths=[hi-lo for lo,hi in cert['bounds'].values()]
    return {'author':state.focal,'cutoff':state.cutoff,'policy':policy,'budget':budget,
            'actual_extra_queries':len(state.complete)-1,'observed_papers':len(state.papers),
            'returned_papers_with_repeats':sum(q['returned_events'] for q in state.query_log),
            'observed_authors':len(state.adj),'known_neighbor_count':len(state.neighbors),
            'gold_new_seen':len(truth['new_seen']),'gold_new_cold':len(truth['new_cold']),
            'gold_repeated':len(truth['repeated']), 'new_edge':metrics,'repeat_edge':repeated,
            'oracle_cn':retrieval(full_cn,truth['new_seen']),
            'oracle_strict_top10_possible':len(full_cn)>=10 and sorted(full_cn.values(),reverse=True)[9] > (sorted(full_cn.values(),reverse=True)[10] if len(full_cn)>10 else 0),
            'full_past_cn_top10_recovery':len(full_top&observed_top)/len(full_top) if full_top else None,
            'certified_top10':cert['certified'],'bounds_coverage':valid_bounds,
            'unseen_candidate_upper':cert['unseen_candidate_upper'],
            'mean_interval_width':float(np.mean(widths)) if widths else None,
            'elapsed_seconds':elapsed,'query_log':state.query_log.copy()}


def run(name,cutoff,count,seed,stage='development'):
    if stage!='development':
        raise ValueError('Validation/test execution requires a frozen model-selection protocol; development runner cannot unlock it')
    if not 2000<=cutoff<=2008:raise ValueError('Development cutoff must be in the predeclared 2000–2008 range')
    started=time.perf_counter();corpus=TemporalCorpus(name)
    cohort=corpus.cohort(cutoff,count,seed)
    settings={'dataset':name,'cutoff':cutoff,'targets':count,'seed':seed,'stage':stage,
              'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()+(PROJECT/'scholartrace/acquisition.py').read_bytes()+(PROJECT/'scholartrace/evaluation.py').read_bytes()).hexdigest(),
              'metric_version':METRIC_VERSION,
              'normalization':corpus.normalization,
              'preprocessing_sha256':file_sha256(Path(__file__).with_name('event_data.py')),
              'primary_metric':'micro recall@10 expected over uniform score-tie permutations; ID ordering retained for audit',
              'policies':POLICIES,'budgets':BUDGETS,'version':VERSION,'cohort':cohort,
              'task':'next-year new edges among historically seen authors; cold-start and repeated ties separately counted',
              'sampling':'at least three papers in trailing five years and two historical neighbors; SHA256 order, no future labels',
              'source':json.loads((PROJECT/'research/temporal-data-manifest.json').read_text())[name]}
    run_id=f'{name}-{cutoff}-n{count}-s{seed}-{VERSION}-{DATA_VERSION}-{METRIC_VERSION}'
    out=ROOT/'runs'/run_id;out.mkdir(parents=True,exist_ok=True)
    metadata=out/'protocol.json'
    if metadata.exists() and json.loads(metadata.read_text())!=settings:raise ValueError('Run ID already describes another protocol')
    metadata.write_text(json.dumps(settings,indent=2)+'\n')
    complete=set()
    for path in out.glob('author-*.json'):
        complete.add(int(path.stem.split('-')[1]))
    for number,author in enumerate(cohort,1):
        if author in complete:continue
        initial=corpus.query(author,cutoff)
        # Evaluator-only oracle; never passed to a policy or score calculation.
        truth=corpus.future(author,cutoff)
        neighbors=corpus.neighbors(author,cutoff)
        full_cn=Counter(v for q in neighbors for v in corpus.neighbors(q,cutoff) if v not in neighbors and v!=author)
        rows=[]
        for policy in POLICIES:
            state=Observation(author,cutoff);state.reveal(author,initial)
            rng=random.Random(f'{seed}|{author}|{policy}')
            policy_start=time.perf_counter()
            for budget in range(max(BUDGETS)+1):
                if budget in BUDGETS:rows.append(evaluate_state(state,truth,full_cn,policy,budget,time.perf_counter()-policy_start))
                if budget==max(BUDGETS):break
                query=state.next_query(policy,rng)
                # Exhausted frontiers keep their last state at every later budget;
                # never drop these targets from high-budget denominators.
                if query is not None:state.reveal(query,corpus.query(query,cutoff))
        dest=out/f'author-{author}.json'
        dest.with_suffix('.tmp').write_text(json.dumps(rows)+'\n');dest.with_suffix('.tmp').replace(dest)
        print(f'{name} {cutoff}: {number}/{len(cohort)} authors, {time.perf_counter()-started:.1f}s',flush=True)
    summarize(out)


def summarize(out):
    protocol=json.loads((out/'protocol.json').read_text())
    rows=[r for p in sorted(out.glob('author-*.json')) for r in json.loads(p.read_text())]
    if len({r['author'] for r in rows})!=len(protocol['cohort']):raise ValueError('Incomplete run; no final summary')
    groups=defaultdict(list)
    for r in rows:groups[r['policy'],r['budget']].append(r)
    result=[]
    for (policy,budget),rr in sorted(groups.items()):
        if len(rr)!=len(protocol['cohort']):raise ValueError('Budget denominator changed')
        gold=sum(r['gold_new_seen'] for r in rr)
        row={'policy':policy,'budget':budget,'n_targets':len(rr),'targets_with_new_seen_edges':sum(r['gold_new_seen']>0 for r in rr),
             'gold_new_seen':gold,'gold_new_cold':sum(r['gold_new_cold'] for r in rr),
             'certified_top10_rate':float(np.mean([r['certified_top10'] for r in rr])),
             'mean_observed_papers':float(np.mean([r['observed_papers'] for r in rr])),
             'mean_returned_papers_with_repeats':float(np.mean([r['returned_papers_with_repeats'] for r in rr])),
             'oracle_cn_recall_at_10':sum(r['oracle_cn']['hits_at_10'] for r in rr)/gold if gold else None,
             'oracle_strict_top10_possible_rate':float(np.mean([r['oracle_strict_top10_possible'] for r in rr])),
             'mean_actual_queries':float(np.mean([r['actual_extra_queries'] for r in rr])),
             'oracle_cn_tie_expected_recall_at_10':sum(r['oracle_cn']['tie_expected']['hits_at_10'] for r in rr)/gold if gold else None,
             'cold_start_fraction':sum(r['gold_new_cold'] for r in rr)/sum(r['gold_new_seen']+r['gold_new_cold'] for r in rr) if sum(r['gold_new_seen']+r['gold_new_cold'] for r in rr) else None,
             'new_edge':{}}
        for method in rr[0]['new_edge']:
            row['new_edge'][method]={'micro_recall_at_10':sum(r['new_edge'][method]['hits_at_10'] for r in rr)/gold if gold else None,
              'candidate_recall':sum(r['new_edge'][method]['candidate_positives'] for r in rr)/gold if gold else None,
              'macro_average_precision_positive_targets':float(np.mean([r['new_edge'][method]['average_precision'] for r in rr if r['gold_new_seen']])) if gold else None,
              'precision_at_10_all_targets':float(np.mean([r['new_edge'][method]['precision_at_10'] for r in rr]))}
            row['new_edge'][method]['tie_expected'] = aggregate_metrics(rr, 'new_edge', method, 'gold_new_seen')
        repeated_gold=sum(r['gold_repeated'] for r in rr)
        row['repeat_edge']={'gold_repeated':repeated_gold,'targets_with_repeated_edges':sum(r['gold_repeated']>0 for r in rr),
                            'methods':{method:aggregate_metrics(rr,'repeat_edge',method,'gold_repeated') for method in rr[0]['repeat_edge']}}
        result.append(row)
    report={'protocol':protocol,'summary':result,'rows_path':str(out.relative_to(PROJECT)),
            'peak_rss_platform_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'peak_rss_unit':'bytes' if sys.platform=='darwin' else 'KiB',
            'limitations':['Development results only, not a frozen test or paper-ready claim.',
                           'Author responses are complete relative to the published dataset; real source completeness must be audited separately.',
                           'Primary metrics average exactly over score ties; fixed-ID metrics are secondary audit only. EdgeBank has no discrimination for new edges.',
                           'No binary accuracy on arbitrary sampled nonedges; fixed future positives remain in recall denominator.']}
    dest=PROJECT/'research/results';dest.mkdir(exist_ok=True)
    (dest/(out.name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('report',dest/(out.name+'.json'),flush=True)


def aggregate_metrics(rows,task,method,gold_key):
    gold=sum(r[gold_key] for r in rows)
    metrics=[r[task][method]['tie_expected'] for r in rows]
    return {'expected_hits_at_10':sum(m['hits_at_10'] for m in metrics),
            'micro_recall_at_10':sum(m['hits_at_10'] for m in metrics)/gold if gold else None,
            'precision_at_10_all_targets':float(np.mean([m['precision_at_10'] for m in metrics])),
            'macro_average_precision_positive_targets':float(np.mean([m['average_precision'] for m,r in zip(metrics,rows) if r[gold_key]])) if gold else None,
            'minimum_hits_at_10':sum(m['minimum_hits_at_10'] for m in metrics),
            'maximum_hits_at_10':sum(m['maximum_hits_at_10'] for m in metrics),
            'cutoff_tied_target_fraction':float(np.mean([m['cutoff_splits_tie'] for m in metrics]))}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',default='coauth-DBLP',choices=['coauth-DBLP','coauth-MAG-History'])
    p.add_argument('--cutoff',type=int,default=2008);p.add_argument('--targets',type=int,default=64)
    p.add_argument('--seed',type=int,default=42);args=p.parse_args()
    run(args.dataset,args.cutoff,args.targets,args.seed)
