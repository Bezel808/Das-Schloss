"""Ranking metrics with exact expectation over uniformly permuted score ties.

Reference: McSherry & Najork, ECIR 2008, https://marc.najork.org/papers/ecir2008.pdf
Unretrieved positives remain in the denominator. No negatives are sampled here.
"""
from itertools import groupby
import math

VERSION = 'tie-expectation-1'


def ranked(scores):
    return sorted(scores, key=lambda a: (-scores[a], a))


def retrieval(scores, gold, k=10):
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError('k must be a positive integer')
    if any(not math.isfinite(v) for v in scores.values()):
        raise ValueError('Ranking scores must be finite')
    positives = set(gold)
    order = ranked(scores)
    hits = len(set(order[:k]) & positives)
    ranks = [i + 1 for i, a in enumerate(order) if a in positives]
    ap = sum(j / r for j, r in enumerate(ranks, 1)) / len(positives) if positives else None
    before = relevant_before = 0
    expected_hits = ap_sum = 0.
    minimum_hits = maximum_hits = 0
    boundary_tied = False
    for _, group in groupby(order, key=lambda a: scores[a]):
        block = list(group)
        m = len(block)
        r = sum(a in positives for a in block)
        take = min(m, max(0, k - before))
        expected_hits += take * r / m
        minimum_hits += max(0, take - (m - r))
        maximum_hits += min(take, r)
        boundary_tied |= 0 < take < m
        # E[I_j (relevant_before + 1 + sum_{i<j} I_i)] / rank_j.
        # For distinct positions in a uniform permutation:
        # E[I_j]=r/m and E[I_i I_j]=r(r-1)/(m(m-1)).
        if r:
            pair = r * (r - 1) / (m * (m - 1)) if m > 1 else 0.
            ap_sum += math.fsum(((relevant_before + 1) * r / m + (j - 1) * pair)
                                / (before + j) for j in range(1, m + 1))
        before += m
        relevant_before += r
    return {
        'k': k, 'hits_at_10': hits, 'recall_at_10': hits / len(positives) if positives else None,
        'precision_at_10': hits / k, 'average_precision': ap,
        'candidate_positives': relevant_before, 'candidates': len(scores),
        'top10': order[:k], 'distinct_scores': len(set(scores.values())),
        'tie_expected': {
            'hits_at_10': expected_hits,
            'recall_at_10': expected_hits / len(positives) if positives else None,
            'precision_at_10': expected_hits / k,
            'average_precision': ap_sum / len(positives) if positives else None,
            'minimum_hits_at_10': minimum_hits, 'maximum_hits_at_10': maximum_hits,
            'cutoff_splits_tie': boundary_tied,
        },
    }
