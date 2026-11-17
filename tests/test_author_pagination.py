import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from scholartrace import server


class AuthorPaginationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)

    def test_opaque_cursor_and_total_survive_round_trip(self):
        cursor = 'next+/==&?漢'
        result = {'results': [{'id': 'https://openalex.org/A13'}],
                  'meta': {'count': 18543, 'next_cursor': 'third+/='}}
        with patch.object(server, 'upstream', return_value=result) as fetch:
            response = self.client.get('/api/authors', params={'q': '  Chao Huang  ', 'cursor': cursor})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)
        self.assertEqual(fetch.call_args.args[1], {'search': 'Chao Huang', 'per_page': 12, 'cursor': cursor})

    def test_first_page_and_invalid_cursor(self):
        with patch.object(server, 'upstream', return_value={'results': []}) as fetch:
            self.assertEqual(self.client.get('/api/authors?q=Huang').status_code, 200)
            self.assertEqual(fetch.call_args.args[1]['cursor'], '*')
            fetch.reset_mock()
            for cursor in ['', 'x' * 4097]:
                self.assertEqual(self.client.get('/api/authors', params={'q': 'Huang', 'cursor': cursor}).status_code, 422)
            fetch.assert_not_called()

    def test_exact_lookups_have_no_following_page(self):
        for query in ['A123', '0000-0003-2780-0393']:
            for author in [None, {'id': 'https://openalex.org/A123'}]:
                with patch.object(server, 'upstream', return_value=author):
                    data = self.client.get('/api/authors', params={'q': query}).json()
                self.assertEqual(data['results'], [author] if author else [])
                self.assertEqual(data['meta'], {'count': int(bool(author)), 'next_cursor': None})


if __name__ == '__main__':
    unittest.main()
