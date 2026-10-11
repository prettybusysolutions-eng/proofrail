"""Exercise the real GitHub adapter through an authenticated JSON-line connector.

The connector must allow only this synthetic canary PR's GET and exact-head
merge request. No credentials are accepted, generated or exported by this script.
"""
import argparse,copy,json,sqlite3,sys,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from integrations.openclaw.github_adapter import GitHubMergeAdapter
from proofrail.permit import mint_permit,execute_github_merge,consume_permit,PermitError

REPOSITORY='prettybusysolutions-eng/xruntime-phase8-canary'
def write(path,data):path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def context(root):
    d=json.loads((root/'context.json').read_text())
    d['public_key']=Ed25519PublicKey.from_public_bytes(bytes.fromhex((root/'verifier.pub').read_text()))
    d['registry_path']=root/'registry.sqlite'
    return d
class ConnectorTransport:
    def __init__(self):self.calls=[]
    def request(self,method,path,*,body=None,idempotency_key=None):
        record=dict(method=method,path=path,body=body,idempotency_key=idempotency_key)
        self.calls.append(record)
        print('PROOFRAIL_REQUEST '+json.dumps(record),flush=True)
        response=json.loads(sys.stdin.readline())
        return response['status'],response.get('headers',{}),response['body']
def run(root,number,head):
    root.mkdir(parents=True,exist_ok=False)
    key=Ed25519PrivateKey.generate()
    (root/'verifier.pub').write_text(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex())
    write(root/'context.json',dict(expected_identity_root='1'*64,expected_evidence_root='2'*64,expected_policy_root='3'*64,expected_state_root='4'*64,expected_approval_digest='5'*64,executor_id='synthetic-authorized-connector'))
    permit=mint_permit(identity_root='1'*64,evidence_root='2'*64,policy_root='3'*64,state_root='4'*64,approval_digest='5'*64,repository=REPOSITORY,pull_number=number,expected_head_sha=head,merge_method='squash',nonce=uuid.uuid4().hex,expires_at=datetime.now(timezone.utc)+timedelta(days=1),issuer_principal_id='synthetic-internal-verifier',issuer_role='verifier',private_key=key,key_id='synthetic-ephemeral')
    write(root/'permit.json',permit)
    transport=ConnectorTransport();adapter=GitHubMergeAdapter(transport)
    bad=copy.deepcopy(permit);bad['effect']['expected_head_sha']='0'*40
    try:execute_github_merge(bad,adapter=adapter,**context(root))
    except PermitError as error:
        if error.code!='invalid_signature':raise
    else:raise RuntimeError('tampered permit accepted')
    if transport.calls:raise RuntimeError('tampered permit reached provider')
    result=execute_github_merge(permit,adapter=adapter,**context(root))
    if result['authority_state']!='RECONCILED' or not result['adapter_receipt']['side_effect_confirmed']:raise RuntimeError('provider effect not reconciled')
    calls=len(transport.calls)
    try:execute_github_merge(permit,adapter=adapter,**context(root))
    except PermitError as error:
        if error.code!='permit_replayed':raise
    else:raise RuntimeError('permit replay accepted')
    if len(transport.calls)!=calls:raise RuntimeError('replay reached provider')
    result.update(status='PASS',tampered_permit_denied_before_provider=True,replay_denied_before_provider=True,transport_calls=transport.calls,scope='real GitHub canary effect via authenticated connector; internally operated synthetic signing identity')
    write(root/'integration-result.json',result)
    with sqlite3.connect(root/'registry.sqlite') as src,sqlite3.connect(root/'registry-backup.sqlite') as dest:src.backup(dest)
    print('PROOFRAIL_DONE '+json.dumps({'status':'PASS','operation':result['adapter_receipt']['remote_operation_id'],'directory':str(root)}),flush=True)
def verify_restored(root):
    permit=json.loads((root/'permit.json').read_text());params=context(root)
    params['registry_path']=root/'registry-backup.sqlite'
    effect=permit['effect']
    try:consume_permit(permit,**params,repository=effect['repository'],pull_number=effect['pull_number'],expected_head_sha=effect['expected_head_sha'],merge_method=effect['merge_method'])
    except PermitError as error:
        if error.code!='permit_replayed':raise
    else:raise RuntimeError('restored registry forgot consumed authority')
    write(root/'restored-live-authority.json',dict(status='PASS',spent_authority_rejected_after_process_restart_and_sqlite_backup=True,provider_calls=0))
    print('RESTORED_LIVE_AUTHORITY_PASS')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['run','verify-restored']);parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--pr',type=int);parser.add_argument('--head');args=parser.parse_args()
    if args.phase=='run':run(args.directory,args.pr,args.head)
    else:verify_restored(args.directory)
