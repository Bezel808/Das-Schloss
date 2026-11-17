import itertools
import math
import random
import unittest

from scholartrace.tpfg import local_evidence, rank, solve_states
from scholartrace.inference import author_profile, infer


def work(i, year, authors):
    return {'id': str(i), 'publication_year': year,
            'authorships': [{'author': {'id': a}} for a in authors]}


class TemporalFactorTests(unittest.TestCase):
    def test_cutoff_excludes_future_publications_from_entire_inference(self):
        history = [work('a', 1990, ['A']), work('ab', 2000, ['A', 'B']), work('ab2', 2002, ['A', 'B'])]
        future = [work('new', 2030, ['A', 'B', 'C'])]
        old = infer({a: history for a in ['A', 'B']}, cutoff=2002)
        current = infer({a: history + future for a in ['A', 'B']}, cutoff=2002)
        self.assertEqual(old, current)
        self.assertNotIn('new', str(current))

    def test_exact_max_marginals_against_exhaustive_enumeration(self):
        rng = random.Random(318)
        # Independent reference: enumerate all joint assignments, including
        # conflicting chains and multiply connected DAGs, with varied potentials.
        for _ in range(25):
            states = {}
            for i in range(5):
                person = str(i)
                states[person] = [{'advisor': None, 'start': -math.inf, 'end': -math.inf, 'potential': .5}]
                for j in range(i):
                    if rng.random() < .6:
                        start = rng.randint(1990, 2010)
                        states[person].append({'advisor': str(j), 'start': start,
                                               'end': start + rng.randint(1, 8), 'potential': rng.uniform(.05, .95)})
            expected = {(p, j): -math.inf for p in states for j in range(len(states[p]))}
            people = list(states)
            for choices in itertools.product(*(range(len(states[p])) for p in people)):
                selected = {p: states[p][j] for p, j in zip(people, choices)}
                if any(s['advisor'] is not None and selected[s['advisor']]['advisor'] is not None and
                       selected[s['advisor']]['end'] >= s['start'] for s in selected.values()):
                    continue
                score = sum(math.log(s['potential']) for s in selected.values())
                for p, j in zip(people, choices):
                    expected[p, j] = max(expected[p, j], score)
            actual, diagnostics = solve_states(states)
            self.assertTrue(all(d['status'] == 'optimal' for d in diagnostics))
            # Independent components have additive constants; compare contrasts.
            for p in people:
                for j, value in enumerate(actual[p]['log_max_marginals']):
                    self.assertAlmostEqual(value - actual[p]['log_max_marginals'][0],
                                           expected[p, j] - expected[p, 0], places=7)
                self.assertAlmostEqual(sum(actual[p]['scores']), 1)

    def test_budget_exhaustion_does_not_return_fabricated_scores(self):
        result, _ = solve_states({'a': [{'advisor': None, 'potential': .5}]}, seconds=0)
        self.assertEqual(result['a']['status'], 'solver_incomplete')
        self.assertIsNone(result['a']['scores'])

    def test_observed_years_not_invented_dates_and_r3(self):
        s = author_profile('S', [work('s0', 1990, ['S']), work('j0', 2000, ['J', 'S'])])
        j = author_profile('J', [work('j0', 2000, ['J', 'S'])])
        e = local_evidence(j, s)
        self.assertFalse(e['eligible'])
        self.assertIn('single_joint_publication_year', e['exclusion_reasons'])
        self.assertAlmostEqual(e['annual_evidence'][0]['kulczynski'], .75)
        self.assertAlmostEqual(e['annual_evidence'][0]['imbalance'], .5)

    def test_equal_career_start_is_not_ordered_by_id(self):
        works = [work('a', 2000, ['A', 'B']), work('b', 2002, ['A', 'B'])]
        evidence, model = rank({a: author_profile(a, works) for a in ['A', 'B']})
        self.assertEqual(evidence, {})
        self.assertEqual(model['status'], 'optimal')

    def test_year2_interval_contains_two_observed_joint_years(self):
        shared = [work('j0', 2000, ['A', 'B']), work('j1', 2010, ['A', 'B'])]
        a = author_profile('A', [work('a0', 1990, ['A'])] + shared)
        b = author_profile('B', shared + [work(str(y), y, ['B']) for y in range(2001, 2015)])
        evidence = local_evidence(b, a)
        self.assertGreaterEqual(evidence['end'], 2010)

    def test_temporal_chain_cannot_be_selected_simultaneously(self):
        null = {'advisor': None, 'start': -math.inf, 'end': -math.inf, 'potential': .2}
        states = {'A': [null], 'B': [null, {'advisor': 'A', 'start': 2000, 'end': 2010, 'potential': .9}],
                  'C': [null, {'advisor': 'B', 'start': 2005, 'end': 2015, 'potential': .8}]}
        result, _ = solve_states(states)
        self.assertEqual(result['B']['map_state'], 1)
        self.assertEqual(result['C']['map_state'], 0)


if __name__ == '__main__':
    unittest.main()
