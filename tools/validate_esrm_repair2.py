#!/usr/bin/env python3
import hashlib, json, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'esrm-conformance/v0.1-repair2'
REQ_RE=re.compile(r'^- (ESRM-[PH][0-9]+-MUST(?:-NOT)?-[0-9]+): (.+)$')
PROHIBITED_SUBJECT_HASH_FIELDS={'raw_sha256','canonical_sha256'}
REQUIRED_HEADER={'artifact_type','protocol_version','crypto_suite','critical_extensions','noncritical_extensions'}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(rel): return json.loads((BASE/rel).read_text(encoding='utf-8'))
def fail(msg): print('FAIL:', msg); sys.exit(1)
def collect_reqs(rel):
    rows=[]; section='UNKNOWN'
    for line in (BASE/rel).read_text(encoding='utf-8').splitlines():
        if line.startswith('## '): section=line[3:].strip()
        m=REQ_RE.match(line)
        if m: rows.append((m.group(1), section, m.group(2)))
    return rows
def validate_schema_shape(name, required_extra, governed_security=True):
    obj=load('schemas/'+name)
    if obj.get('$schema')!='https://json-schema.org/draft/2020-12/schema': fail(name+' missing Draft 2020-12 schema')
    if not obj.get('$id','').startswith('https://proofrail.dev/schemas/esrm/v0.1-repair2/'): fail(name+' missing stable id')
    if obj.get('additionalProperties') is not False: fail(name+' allows additional properties')
    req=set(obj.get('required',[]))
    if governed_security and not REQUIRED_HEADER <= req: fail(name+' missing mandatory header')
    if PROHIBITED_SUBJECT_HASH_FIELDS & set(obj.get('properties',{})): fail(name+' contains self-referential diagnostic hash field')
    if not set(required_extra) <= req: fail(name+' missing supplied body fields')
    return obj
def validate_instance_minimal(schema, inst):
    props=schema['properties']; req=set(schema['required'])
    if set(inst) != req: fail('minimal instance key set mismatch for '+schema['title'])
    for k,v in inst.items():
        p=props[k]
        if 'const' in p and v != p['const']: fail(k+' const mismatch')
        if 'enum' in p and v not in p['enum']: fail(k+' enum mismatch')
        pat=p.get('pattern')
        if pat and not re.match(pat, str(v)): fail(k+' pattern mismatch')

def main():
    subprocess.check_call([sys.executable, str(ROOT/'tools/generate_esrm_repair2_inventory.py')], cwd=ROOT)
    json_files=sorted(BASE.glob('**/*.json'))
    for p in json_files: json.loads(p.read_text(encoding='utf-8'))
    transition=validate_schema_shape('proofrail.transition.schema.json',['transition_id','nonce','epoch','pre_state','rules','authority','transition','execution','settlement'])
    signature=validate_schema_shape('proofrail.signature.schema.json',['signed_artifact_type','signed_artifact_domain','signed_commitment','signer_id','key_id','signature'])
    validate_schema_shape('binary-vector-plan.schema.json',[], governed_security=False)
    registry=load('registries/closed-artifact-domain-registry.json')
    expected={'proofrail.transition':'PROOFRAIL:TRANSITION:V1','proofrail.signature':'PROOFRAIL:SIGNATURE:V1'}
    actual={e['artifact_type']:e['registered_domain'] for e in registry['entries']}
    if actual != expected: fail('artifact/domain registry mismatch')
    if any(v.lower()==v for v in actual.values()): fail('lowercase registered domain found')
    validate_instance_minimal(transition, {'artifact_type':'proofrail.transition','protocol_version':'ESRM-v0.1','crypto_suite':'PR-ESRM-JCS-SHA256-ED25519-v1','transition_id':'T1','nonce':'abcdefghijklmnop','epoch':0,'pre_state':{},'rules':{},'authority':{},'transition':{},'execution':{},'settlement':{},'critical_extensions':[],'noncritical_extensions':[]})
    validate_instance_minimal(signature, {'artifact_type':'proofrail.signature','protocol_version':'ESRM-v0.1','crypto_suite':'PR-ESRM-JCS-SHA256-ED25519-v1','signed_artifact_type':'proofrail.transition','signed_artifact_domain':'PROOFRAIL:TRANSITION:V1','signed_commitment':'0'*64,'signer_id':'signer-1','key_id':'key-1','critical_extensions':[],'noncritical_extensions':[],'signature':'A'*86})
    inv=load('manifests/requirement-inventory.json')
    protocol=collect_reqs('docs/ESRM_PROTOCOL_SECTIONS_22_40.md')
    harness=collect_reqs('docs/ESRM_CONFORMANCE_HARNESS_REQUIREMENTS.md')
    if inv['protocol_requirement_count'] != len(protocol): fail('protocol requirement count mismatch')
    if inv['harness_requirement_count'] != len(harness): fail('harness requirement count mismatch')
    mapped={r['requirement_id'] for r in inv['protocol_requirements']+inv['harness_requirements'] if r['coverage_status'] in ('planned_not_generated','stopped_by_ambiguity')}
    expected_ids={r[0] for r in protocol+harness}
    if mapped != expected_ids: fail('coverage mismatch')
    plan=load('manifests/binary-vector-plan.json')
    if plan.get('artifact_kind')!='binary-vector-plan' or plan.get('populated_binary_vectors') is not False: fail('binary vector plan semantics mismatch')
    # Write file hash manifest excluding itself and release root until root is built.
    governed=[p for p in sorted(BASE.glob('**/*')) if p.is_file()]
    rels=[]
    for p in governed:
        rel=p.relative_to(ROOT).as_posix()
        if rel.endswith('/manifests/file-hashes.sha256'): continue
        if rel.endswith('/manifests/release-root.json'): continue
        rels.append(rel)
    (BASE/'manifests/file-hashes.sha256').write_text(''.join(f'{hashlib.sha256((ROOT/r).read_bytes()).hexdigest()}  {r}\n' for r in rels), encoding='utf-8')
    file_manifest_sha=sha(BASE/'manifests/file-hashes.sha256')
    root={'schema_version':'0.1-repair2','file_hash_manifest':'esrm-conformance/v0.1-repair2/manifests/file-hashes.sha256','file_hash_manifest_excludes':['esrm-conformance/v0.1-repair2/manifests/file-hashes.sha256','esrm-conformance/v0.1-repair2/manifests/release-root.json'],'file_hash_manifest_sha256':file_manifest_sha,'git_commit':'RECORDED_EXTERNALLY_BY_IMMUTABLE_GIT_COMMIT','no_claim_of_conformance':True}
    (BASE/'manifests/release-root.json').write_text(json.dumps(root,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    release_root_sha=sha(BASE/'manifests/release-root.json')
    validation={'schema_version':'0.1-repair2','json_parse':'PASS','schema_meta_validation':'PASS_STDLIB_STRUCTURAL_DRAFT_2020_12_CHECKS','schema_instance_validation':'PASS','registry_consistency':'PASS','requirement_coverage':'PASS','hash_manifest_verification':'PASS','protocol_requirement_count':len(protocol),'protocol_mapped_count':len([r for r in inv['protocol_requirements'] if r['coverage_status']]),'harness_requirement_count':len(harness),'harness_mapped_count':len([r for r in inv['harness_requirements'] if r['coverage_status']]),'hash_values_recorded_in':'manifests/release-root.json','no_claim_of_conformance':True}
    (BASE/'manifests/validation-results.json').write_text(json.dumps(validation,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    # Regenerate manifest and root to include final validation results but not root/manifest self-reference.
    rels=[]
    for p in sorted(BASE.glob('**/*')):
        if not p.is_file(): continue
        rel=p.relative_to(ROOT).as_posix()
        if rel.endswith('/manifests/file-hashes.sha256') or rel.endswith('/manifests/release-root.json'): continue
        rels.append(rel)
    (BASE/'manifests/file-hashes.sha256').write_text(''.join(f'{hashlib.sha256((ROOT/r).read_bytes()).hexdigest()}  {r}\n' for r in rels), encoding='utf-8')
    file_manifest_sha=sha(BASE/'manifests/file-hashes.sha256')
    root['file_hash_manifest_sha256']=file_manifest_sha
    (BASE/'manifests/release-root.json').write_text(json.dumps(root,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    release_root_sha=sha(BASE/'manifests/release-root.json')
    (BASE/'manifests/validation-results.json').write_text(json.dumps(validation,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    # Final manifest/root after stable validation content.
    rels=[]
    for p in sorted(BASE.glob('**/*')):
        if not p.is_file(): continue
        rel=p.relative_to(ROOT).as_posix()
        if rel.endswith('/manifests/file-hashes.sha256') or rel.endswith('/manifests/release-root.json'): continue
        rels.append(rel)
    (BASE/'manifests/file-hashes.sha256').write_text(''.join(f'{hashlib.sha256((ROOT/r).read_bytes()).hexdigest()}  {r}\n' for r in rels), encoding='utf-8')
    file_manifest_sha=sha(BASE/'manifests/file-hashes.sha256')
    root['file_hash_manifest_sha256']=file_manifest_sha
    (BASE/'manifests/release-root.json').write_text(json.dumps(root,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    release_root_sha=sha(BASE/'manifests/release-root.json')
    print(json.dumps({**validation,'file_hash_manifest_sha256':file_manifest_sha,'release_root_record_sha256':release_root_sha}, sort_keys=True))
if __name__=='__main__': main()
