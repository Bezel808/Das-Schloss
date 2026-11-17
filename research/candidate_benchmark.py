"""Fixed-query candidate/score factorial ablation, using saved development traces."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from temporal_benchmark import TemporalCorpus, Observation, PROJECT, ROOT, retrieval
from scholartrace.forecasting import observed_walk, VERSION


def run(path):
    report=json.loads(path.read_text());protocol=report['protocol']
    if protocol['stage']!='development' or protocol['cutoff']>2008:raise ValueError('Development only')
    corpus=TemporalCorpus(protocol['dataset'])
    if corpus.normalization!=protocol['normalization']:raise ValueError('Normalization mismatch')
    origin=PROJECT/report['rows_path'];destination=origin/VERSION;destination.mkdir(exist_ok=True)
    settings={'source_report':str(path.relative_to(PROJECT)),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()+(PROJECT/'scholartrace/forecasting.py').read_bytes()+(PROJECT/'scholartrace/evaluation.py').read_bytes()).hexdigest(),
              'policies':['neighbor_degree','observed_degree'],'budget':20,'alpha':.85,'half_life_years':3,
              'version':VERSION,'stage':'development'}
    metadata=destination/'protocol.json'
    if metadata.exists() and json.loads(metadata.read_text())!=settings:raise ValueError('Existing ablation belongs to a different implementation')
    metadata.write_text(json.dumps(settings,indent=2)+'\n')
    started=time.perf_counter()
    for index,author in enumerate(protocol['cohort'],1):
        dest=destination/f'author-{author}.json'
        if dest.exists():continue
        saved=json.loads((origin/f'author-{author}.json').read_text());rows=[]
        for policy in settings['policies']:
            record=next(r for r in saved if r['policy']==policy and r['budget']==20)
            state=Observation(author,protocol['cutoff'])
            for q in record['query_log']:state.reveal(q['author'],corpus.query(q['author'],state.cutoff))
            classical=state.scores();twohop={a for a,v in classical.items() if v['common_neighbors']>0}
            score_maps={name:{a:v[name] for a,v in classical.items()} for name in ['common_neighbors','adamic_adar','resource_allocation']}
            diagnostics={}
            for weighting in ['unweighted','count','recent_fractional']:
                result=observed_walk(state,weighting);name='ppr_'+weighting
                score_maps[name]=result.pop('scores');diagnostics[name]=result
            # Gold is used only by the evaluator after feature/score construction.
            gold=corpus.future(author,state.cutoff)['new_seen']
            assert len(gold)==record['gold_new_seen']
            if policy=='neighbor_degree':assert twohop==state.candidates()
            for pool,candidates in [('twohop',twohop),('all_observed',state.candidates())]:
                for method,scores in score_maps.items():
                    metric=retrieval({a:s for a,s in scores.items() if a in candidates},gold)
                    rows.append({'author':author,'policy':policy,'pool':pool,'method':method,'gold':len(gold),
                                 'actual_queries':record['actual_extra_queries'],'returned_papers':record['returned_papers_with_repeats'],
                                 'metric':metric,'numerical_diagnostics':diagnostics.get(method)})
        dest.with_suffix('.tmp').write_text(json.dumps(rows)+'\n');dest.with_suffix('.tmp').replace(dest)
        if index%128==0:print(protocol['dataset'],protocol['cutoff'],index,'/',len(protocol['cohort']),round(time.perf_counter()-started,1),'s',flush=True)
    rows=[r for p in destination.glob('author-*.json') for r in json.loads(p.read_text())]
    groups=defaultdict(list)
    for row in rows:groups[row['policy'],row['pool'],row['method']].append(row)
    summaries=[]
    for (policy,pool,method),rr in sorted(groups.items()):
        assert len(rr)==len(protocol['cohort']) and {r['author'] for r in rr}==set(protocol['cohort'])
        gold=sum(r['gold'] for r in rr);discovered=sum(r['metric']['candidate_positives'] for r in rr)
        hits=sum(r['metric']['tie_expected']['hits_at_10'] for r in rr)
        summaries.append({'policy':policy,'pool':pool,'method':method,'targets':len(rr),'gold':gold,
                          'expected_hits_at_10':hits,'micro_recall_at_10':hits/gold if gold else None,
                          'candidate_coverage':discovered/gold if gold else None,
                          'conditional_recall_at_10':hits/discovered if discovered else None,
                          'macro_ap_positive_targets':float(np.mean([r['metric']['tie_expected']['average_precision'] for r in rr if r['gold']])) if gold else None,
                          'mean_candidates':float(np.mean([r['metric']['candidates'] for r in rr])),
                          'mean_actual_queries':float(np.mean([r['actual_queries'] for r in rr])),
                          'mean_returned_papers':float(np.mean([r['returned_papers'] for r in rr]))})
    result={'protocol':settings,'dataset':protocol['dataset'],'cutoff':protocol['cutoff'],
            'summary':summaries,'rows_path':str(destination.relative_to(PROJECT)),
            'interpretation':'Prediction baselines on the same returned historical graph; PPR scores do not inherit CN missing-edge certificates. Candidate and ranking changes are separate factors.'}
    output=PROJECT/'research/results'/f'candidate-{protocol["dataset"]}-{protocol["cutoff"]}-{VERSION}.json'
    output.write_text(json.dumps(result,indent=2)+'\n');print('Completed',output.name,flush=True)


if __name__=='__main__':
    for path in sorted((PROJECT/'research/results').glob('coauth-*-unique-incidence-1-tie-expectation-1.json')):run(path)
