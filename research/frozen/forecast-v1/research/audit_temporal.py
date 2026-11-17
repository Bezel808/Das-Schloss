"""Audit event normalization without changing or replacing original source arrays."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
from temporal_benchmark import TemporalCorpus, ROOT, PROJECT


def audit(name, years):
    corpus=TemporalCorpus(name)
    raw=np.load(ROOT/(name+'.npz'))
    affected=np.flatnonzero(raw['nverts']!=corpus.nverts)
    changes=[]
    for event in affected:
        old=raw['vertices'][raw['offsets'][event]:raw['offsets'][event+1]].tolist()
        new=corpus.vertices[corpus.offsets[event]:corpus.offsets[event+1]].tolist()
        assert set(old)==set(new) and len(new)==len(set(old))
        assert new==list(dict.fromkeys(old))
        changes.append({'event_id':int(event),'year':int(corpus.times[event]),
                        'before':old,'after':new,'removed':{str(a):n-1 for a,n in Counter(old).items() if n>1}})
    assert len(corpus.vertices)==len(raw['vertices'])-corpus.normalization['removed_duplicate_incidences']
    # Full author-index conservation: each event appears once for each distinct
    # author, and no event is lost, including singleton/repeated-author papers.
    assert np.array_equal(np.bincount(corpus.events,minlength=len(corpus.times)),corpus.nverts)
    assert np.array_equal(np.unique(raw['vertices']),np.unique(corpus.vertices))
    raw_first=np.full(corpus.n_nodes,10000,dtype=np.int32)
    np.minimum.at(raw_first,raw['vertices'],np.repeat(raw['times'],raw['nverts']))
    assert np.array_equal(raw_first,corpus.first)
    # Audit the previously declared cohort rule both before and after cleanup.
    cohorts=[]
    for year in years:
        recent=(corpus.times>=year-4)&(corpus.times<=year)
        before=np.bincount(raw['vertices'][np.repeat(recent,raw['nverts'])],minlength=corpus.n_nodes)
        after=np.bincount(corpus.vertices[np.repeat(recent,corpus.nverts)],minlength=corpus.n_nodes)
        order=sorted(np.flatnonzero(before>=3).tolist(),key=lambda a:hashlib.sha256(f'{name}|{year}|42|{a}'.encode()).digest())
        old_cohort=[]
        for author in order:
            if len(corpus.neighbors(author,year))>=2:old_cohort.append(author)
            if len(old_cohort)==512:break
        new_cohort=corpus.cohort(year,512,42)
        cohorts.append({'cutoff':year,'activity_eligible_before':int((before>=3).sum()),
                        'activity_eligible_after':int((after>=3).sum()),
                        'changed_activity_eligibility':np.flatnonzero((before>=3)!=(after>=3)).tolist(),
                        'selected_removed':sorted(set(old_cohort)-set(new_cohort)),
                        'selected_added':sorted(set(new_cohort)-set(old_cohort))})
    digest=hashlib.sha256()
    for key,array in [('times',corpus.times),('nverts',corpus.nverts),('offsets',corpus.offsets),('vertices',corpus.vertices)]:
        digest.update(key.encode());digest.update(np.asarray(array,dtype='<i8').tobytes())
    return {'dataset':name,'normalization':corpus.normalization,
            'source_sha256':hashlib.sha256((ROOT/(name+'.npz')).read_bytes()).hexdigest(),
            'preprocessing_sha256':hashlib.sha256(Path(__file__).with_name('event_data.py').read_bytes()).hexdigest(),
            'canonical_arrays_sha256':digest.hexdigest(),'canonical_hash_encoding':'named times/nverts/offsets/vertices, little endian int64',
            'events':len(corpus.times),'incidences_before':len(raw['vertices']),'incidences_after':len(corpus.vertices),
            'affected_by_year':dict(sorted(Counter(str(r['year']) for r in changes).items())),
            'events_changed':changes,'cohort_changes':cohorts,
            'checks_passed':['event IDs and timestamps preserved','distinct author set preserved','first appearance unchanged',
                             'exact incidence conservation','index event multiplicities match canonical teams']}


if __name__=='__main__':
    results=[audit(name,years) for name,years in [('coauth-DBLP',[2000,2002,2004,2006,2008]),('coauth-MAG-History',[2004,2006,2008])]]
    (PROJECT/'research/results/temporal-normalization-audit.json').write_text(json.dumps(results,indent=2)+'\n')
    for r in results:print(r['dataset'],r['normalization'],r['cohort_changes'])
