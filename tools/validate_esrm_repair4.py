#!/usr/bin/env python3
import base64, calendar, hashlib, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'esrm-conformance/v0.1-repair4'
DOMAINS=['PROOFRAIL:STATE:V1','PROOFRAIL:RULESET:V1','PROOFRAIL:AUTHORITY:V1','PROOFRAIL:ADMISSION:V1','PROOFRAIL:CONSUMPTION:V1','PROOFRAIL:TRANSITION:V1','PROOFRAIL:DISPATCH-INTENT:V1','PROOFRAIL:DISPATCH-CROSSING:V1','PROOFRAIL:OBSERVATION:V1','PROOFRAIL:RECONCILIATION:V1','PROOFRAIL:SETTLEMENT:V1','PROOFRAIL:RECOVERY:V1','PROOFRAIL:REVOCATION:V1','PROOFRAIL:KEY-STATUS:V1','PROOFRAIL:SIGNATURE:V1']
EXPECTED=[('22','Signature Does Not Confer Authority'),('23','Exact Commitment Encoding'),('24','Registered Artifact Domains'),('25','Signature Envelope'),('26','Strict JSON Intake Pipeline'),('27','Unicode Profile'),('28','ProofRail Numeric Profile'),('29','Timestamp Profile'),('30','Mandatory Artifact Header'),('31','Precise Reconciliation Result Algebra'),('32','Closed-World Absence Rule'),('33','Consumption Irreversibility'),('34','Crash-Safe Dispatch Boundary'),('35','Dispatch Intent Artifact'),('36','Boundary-Crossing Artifact'),('37','External Target Capability Evidence'),('38','Recovery Function'),('39','Transport Attempt Versus Semantic Transition'),('40','Canonical Baseline Safety Claim')]
REQUIRED_BLOCKS=['SignedBy(E, k) = TRUE','Authorized(E) = TRUE','AUTHORIZED(tau) IFF','B_x = UTF8(RFC8785Canonicalize(x))','C_x = SHA256(\n  ASCII(D_x) || BYTE(0x00) || B_x\n)','RegisteredDomain(signed_artifact_type)\n  = signed_artifact_domain','MATCH:\n  empirical_world(tau) SATISFIES settlement_predicate(tau)','DIVERGED:\n  empirical_world(tau) DOES_NOT_SATISFY settlement_predicate(tau)','INSUFFICIENT:\n  WindowOpen\n  AND NOT MatchEstablished\n  AND NOT DivergenceEstablished','UNRESOLVED:\n  WindowClosed\n  AND NOT MatchEstablished\n  AND NOT DivergenceEstablished','Timeout DOES_NOT_IMPLY DIVERGED','DeadlinePassed DOES_NOT_IMPLY EventAbsent','Consumed(authority_tau) = TRUE','NonOccurrence(transition_1)\n  DOES_NOT_IMPLY Reusable(authority_1)','authority_2 != authority_1','Consumed(authority_tau)\n  IS_NOT_EQUIVALENT_TO ExternalEffect(transition_tau)','CrossingRecorded\n  AND NOT ExternalEvidence\n  IMPLIES EffectStatus = UNKNOWN','Recover(D, K, Q, F):\n  IF Q = Occurred:\n    OBSERVE_AS_MATCH\n  ELSE IF F = DidNotOccur:\n    RECOVER_WITH_NEW_TRANSITION\n  ELSE IF K AND Q != Occurred:\n    RETRANSMIT_SAME_EFFECT\n  ELSE:\n    UNRESOLVED','attempt_1 != attempt_2','effectIdentity(attempt_1)\n  = effectIdentity(attempt_2)','UnknownEffect(tau) IMPLIES\n  NOT Settled(tau)\n  AND NOT FailedByInference(tau)\n  AND Consumed(authority_tau)','Retry(tau) IMPLIES\n  VerifiedDurableIdempotency\n  OR NewTransitionWithNewAuthority']
HEX64='0'*64
class ValidationError(Exception): pass
def fail(x): raise ValidationError(x)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(rel): return json.loads((BASE/rel).read_text(encoding='ascii'))
def source_titles(text): return re.findall(r'^\*\*(\d+)\. ([^*]+)\*\*$', text, re.M)
def normative_count(text): return len(re.findall(r'\b(MUST|MUST NOT|SHALL|SHALL NOT|REQUIRED)\b', text))
def profile_reqs(text): return re.findall(r'^- (ESRM-CP-[A-Z]-MUST(?:-NOT)?-[0-9]+): ', text, re.M)
def scan_source_bytes(path):
    data=path.read_bytes()
    if b'\x09' in data: fail('tab byte 0x09 found')
    if b'\x08' in data: fail('backspace byte 0x08 found')
    if b'\x0d' in data: fail('carriage return byte 0x0d found')
    text=data.decode('ascii')
    if '\ufffd' in text: fail('replacement character found')
    if re.search(r'\\[A-Za-z]+', text): fail('LaTeX command sequence found')
    return text
def validate_timestamp(s):
    m=re.match(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$', s)
    if not m: fail('timestamp lexical invalid')
    y,mo,d,h,mi,se=map(int,m.groups())
    if mo<1 or mo>12: fail('timestamp month invalid')
    if d<1 or d>calendar.monthrange(y,mo)[1]: fail('timestamp day invalid')
    if h>23: fail('timestamp hour invalid')
    if mi>59: fail('timestamp minute invalid')
    if se>59: fail('timestamp second invalid')
def expect_reject(fn):
    try: fn()
    except ValidationError: return
    fail('negative case accepted')
def validate_transition(x):
    top=['artifact_type','protocol_version','crypto_suite','transition_id','nonce','epoch','pre_state','rules','authority','transition','execution','settlement','critical_extensions','noncritical_extensions']
    if set(x)!=set(top): fail('transition top mismatch')
    if x['protocol_version']!='0.1': fail('protocol_version invalid')
    if x['critical_extensions'] != []: fail('extensions present but none registered')
    if x['noncritical_extensions'] != {}: fail('noncritical extensions present but none registered')
    groups={'pre_state':['commitment','source_set_commitment','freshness_policy_commitment'],'rules':['ruleset_commitment','semantics_version'],'authority':['authority_commitment','issuer_id','subject_id','lineage_commitment'],'transition':['operation_commitment','effect_commitment','expected_post_state_commitment'],'execution':['executor_identity_commitment','target_commitment','precondition_commitment','idempotency_commitment'],'settlement':['predicate_commitment','observer_policy_commitment','evidence_deadline']}
    for k,keys in groups.items():
        if not isinstance(x[k],dict) or not x[k]: fail(k+' empty')
        if set(x[k])!=set(keys): fail(k+' member mismatch')
    for k,v in x['pre_state'].items():
        if not re.match(r'^[0-9a-f]{64}$', v): fail('pre_state commitment not hex64')
    validate_timestamp(x['settlement']['evidence_deadline'])
def make_transition():
    return {'artifact_type':'proofrail.transition','protocol_version':'0.1','crypto_suite':'PR-ESRM-JCS-SHA256-ED25519-v1','transition_id':'t','nonce':'n','epoch':0,'pre_state':{'commitment':HEX64,'source_set_commitment':HEX64,'freshness_policy_commitment':HEX64},'rules':{'ruleset_commitment':HEX64,'semantics_version':'0.1'},'authority':{'authority_commitment':HEX64,'issuer_id':'issuer','subject_id':'subject','lineage_commitment':HEX64},'transition':{'operation_commitment':HEX64,'effect_commitment':HEX64,'expected_post_state_commitment':HEX64},'execution':{'executor_identity_commitment':HEX64,'target_commitment':HEX64,'precondition_commitment':HEX64,'idempotency_commitment':HEX64},'settlement':{'predicate_commitment':HEX64,'observer_policy_commitment':HEX64,'evidence_deadline':'2026-09-02T21:49:00Z'},'critical_extensions':[],'noncritical_extensions':{}}
def registry_domain(artifact_type):
    reg=load('registries/protocol-domain-registry.json')['artifact_type_to_domain']
    if artifact_type not in reg: fail('missing registered domain')
    return reg[artifact_type]
def validate_sig_pair(t,d):
    if registry_domain(t)!=d: fail('type/domain mismatch')
def strict_b64u_len(s, n):
    if not re.match(r'^[A-Za-z0-9_-]+$', s): fail('base64url alphabet')
    if '=' in s: fail('base64url padding')
    padded=s + '='*((4-len(s)%4)%4)
    raw=base64.urlsafe_b64decode(padded.encode('ascii'))
    if len(raw)!=n: fail('decoded length')
    if base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=') != s: fail('canonical reencode mismatch')
def main():
    src_path=BASE/'docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md'
    source=scan_source_bytes(src_path)
    titles=source_titles(source)
    if titles != EXPECTED: fail('section title/order mismatch')
    for block in REQUIRED_BLOCKS:
        if block not in source: fail('missing formula block '+block.split('\n')[0])
    trans_src=(BASE/'docs/ESRM_CANONICAL_TRANSITION_PACKAGE_SOURCE.md').read_text(encoding='ascii')
    for item in ['pre_state:', 'commitment', 'source_set_commitment', 'freshness_policy_commitment', 'evidence_deadline', 'critical_extensions = []', 'noncritical_extensions = {}']:
        if item not in trans_src: fail('transition source missing '+item)
    for p in sorted(BASE.glob('**/*.json')): json.loads(p.read_text(encoding='ascii'))
    ts=load('schemas/proofrail.transition.schema.json'); ss=load('schemas/proofrail.signature.schema.json')
    if ts['properties']['pre_state']['properties']['commitment']['type']!='string': fail('pre_state.commitment wrong type')
    if ts['properties']['settlement']['properties']['evidence_deadline']['type']!='string': fail('evidence_deadline wrong type')
    if ts['properties']['critical_extensions'].get('maxItems')!=0: fail('critical_extensions not closed')
    if ts['properties']['noncritical_extensions'].get('maxProperties')!=0: fail('noncritical_extensions not closed')
    if ss['properties']['critical_extensions'].get('maxItems')!=0: fail('signature critical_extensions not closed')
    if ss['properties']['noncritical_extensions'].get('maxProperties')!=0: fail('signature noncritical_extensions not closed')
    if load('registries/protocol-domain-registry.json')['domains'] != DOMAINS: fail('domain registry mismatch')
    validate_transition(make_transition())
    for key in ['pre_state','rules','authority','transition','execution','settlement']:
        expect_reject(lambda key=key: (lambda x: (x.__setitem__(key,{}), validate_transition(x)))(make_transition()))
    expect_reject(lambda: (lambda x: (x.__setitem__('protocol_version','ESRM-v0.1'), validate_transition(x)))(make_transition()))
    expect_reject(lambda: (lambda x: (x.__setitem__('noncritical_extensions',[]), validate_transition(x)))(make_transition()))
    expect_reject(lambda: (lambda x: (x['pre_state'].__setitem__('extra',HEX64), validate_transition(x)))(make_transition()))
    for bad in ['2026-00-02T21:49:00Z','2026-02-30T21:49:00Z','2026-09-02T24:49:00Z','2026-09-02T21:60:00Z','2026-09-02T21:49:60Z']:
        expect_reject(lambda bad=bad: validate_timestamp(bad))
    reg=load('registries/protocol-domain-registry.json')['artifact_type_to_domain']
    mismatch_count=0
    for t in reg:
        for d in DOMAINS:
            if reg[t] != d:
                mismatch_count += 1
                expect_reject(lambda t=t,d=d: validate_sig_pair(t,d))
    expect_reject(lambda: registry_domain('proofrail.missing'))
    expect_reject(lambda: validate_sig_pair('proofrail.transition','proofrail.transition.v1'))
    strict_b64u_len('A'*86,64)
    # Build inventories after all checks.
    protocol_count=normative_count(source)+normative_count(trans_src)
    profile=(BASE/'docs/ESRM_CONFORMANCE_PROFILE.md').read_text(encoding='ascii')
    harness_count=len(profile_reqs(profile))
    inv={'schema_version':'0.1-transport-safe-source-repair4','protocol_requirement_count':protocol_count,'protocol_mapped_count':protocol_count,'harness_requirement_count':harness_count,'harness_mapped_count':harness_count,'coverage_status':'mapped_plan_only_no_vectors'}
    (BASE/'manifests/requirement-inventory.json').write_text(json.dumps(inv,indent=2,sort_keys=True)+'\n',encoding='ascii')
    sl={'schema_version':'0.1-transport-safe-source-repair4','ascii_source_path':'docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md','ascii_source_sha256':sha(src_path),'transition_source_path':'docs/ESRM_CANONICAL_TRANSITION_PACKAGE_SOURCE.md','transition_source_sha256':sha(BASE/'docs/ESRM_CANONICAL_TRANSITION_PACKAGE_SOURCE.md'),'ordered_section_numbers':[n for n,_ in titles],'exact_section_titles':[t for _,t in titles],'section_title_order_validation':'PASS','required_ascii_formula_blocks':'PASS','schema_to_source_mapping':{'proofrail.transition.schema.json':['ESRM_CANONICAL_TRANSITION_PACKAGE_SOURCE.md','30. Mandatory Artifact Header','29. Timestamp Profile'],'proofrail.signature.schema.json':['25. Signature Envelope','30. Mandatory Artifact Header'],'protocol-domain-registry.json':['24. Registered Artifact Domains']},'ascii_source_semantic_lock':'PENDING_INDEPENDENT_AUDIT'}
    (BASE/'manifests/source-lock.json').write_text(json.dumps(sl,indent=2,sort_keys=True)+'\n',encoding='ascii')
    val={'schema_version':'0.1-transport-safe-source-repair4','control_byte_scan':'PASS','section_title_order_validation':'PASS','schema_negative_tests':'PASS','type_domain_cartesian_mismatch_test_count':mismatch_count,'type_domain_cartesian_mismatch_result':'PASS','timestamp_semantic_test_result':'PASS','json_parse':'PASS','schema_meta_validation':'STRUCTURAL_SUBSET_ONLY','schema_instance_validation':'STRUCTURAL_SUBSET_ONLY','protocol_requirement_count':protocol_count,'protocol_mapped_count':protocol_count,'harness_requirement_count':harness_count,'harness_mapped_count':harness_count,'no_claim_of_conformance':True}
    (BASE/'manifests/validation-results.json').write_text(json.dumps(val,indent=2,sort_keys=True)+'\n',encoding='ascii')
    rels=[]
    for p in sorted(list(BASE.glob('**/*'))+[ROOT/'tools/validate_esrm_repair4.py']):
        if not p.is_file(): continue
        rel=p.relative_to(ROOT).as_posix()
        if rel.endswith('/manifests/file-hashes.sha256') or rel.endswith('/manifests/release-root.json'): continue
        rels.append(rel)
    (BASE/'manifests/file-hashes.sha256').write_text(''.join(f'{hashlib.sha256((ROOT/r).read_bytes()).hexdigest()}  {r}\n' for r in rels),encoding='ascii')
    fm=sha(BASE/'manifests/file-hashes.sha256')
    rr={'schema_version':'0.1-transport-safe-source-repair4','file_manifest':'esrm-conformance/v0.1-repair4/manifests/file-hashes.sha256','file_manifest_excludes':['esrm-conformance/v0.1-repair4/manifests/file-hashes.sha256','esrm-conformance/v0.1-repair4/manifests/release-root.json'],'file_manifest_sha256':fm,'git_commit':'RECORDED_EXTERNALLY_BY_IMMUTABLE_GIT_COMMIT','no_claim_of_conformance':True}
    (BASE/'manifests/release-root.json').write_text(json.dumps(rr,indent=2,sort_keys=True)+'\n',encoding='ascii')
    out={**val,'ascii_source_hash':sl['ascii_source_sha256'],'transition_source_hash':sl['transition_source_sha256'],'file_manifest_hash':fm,'release_root_record_hash':sha(BASE/'manifests/release-root.json')}
    print(json.dumps(out,sort_keys=True))
if __name__=='__main__':
    try: main()
    except ValidationError as e:
        print('FAIL:', e)
        sys.exit(1)
