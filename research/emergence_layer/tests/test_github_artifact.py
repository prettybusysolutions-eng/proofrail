"""Synthetic negative controls; the committed live evidence is separate."""
import json
import pytest
from live_github_trial import prepare, verify, write_json


@pytest.fixture
def run(tmp_path):
    directory = tmp_path / 'run'
    prepare(directory, 'fixture/repo', 'trial/emergence-test', 'a' * 40, 'b' * 40)
    request = json.loads((directory / 'request.json').read_text())
    readback = {'repository': 'fixture/repo', 'path': request['path'],
                'observed_ref': 'c' * 40, 'branch_head': 'c' * 40,
                'commit': {'sha': 'c' * 40, 'parents': [{'sha': 'a' * 40}]},
                'file_content': request['content']}
    return directory, readback


def test_matching_synthetic_readback_and_repeat_dispatch_denial(run):
    directory, readback = run
    write_json(directory / 'provider-readback.json', readback)
    verify(directory)
    result = json.loads((directory / 'result.json').read_text())
    assert result['outcome'] == 'MATCH' and result['repeat_dispatch_rejected']


@pytest.mark.parametrize('mutation', ['repository', 'path', 'ref', 'parent', 'branch', 'content', 'execution', 'whitespace'])
def test_readback_substitutions_are_rejected(run, mutation):
    directory, readback = run
    if mutation == 'repository':
        readback['repository'] = 'another/repo'
    elif mutation == 'path':
        readback['path'] = 'evidence/other.json'
    elif mutation == 'ref':
        readback['observed_ref'] = 'main'
    elif mutation == 'parent':
        readback['commit']['parents'] = [{'sha': 'd' * 40}]
    elif mutation == 'branch':
        readback['branch_head'] = 'd' * 40
    elif mutation == 'whitespace':
        readback['file_content'] += '\n'
    else:
        content = json.loads(readback['file_content'])
        content['artifact' if mutation == 'content' else 'execution_id'] = 'substituted'
        readback['file_content'] = json.dumps(content, sort_keys=True, indent=2) + '\n'
    write_json(directory / 'provider-readback.json', readback)
    with pytest.raises(ValueError):
        verify(directory)
