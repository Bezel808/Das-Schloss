import itertools
import math
import unittest
from scholartrace.evaluation import retrieval


class RankingExpectationTests(unittest.TestCase):
    def test_exact_against_every_permutation_and_labeling(self):
        # Independent enumeration, including a missing positive outside the pool.
        blocks = [[0, 1], [2, 3, 4], [5]]
        scores = {a: 3 - i for i, block in enumerate(blocks) for a in block}
        orders = [sum((list(g) for g in groups), []) for groups in
                  itertools.product(*(itertools.permutations(b) for b in blocks))]
        for flags in itertools.product([False, True], repeat=7):
            gold = {a for a, flag in enumerate(flags) if flag}
            for k in [1, 3, 5, 10]:
                value = retrieval(scores, gold, k)['tie_expected']
                hits = [sum(a in gold for a in order[:k]) for order in orders]
                self.assertAlmostEqual(value['hits_at_10'], sum(hits) / len(hits))
                self.assertEqual(value['minimum_hits_at_10'], min(hits))
                self.assertEqual(value['maximum_hits_at_10'], max(hits))
                if gold:
                    aps = []
                    for order in orders:
                        ranks = [i + 1 for i, a in enumerate(order) if a in gold]
                        aps.append(sum(j / rank for j, rank in enumerate(ranks, 1)) / len(gold))
                    self.assertAlmostEqual(value['average_precision'], sum(aps) / len(aps))
                else:
                    self.assertIsNone(value['average_precision'])

    def test_identifier_permutation_cannot_change_expectation(self):
        a = retrieval({i: 0. for i in range(20)}, {0, 1})
        b = retrieval({i: 0. for i in range(20)}, {18, 19})
        self.assertNotEqual(a['hits_at_10'], b['hits_at_10'])
        self.assertEqual(a['tie_expected'], b['tie_expected'])
        self.assertEqual(a['tie_expected']['hits_at_10'], 1.)

    def test_no_ties_and_empty_candidates(self):
        a = retrieval({0: 2., 1: 1.}, {1, 2})
        for key in ['hits_at_10', 'recall_at_10', 'precision_at_10', 'average_precision']:
            self.assertEqual(a[key], a['tie_expected'][key])
        self.assertEqual(retrieval({}, {1})['tie_expected']['average_precision'], 0.)
        self.assertIsNone(retrieval({}, set())['tie_expected']['average_precision'])

    def test_invalid_scores_and_cutoffs_are_rejected(self):
        for value in [math.nan, math.inf, -math.inf]:
            with self.assertRaises(ValueError): retrieval({0: value}, {0})
        for k in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError): retrieval({}, set(), k)
