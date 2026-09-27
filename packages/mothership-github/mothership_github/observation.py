"""Read-only observation compatibility adapter; credentials are explicit inputs."""
from __future__ import annotations

from urllib.request import Request
from . import public_observation as public

class GitHubObservationAdapter:
    """Observe one PR through the companion's validated, no-redirect fetch path.

    No environment credentials are read. An injected opener is a trusted I/O
    dependency, primarily for offline tests; the default rejects redirects.
    """
    def __init__(self, token: str | None = None,
                 base_url: str = "https://api.github.com", timeout: float = 10.0,
                 user_agent: str = "mothership-github-observer/1.0", *, opener=None):
        if base_url not in {"https://api.github.com", "https://api.github.com/"}:
            raise ValueError("base_url must be the exact GitHub API origin")
        if token is not None and (type(token) is not str or '\r' in token or '\n' in token):
            raise ValueError("token must be a single-line string")
        self._token = token or ""
        self._base_url = base_url.rstrip('/')
        self._timeout = timeout
        self._user_agent = user_agent
        self._opener = opener or public._default_open

    def fetch_pull_request(self, repository: str, pull_request: int) -> dict:
        if type(pull_request) is not int or pull_request < 1:
            raise ValueError("pull_request must be a positive integer")
        if type(repository) is not str:
            raise ValueError("repository must be owner/repo text")
        repo = public.parse_github_repository("https://github.com/" + repository)
        ref = public.parse_github_ref(f"{repo.source_url}/pull/{pull_request}")
        request = Request(ref.api_url, method="GET", headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": self._user_agent,
        })
        if self._token:
            request.add_header("Authorization", f"Bearer {self._token}")
        def open_once(req, *, timeout):
            return self._opener(req, timeout=self._timeout)
        data = public._fetch_json(request, opener=open_once)
        public._parse_observation(ref, data)
        base = data.get('base')
        if type(base) is not dict:
            raise public.GitHubObservationError('invalid PR base')
        public._safe_text(base.get('ref'), 'base.ref')
        if data.get('mergeable_state') is not None:
            public._safe_text(data['mergeable_state'], 'mergeable_state')
        for key in ('merged', 'mergeable'):
            if data.get(key) is not None and type(data[key]) is not bool:
                raise public.GitHubObservationError("invalid optional PR state")
        head_ref = data['head'].get('ref')
        if head_ref is not None:
            public._safe_text(head_ref, 'head.ref')
        return data

    def fetch_commit(self, repository: str, sha: str) -> dict:
        """Fetch one exact public commit object without following redirects.

        The requested repository and commit identifier are validated before a
        request is constructed.  The returned object is intentionally left to
        the caller for semantic projection because GitHub's commit response
        contains more fields than the bounded read-back evidence retains.
        """
        if type(repository) is not str:
            raise ValueError("repository must be owner/repo text")
        repo = public.parse_github_repository("https://github.com/" + repository)
        if type(sha) is not str or public._SHA.fullmatch(sha) is None or sha != sha.lower():
            raise ValueError("sha must be a lowercase 40-hex commit identifier")
        request = Request(
            f"{self._base_url}/repos/{repo.owner}/{repo.repo}/git/commits/{sha}",
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": self._user_agent,
            },
        )
        if self._token:
            request.add_header("Authorization", f"Bearer {self._token}")

        def open_once(req, *, timeout):
            return self._opener(req, timeout=self._timeout)

        data = public._fetch_json(request, opener=open_once)
        if type(data) is not dict:
            raise public.GitHubObservationError("invalid commit response")
        return data

    def observe_candidate_pr(self, repository: str, pull_request: int) -> dict:
        data = self.fetch_pull_request(repository, pull_request)
        return {
            "source": "github_observation", "repository": repository,
            "pull_request": pull_request, "title": data['title'],
            "state": data['state'], "merged": data.get('merged'),
            "head_sha": data['head']['sha'], "head_ref": data['head'].get('ref'),
            "base_ref": data['base']['ref'], "mergeable": data.get('mergeable'),
            "mergeable_state": data.get('mergeable_state'), "draft": data['draft'],
        }
