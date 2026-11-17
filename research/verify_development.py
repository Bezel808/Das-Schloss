"""Check saved real-data runs across policies, budgets and repeated-edge tasks."""
import hashlib
import json
from pathlib import Path
from temporal_benchmark import PROJECT, BUDGETS, POLICIES


def verify(path):
    report=json.loads(path.read_text());protocol=report['protocol']
    folder=PROJECT/report['rows_path']
    assert json.loads((folder/'protocol.json').read_text())==protocol
    files=sorted(folder.glob('author-*.json'))
    assert len(files)==len(protocol['cohort'])==512
    seen=set();states=0
    for file in files:
        rows=json.loads(file.read_text());author=int(file.stem.split('-')[1]);seen.add(author)
        assert len(rows)==len(POLICIES)*len(BUDGETS)
        assert {(r['policy'],r['budget']) for r in rows}=={(p,b) for p in POLICIES for b in BUDGETS}
        reference=rows[0]
        for row in rows:
            assert row['author']==author and row['cutoff']==protocol['cutoff']
            assert row['bounds_coverage'] and row['actual_extra_queries']<=row['budget']
            assert row['actual_extra_queries']==len(row['query_log'])-1
            assert len({q['author'] for q in row['query_log']})==len(row['query_log'])
            for key in ['gold_new_seen','gold_new_cold','gold_repeated','oracle_cn','repeat_edge']:
                assert row[key]==reference[key],(author,row['policy'],row['budget'],key)
            for task,gold_key in [('new_edge','gold_new_seen'),('repeat_edge','gold_repeated')]:
                for metric in row[task].values():
                    expected=metric['tie_expected']
                    assert -1e-10<=expected['hits_at_10']<=min(10,metric['candidate_positives'])+1e-10
                    assert expected['minimum_hits_at_10']-1e-10<=expected['hits_at_10']<=expected['maximum_hits_at_10']+1e-10
                    assert metric['candidate_positives']<=row[gold_key]
            states+=1
    assert seen==set(protocol['cohort'])
    return {'source':str(path.relative_to(PROJECT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'targets':len(seen),'saved_states':states,'passed':True}


if __name__=='__main__':
    files=sorted((PROJECT/'research/results').glob('coauth-*-unique-incidence-1-tie-expectation-1.json'))
    assert len(files)==8,'All eight predeclared cohorts are required'
    results=[verify(path) for path in files]
    result={'runs':results,'total_target_years':sum(r['targets'] for r in results),
            'total_saved_states':sum(r['saved_states'] for r in results),
            'checks':['fixed cohorts and denominators','unique policies/budgets','complete-author query accounting',
                      'historical bound coverage','repeat-edge metrics invariant to extra acquisition',
                      'oracle and gold independent of acquisition','expected hit ranges and candidate coverage'],
            'interpretation':'Consistency checks on real experiment artifacts; not evidence of prediction superiority.'}
    (PROJECT/'research/results/development-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified',result['total_target_years'],'target-years,',result['total_saved_states'],'saved states')
