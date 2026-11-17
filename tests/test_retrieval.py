import unittest
from scholartrace.retrieval import retrieve, abstract

class RetrievalTests(unittest.TestCase):
    def test_evidence_and_empty_match(self):
        works=[{'id':'W1','title':'Quantum theory','abstract_inverted_index':{'quantum':[0],'theory':[1]}}, {'id':'W2','title':'Gravity waves'}]
        self.assertEqual(retrieve(works,'quantum')[0]['id'],'W1')
        self.assertEqual(retrieve(works,'biology'),[])
        self.assertEqual(abstract(works[0]),'quantum theory')
        self.assertEqual(retrieve([], 'quantum'),[])
