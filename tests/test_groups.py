import copy
import unittest
from scholartrace.groups import portrait, people


def work(wid,year,authors,institutions=None):
    return {'id':wid,'publication_year':year,'title':wid,'authorships':[
        {'author':{'id':a,'display_name':a},'institutions':[{'id':i} for i in (institutions or {}).get(a,['I1'])]}
        for a in authors]}


class GroupCohortTests(unittest.TestCase):
    def setUp(self):
        self.works=[work('a0',1990,['A']),work('b0',2000,['B']),work('ab1',2014,['A','B']),
                    work('ab2',2015,['A','B']),work('entry',2018,['A','B','C']),
                    work('bc1',2019,['B','C']),work('bc2',2020,['B','C']),
                    work('dentry',2020,['A','D']),work('e0',2010,['E']),work('eentry',2018,['A','E'])]
        self.corpora={a:[w for w in self.works if a in people(w)] for a in 'ABCDE'}
        self.coverage={a:{'complete':True,'through':2024} for a in self.corpora}

    def result(self,**kwargs):
        return portrait(self.corpora,'A',self.coverage,start=2018,end=2020,early_papers=2,**kwargs)

    def test_non_focal_papers_in_denominator_and_distinct_newcomers(self):
        result=self.result();rows={r['id']:r for r in result['cohorts']}
        self.assertEqual(rows['C']['focal_share'],.5)
        self.assertTrue(rows['C']['persistent_peer_supported'])
        self.assertEqual(rows['C']['persistent_peer_ids'],['B'])
        self.assertEqual(rows['C']['independent_peer_work_ids'],['bc1'])
        self.assertTrue(rows['C']['circle_continuation'])
        self.assertEqual(rows['E']['category'],'experienced')
        self.assertEqual(result['summary']['assessed'],1)
        self.assertEqual(result['summary']['right_censored'],1)

    def test_uncollected_history_is_unknown_not_a_new_student(self):
        self.corpora.pop('C');self.coverage.pop('C')
        result=self.result();row=next(r for r in result['cohorts'] if r['id']=='C')
        self.assertEqual(row['category'],'unknown')
        self.assertIsNone(row['first_observed_publication_year'])
        self.assertEqual(result['summary']['assessed'],0)
        self.assertIsNone(result['summary']['persistent_peer_rate'])

    def test_missing_year_prevents_false_early_career_classification(self):
        self.corpora['C'].append(work('undated',None,['C']))
        row=next(r for r in self.result()['cohorts'] if r['id']=='C')
        self.assertEqual(row['category'],'unknown')

    def test_same_year_is_a_batch_not_an_arbitrary_first_k_order(self):
        extra=work('same-year',2018,['C'])
        self.corpora['C'].append(extra)
        result=portrait(self.corpora,'A',self.coverage,start=2018,end=2020,early_papers=1)
        row=next(r for r in result['cohorts'] if r['id']=='C')
        self.assertEqual(set(row['early_work_ids']),{'entry','same-year'})
        self.assertEqual(row['focal_share'],.5)

    def test_institution_unknown_not_silently_same_and_scope_is_explicit(self):
        w=work('external',2018,['A','X'],{'A':['I1'],'X':[]})
        self.corpora['A'].append(w)
        self.assertNotIn('X',{r['id'] for r in self.result()['members']})
        self.assertIn('X',{r['id'] for r in self.result(scope='all_collaborators')['members']})

    def test_focal_cliques_do_not_prove_independent_collaboration(self):
        for aid in self.corpora:self.corpora[aid]=[w for w in self.corpora[aid] if w['id'] not in {'bc1','bc2'}]
        r=self.result()
        self.assertEqual(r['structure']['edges'],[])
        self.assertEqual(r['structure']['observed_subgroups'],[])

    def test_independent_graph_does_not_backdate_circle_membership(self):
        old=work('before-entry',2017,['B','C'])
        self.corpora['B'].append(old);self.corpora['C'].append(old)
        r=self.result()
        self.assertNotIn('before-entry',r['structure']['independent_work_ids'])
        self.assertEqual(set(r['structure']['independent_work_ids']),{'bc1','bc2'})

    def test_prior_incumbent_and_career_evidence_is_exported(self):
        r=self.result();c=next(x for x in r['cohorts'] if x['id']=='C')
        self.assertEqual(c['incumbent_evidence']['B'],['ab1','ab2'])
        for member in r['members']:
            self.assertTrue(set(member['career_evidence_work_ids'])<=set(r['evidence']))
        self.assertEqual(c['incumbent_evidence'],{'B':['ab1','ab2']})

    def test_future_events_cannot_change_past_entry_or_incumbents(self):
        before=self.result()
        self.corpora['A'].append(work('future',2028,['A','X']))
        after=self.result()
        self.assertEqual(before,after)
        # A member whose qualifying collaborations begin alongside the newcomer
        # cannot become a prior incumbent by appearing twice later.
        for wid,year in [('late1',2018),('late2',2019)]:
            w=work(wid,year,['A','C','X']);self.corpora['A'].append(w);self.corpora['C'].append(w)
        row=next(r for r in self.result()['cohorts'] if r['id']=='C')
        self.assertNotIn('X',row['incumbents'])

    def test_snapshot_year_controls_followup_not_last_publication_year(self):
        self.coverage['C']['through']=2019
        row=next(r for r in self.result()['cohorts'] if r['id']=='C')
        self.assertEqual(row['assessment'],'right_censored')
        self.assertIsNone(row['circle_continuation'])
        self.coverage['C']['through']=None
        self.assertEqual(next(r for r in self.result()['cohorts'] if r['id']=='C')['assessment'],'coverage_date_unknown')

    def test_invalid_parameters_and_incomplete_anchor_are_rejected(self):
        with self.assertRaises(ValueError):self.result(scope='guessed_lab')
        self.coverage['A']['complete']=False
        with self.assertRaises(ValueError):self.result()

    def test_older_evidence_survives_missing_years_and_partial_history(self):
        self.corpora['E'].append(work('undated',None,['E']))
        self.coverage['E']['complete']=False
        r=next(x for x in self.result()['cohorts'] if x['id']=='E')
        self.assertEqual(r['category'],'experienced')
        self.assertEqual(r['classification_basis'],'observed_lower_bound')
        self.assertIn('e0',r['career_evidence_work_ids'])

    def test_identity_mismatch_cannot_be_overridden_by_old_papers(self):
        self.corpora['E'].append(work('wrong',2005,['X']))
        r=next(x for x in self.result()['cohorts'] if x['id']=='E')
        self.assertEqual(r['category'],'unknown')
        self.assertEqual(r['missing_reason'],'author_mismatch')
