"""Describe actual returned-event volumes; page counts are explicitly a proxy."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def quantiles(values):
    q=[0,.25,.5,.75,.9,.95,.99,1.]
    return {str(int(100*p)):float(v) for p,v in zip(q,np.quantile(values,q))}


if __name__=='__main__':
    source=ROOT/'research/results/frozen-forecast-v1.json';report=json.loads(source.read_text())
    base=ROOT/'data/research/temporal/holdout'/report['protocol_sha256'][:16];result=[]
    for cohort in report['reports']:
        rows=[json.loads(p.read_text()) for p in (base/f'{cohort["dataset"]}-{cohort["cutoff"]}').glob('author-*.json')]
        result.append({'dataset':cohort['dataset'],'cutoff':cohort['cutoff'],'stage':cohort['stage'],'targets':len(rows),
                       'actual_extra_author_queries':quantiles([r['actual_queries'] for r in rows]),
                       'returned_events_including_duplicates':quantiles([r['returned_papers'] for r in rows]),
                       'unique_observed_events':quantiles([r['query_log'][-1]['observed_events'] for r in rows]),
                       'cold_cache_pages_proxy_100':quantiles([sum(max(1,(q['returned_events']+99)//100) for q in r['query_log']) for r in rows])})
    out={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rows':result,
         'scope':'Event counts are measured from the frozen query traces. Pages are a proxy assuming 100 events per page, complete sequential responses, and no reuse across focal targets; not measured OpenAlex billing, HTTP requests or latency. The focal author query is included in event/page volume but excluded from the extra-author budget.',
         'quantiles':'0,25,50,75,90,95,99,100 percentiles; all 512 targets retained'}
    (ROOT/'research/results/frozen-forecast-costs.json').write_text(json.dumps(out,indent=2)+'\n')
    print('Cost distributions saved for',len(result),'cohorts')
