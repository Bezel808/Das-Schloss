import unittest
from unittest.mock import patch
from fastapi import HTTPException
from scholartrace.identifiers import orcid_id
from scholartrace.server import authors, upstream
import httpx

class OrcidTests(unittest.TestCase):
    def test_variants(self):
        for value in ['0000-0003-2780-0393', 'https://orcid.org/0000-0003-2780-0393/', 'http://orcid.org/0000-0003-2780-0393', 'ORCID: 0000-0003-2780-0393','0000000327800393']:
            self.assertEqual(orcid_id(value),'0000-0003-2780-0393')
        self.assertEqual(orcid_id('0000-0002-9079-593x'),'0000-0002-9079-593X')
        self.assertIsNone(orcid_id('Albert Einstein'))
        self.assertIsNone(orcid_id('A5109805546'))

    def test_invalid(self):
        for value in ['0000-0003-2780-0394','https://orcid.org/nonsense','0000-1234']:
            with self.assertRaises(ValueError):orcid_id(value)
        with patch('scholartrace.server.upstream') as fetch:
            with self.assertRaises(HTTPException) as error:authors('0000-0003-2780-0394')
            self.assertEqual(error.exception.status_code,422)
            fetch.assert_not_called()

    def test_matching_and_missing(self):
        with patch('scholartrace.server.upstream',return_value={'id':'https://openalex.org/A1'}) as fetch:
            self.assertEqual(authors('0000-0003-2780-0393')['results'][0]['id'],'https://openalex.org/A1')
            self.assertEqual(fetch.call_args.args[0],'authors/orcid:0000-0003-2780-0393')
        with patch('scholartrace.server.upstream',return_value=None):
            self.assertEqual(authors('0000-0003-2780-0393')['results'],[])
        with patch('scholartrace.server.SOURCE_CLIENT.get',return_value=httpx.Response(404)):
            self.assertIsNone(upstream('authors/orcid:0000-0003-2780-0393'))
