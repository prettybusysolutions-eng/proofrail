"""Export existing frozen Gate 1B inputs without altering the semantic target."""
import argparse,hashlib,json,subprocess
from pathlib import Path
HANDOFF='55fa2c47608287e9b22d09c7982d9949b079a232'
def git_bytes(commit,path):return subprocess.check_output(['git','show',f'{commit}:{path}'])
def package(output):
    manifest=json.loads(git_bytes(HANDOFF,'gate1/external-review-inputs.json'))
    output.mkdir(parents=True,exist_ok=False)
    for item in manifest['inputs']:
        data=git_bytes(item['commit'],item['path'])
        if len(data)!=item['size_bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('frozen input hash mismatch: '+item['path'])
        path=output/item['commit']/item['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    for name in ['REVIEW_TARGET.md','REVIEWER_SELECTION.md','EXTERNAL_REVIEW_HANDOFF.md','EXTERNAL_REVIEW_REQUEST.md']:
        path=output/'handoff'/name;path.parent.mkdir(exist_ok=True);path.write_bytes(git_bytes(HANDOFF,'gate1/'+name))
    manifest['handoff_commit']=HANDOFF
    (output/'review-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    paths={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
    (output/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(paths.items())))
    print(json.dumps({'status':'HANDOFF_ONLY_GATE_1B_OPEN','verified_frozen_inputs':len(manifest['inputs']),'output':str(output)}))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);package(parser.parse_args().output)
