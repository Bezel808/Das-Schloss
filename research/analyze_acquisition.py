"""Paired target-level uncertainty for fixed-graph development query experiments."""
import json
from pathlib import Path
import numpy as np

PROJECT=Path(__file__).resolve().parents[1]

def analyze(path,baseline='neighbor_degree',tie_expected=False):
    report=json.loads(path.read_text());rows=[]
    for p in (PROJECT/report['rows_path']).glob('author-*.json'):rows.extend(json.loads(p.read_text()))
    index={(r['author'],r['policy'],r['budget']):r for r in rows}
    ids=report['protocol']['cohort'];rng=np.random.default_rng(813)
    resamples=rng.integers(0,len(ids),size=(2000,len(ids)))
    result=[]
    for budget in report['protocol']['budgets']:
        for policy in report['protocol']['policies']:
            if policy==baseline:continue
            a=[index[i,policy,budget] for i in ids];b=[index[i,baseline,budget] for i in ids]
            gold=np.array([r['gold_new_seen'] for r in a],dtype=float)
            def hits(row):
                m=row['new_edge']['common_neighbors']
                return (m['tie_expected'] if tie_expected else m)['hits_at_10']
            delta=np.array([hits(x)-hits(y) for x,y in zip(a,b)])
            numerator=delta[resamples].sum(axis=1);denominator=gold[resamples].sum(axis=1)
            valid=denominator>0
            ci=np.quantile(numerator[valid]/denominator[valid],[.025,.975]).tolist() if valid.any() else None
            cert=np.array([int(x['certified_top10'])-int(y['certified_top10']) for x,y in zip(a,b)])
            result.append({'policy':policy,'baseline':baseline,'budget':budget,'targets':len(ids),
                'positive_targets':int((gold>0).sum()),'gold_new_edges':int(gold.sum()),
                'hits':sum(hits(r) for r in a),
                'baseline_hits':sum(hits(r) for r in b),
                'micro_recall_difference':float(delta.sum()/gold.sum()) if gold.sum() else None,
                'paired_target_bootstrap_95':ci,'valid_resamples':int(valid.sum()),
                'certification_rate_difference':float(cert.mean()),
                'certification_difference_bootstrap_95':np.quantile(cert[resamples].mean(axis=1),[.025,.975]).tolist()})
    return {'source':str(path.relative_to(PROJECT)),'comparisons':result,
            'metric':'tie_expected' if tie_expected else 'fixed_id',
            'interpretation':'Conditional on a fixed observed source graph and the stated historical-activity cohort sampling. These paired target-level intervals do not establish temporal or cross-domain generalization.',
            'resampling_unit':'target author; budgets and candidate edges are not independent replicates','seed':813,'resamples':2000}

if __name__=='__main__':
    files=sorted((PROJECT/'research/results').glob('coauth-*-unique-incidence-1-tie-expectation-1.json'))
    result=[analyze(p,tie_expected=True) for p in files]
    destination=PROJECT/'research/results/acquisition-paired-tie-development.json'
    destination.write_text(json.dumps(result,indent=2)+'\n')
    for report in result:
        print(report['source'])
        print([r for r in report['comparisons'] if r['policy']=='ambiguity_cover' and r['budget']==20])
