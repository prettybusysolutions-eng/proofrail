"""The GitHub Git Data calls the dispatcher makes, served by a real local git repository.

This lets an operator run the unmodified `enforcing_dispatcher.Dispatcher` without
GitHub credentials. Objects, commits and ref updates are real git operations on a
disposable bare repository. It is NOT GitHub: it does not exercise GitHub's
transport, authentication, token scope, rate limits or branch protection, and it
is not evidence for the HTTPS client in `enforcing_dispatcher.GitHubAPI`.
"""
import base64
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

GIT_ENV = {
    'PATH': '/usr/local/bin:/usr/bin:/bin',
    'LANG': 'C', 'LC_ALL': 'C',
    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
    'GIT_TERMINAL_PROMPT': '0',
    'GIT_AUTHOR_NAME': 'ProofRail dispatcher', 'GIT_AUTHOR_EMAIL': 'dispatcher@pilot.invalid',
    'GIT_COMMITTER_NAME': 'ProofRail dispatcher', 'GIT_COMMITTER_EMAIL': 'dispatcher@pilot.invalid',
}


def git(git_dir, *args, input=None, env=None):
    result = subprocess.run(['git', '--git-dir', str(git_dir), *args], input=input,
                            capture_output=True, env={**GIT_ENV, **(env or {})}, check=False)
    if result.returncode != 0:
        raise RuntimeError('git_failed: ' + ' '.join(args[:2]))
    return result.stdout


def create_repository(git_dir, branch, files, message='Initial content'):
    """Create a disposable bare repository whose `branch` holds `files` (path -> text)."""
    git_dir = Path(git_dir)
    subprocess.run(['git', 'init', '--quiet', '--bare', str(git_dir)], check=True,
                   env=GIT_ENV, capture_output=True)
    index = git_dir / 'demo-index'
    env = {'GIT_INDEX_FILE': str(index)}
    for path, text in sorted(files.items()):
        blob = git(git_dir, 'hash-object', '-w', '--stdin', input=text.encode()).decode().strip()
        git(git_dir, 'update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + path, env=env)
    tree = git(git_dir, 'write-tree', env=env).decode().strip()
    index.unlink()
    commit = git(git_dir, 'commit-tree', tree, '-m', message).decode().strip()
    git(git_dir, 'update-ref', 'refs/heads/' + branch, commit, '0' * 40)
    return commit, tree


def commit_file(git_dir, branch, path, text, message):
    """An out-of-band change by someone other than the dispatcher (for detection demos)."""
    head = git(git_dir, 'rev-parse', 'refs/heads/' + branch).decode().strip()
    index = Path(git_dir) / 'demo-index'
    env = {'GIT_INDEX_FILE': str(index)}
    git(git_dir, 'read-tree', head, env=env)
    blob = git(git_dir, 'hash-object', '-w', '--stdin', input=text.encode()).decode().strip()
    git(git_dir, 'update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + path, env=env)
    tree = git(git_dir, 'write-tree', env=env).decode().strip()
    index.unlink()
    commit = git(git_dir, 'commit-tree', tree, '-p', head, '-m', message).decode().strip()
    git(git_dir, 'update-ref', 'refs/heads/' + branch, commit, head)
    return commit


class LocalGitProvider:
    """Answers exactly the requests `Dispatcher` issues; anything else is refused.

    `calls` records method and path (never bodies) so the evidence can show how
    many write calls each step made.
    """
    WRITES = ('POST', 'PATCH', 'PUT', 'DELETE')

    def __init__(self, git_dir, repository):
        self.git_dir, self.repository = Path(git_dir), repository
        self.prefix = '/repos/' + repository
        self.calls = []

    def writes(self, since=0):
        return [c for c in self.calls[since:] if c[0] in self.WRITES]

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        if not path.startswith(self.prefix + '/'):
            raise RuntimeError('provider_rejected: other repository')
        parts = urlsplit(path[len(self.prefix):])
        route, query = unquote(parts.path), parts.query
        if method == 'GET' and route.startswith('/git/ref/heads/'):
            ref = 'refs/heads/' + route[len('/git/ref/heads/'):]
            return {'ref': ref, 'object': {'sha': self._rev(ref)}}
        if method == 'GET' and route.startswith('/git/commits/'):
            return self._commit(route.rsplit('/', 1)[1])
        if method == 'GET' and route.startswith('/contents/'):
            ref = dict(p.split('=', 1) for p in query.split('&') if '=' in p).get('ref')
            data = git(self.git_dir, 'cat-file', 'blob', ref + ':' + route[len('/contents/'):])
            return {'encoding': 'base64', 'content': base64.encodebytes(data).decode()}
        if method == 'POST' and route == '/git/trees':
            return {'sha': self._tree(body)}
        if method == 'POST' and route == '/git/commits':
            args = ['commit-tree', body['tree'], '-m', body['message']]
            for parent in body['parents']:
                args += ['-p', parent]
            return {'sha': git(self.git_dir, *args).decode().strip()}
        if method == 'PATCH' and route.startswith('/git/refs/heads/'):
            ref = 'refs/heads/' + route[len('/git/refs/heads/'):]
            old = self._rev(ref)
            if not body.get('force'):
                ff = subprocess.run(['git', '--git-dir', str(self.git_dir), 'merge-base',
                                     '--is-ancestor', old, body['sha']], env=GIT_ENV,
                                    capture_output=True).returncode == 0
                if not ff:
                    raise RuntimeError('provider_rejected: not a fast forward')
            # Compare-and-swap against the value just read (stricter than GitHub REST).
            git(self.git_dir, 'update-ref', ref, body['sha'], old)
            return {'ref': ref, 'object': {'sha': body['sha']}}
        raise RuntimeError('provider_rejected: unsupported request')

    def _rev(self, ref):
        return git(self.git_dir, 'rev-parse', '--verify', ref).decode().strip()

    def _commit(self, sha):
        raw = git(self.git_dir, 'cat-file', 'commit', sha).decode()
        header = raw.split('\n\n', 1)[0].splitlines()
        tree = next(line.split()[1] for line in header if line.startswith('tree '))
        parents = [line.split()[1] for line in header if line.startswith('parent ')]
        return {'sha': sha, 'tree': {'sha': tree}, 'parents': [{'sha': p} for p in parents]}

    def _tree(self, body):
        index = self.git_dir / ('provider-index-' + str(os.getpid()))
        env = {'GIT_INDEX_FILE': str(index)}
        try:
            git(self.git_dir, 'read-tree', body['base_tree'], env=env)
            for entry in body['tree']:
                if entry.get('type') != 'blob' or entry.get('mode') != '100644':
                    raise RuntimeError('provider_rejected: unsupported tree entry')
                blob = git(self.git_dir, 'hash-object', '-w', '--stdin',
                           input=entry['content'].encode()).decode().strip()
                git(self.git_dir, 'update-index', '--add', '--cacheinfo',
                    '100644,' + blob + ',' + entry['path'], env=env)
            return git(self.git_dir, 'write-tree', env=env).decode().strip()
        finally:
            index.unlink(missing_ok=True)


class ResponseLostAfterRefUpdate:
    """Fault injection: the ref update takes effect, then the caller never sees the reply."""
    def __init__(self, provider):
        self.provider = provider

    def request(self, method, path, body=None):
        result = self.provider.request(method, path, body)
        if method == 'PATCH':
            raise RuntimeError('provider_outcome_unknown')
        return result
