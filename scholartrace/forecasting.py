"""Personalized random-walk baselines on returned historical papers only.

This is a prediction score, not a CN certificate or a calibrated probability
of a future collaboration. PageRank reference: Page et al., Stanford 1999.
"""
from collections import defaultdict
from itertools import combinations
import math
import numpy as np
from scipy.sparse import csr_matrix

VERSION = 'observed-ppr-1'


def personalized_walk(nodes, weights, focal, alpha=.85, tolerance=1e-10, max_iter=500):
    if not 0 < alpha < 1 or tolerance <= 0 or max_iter < 1:
        raise ValueError('Invalid walk convergence parameters')
    ids=sorted(set(nodes));index={a:i for i,a in enumerate(ids)}
    if focal not in index:raise ValueError('Focal author is absent')
    degree=np.zeros(len(ids));entries=[]
    for (a,b),weight in weights.items():
        if a not in index or b not in index or a==b or not math.isfinite(weight) or weight<0:
            raise ValueError('Invalid undirected weighted edge')
        if not weight:continue
        i,j=index[a],index[b];entries.extend([(i,j,weight),(j,i,weight)])
        degree[i]+=weight;degree[j]+=weight
    rows=[j for i,j,w in entries];columns=[i for i,j,w in entries]
    matrix=csr_matrix(([w/degree[i] for i,j,w in entries],(rows,columns)),shape=(len(ids),len(ids)))
    teleport=np.zeros(len(ids));teleport[index[focal]]=1.
    value=teleport.copy();dangling=degree==0
    for iteration in range(1,max_iter+1):
        updated=alpha*(matrix@value+value[dangling].sum()*teleport)+(1-alpha)*teleport
        delta=float(np.abs(updated-value).sum());value=updated
        # The stochastic PageRank map is an alpha-contraction in L1. This
        # conservative a posteriori bound concerns numerical solution error.
        error_bound=delta/(1-alpha)
        if error_bound<=tolerance:
            return {'scores':dict(zip(ids,value.tolist())),'iterations':iteration,
                    'numerical_l1_error_bound':error_bound}
    raise ValueError('Personalized walk did not converge; no scores published')


def observed_walk(state, weighting='unweighted', half_life=3.):
    if weighting not in {'unweighted','count','recent_fractional'} or half_life<=0:
        raise ValueError('Unknown weighting or invalid half-life')
    weights=defaultdict(float)
    for year,people in state.event_content.values():
        if year>state.cutoff:raise ValueError('Future paper cannot enter prediction')
        if len(people)<2:continue
        for edge in combinations(sorted(people),2):
            if weighting=='unweighted':weights[edge]=1.
            elif weighting=='count':weights[edge]+=1.
            else:weights[edge]+=2**(-(state.cutoff-year)/half_life)/(len(people)-1)
    result=personalized_walk(state.adj,weights,state.focal)
    candidates=state.candidates()
    result['scores']={a:s for a,s in result['scores'].items() if a in candidates}
    result['weighting']=weighting
    return result
