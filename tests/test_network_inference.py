import unittest
import numpy as np
from scholartrace import analyze
from scholartrace.network import decorate_graph
from scholartrace.inference import infer, author_profile, pair_features
from scholartrace.learning import train, predict


def paper(wid, year, people):
    return {'id':wid,'publication_year':year,'authorships':[{'author':{'id':a,'display_name':a},'author_position':'first' if i==0 else 'last','institutions':[]} for i,a in enumerate(people)]}


class GraphTests(unittest.TestCase):
    def test_community_split_and_evidence(self):
        works=[paper('W1',2020,['F','A','B']),paper('W2',2021,['F','C','D'])]
        graph=decorate_graph(analyze('F',works)['graph'],works,'F')
        nodes={n['id']:n for n in graph['nodes']}
        self.assertEqual(nodes['A']['community'],nodes['B']['community'])
        self.assertNotEqual(nodes['A']['community'],nodes['C']['community'])
        self.assertEqual(nodes['F']['community'],-1)
        self.assertEqual(nodes['A']['work_ids'],['W1'])
        self.assertEqual(graph,decorate_graph(analyze('F',works)['graph'],works,'F'))

    def test_isolated_collaborators(self):
        works=[paper('W1',2020,['F','A']),paper('W2',2020,['F','B'])]
        graph=decorate_graph(analyze('F',works)['graph'],works,'F')
        self.assertIsNone(graph['modularity'])
        self.assertEqual(len(graph['communities']),2)


class InferenceTests(unittest.TestCase):
    def test_own_career_not_first_focal_coauthorship(self):
        s=author_profile('S',[paper('W0',1990,['S']),paper('W1',2010,['J','S'])])
        j=author_profile('J',[paper('W2',2000,['J']),paper('W1',2010,['J','S'])])
        features=pair_features(s,j)['features']
        self.assertEqual(features['entry_delay'],10)
        self.assertEqual(features['early_dependency'],0)
        result=infer({'S':s['works'],'J':j['works']})
        self.assertEqual(result['relationships'][0]['prediction'],'unresolved')
        self.assertEqual(result['model']['status'],'optimal')

    def test_same_year_early_papers_not_arbitrarily_cut(self):
        p=author_profile('J',[paper('W'+str(i),2000,['J','S']) for i in range(8)])
        self.assertEqual(len(p['early']),8)
        result = infer({'J': p['works']})
        self.assertFalse(result['capabilities']['degree_prediction'])
        self.assertNotIn('career_transitions', result)

    def test_training_json_predict_and_range_abstention(self):
        # Synthetic data checks mechanics only, never real-world model quality.
        rows=[{'features':{'x':float(i%2),'y':float(i%7)},'label':'yes' if i%2 else 'no',
               'people':['synthetic-'+str(i)],'source':'synthetic test only','cutoff':2020} for i in range(80)]
        model=train(rows,['x','y'],'test')
        result=predict(model,{'x':1,'y':3})
        self.assertEqual(result['label'],'yes')
        self.assertAlmostEqual(sum(result['probabilities'].values()),1)
        self.assertEqual(predict(model,{'x':100,'y':3})['status'],'out_of_training_range')
        self.assertEqual(model['metrics']['n_train']+model['metrics']['n_validation']+model['metrics']['n_test'],80)

    def test_refuses_leaky_single_component_training(self):
        rows=[{'features':{'x':i},'label':str(i%2),'people':['same-person',str(i)],'source':'test','cutoff':2020} for i in range(40)]
        with self.assertRaisesRegex(ValueError,'disconnected'):train(rows,['x'],'test')
