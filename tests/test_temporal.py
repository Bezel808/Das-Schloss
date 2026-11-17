import unittest
from scholartrace import analyze
from scholartrace.temporal import publication_time
def paper(wid, year, people):
    return {'id':wid,'publication_year':year,'authorships':[{'author':{'id':a}} for a in people]}


class TemporalTests(unittest.TestCase):
    def test_sparse_events_not_continuous_interval(self):
        works=[paper('W1',2018,['A','B']),paper('W2',2021,['A','B','C'])]
        e=analyze('A',works)['graph']['edges'][0]
        self.assertEqual(e['active_years'],[2018,2021])
        self.assertFalse(e['continuity_assumed'])
        self.assertEqual(e['yearly_weights'][0]['weight_fractional'],1)
        self.assertEqual(e['yearly_weights'][1]['weight_fractional'],.5)
        self.assertEqual(e['events'][1]['work_id'],'W2')

    def test_source_date_and_year_precision(self):
        d=publication_time({'publication_year':2020,'publication_date':'2020-05-23'})
        self.assertEqual(d['date'],'2020-05-23')
        self.assertEqual(d['precision'],'source_day_unverified')
        d=publication_time({'publication_year':2020})
        self.assertIsNone(d['date'])
        self.assertEqual(d['precision'],'year')
        self.assertEqual((d['interval_start'],d['interval_end']),('2020-01-01','2020-12-31'))

    def test_conflicting_and_invalid_dates_not_silently_used(self):
        for value in ['2019-05-23','2020-02-30','invalid']:
            d=publication_time({'publication_year':2020,'publication_date':value})
            self.assertIsNone(d['date'])
            self.assertEqual(d['source_date'],value)
            self.assertEqual(d['precision'],'year')
        self.assertTrue(publication_time({'publication_year':2020,'publication_date':'2019-05-23'})['date_year_conflict'])

    def test_duplicate_does_not_duplicate_events(self):
        w=paper('W1',2018,['A','B'])
        self.assertEqual(len(analyze('A',[w,w])['graph']['edges'][0]['events']),1)
