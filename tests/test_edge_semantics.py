import unittest
from scholartrace import analyze
from scholartrace.network import decorate_graph


def work(wid,year,institutions):
 return {'id':wid,'publication_year':year,'title':wid,'authorships':[
  {'author':{'id':a,'display_name':a},'institutions':[{'id':i} for i in ids]}
  for a,ids in institutions.items()]}

class EdgeSemanticsTests(unittest.TestCase):
 def test_types_and_per_paper_institutions_are_not_current_affiliations(self):
  works=[work('W1',2020,{'F':['I1'],'A':['I1'],'B':['I2']}),
         work('W2',2021,{'F':['I1'],'A':['I2'],'B':[]}),
         work('W3',2022,{'F':[],'A':['I2']})]
  graph=decorate_graph(analyze('F',works)['graph'],works,'F')
  edges={frozenset([e['source'],e['target']]):e for e in graph['edges']}
  fa=edges[frozenset(['F','A'])]['semantics']
  self.assertEqual(fa['kind'],'focal_coauthor')
  self.assertEqual(fa['institution_work_ids'],{'shared':['W1'],'disjoint':['W2'],'unknown':['W3']})
  self.assertFalse(fa['directed']);self.assertIsNone(fa['relation_inference'])
  ab=edges[frozenset(['A','B'])]['semantics']
  self.assertEqual(ab['kind'],'coauthors_on_focal_papers')
  self.assertEqual(ab['institution_work_ids']['unknown'],['W2'])
  historical=decorate_graph(analyze('F',works[:1])['graph'],works[:1],'F')
  fa=next(e for e in historical['edges'] if set([e['source'],e['target']])=={'F','A'})
  self.assertEqual(fa['semantics']['institution_work_ids'],{'shared':['W1'],'disjoint':[],'unknown':[]})
