import itertools
import copy
import random
import unittest
from scholartrace.acquisition import Observation

class AcquisitionTests(unittest.TestCase):
    def test_rejected_query_cannot_create_a_phantom_candidate(self):
        state=Observation(1,2000);state.reveal(1,[(10,1990,[1,2])])
        before=copy.deepcopy(state.__dict__)
        with self.assertRaises(ValueError):state.reveal(99,[(11,1990,[1,99])])
        self.assertEqual(state.__dict__,before)
        self.assertNotIn(99,state.candidates())

    def test_conflicting_event_content_is_rejected_without_completing_author(self):
        s=Observation(0,2000);s.reveal(0,[(10,1990,[0,1])])
        with self.assertRaises(ValueError):s.reveal(1,[(10,1995,[0,1,2])])
        self.assertNotIn(1,s.complete)
        self.assertNotIn(2,s.adj)
        with self.assertRaises(ValueError):s.reveal(1,[(10,1990,[0,1]),(10,1990,[0,1,2])])

    def test_future_response_is_rejected_atomically(self):
        s=Observation(0,2000)
        with self.assertRaises(ValueError):s.reveal(0,[(1,1999,[0,1]),(2,2001,[0,2])])
        self.assertFalse(s.papers)
        self.assertFalse(s.complete)

    def test_known_incident_paper_cannot_disappear_even_if_neighbor_stays(self):
        s=Observation(0,2000);s.reveal(0,[(10,1990,[0,1]),(11,1991,[0,1])])
        with self.assertRaises(ValueError):s.reveal(1,[(10,1990,[0,1])])
        self.assertNotIn(1,s.complete)

    def test_bounds_exhaustively_cover_all_missing_graph_completions(self):
        # Focal row and one neighbor row are known; all other non-observed
        # edges among unqueried vertices can independently exist or not.
        s=Observation(0,2000)
        s.reveal(0,[(0,2000,[0,1]),(1,2000,[0,2]),(2,2000,[0,3])])
        s.reveal(1,[(0,2000,[0,1]),(3,2000,[1,4]),(4,2000,[1,5])])
        bounds,_=s.bounds()
        unknown=[(a,b) for a,b in itertools.combinations(range(6),2)
                 if a not in s.complete and b not in s.complete and b not in s.adj[a]]
        values={v:[] for v in bounds}
        for flags in itertools.product([False,True],repeat=len(unknown)):
            adj={a:set(s.adj[a]) for a in range(6)}
            for (a,b),flag in zip(unknown,flags):
                if flag:adj[a].add(b);adj[b].add(a)
            for v in bounds:values[v].append(len(adj[0]&adj[v]))
        for v,(lo,hi) in bounds.items():
            self.assertEqual((lo,hi),(min(values[v]),max(values[v])))
        s.reveal(4,[(3,2000,[1,4]),(5,2000,[2,4])])
        self.assertEqual(s.bounds()[0][4],(2,2))

    def test_certificate_requires_strict_gap_and_accounts_for_unseen(self):
        s=Observation(0,2000)
        s.reveal(0,[(0,2000,[0,1]),(1,2000,[0,2])])
        s.reveal(1,[(0,2000,[0,1]),(2,2000,[1,3])])
        self.assertFalse(s.certificate(1)['certified'])
        s.reveal(2,[(1,2000,[0,2]),(3,2000,[2,3])])
        self.assertTrue(s.certificate(1)['certified'])
        self.assertEqual(s.certificate(1)['members'],[3])

    def test_query_policies_only_select_discovered_unqueried_authors(self):
        s=Observation(0,2000);s.reveal(0,[(0,2000,[0,1,2])])
        for policy in ['random','observed_degree','uncertainty','uniform_cover','ambiguity_cover']:
            self.assertIn(s.next_query(policy,random.Random(1)),{1,2})
