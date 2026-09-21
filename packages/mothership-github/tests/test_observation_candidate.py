import io
import json
import unittest
from unittest.mock import patch
from mothership_github.observation import GitHubObservationAdapter
from mothership_github import cli

class Response:
    status=200
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return 'https://api.github.com/repos/owner/repo/pulls/1'
    def getcode(self):return self.status
    def read(self,limit):return json.dumps(self.data).encode()

def payload():
    return dict(number=1,title='Synthetic PR',state='open',draft=False,
                updated_at='2026-09-21T00:00:00Z',head={'sha':'a'*40,'ref':'feature'},
                base={'ref':'main'},merged=False,mergeable=None)

class CandidateObservationTests(unittest.TestCase):
    def test_ambient_credentials_are_never_read(self):
        calls=[]
        def opener(req,**kw): calls.append(req); return Response(payload())
        with patch('os.environ.get',side_effect=AssertionError('ambient read')):
            adapter=GitHubObservationAdapter(opener=opener)
            result=adapter.observe_candidate_pr('owner/repo',1)
        self.assertEqual('a'*40,result['head_sha'])
        self.assertEqual('github_observation',result['source'])
        self.assertFalse(calls[0].has_header('Authorization'))

    def test_explicit_token_and_exact_origin(self):
        calls=[]
        def opener(req,**kw): calls.append(req); return Response(payload())
        adapter=GitHubObservationAdapter(token='synthetic-token',opener=opener)
        adapter.observe_candidate_pr('owner/repo',1)
        self.assertEqual('Bearer synthetic-token',calls[0].get_header('Authorization'))
        for url in ['https://evil.example','https://api.github.com/x','https://api.github.com?x=1']:
            with self.subTest(url=url),self.assertRaises(ValueError):
                GitHubObservationAdapter(base_url=url)

    def test_identity_mismatch_is_rejected(self):
        data=payload();data['number']=2
        with self.assertRaises(ValueError):
            GitHubObservationAdapter(opener=lambda *a,**k:Response(data)).observe_candidate_pr('owner/repo',1)

    def test_companion_cli_forwards_public_observation_commands(self):
        with patch('mothership.cli.main',return_value=0) as main:
            self.assertEqual(0,cli.main(['github-candidate-window','--repo','owner/repo']))
            main.assert_called_once_with(['github-candidate-window','--repo','owner/repo'])

    def test_malformed_base_and_optional_state_fail_closed(self):
        for field, value in [('base', None), ('base', {}), ('base', {'ref': []}),
                             ('merged', 'false'), ('mergeable_state', []), ('head', {'sha': 'a'*40, 'ref': []})]:
            data=payload();data[field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                GitHubObservationAdapter(opener=lambda *a,**k:Response(data)).observe_candidate_pr('owner/repo',1)

    def test_observe_cli_catches_typed_observation_error_without_details(self):
        from orchestration.lib.github_observation import GitHubObservationError
        self.assertTrue(issubclass(GitHubObservationError, ValueError))
        stdout=io.StringIO();stderr=io.StringIO()
        with patch.object(GitHubObservationAdapter,'observe_candidate_pr',side_effect=GitHubObservationError('synthetic-private-error')), patch('sys.stdout',stdout), patch('sys.stderr',stderr):
            self.assertEqual(1,cli.main(['observe-pr','--repo','owner/repo','--pr','1']))
        self.assertEqual('',stdout.getvalue())
        self.assertEqual('observe-pr: unable to obtain observation\n',stderr.getvalue())
