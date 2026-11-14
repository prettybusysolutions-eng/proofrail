#!/usr/bin/env node
// Tenant-boundary fixture harness (Issue #82). Deterministic; no network except the optional
// static-scanner baseline (`npx mcp-tenant-isolation`). Usage:
//   node research/tenant-boundary/harness/run.mjs [--no-scanner] [--out <dir>]
//
// For the correct runtime and each defect variant it runs one fixed two-tenant workload, then:
//   ORACLE  fixture self-check with privileged access to every store (ground-truth confirmation;
//           NOT a candidate detector),
//   V1      the runtime's documented isolation settings + authentication check,
//   V2a     the open-source static scanner mcp-tenant-isolation, diffed against the correct variant,
//   V2b     a black-box cross-session probe battery in the style of promptfoo's cross-session-leak
//           and BOLA plugins (only sees outputs; plays both tenants; knows its own planted markers).

import { cpSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = resolve(HERE, '..');
const args = process.argv.slice(2);
const useScanner = !args.includes('--no-scanner');
const outDir = args.includes('--out') ? resolve(args[args.indexOf('--out') + 1]) : join(BASE, 'results');

const TENANTS = ['acme', 'globex'];
const TOKENS = { 'tok-acme': 'acme', 'tok-globex': 'globex' };
const BOTS = { acme: 'bot-acme', globex: 'bot-globex' };
const USER = 'u-100'; // the same person is a member of both tenants (realistic; needed for D3)
const mk = (t, surface) => `MK-${t}-${surface}`;
const RECORDS = Object.fromEntries(TENANTS.map((t) => [t, { 'q3-plan-1': `plan ${mk(t, 'rec')}` }]));
const MARKER_RE = /MK-(acme|globex)-[a-z]+/gi;

// ---------- variant generation ----------
function buildVariants(work) {
  const src = readFileSync(join(BASE, 'fixture', 'runtime.ts'), 'utf8');
  const { defects } = JSON.parse(readFileSync(join(BASE, 'defects.json'), 'utf8'));
  const variants = [{ id: 'C0-correct', boundary: null, dir: join(work, 'C0-correct') }];
  mkdirSync(variants[0].dir, { recursive: true });
  writeFileSync(join(variants[0].dir, 'runtime.ts'), src);
  for (const d of defects) {
    const lines = src.split('\n');
    const hits = lines.map((l, i) => (l.includes(`// @anchor:${d.anchor}`) ? i : -1)).filter((i) => i >= 0);
    if (hits.length !== 1) throw new Error(`${d.id}: anchor ${d.anchor} matched ${hits.length} lines`);
    const i = hits[0];
    const indent = lines[i].match(/^\s*/)[0];
    lines[i] = `${indent}${d.replacement} // DEFECT ${d.id}`;
    const dir = join(work, d.id);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'runtime.ts'), lines.join('\n'));
    variants.push({ id: d.id, boundary: d.boundary, dir });
  }
  return variants;
}

// ---------- workload ----------
function auth(t) { return { tenantToken: Object.keys(TOKENS).find((k) => TOKENS[k] === t), user: USER, botId: BOTS[t] }; }

function workload(rt, outputs) {
  const turn = (t, s, a) => { const o = rt.turn(s, a); outputs.push({ tenant: t, action: a, out: o, phase: 'workload' }); return o; };
  const sessions = {};
  for (const t of TENANTS) sessions[t] = rt.openSession(auth(t));
  for (const t of TENANTS) {
    const s = sessions[t];
    turn(t, s, { op: 'remember', text: `note ${mk(t, 'mem')}` });
    turn(t, s, { op: 'summarize', topic: 'q3-plan' });
    turn(t, s, { op: 'artifact', name: 'notes.txt', text: `draft ${mk(t, 'art')}` });
    turn(t, s, { op: 'delegate', task: { op: 'remember', text: `sub ${mk(t, 'dlg')}` } });
    turn(t, s, { op: 'get_record', id: 'q3-plan-1' });
  }
  // adversarial step inside the workload: tenant globex's model is induced to name acme's tenant
  turn('globex', sessions.globex, { op: 'get_record', id: 'q3-plan-1', tenant_id: 'acme' });
  return sessions;
}

const PROBES = (victim) => [
  { op: 'recall' },
  { op: 'history' },
  { op: 'summarize', topic: 'q3-plan' },
  { op: 'get_record', id: 'q3-plan-1', tenant_id: victim },
  { op: 'delegate', task: { op: 'recall' } },
  { op: 'list_artifacts' },
  { op: 'read_logs' },
  { op: 'consolidate' },
  { op: 'recall' },
];

// ---------- ORACLE: privileged self-check ----------
function walk(dir) {
  const out = [];
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) out.push(...walk(p)); else out.push(p);
  }
  return out;
}
function ownerOfPath(root, p) {
  const parts = relative(root, p).split(sep);
  return parts[0] === 'tenants' && TENANTS.includes(parts[1]) ? parts[1] : 'shared';
}
function ownerOfKey(key) { return TENANTS.find((t) => key.split(':').includes(t)) ?? 'shared'; }
function markerTenants(text) { return [...new Set([...String(text).matchAll(MARKER_RE)].map((m) => m[1].toLowerCase()))]; }

function oracle(rt, outputs) {
  const v = [];
  for (const f of walk(rt.root)) {
    const owner = ownerOfPath(rt.root, f);
    for (const t of markerTenants(readFileSync(f, 'utf8'))) if (t !== owner) v.push({ store: `file:${relative(rt.root, f)}`, owner, foreign: t });
  }
  for (const [k, lines] of rt.sessions) for (const t of markerTenants(lines.join('\n'))) if (t !== ownerOfKey(k)) v.push({ store: `session:${k}`, owner: ownerOfKey(k), foreign: t });
  for (const [k, val] of rt.cache) for (const t of markerTenants(val)) if (t !== ownerOfKey(k)) v.push({ store: `cache:${k}`, owner: ownerOfKey(k), foreign: t });
  for (const o of outputs) for (const t of markerTenants(o.out)) if (t !== o.tenant) v.push({ store: `output:${o.phase}:${o.action.op}`, owner: o.tenant, foreign: t });
  return v;
}

// ---------- V2b: black-box probe battery ----------
function blackBox(rt, outputs) {
  const seen = (o) => markerTenants(o.out).some((t) => t !== o.tenant);
  let probesRun = 0;
  const firstHit = outputs.find(seen);
  if (firstHit) return { detected: true, probesRun, via: `workload:${firstHit.action.op}` };
  for (const attacker of TENANTS) {
    const victim = TENANTS.find((t) => t !== attacker);
    for (const fresh of [false, true]) {
      const s = rt.openSession(fresh ? { ...auth(attacker), user: 'u-probe' } : auth(attacker));
      for (const a of PROBES(victim)) {
        const o = { tenant: attacker, action: a, out: rt.turn(s, a), phase: 'probe' };
        outputs.push(o); probesRun++;
        if (seen(o)) return { detected: true, probesRun, via: `probe:${attacker}:${fresh ? 'fresh' : 'same-user'}:${a.op}` };
      }
    }
  }
  return { detected: false, probesRun, via: null };
}

// ---------- V1: documented settings + authentication ----------
function v1(mod, rt) {
  const s = mod.ISOLATION_SETTINGS;
  const settingsClaimIsolation = Object.values(s).every((x) => ['per-tenant', 'bot+tenant+user', 'tenant-keyed', 'tenant-from-session', 'inherit-session', 'deny'].includes(x));
  let deniesUnauth = false;
  try { rt.openSession({ tenantToken: 'tok-unknown', user: USER, botId: 'x' }); } catch { deniesUnauth = true; }
  return { detected: !(settingsClaimIsolation && deniesUnauth), settingsClaimIsolation, deniesUnauth };
}

// ---------- V2a: static scanner ----------
// The published package's `mti` bin lacks a shebang in 2.0.0, so install it into a temp prefix and
// run its CLI entry with node directly.
const SCANNER_VERSION = '2.0.0';
let scannerCli = null;
function scannerEntry(work) {
  if (scannerCli) return scannerCli;
  const prefix = join(work, 'scanner');
  mkdirSync(prefix, { recursive: true });
  execFileSync('npm', ['install', '--silent', '--no-audit', '--no-fund', '--prefix', prefix, `mcp-tenant-isolation@${SCANNER_VERSION}`], { stdio: 'ignore', timeout: 300000 });
  scannerCli = join(prefix, 'node_modules', 'mcp-tenant-isolation', 'dist', 'cli', 'index.js');
  return scannerCli;
}
function scan(work, dir) {
  try {
    const raw = execFileSync(process.execPath, [scannerEntry(work), 'scan', '-p', dir, '-f', 'json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 300000 });
    return { ok: true, raw };
  } catch (e) {
    if (e.stdout) return { ok: true, raw: String(e.stdout) }; // non-zero exit when findings exist
    return { ok: false, error: String(e.message).slice(0, 300) };
  }
}
// Defects replace one line without changing line numbers, so rule + line + snippet identifies a finding.
function findingKeys(raw) {
  try {
    const j = JSON.parse(raw);
    return (j.findings ?? []).map((f) => `${f.ruleId}|L${f.evidence?.lineStart}|${f.evidence?.codeSnippet ?? ''}`);
  } catch { return null; }
}

// ---------- functional checks (guard against vacuous isolation) ----------
function functional(rt, sessions) {
  const own = rt.turn(sessions.acme, { op: 'recall' });
  return { ownRecallWorks: own.toLowerCase().includes(mk('acme', 'mem').toLowerCase()) };
}

// ---------- main ----------
const work = mkdtempSync(join(tmpdir(), 'tenant-boundary-'));
const variants = buildVariants(work);
const results = [];
let correctScan = null;
for (const v of variants) {
  const t0 = performance.now();
  const mod = await import(join(v.dir, 'runtime.ts'));
  const root = join(work, 'state', v.id);
  mkdirSync(root, { recursive: true });
  const rt = new mod.Runtime(root, TOKENS, RECORDS);
  const outputs = [];
  const sessions = workload(rt, outputs);
  const atRestState = oracle(rt, []); // stored state only, before any probe
  const workloadOracle = oracle(rt, outputs);
  const bb = blackBox(rt, outputs);
  const finalOracle = oracle(rt, outputs);
  const fn = functional(rt, sessions);
  const v1r = v1(mod, rt);
  const ms = performance.now() - t0;
  let scanner = null;
  if (useScanner) {
    const s = scan(work, v.dir);
    const keys = s.ok ? findingKeys(s.raw) : null;
    if (v.id === 'C0-correct') correctScan = keys;
    const extra = keys && correctScan ? keys.filter((k) => !correctScan.includes(k)) : null;
    scanner = {
      ok: s.ok,
      findings: keys ? keys.length : null,
      all: keys,
      newVsCorrect: extra,
      // On the correct variant, any finding is a false alarm; on a defect variant, only new findings count.
      detected: v.id === 'C0-correct' ? (keys ? keys.length > 0 : null) : (extra ? extra.length > 0 : null),
      error: s.ok ? undefined : s.error,
      rawHead: s.ok && !keys ? s.raw.slice(0, 400) : undefined,
    };
  }
  results.push({
    variant: v.id,
    boundary: v.boundary,
    groundTruthLeak: v.id !== 'C0-correct',
    oracle: { atRestStateViolations: atRestState.length, afterWorkloadViolations: workloadOracle.length, finalViolations: finalOracle.length, sample: finalOracle.slice(0, 4) },
    blackBox: bb,
    v1: v1r,
    scanner,
    functional: fn,
    ms: Math.round(ms * 10) / 10,
  });
}

mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, 'results.json'), JSON.stringify({ generatedAt: new Date().toISOString(), node: process.version, scanner: useScanner ? 'mcp-tenant-isolation@2.0.0' : 'skipped', results }, null, 2));

const yn = (b) => (b === null || b === undefined ? 'n/a' : b ? 'YES' : 'no');
const rows = results.map((r) => `| ${r.variant} | ${r.boundary ?? '—'} | ${yn(r.groundTruthLeak)} | ${r.oracle.atRestStateViolations} / ${r.oracle.finalViolations} | ${yn(r.v1.detected)} | ${r.scanner ? yn(r.scanner.detected) : 'skipped'} | ${yn(r.blackBox.detected)} (${r.blackBox.via ?? '-'}, probes ${r.blackBox.probesRun}) | ${yn(r.functional.ownRecallWorks)} | ${r.ms} |`);
const md = [
  '| Variant | Boundary | Ground-truth leak | Oracle violations (at rest / final) | V1 settings+auth | V2a static scanner (new findings vs correct) | V2b black-box probes | Own-tenant recall works | ms |',
  '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
  ...rows,
].join('\n');
writeFileSync(join(outDir, 'RESULTS.md'), md + '\n');
console.log(md);
rmSync(work, { recursive: true, force: true });
