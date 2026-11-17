"""Evaluate one immutable selection on validation and final temporal holdouts."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import sys
import numpy as np
from scipy.special import expit
from temporal_benchmark import TemporalCorpus, Observation, PROJECT, ROOT, retrieval
from forecast_features import features, FEATURES
from scholartrace.forecasting import observed_walk

PROTOCOL=PROJECT/'research/protocols/frozen-forecast-v1.json'


def run():
    frozen=json.loads(PROTOCOL.read_text());protocol_hash=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    for path,sha in frozen['components_sha256'].items():
        if hashlib.sha256((PROJECT/path).read_bytes()).hexdigest()!=sha:
            raise ValueError('Frozen implementation changed: '+path)
    reports=[]
    for dataset in frozen['datasets']:
        corpus=TemporalCorpus(dataset)
        if hashlib.sha256((ROOT/(dataset+'.npz')).read_bytes()).hexdigest()!=frozen['source_sha256'][dataset]:
            raise ValueError('Frozen data changed')
        for stage,years in frozen['stages'].items():
            for year in years:
                cohort=corpus.cohort(year,frozen['targets'],frozen['seed'])
                folder=ROOT/'holdout'/protocol_hash[:16]/f'{dataset}-{year}'
                folder.mkdir(parents=True,exist_ok=True)
                metadata={'protocol_sha256':protocol_hash,'dataset':dataset,'cutoff':year,'stage':stage,'cohort':cohort,
                          'normalization':corpus.normalization}
                dest=folder/'protocol.json'
                if dest.exists() and json.loads(dest.read_text())!=metadata:raise ValueError('Holdout checkpoint mismatch')
                dest.write_text(json.dumps(metadata,indent=2)+'\n')
                for index,author in enumerate(cohort,1):
                    dest=folder/f'author-{author}.json'
                    if dest.exists():continue
                    state=Observation(author,year);state.reveal(author,corpus.query(author,year))
                    rng=random.Random(f'{frozen["seed"]}|{author}|{frozen["policy"]}')
                    for _ in range(frozen['budget']):
                        query=state.next_query(frozen['policy'],rng)
                        if query is None:break
                        state.reveal(query,corpus.query(query,year))
                    classical=state.scores()
                    scores={name:{a:r[name] for a,r in classical.items()} for name in frozen['graph_baselines']}
                    walk=observed_walk(state,'recent_fractional',frozen['half_life_years'])
                    scores['ppr_recent_fractional']=walk.pop('scores')
                    ids,x=features(state,corpus)
                    for name,model in frozen['models'].items():
                        columns=[FEATURES.index(k) for k in model['features']]
                        standardized=(x[:,columns]-np.array(model['mean']))/np.array(model['scale'])
                        probabilities=expit(standardized@np.array(model['coefficient'])+model['intercept'])
                        scores['ml_'+name]=dict(zip(ids,probabilities.tolist()))
                    # No future labels are read until every score has been fixed.
                    truth=corpus.future(author,year)
                    result={'author':author,'cutoff':year,'stage':stage,'gold_new_seen':len(truth['new_seen']),
                            'gold_new_cold':len(truth['new_cold']),'actual_queries':len(state.complete)-1,
                            'returned_papers':sum(q['returned_events'] for q in state.query_log),
                            'query_log':state.query_log,'walk_diagnostics':walk,
                            'metrics':{name:retrieval(s,truth['new_seen']) for name,s in scores.items()}}
                    dest.with_suffix('.tmp').write_text(json.dumps(result)+'\n');dest.with_suffix('.tmp').replace(dest)
                    if index%128==0:print(stage,dataset,year,index,'/',len(cohort),flush=True)
                rows=[json.loads(p.read_text()) for p in folder.glob('author-*.json')]
                assert {r['author'] for r in rows}==set(cohort)
                reports.append(summarize(metadata,rows,frozen))
                corpus.query_cache.clear()
    report={'protocol':frozen,'protocol_sha256':protocol_hash,'reports':reports,
            'interpretation':'Immutable chronological holdout; no post-holdout parameter selection. Paired intervals are conditional on each fixed source graph and historical-activity cohort. Not new-person generalization, causal career effects or mentor identification.'}
    destination=PROJECT/'research/results/frozen-forecast-v1.json'
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print('Completed frozen validation and final holdout:',sum(r['targets'] for r in reports),'target-years',flush=True)


def summarize(metadata,rows,frozen):
    rows=sorted(rows,key=lambda r:r['author']);gold=np.asarray([r['gold_new_seen'] for r in rows],dtype=float)
    samples=np.random.default_rng(813).integers(0,len(rows),size=(2000,len(rows)))
    denominators=gold[samples].sum(axis=1);valid=denominators>0
    models=[]
    reference=np.array([r['metrics'][frozen['primary_baseline']]['tie_expected']['hits_at_10'] for r in rows])
    for method in rows[0]['metrics']:
        hits=np.array([r['metrics'][method]['tie_expected']['hits_at_10'] for r in rows])
        delta=hits-reference
        interval=np.quantile(delta[samples].sum(axis=1)[valid]/denominators[valid],[.025,.975]).tolist() if valid.any() else None
        models.append({'method':method,'gold':int(gold.sum()),'expected_hits_at_10':float(hits.sum()),
                       'micro_recall_at_10':float(hits.sum()/gold.sum()) if gold.sum() else None,
                       'candidate_coverage':sum(r['metrics'][method]['candidate_positives'] for r in rows)/gold.sum() if gold.sum() else None,
                       'macro_ap_positive_targets':float(np.mean([r['metrics'][method]['tie_expected']['average_precision'] for r in rows if r['gold_new_seen']])) if gold.sum() else None,
                       'difference_vs_primary_baseline':float(delta.sum()/gold.sum()) if gold.sum() else None,
                       'paired_target_bootstrap_95':interval,'valid_resamples':int(valid.sum())})
    return {'dataset':metadata['dataset'],'cutoff':metadata['cutoff'],'stage':metadata['stage'],'targets':len(rows),
            'positive_targets':int((gold>0).sum()),'cold_start_associations':sum(r['gold_new_cold'] for r in rows),
            'mean_actual_queries':float(np.mean([r['actual_queries'] for r in rows])),
            'mean_returned_papers':float(np.mean([r['returned_papers'] for r in rows])),
            'models':models}


if __name__=='__main__':run()
