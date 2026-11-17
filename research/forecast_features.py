"""Reconstruct past-only features from saved acquisition traces for ML evaluation."""
from collections import Counter,defaultdict
import math
from pathlib import Path
import numpy as np

FEATURES=['log_focal_papers_3y','log_candidate_papers_3y','log_candidate_observed_age',
          'log_focal_degree','log_candidate_degree','log_common_neighbors','adamic_adar',
          'resource_allocation','candidate_complete','focal_neighbors_queried_fraction','cn_interval_width']
ACTIVITY=[0,1,2]
NETWORK=list(range(8))
COVERAGE=list(range(len(FEATURES)))


def features(state,corpus):
    # Rebuild from returned event IDs, never from a candidate's unqueried history.
    recent=Counter();first={}
    for e in state.papers:
        year=int(corpus.times[e])
        if year>state.cutoff:raise AssertionError('Future event entered features')
        for a in corpus.vertices[corpus.offsets[e]:corpus.offsets[e+1]]:
            a=int(a);first[a]=min(year,first.get(a,year))
            if year>=state.cutoff-2:recent[a]+=1
    scores=state.scores();bounds,_=state.bounds();neighbors=state.neighbors
    fraction=len(neighbors&state.complete)/len(neighbors) if neighbors else 0.
    ids=sorted(scores);rows=[]
    for v in ids:
        r=scores[v]
        rows.append([math.log1p(recent[state.focal]),math.log1p(recent[v]),math.log1p(state.cutoff-first[v]),
                     math.log1p(len(neighbors)),math.log1p(len(state.adj[v])),math.log1p(r['common_neighbors']),
                     r['adamic_adar'],r['resource_allocation'],float(v in state.complete),fraction,
                     float(bounds[v][1]-bounds[v][0])])
    return ids,np.asarray(rows,dtype=float).reshape(-1,len(FEATURES))
