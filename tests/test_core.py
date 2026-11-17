import json
import unittest
from pathlib import Path
from scholartrace import analyze


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.works = json.loads((Path(__file__).parents[1] / 'examples/synthetic.json').read_text())
        self.focal = 'https://openalex.org/A1'

    def test_fractional_projection_and_evidence(self):
        report = analyze(self.focal, self.works)
        edges = {(e['source'].split('/')[-1], e['target'].split('/')[-1]): e for e in report['graph']['edges']}
        self.assertEqual(edges['A1', 'A2']['weight_raw'], 2)
        self.assertEqual(edges['A1', 'A2']['weight_fractional'], 1.5)
        self.assertEqual(edges['A2', 'A3']['work_ids'], ['https://openalex.org/W1'])
        self.assertEqual([r['work_count'] for r in report['timeline']], [1, 1, 1])
        self.assertEqual(report['timeline'][2]['roles']['first'], ['https://openalex.org/W3'])

    def test_duplicate_work_does_not_double_count(self):
        self.assertEqual(analyze(self.focal, self.works), analyze(self.focal, self.works + self.works))

    def test_excludes_external_papers(self):
        report = analyze('https://openalex.org/A3', self.works)
        self.assertEqual(len(report['timeline']), 1)
        self.assertEqual(report['excluded']['not_focal'], 2)

    def test_rejects_truncated_authorships(self):
        self.works[0]['authors_count'] = 101
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            analyze(self.focal, self.works)

    def test_rejects_unknown_year(self):
        self.works[0]['publication_year'] = None
        with self.assertRaisesRegex(ValueError, 'year'):
            analyze(self.focal, self.works)

    def test_single_author_no_edges(self):
        self.assertEqual(analyze(self.focal, self.works[2:])['graph']['edges'], [])


if __name__ == '__main__':
    unittest.main()
