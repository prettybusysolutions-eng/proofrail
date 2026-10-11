"""Two-process/two-runner replay-state restoration with synthetic authority only."""
import argparse,hashlib,json,os,shutil,sqlite3,subprocess,sys,tempfile,time,uuid
from contextlib import closing
from datetime import datetime,timedelta,timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from proofrail.permit import mint_permit,consume_permit,PermitError
from proofrail.trust import create_trust_checkpoint,replay_registry_root,verify_trust_checkpoint

ROOTS=dict(identity='1'*64,evidence='2'*64,policy='3'*64,state='4'*64)
def write(path,data):
    with path.open('w') as stream:
        json.dump(data,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def read(path):return json.loads(path.read_text())
def context(root,registry):
    return dict(registry_path=registry,public_key=Ed25519PublicKey.from_public_bytes(bytes.fromhex((root/'verifier.pub').read_text())),**{'expected_'+k+'_root':v for k,v in ROOTS.items()},expected_approval_digest='5'*64,repository='synthetic/recovery',pull_number=1,expected_head_sha='a'*40,merge_method='squash',executor_id='synthetic-recovery')
def trust(checkpoint):
    return dict(replay_root=checkpoint['roots']['replay'],checkpoint_root=checkpoint['record_hash'],observation_root=checkpoint['roots']['observation'],minimum_checkpoint_epoch=checkpoint['epoch'],monotonic_counter=checkpoint['monotonic_counter'])
def backup(source,destination):
    with closing(sqlite3.connect(f'file:{source}?mode=ro',uri=True)) as src,closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('backup integrity failed')
def prepare(bundle):
    bundle.mkdir(parents=True,exist_ok=False)
    key=Ed25519PrivateKey.generate();checkpoint_key=Ed25519PrivateKey.generate()
    (bundle/'verifier.pub').write_text(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex())
    (bundle/'checkpoint.pub').write_text(checkpoint_key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex())
    def mint(binding=None):
        return mint_permit(**{k+'_root':v for k,v in ROOTS.items()},approval_digest='5'*64,repository='synthetic/recovery',pull_number=1,expected_head_sha='a'*40,merge_method='squash',nonce=uuid.uuid4().hex,expires_at=datetime.now(timezone.utc)+timedelta(days=1),issuer_principal_id='synthetic-verifier',issuer_role='verifier',private_key=key,key_id='synthetic-only',trust=binding)
    with tempfile.TemporaryDirectory() as temporary:
        source=Path(temporary)/'source.sqlite'
        consume_permit(mint(),**context(bundle,source))
        checkpoint=create_trust_checkpoint(replay_root=replay_registry_root(source),epoch=1,monotonic_counter=1,private_key=checkpoint_key,key_id='synthetic-checkpoint')
        backup(source,bundle/'stale.sqlite')
        write(bundle/'before.json',checkpoint)
        write(bundle/'spent.json',mint(trust(checkpoint)))
        worker=subprocess.run([sys.executable,str(Path(__file__).resolve()),'crash','--bundle',str(bundle.resolve()),'--registry',str(source)])
        if worker.returncode!=137:raise RuntimeError(f'worker did not crash after claim: {worker.returncode}')
        advanced=create_trust_checkpoint(replay_root=replay_registry_root(source),epoch=2,monotonic_counter=2,private_key=checkpoint_key,key_id='synthetic-checkpoint',previous_checkpoint_hash=checkpoint['record_hash'])
        write(bundle/'checkpoint.json',advanced)
        write(bundle/'fresh.json',mint(trust(advanced)))
        backup(source,bundle/'registry.sqlite')
    write(bundle/'producer.json',dict(status='PASS',claim_committed_before_forced_exit=True,exit_code=137,private_keys_exported=False,created_at=datetime.now(timezone.utc).isoformat(),job=os.getenv('GITHUB_JOB','local-producer'),host=hashlib.sha256(os.uname().nodename.encode()).hexdigest()))
    write(bundle/'manifest.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(bundle.iterdir()) if p.is_file()})
def restore(bundle,output):
    started=time.perf_counter();output.mkdir(parents=True,exist_ok=False)
    for name,digest in read(bundle/'manifest.json').items():
        if Path(name).name!=name or hashlib.sha256((bundle/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('manifest mismatch')
    source=bundle/'registry.sqlite';database=output/'restored.sqlite';backup(source,database)
    checkpoint=read(bundle/'checkpoint.json');key=Ed25519PublicKey.from_public_bytes(bytes.fromhex((bundle/'checkpoint.pub').read_text()))
    if not verify_trust_checkpoint(checkpoint,registry_path=database,public_key=key)['valid']:raise RuntimeError('restored trust mismatch')
    if verify_trust_checkpoint(checkpoint,registry_path=bundle/'stale.sqlite',public_key=key)['valid']:raise RuntimeError('stale state accepted')
    with sqlite3.connect(database) as connection:
        count=connection.execute('SELECT COUNT(*) FROM permit_claims').fetchone()[0]
    if count!=2:raise RuntimeError('committed claim lost')
    kwargs=dict(**context(bundle,database),trust_checkpoint=checkpoint,checkpoint_public_key=key)
    try:consume_permit(read(bundle/'spent.json'),**kwargs)
    except PermitError as error:
        if error.code!='permit_replayed':raise
    else:raise RuntimeError('spent authority became reusable')
    result=consume_permit(read(bundle/'fresh.json'),**kwargs)
    if result['state']!='CONSUMED':raise RuntimeError('new authority unusable')
    try:consume_permit(read(bundle/'fresh.json'),**context(bundle,database),trust_checkpoint=checkpoint,checkpoint_public_key=key)
    except PermitError:pass
    else:raise RuntimeError('new authority replayed')
    evidence=dict(status='PASS',restored_claims=count,committed_claim_loss=0,stale_backup_rejected=True,spent_authority_rejected=True,fresh_authority_consumed_once=True,restore_and_validation_seconds=time.perf_counter()-started,job=os.getenv('GITHUB_JOB','local-consumer'),host=hashlib.sha256(os.uname().nodename.encode()).hexdigest(),scope='synthetic replay registry; no production RTO/RPO or independent-retention certification')
    write(output/'recovery-evidence.json',evidence);print(json.dumps(evidence))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['prepare','crash','restore']);parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--registry',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.phase=='prepare':prepare(args.bundle)
    elif args.phase=='restore':restore(args.bundle,args.output)
    else:
        consume_permit(read(args.bundle/'spent.json'),**context(args.bundle,args.registry),trust_checkpoint=read(args.bundle/'before.json'),checkpoint_public_key=Ed25519PublicKey.from_public_bytes(bytes.fromhex((args.bundle/'checkpoint.pub').read_text())))
        os._exit(137)
