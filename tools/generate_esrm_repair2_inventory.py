#!/usr/bin/env python3
import json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'esrm-conformance/v0.1-repair2'
REQ_RE=re.compile(r'^- (?P<id>ESRM-[PH][0-9]+-MUST(?:-NOT)?-[0-9]+): (?P<sentence>.+)$')
def collect(path, source):
    rows=[]; section='UNKNOWN'
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('## '): section=line[3:].strip()
        m=REQ_RE.match(line)
        if m:
            rid=m.group('id'); neg='MUST-NOT' in rid or 'MUST NOT' in m.group('sentence')
            rows.append({
                'requirement_id':rid,
                'source_document':source,
                'section':section,
                'normative_sentence':m.group('sentence'),
                'enforcement_stage':infer_stage(m.group('sentence')),
                'positive_vector_ids':[] if neg else [rid+'-POS-PLAN'],
                'negative_vector_ids':[rid+'-NEG-PLAN'],
                'implementation_track':'rust_and_go_future_independent_tracks',
                'coverage_status':'planned_not_generated'
            })
    return rows
def infer_stage(s):
    l=s.lower()
    for key,stage in [('raw','RAW_INTAKE'),('utf-8','UTF8_DECODE'),('json','JSON_PARSE'),('schema','SCHEMA_VALIDATION'),('numeric','NUMERIC_PROFILE'),('canonical','CANONICALIZATION'),('domain','DOMAIN_REGISTRY'),('commitment','COMMITMENT'),('signature','SIGNATURE_VERIFICATION'),('key','KEY_RESOLUTION'),('authority','AUTHORITY_SEPARATION'),('resource','RESOURCE_LIMIT'),('binary','CORPUS_MANIFEST'),('manifest','CORPUS_MANIFEST'),('rust','DEPENDENCY_INDEPENDENCE'),('go','DEPENDENCY_INDEPENDENCE'),('audit','IMPLEMENTATION_GATE')]:
        if key in l: return stage
    return 'SEMANTIC_VALIDATION'
def main():
    protocol=collect(BASE/'docs/ESRM_PROTOCOL_SECTIONS_22_40.md','ESRM_PROTOCOL_SECTIONS_22_40.md')
    harness=collect(BASE/'docs/ESRM_CONFORMANCE_HARNESS_REQUIREMENTS.md','ESRM_CONFORMANCE_HARNESS_REQUIREMENTS.md')
    inv={'schema_version':'0.1-repair2','protocol_requirement_count':len(protocol),'harness_requirement_count':len(harness),'protocol_requirements':protocol,'harness_requirements':harness}
    (BASE/'manifests/requirement-inventory.json').write_text(json.dumps(inv,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    plan={'artifact_kind':'binary-vector-plan','schema_version':'0.1-repair2','populated_binary_vectors':False,'requirements':[{'requirement_id':r['requirement_id'],'planned_vector_ids':r['positive_vector_ids']+r['negative_vector_ids'],'status':'stopped_by_ambiguity' if r['requirement_id'] in {'ESRM-P00-MUST-001','ESRM-P00-MUST-NOT-001'} else 'planned'} for r in protocol+harness]}
    (BASE/'manifests/binary-vector-plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    md=['# ESRM Repair 2 Test Inventory','','This inventory is generated from the protocol document and harness document, not from a generated lexical profile. Planned vector IDs are not executable binary vectors.']
    for r in protocol+harness:
        md.append(f"- `{r['requirement_id']}` ({r['source_document']} / {r['section']}): {r['normative_sentence']} Planned: {', '.join(r['positive_vector_ids']+r['negative_vector_ids'])}.")
    (BASE/'docs/TEST_INVENTORY.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
if __name__=='__main__': main()
