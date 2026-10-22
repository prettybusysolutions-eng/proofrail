"""Exact Git data request preparation and immutable-commit readback checking.

The authenticated GitHub connector executes requests outside this module.
No token is stored here. The connector operator is inside the trust boundary.
"""
import hashlib
import json
import time
from acceptance_bridge import full_digest, require, verify_handoff


def prepare_commit(ledger, execution_id, handoff, contract, trust, *, clock=time.time):
    require(contract['action_type'] == 'github_artifact_commit', 'wrong_github_action')
    params = contract['parameters']
    require(set(params) == {'repository', 'branch', 'path', 'parent_sha', 'base_tree'}, 'github_scope_fields')
    require(params['branch'].startswith('trial/emergence-'), 'trial_branch_required')
    require(params['path'].startswith('evidence/') and '..' not in params['path'].split('/'), 'evidence_path_required')
    target = 'github:' + params['repository'] + ':' + params['branch'] + ':' + params['path']
    require(contract['target'] == target, 'github_target_changed')
    payload = handoff['payload']['task']['artifact']
    require(isinstance(payload, str), 'artifact_text_required')
    require(hashlib.sha256(payload.encode()).hexdigest() == contract['expected_sha256'], 'artifact_digest_changed')
    consumption = ledger.begin_dispatch(execution_id, handoff, contract, trust, clock=clock)
    content = json.dumps({'kind': 'emergence.github-artifact.v1',
                          'execution_id': execution_id, 'consumption_digest': full_digest(consumption),
                          'tenant': contract['tenant'], 'task_id': contract['task_id'],
                          'artifact': payload}, sort_keys=True, indent=2) + '\n'
    return {**params, 'content': content, 'content_sha256': hashlib.sha256(content.encode()).hexdigest(),
            'execution_id': execution_id, 'consumption_digest': full_digest(consumption)}


def verify_commit(ledger, execution_id, handoff, contract, trust, *,
                  commit, file_content, repository, path, observed_ref):
    consumption, started = ledger.get(execution_id)
    require(started, 'dispatch_not_started')
    binding = verify_handoff(handoff, contract, trust, now=consumption['consumed_at'])
    for field in ('handoff_digest', 'authority_digest', 'contract_digest'):
        require(consumption[field] == binding[field], 'consumption_binding_changed')
    params = contract['parameters']
    require(repository == params['repository'] and path == params['path'], 'github_read_scope_changed')
    require(observed_ref == commit['sha'], 'immutable_commit_read_required')
    require([p['sha'] for p in commit['parents']] == [params['parent_sha']], 'commit_parent_changed')
    # Both values must be returned by authenticated GitHub fetches. A commit
    # response or parsed object supplied by an arbitrary caller is not trusted.
    data = json.loads(file_content)
    expected = {'kind': 'emergence.github-artifact.v1', 'execution_id': execution_id,
                'consumption_digest': full_digest(consumption), 'tenant': contract['tenant'],
                'task_id': contract['task_id'], 'artifact': handoff['payload']['task']['artifact']}
    require(data == expected, 'github_content_or_provenance_changed')
    require(file_content == json.dumps(expected, sort_keys=True, indent=2) + '\n', 'github_exact_bytes_changed')
    require(hashlib.sha256(data['artifact'].encode()).hexdigest() == contract['expected_sha256'], 'artifact_digest_changed')
    return {'outcome': 'MATCH', 'execution_authorized': False, 'execution_id': execution_id,
            'commit_sha': commit['sha'], 'consumption_digest': full_digest(consumption),
            'file_sha256': hashlib.sha256(file_content.encode()).hexdigest(),
            'scope': 'Authenticated GitHub commit readback; operator-mediated dispatch'}


def git_blob_sha(data):
    """Git's object ID for a blob with these bytes (SHA-1 object format)."""
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def _tree_entries(listing):
    require(isinstance(listing, dict) and listing.get('truncated') is False and
            isinstance(listing.get('tree'), list), 'tree_listing_incomplete')
    leaves, trees = {}, set()
    for entry in listing['tree']:
        require(isinstance(entry, dict) and isinstance(entry.get('path'), str) and
                all(isinstance(entry.get(k), str) for k in ('mode', 'type', 'sha')), 'tree_entry_invalid')
        require(entry['path'] not in leaves and entry['path'] not in trees, 'tree_entry_duplicate')
        if entry['type'] == 'tree':
            trees.add(entry['path'])
        else:
            leaves[entry['path']] = (entry['mode'], entry['type'], entry['sha'])
    return leaves, trees


def verify_tree_change(base_listing, head_listing, path, content):
    """The commit's whole tree must be the approved base tree plus exactly one
    regular, non-executable file at `path` holding `content`.

    Checking only the bytes served for `path` is a projection: the GitHub contents
    API follows a symlink to a normal file, and it says nothing about the mode or
    about other paths. Both listings must be complete (`truncated` false).
    """
    base_leaves, base_trees = _tree_entries(base_listing)
    head_leaves, head_trees = _tree_entries(head_listing)
    expected = dict(base_leaves)
    expected[path] = ('100644', 'blob', git_blob_sha(content.encode('utf-8')))
    parents = {'/'.join(path.split('/')[:i]) for i in range(1, path.count('/') + 1)}
    require(head_leaves == expected and head_trees == base_trees | parents,
            'commit_tree_not_exact_approved_change')
