"""Separate discovery failure, ranking failure and unidentifiable cold start."""
import json
from pathlib import Path
from temporal_benchmark import PROJECT


def decompose(report):
    root=PROJECT/report['rows_path'];totals={k:0. for k in ['gold_seen','gold_cold','discovered_positive','expected_hits','full_twohop_positive','full_cn_expected_hits']}
    for path in root.glob('author-*.json'):
        rows=json.loads(path.read_text());r=next(x for x in rows if x['policy']=='neighbor_degree' and x['budget']==20)
        m=r['new_edge']['common_neighbors'];oracle=r['oracle_cn']
        for key,value in [('gold_seen',r['gold_new_seen']),('gold_cold',r['gold_new_cold']),('discovered_positive',m['candidate_positives']),('expected_hits',m['tie_expected']['hits_at_10']),('full_twohop_positive',oracle['candidate_positives']),('full_cn_expected_hits',oracle['tie_expected']['hits_at_10'])]:totals[key]+=value
    totals['not_discovered']=totals['gold_seen']-totals['discovered_positive']
    totals['discovered_but_below_top10']=totals['discovered_positive']-totals['expected_hits']
    total=totals['gold_seen']+totals['gold_cold']
    totals['all_future_new_associations']=total
    assert abs(sum(totals[k] for k in ['gold_cold','not_discovered','discovered_but_below_top10','expected_hits'])-total)<1e-8
    return {'dataset':report['protocol']['dataset'],'cutoff':report['protocol']['cutoff'],'targets':report['protocol']['targets'],
            'policy':'neighbor_degree','budget':20,'counts':totals,
            'full_twohop_coverage_of_seen':totals['full_twohop_positive']/totals['gold_seen'] if totals['gold_seen'] else None,
            'shares_of_all_new_associations':{k:totals[k]/total if total else None for k in ['gold_cold','not_discovered','discovered_but_below_top10','expected_hits']}}


if __name__=='__main__':
    files=sorted((PROJECT/'research/results').glob('coauth-*-unique-incidence-1-tie-expectation-1.json'))
    results=[decompose(json.loads(path.read_text())) for path in files]
    (PROJECT/'research/results/collaboration-error-decomposition.json').write_text(json.dumps({
        'rows':results,'interpretation':'Fixed neighbor-degree acquisition at budget 20. Future labels are evaluator-only. Complete-history two-hop coverage is a reference for that candidate rule, not a ceiling for broader candidate retrieval or prediction.',
        'denominator':'target-partner associations, not deduplicated undirected edges'},indent=2)+'\n')
    for row in results:print(row['dataset'],row['cutoff'],row['shares_of_all_new_associations'])
