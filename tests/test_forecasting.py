import unittest
import networkx as nx
from scholartrace.forecasting import personalized_walk, observed_walk
from scholartrace.acquisition import Observation


class RandomWalkTests(unittest.TestCase):
    def test_matches_independent_networkx_for_weighted_and_dangling_graphs(self):
        for weights in [{(0,1):1.,(1,2):3.,(2,3):.2},{(0,1):2.},{}]:
            graph=nx.Graph();graph.add_nodes_from(range(5))
            for (a,b),w in weights.items():graph.add_edge(a,b,weight=w)
            expected=nx.pagerank(graph,personalization={0:1.},tol=1e-14,max_iter=1000)
            actual=personalized_walk(range(5),weights,0)
            self.assertLessEqual(actual['numerical_l1_error_bound'],1e-10)
            self.assertAlmostEqual(sum(actual['scores'].values()),1.)
            for a in expected:self.assertAlmostEqual(actual['scores'][a],expected[a],places=10)

    def test_only_observed_papers_and_new_partner_candidates_are_used(self):
        state=Observation(0,2000);state.reveal(0,[(1,1990,[0,1])])
        state.reveal(1,[(1,1990,[0,1]),(2,2000,[1,2,3])])
        before=observed_walk(state,'recent_fractional')
        self.assertEqual(set(before['scores']),{2,3})
        self.assertAlmostEqual(before['scores'][2],before['scores'][3])
        state.reveal(2,[(2,2000,[1,2,3])])
        self.assertEqual(before,observed_walk(state,'recent_fractional'))
        state.event_content[3]=(2001,(1,4))
        with self.assertRaises(ValueError):observed_walk(state)

    def test_invalid_or_unconverged_scores_are_not_returned(self):
        with self.assertRaises(ValueError):personalized_walk([0,1],{(0,1):-1.},0)
        with self.assertRaises(ValueError):personalized_walk([0,1],{(0,1):1.},0,max_iter=1)
