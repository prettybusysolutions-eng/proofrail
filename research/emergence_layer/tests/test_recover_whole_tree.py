"""Recovery confirms the whole commit tree, not only the bytes served for the approved path.

Before this check, `Dispatcher.recover` returned MATCH for a commit it never wrote,
when that commit sat on the approved parent and served the approved bytes but also
added a file, changed the mode, or (on GitHub, whose contents API follows symlinks
to normal files) made the path a symlink. These run against real git objects via
buyer_demo/local_git_provider.py; GitHubLikeProvider adds GitHub's documented
symlink-following behaviour to the contents call.
"""
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEMO = Path(__file__).resolve().parents[1] / 'buyer_demo'
sys.path.insert(0, str(DEMO))
import run_demo as demo  # noqa: E402
from local_git_provider import LocalGitProvider, create_repository, git  # noqa: E402
from github_artifact import git_blob_sha  # noqa: E402


class GitHubLikeProvider(LocalGitProvider):
    """Contents call follows a symlink whose target is a regular file, as GitHub documents."""
    def request(self, method, path, body=None):
        if method == 'GET' and '/contents/' in path:
            route, ref = path.split('/contents/', 1)[1].split('?ref=')
            mode = git(self.git_dir, 'ls-tree', ref, '--', route).decode().split(' ', 1)[0]
            if mode == '120000':
                target = git(self.git_dir, 'cat-file', 'blob', ref + ':' + route).decode()
                route = str(Path(route).parent / target)
                path = path.split('/contents/')[0] + '/contents/' + route + '?ref=' + ref
        return super().request(method, path, body)


def lookalike(git_dir, base, entries):
    """Commit on `base` whose tree is base plus `entries` (path -> (mode, bytes) or None to delete)."""
    index = Path(git_dir) / 'lookalike-index'
    env = {'GIT_INDEX_FILE': str(index)}
    git(git_dir, 'read-tree', base, env=env)
    for path, value in entries.items():
        if value is None:  # mode 0 removes the entry; --force-remove needs a work tree
            git(git_dir, 'update-index', '--index-info', input=f'0 {"0" * 40}\t{path}\n'.encode(), env=env)
            continue
        mode, data = value
        obj = (data.decode() if mode == '160000' else
               git(git_dir, 'hash-object', '-w', '--stdin', input=data).decode().strip())
        git(git_dir, 'update-index', '--add', '--cacheinfo', f'{mode},{obj},{path}', env=env)
    tree = git(git_dir, 'write-tree', env=env).decode().strip()
    index.unlink()
    return git(git_dir, 'commit-tree', tree, '-p', base, '-m', 'look-alike').decode().strip()


@pytest.fixture
def written(tmp_path):
    keys = {n: Ed25519PrivateKey.generate() for n in ('agent', 'approver', 'consumer', 'observer')}
    git_dir = tmp_path / 'repo.git'
    base, tree = create_repository(git_dir, demo.BRANCH, {'README.md': 'base\n', 'docs/guide.md': 'guide\n'})
    handoff, contract, trust = demo.approve(keys, artifact=demo.APPROVED_ARTIFACT, parent_sha=base,
                                            base_tree=tree, task_id='whole-tree')
    dispatcher, _ = demo.service(tmp_path, 'svc', keys, trust, git_dir)
    provider = GitHubLikeProvider(git_dir, demo.REPOSITORY)
    dispatcher.api = provider
    result = dispatcher.dispatch(handoff, contract)
    assert result['outcome'] == 'MATCH'
    content = git(git_dir, 'cat-file', 'blob', result['commit_sha'] + ':' + demo.PATH)
    return dispatcher, provider, handoff, contract, git_dir, base, content


def variants(content):
    return {
        'extra file': {demo.PATH: ('100644', content), 'deploy/run.sh': ('100755', b'#!/bin/sh\n')},
        'executable': {demo.PATH: ('100755', content)},
        'symlink to exact bytes': {'evidence/real.json': ('100644', content),
                                   demo.PATH: ('120000', b'real.json')},
        'submodule beside file': {demo.PATH: ('100644', content), 'vendor/lib': ('160000', b'e' * 40)},
        'deleted base file': {demo.PATH: ('100644', content), 'docs/guide.md': None},
        'changed base file': {demo.PATH: ('100644', content), 'README.md': ('100644', b'changed\n')},
    }


@pytest.mark.parametrize('name', list(variants(b'')))
def test_lookalike_commit_is_not_confirmed(written, name):
    dispatcher, provider, handoff, contract, git_dir, base, content = written
    fake = lookalike(git_dir, base, variants(content)[name])
    git(git_dir, 'update-ref', 'refs/heads/' + demo.BRANCH, fake)  # e.g. an administrative rewind
    before = len(provider.calls)
    with pytest.raises(ValueError, match='commit_tree_not_exact_approved_change'):
        dispatcher.recover(handoff, contract)
    assert provider.writes(before) == []


def test_symlink_variant_serves_exact_bytes_through_contents(written):
    """Shows the symlink case passes the byte check and is caught only by the tree check."""
    dispatcher, provider, handoff, contract, git_dir, base, content = written
    fake = lookalike(git_dir, base, variants(content)['symlink to exact bytes'])
    served = provider.request('GET', '/repos/' + demo.REPOSITORY + '/contents/' + demo.PATH + '?ref=' + fake)
    import base64
    assert base64.b64decode(served['content']) == content


def test_truncated_listing_is_not_confirmed(written):
    dispatcher, provider, handoff, contract, *_ = written

    class Truncating:
        def request(self, method, path, body=None):
            result = provider.request(method, path, body)
            return {**result, 'truncated': True} if '/git/trees/' in path else result
    dispatcher.api = Truncating()
    with pytest.raises(ValueError, match='tree_listing_incomplete'):
        dispatcher.recover(handoff, contract)


def test_genuine_commit_still_confirmed_read_only(written):
    dispatcher, provider, handoff, contract, *_ = written
    before = len(provider.calls)
    assert dispatcher.recover(handoff, contract)['outcome'] == 'MATCH'
    assert provider.writes(before) == []


def test_blob_id_matches_git():
    assert git_blob_sha(b'hello\n') == 'ce013625030ba8dba906f756967f9e9ca394464a'
