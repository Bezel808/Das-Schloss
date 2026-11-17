import math
import unittest
import networkx as nx
from scholartrace.analytics import annual_panel, role_metrics, brokerage
from scholartrace.ranking import compare_rankings, size_adjusted


def work(wid, year, people, refs=None, field='F'):
    return {'id':wid,'publication_year':year,'referenced_works':refs or [],
            'primary_topic':{'field':{'id':field,'display_name':field}},
            'authorships':[{'author':{'id':a},'institutions':[{'id':i} for i in inst]} for a,inst in people]}


class AnalyticsTests(unittest.TestCase):
    def test_extending_end_does_not_remove_old_doi_duplicate(self):
        old=work('Z',2000,[('a',['X'])]);old['doi']='https://doi.org/same'
        new=work('A',2001,[('a',['X'])]);new['doi']=old['doi']
        a=annual_panel([old,new],'a',2000,2000)
        b=annual_panel([old,new],'a',2000,2001)
        self.assertEqual(a['rows'][0],b['rows'][0])

    def test_partial_orcid_does_not_duplicate_person_year(self):
        first=work('1',2000,[('a',['X'])]);second=work('2',2000,[('a',['X'])])
        first['authorships'][0]['author']['orcid']='https://orcid.org/0000-0002-1825-0097'
        result=compare_rankings([first,second],2000,2000)
        self.assertEqual(result['rows'][0]['annual_author_equivalents'],1)

    def test_returning_collaborator_is_not_first_observed_partner(self):
        works=[work('1',2000,[('a',['X']),('b',['Y'])]),work('2',2005,[('a',['X']),('b',['Y'])])]
        panel=annual_panel(works,'a',2004,2005,window=2)
        self.assertEqual(panel['rows'][-1]['window_added_neighbors'],1)
        self.assertEqual(panel['rows'][-1]['first_observed_partners'],0)

    def test_sparse_brokerage_matches_independent_networkx_implementation(self):
        for seed in range(10):
            g=nx.gnp_random_graph(15,.3,seed=seed)
            for a,b in g.edges:g[a][b]['weight']=(a+b)%7+1
            for a in g:
                if g.degree(a):
                    c,e=brokerage(g,a)
                    self.assertAlmostEqual(c,nx.constraint(g,nodes=[a],weight='weight')[a])
                    self.assertAlmostEqual(e,nx.effective_size(g,nodes=[a],weight='weight')[a])

    def test_fractional_mass_and_person_year_conservation(self):
        works=[work('1',2000,[('a',['X','Y']),('b',['X']),('c',[])]),
               work('2',2000,[('a',['X'])])]
        r=compare_rankings(works,2000,2001)
        rows={x['id']:x for x in r['rows']}
        self.assertAlmostEqual(rows['X']['fractional_papers'],1.5)
        self.assertAlmostEqual(rows['Y']['fractional_papers'],1/6)
        self.assertAlmostEqual(sum(x['annual_author_equivalents'] for x in r['rows']),1.)
        self.assertAlmostEqual(rows['X']['annual_author_equivalents'],.875)
        self.assertAlmostEqual(sum(x['excess'] for x in r['rows']),0)
        self.assertEqual(rows['X']['full_papers'],2)

    def test_geometric_mean_includes_selected_zero_area(self):
        works=[work('1',2000,[('a',['X'])],field='F'),work('2',2000,[('b',['Y'])],field='G')]
        r=compare_rankings(works,2000,2000)
        self.assertAlmostEqual(r['rows'][0]['area_geometric_mean'],math.sqrt(2))
        self.assertEqual({x['area_geometric_mean_rank'] for x in r['rows']},{1})

    def test_power_law_matches_constructed_mean_and_handles_no_finite_fit(self):
        r=size_adjusted([2,8,18],[1,2,3])
        self.assertAlmostEqual(r['beta'],2)
        for actual,expected in zip(r['expected'],[2,8,18]):self.assertAlmostEqual(actual,expected)
        self.assertEqual(size_adjusted([1,1],[1,1])['status'],'equal_sizes_beta_unidentified')
        self.assertEqual(size_adjusted([0,1],[1,2])['status'],'no_finite_mle')

    def test_cutoff_and_citation_clock_do_not_use_future(self):
        works=[work('1',2000,[('a',['X']),('b',['Y'])]),
               work('2',2002,[('b',['Y'])],refs=['1'])]
        future=work('0',2030,[('a',['X'])],refs=['1'])
        old=annual_panel(works,'a',2000,2002,window=2)
        self.assertEqual(old,annual_panel(works+[future],'a',2000,2002,window=2))
        self.assertEqual(old['rows'][0]['citations_within_corpus'],0)
        self.assertEqual(old['rows'][-1]['citations_within_corpus'],1)
        self.assertEqual(old['rows'][-1]['h_index_within_corpus'],1)
        self.assertIsNone(old['rows'][-1]['degree'])

    def test_star_brokerage_and_undefined_normalization(self):
        g=nx.star_graph(3); nx.set_edge_attributes(g,1.,'weight')
        row=role_metrics(g,0)
        self.assertAlmostEqual(row['constraint'],1/3)
        self.assertAlmostEqual(row['effective_size'],3)
        self.assertEqual(row['core'],1)
        g=nx.Graph();g.add_node('alone')
        row=role_metrics(g,'alone')
        self.assertIsNone(row['within_module_z'])
        self.assertIsNone(row['participation'])
        self.assertIsNone(row['constraint'])
