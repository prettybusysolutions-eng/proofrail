# Round 1 — Claude A–H Research (source-text archival import)

> **Source:** Founder-supplied 24-page PDF titled 'Round 1 — A–H analysis', authored November 13, 2026. This file is a text-only transcription preserving page order; the original PDF's graphics/tables are not fully represented. Use the original PDF to interpret diagrams and complex tables. Claims are the author's research claims, not independently verified facts. The Round 1 thesis is explicitly superseded by the correction described on page 1 and follow-up Round 2 research. No customer or private operational data is intended to be included here.

## Source PDF page 1

~~~text
Round 1 — A–H analysis




  Project Axiom — Claude's Adversarial
  Analysis
    Nov 13, 2026         ·   ​@Aurex   · Response to the Architect-to-Architect brief


  Bottom line

      Correction (Round 2): Postcept and Pruvz already sell per-claim effect verification,
      which my Round 1 searches missed. The Effect Oracle is not an open category.
      Revised analysis: ​Round 2 — response to GPT-6

  Do not build Axiom as specified. Six of its seven pillars now have a funded standard or
  incumbent: tool authorization (MCP 2026-07-28 + Enterprise-Managed Authorization),
  agent identity (A2A v1.0 signed agent cards), payment authority (AP2 at FIDO, Visa TAP,
  Mastercard Verifiable Intent), durable execution (Temporal's GA agent-framework
  integrations), settlement (x402 Foundation, Stripe MPP) and signed receipts (at least
  eight IETF drafts plus several shipping tools).

  The gap they all defer is one question: did the claimed effect actually happen in the
  system of record, as observed by a party that is not paid for the claim? Receipts prove
  who said what. Mandates prove who allowed what. Nothing standard proves the world
  changed.

  Recommendation: narrow to an Effect Oracle — single-use authority consumed before a
  side effect, independent read-back of provider state, and a signed PASS / FAIL /
  UNKNOWN verdict that billing, escrow, reputation registries and insurers can settle
  against. The founder's Grantifold (ex-ProofRail) repo already implements the core loop; its
  137 tests passed when I ran them.

  The weak point is demand, not engineering. The agent-as-buyer market is still mostly
  signal, not commerce. The first paying buyer is more likely a human: a company paying an
  AI vendor per "resolution" with no independent way to check the count.

  First proof: a free, local + GitHub CI harness that shows the oracle catches false-success
  and duplicate-effect claims that a strong baseline (durable workflow + idempotency keys
  + operator-signed logs) cannot — specifically when the operator lies. If the baseline
  matches us, the technical thesis is dead and only neutrality remains.




                                                                                          Page 1 of 24
~~~

## Source PDF page 2

~~~text
Round 1 — A–H analysis




  A — Competitive reality
  Every layer Axiom planned to own has a named owner as of November 2026; the open
  space is between layers, not inside one. Status below is from public docs and reporting
  found by search (Sources at the end); none of it was verified by running the products.


     Layer               Incumbent /          What it         What it leaves        Our stance
                         standard (status)    covers          open

     Personal            OpenClaw —           Agent loop,     Skill supply chain:   Integrator and
     agent runtime       open-source, self-   memory,         Koi found 341         channel, not
                         hosted, MCP          channels,       malicious of 2,857    competitor
                         tools, sub-agents,   skills          ClawHub skills
                         ClawHub skills                       (Feb 2026); Unit
                         market                               42 found more
                                                              evading scans
                                                              through May

     Personal            Hermes Agent         Model-          Governance of         Integrator and
     agent runtime       (Nous, MIT, Feb      agnostic        learned skills;       channel
                         2026) — self-        harness,        proof of results
                         improving, writes    learning loop   to third parties
                         skills from
                         experience, MCP,
                         cron, Nous Portal
                         billing

     Consumer            Meta Muse (US,       Full stack,     Nothing we can        Ignore as
     agent               Sep 8 2026) —        closed          plug into             customer; it
                         cloud Secure VM,                                           proves
                         shops and pays                                             platforms keep
                         with user's card;                                          consumer trust
                         credentials in a                                           in-house
                         store the agent
                         can't read




                                                                                                 Page 2 of 24
~~~

## Source PDF page 3

~~~text
Round 1 — A–H analysis




     Layer               Incumbent /          What it          What it leaves       Our stance
                         standard (status)    covers           open

     Durable             Temporal — GA        Retries, crash   Same-operator        Reuse; do not
     execution           integrations (Oct    recovery,        history: the party   build pillar D
                         30 2026) for         history          that ran the work
                         OpenAI Agents                         also writes the
                         SDK, Google ADK,                      record
                         AWS Strands,
                         LangGraph,
                         Vercel AI SDK

     Tool                MCP 2026-07-28       Who may call     Multi-hop            Consume
     authorization       — OAuth 2.1          which server     delegation is        tokens; don't
                         resource servers,                     unaccountable        issue them
                         Enterprise-                           per Tigera;
                         Managed                               runtime per-
                         Authorization (ID-                    action policy left
                         JAG), client-                         to engines
                         credentials                           (Permit.io)
                         extension

     Agent-to-           A2A v1.0 — 150+      Discovery,       A signed card        Ship as an A2A
     agent               orgs, signed         identity, task   proves identity,     extension
                         agent cards;         lifecycle        not authority or
                         hosted by AAIF                        outcome
                         since Aug 17 2026

     Payment             AP2 (donated to      User intent →    Whether the          Read mandates
     authority           FIDO Apr 2026),      signed           purchased work       as contract
                         Visa TAP,            mandate →        was delivered        input
                         Mastercard           checkout
                         Verifiable Intent;
                         joint KYA
                         framework (Sep
                         10 2026)




                                                                                                 Page 3 of 24
~~~

## Source PDF page 4

~~~text
Round 1 — A–H analysis




     Layer               Incumbent /          What it         What it leaves       Our stance
                         standard (status)    covers          open

     Settlement          x402 Foundation      HTTP-native     Conditional          Emit verdicts a
                         (LF, Jul 14 2026,    pay-per-call    release on           facilitator can
                         40 members);                         verified delivery;   gate on; never
                         Stripe MPP                           Forkast estimates    hold funds
                                                              ~95% of headline
                                                              volume is
                                                              signaling

     Signed              IETF drafts (sahu,   Tamper-         Truth of the claim   Commodity:
     receipts            farley-acta,         evident         about the outside    adopt one
                         marques-asqav,       record of       world                format, don't
                         sharif, noa-scitt,   what the                             invent
                         emirdag-scitt,       agent says it
                         thaha-scitt,         did
                         xkumakichi);
                         Signet; Microsoft
                         AGT proposal;
                         Archipelo Salmon
                         EVI (Sep 25 2026)

     Observability       OTel GenAI           Spans for       Not evidence; no     Emit verdicts
                         conventions —        agent, tool,    independence         as span events
                         Development          model calls
                         status, own repo
                         since Jun 12 2026

     Reputation /        ERC-8004 (draft)     Where           Who actually         Be a validator,
     validation          — identity,          verdicts get    validates off-       not a registry
                         reputation,          posted          chain work
                         validation
                         registries

     Agent               Virtuals ACP         Job escrow      Evaluator            Potential
     marketplaces        (escrow +            and evaluator   honesty; analysts    evaluator
                         evaluator agents),   hook            question self-       customer,
                         Olas Mech                            reported "aGDP"      crypto-only




                                                                                                 Page 4 of 24
~~~

## Source PDF page 5

~~~text
Round 1 — A–H analysis




     Layer                  Incumbent /         What it          What it leaves       Our stance
                            standard (status)   covers           open

     Certification          AIUC-1 — SOC 2-     Point-in-time    Continuous per-      Evidence
     + insurance            style standard,     audit +          action loss          supplier, later
                            first policy        coverage         evidence
                            (ElevenLabs) Feb
                            2026, $40M Series
                            A Sep 2026, Drata
                            support

     Outcome-               Intercom Fin        The work         The vendor           First buyer
     priced agents          $0.99/outcome;      itself           defines and          pain (see G)
                            Zendesk ~$1.50–                      counts the
                            2.00; Sierra,                        billable outcome
                            Decagon




  The seven experiments, judged
  Only B survives as a product; A and D survive as small primitives inside it; C, E and F are
  downstream consumers we should feed, not build.


     #          Idea                  Already exists?                   Verdict

     A          Outcome               Partly: AP2 Checkout/Payment      Keep, thin. A contract is only
                contracts             mandates bound purchase           worth something if a verifier
                                      scope; Virtuals ACP has job       can evaluate it. Write
                                      terms. No standard binds a        success as a postcondition
                                      success postcondition plus a      over observable provider
                                      verification procedure for non-   state, with an explicit
                                      purchase work.                    UNKNOWN when the state
                                                                        is not observable (formal-
                                                                        methods lesson: most real
                                                                        outcomes are only partially
                                                                        observable).




                                                                                                   Page 5 of 24
~~~

## Source PDF page 6

~~~text
Round 1 — A–H analysis




     #          Idea                Already exists?                   Verdict

     B          Agent-              Receipts are everywhere, but      The core. Independence
                independent trust   every receipt is signed by the    comes from who observes
                                    party making the claim.           (separate identity, read-only
                                    Cryptography proves who said      credentials, separate key),
                                    it, not that it is true.          not from better signatures.

     C          Outcome router      Model routing exists              Defer. Becomes possible
                                    (OpenRouter); agent               only after the oracle
                                    marketplaces own their own        accumulates per-agent
                                    matching. A router needs          verdict history.
                                    verified-outcome history we
                                    don't have.

     D          Failure-resistant   Temporal and peers cover          Don't build. Keep one
                execution           retries, recovery, compensation   primitive: a single-use permit
                                    inside one operator.              consumed before the effect,
                                                                      which acts as a fencing token
                                                                      across org boundaries where
                                                                      no shared workflow engine
                                                                      exists.

     E          Evidence-backed     Hermes already turns              Design rule, not product.
                learning            experience into skills;           Learned behavior may
                                    Grantifold already denies the     propose; only verdict-
                                    learner a policy-promotion key.   backed evidence plus a
                                                                      governor key may promote.

     F          Economic            x402, AP2, ACP escrow, ERC-       Feed it, don't hold money.
                coordination        8004 reputation.                  Escrow, disputes, KYC and
                                                                      liability are regulated; a solo
                                                                      founder holding funds risks
                                                                      money-transmission rules.
                                                                      Emit verdicts that others'
                                                                      escrow releases on.



  G — The missing eighth category: Recall
  When something an agent relied on turns out to be bad, nobody can answer "what did it
  touch?" A malicious ClawHub skill, a buggy tool version, a revoked delegation, a policy
  later found wrong, a model that was tampering with its own traces — each needs three



                                                                                                  Page 6 of 24
~~~

## Source PDF page 7

~~~text
Round 1 — A–H analysis




  answers fast:

        1. Which past effects depended on it (blast radius)?
        2. Which in-flight authorities must be revoked, and how fast does revocation reach
          every agent running for weeks?
        3. Which outcomes must be re-verified, compensated or disclosed?

  Adjacent disciplines already solved halves of this: product recall and food traceability,
  CVE-to-SBOM impact analysis (Dependency-Track), certificate revocation (CRL/OCSP
  latency), financial restatement. Sigstore and in-toto trace build artifacts; nothing I found
  traces runtime effects back to the skill, tool, model and policy versions that produced
  them. The ClawHub incidents show the trigger events are real and recurring.

  Recall is cheap to add once every verdict records its provenance tuple (agent, skill/tool
  versions, model, policy hash, permit). That makes it the oracle's natural second product,
  not a separate company.


  G2 — Audit sampling (runner-up)
  Full verification of every action can cost more than the action. Financial auditing settled
  this decades ago with statistical sampling: verify a random sample, report an error rate
  with a confidence bound, escalate when it exceeds tolerance. An oracle that supports
  sampled verification can price verification per action and still give a buyer a defensible
  number. Incumbent: none for agents that I found; the method itself is standard (attribute
  sampling, sequential testing).


  B — Discovery map
  The independent effect verifier ranks first; signed receipts, routing and escrow rank last
  because incumbents or regulation own them. Scores are my judgment, 1 (worst) to 5
  (best); "Build cost" 5 = cheapest for one founder at $0 infra.


    Rank       Opportunity             Urgency Differentiation Integration   Build   Demonstrability Total
                                                               ease          cost

    1          Effect Oracle —         4        5              4             3       5               21
               independent read-back
               of provider state,
               signed
               PASS/FAIL/UNKNOWN
               verdict




                                                                                                      Page 7 of 24
~~~

## Source PDF page 8

~~~text
Round 1 — A–H analysis




    Rank       Opportunity                Urgency Differentiation Integration   Build   Demonstrability Total
                                                                  ease          cost

    2          Outcome-bill audit —       4        4              3             4       5               20
               recheck what an
               outcome-priced AI
               vendor billed against
               the customer's own
               records

    3          Cross-boundary fence       3        3              4             4       5               19
               — single-use permit
               consumed before
               effect (exactly-once
               without a shared
               workflow engine)

    4          Audit sampling —           3        4              4             4       4               19
               statistically bounded
               verification at a chosen
               cost (G2)

    5          Agent change gate —        4        2              4             5       4               19
               permits for agent-made
               merges and migrations
               (Grantifold today)

    6          Recall — provenance-       3        5              3             3       4               18
               indexed blast radius
               and revocation
               propagation (G)

    7          Skill provenance gate      4        2              4             3       4               17
               for agent skill markets

    8          Signed receipt format      2        1              5             5       4               17

    9          Continuous verdict         3        4              2             3       3               15
               evidence for AI insurers
               / AIUC-1 audits

    10         Learned-skill promotion    2        4              3             3       3               15
               governance (Hermes-
               style agents)

    11         Multi-hop delegation       3        3              2             2       3               13
               accountability for MCP
               chains

    12         Outcome router across      2        3              2             2       2               11
               agent providers




                                                                                                         Page 8 of 24
~~~

## Source PDF page 9

~~~text
Round 1 — A–H analysis




    Rank       Opportunity             Urgency Differentiation Integration   Build   Demonstrability Total
                                                               ease          cost

    13         Escrow / conditional    2        1              2             1       3               9
               settlement we operate


  Three notes on the ranking:

         #7 is crowded. ClawHub already added VirusTotal and ClawScan screening after the
         February incidents; supply-chain security vendors are on it.
         #5 has real buyers but a giant neighbor. GitHub rulesets and required reviews sit one
         feature away. Use it as the first adapter, not the company.
         #8 total is misleading. Easy and demonstrable, but differentiation 1 means anything
         we ship there is a commodity on arrival.



  C — Strongest discovery: the Effect Oracle
  Own the verdict, not the agent stack. An Effect Oracle answers one question for a party
  that does not trust the agent's operator: is the claimed effect now true in the system of
  record? It returns PASS, FAIL or UNKNOWN, signed by a key the operator never holds,
  with the observation that justifies it.

  How it differs from what exists:


     Artifact                    Answers                Signed by                Trust gap

     Mandate (AP2,               Was the agent          User / issuer            Says nothing about
     Verifiable Intent)          allowed to do X?                                delivery

     Receipt (IETF drafts,       Does the agent         Agent or operator        The claimant signs its
     Signet)                     claim it did X?                                 own claim

     Durable history             What steps ran?        Operator's               Same party runs and
     (Temporal)                                         infrastructure           records

     Verdict (Effect             Is X true in the       Independent              Bounded by what the
     Oracle)                     provider now?          observer                 provider exposes


  Why OpenClaw or Hermes developers would adopt rather than build it:




                                                                                                      Page 9 of 24
~~~

## Source PDF page 10

~~~text
Round 1 — A–H analysis




     1. Conflict of interest. A platform verifying its own agents' success is self-grading.
         Buyers, insurers and counterparties discount it, the same reason companies hire
         outside auditors.
     2. Adapter semantics are tedious and shared. What "done" means, how long eventual
        consistency lasts, and how idempotency behaves differ per system (GitHub, Stripe,
         Shopify, Zendesk, QuickBooks, DNS). One shared library beats every platform
         rediscovering them.
     3. Standards already have a slot for it. ERC-8004's Validation Registry, Virtuals ACP's
         evaluator role and an A2A extension all need a validator; none supplies one.

  What could make it non-commodity (honestly weak at first):

         A calibrated record of false-success rates per agent, tool and adapter — data nobody
         else collects independently.
         Recall (G) built on the same provenance records.
         Neutrality as a reputation, which takes years and is lost in one scandal.

  Adapters alone are copyable. If the verdict history never accumulates because volume
  never arrives, this is a feature, not a company.

  Do the founder's projects combine into an advantage? Partly. Grantifold supplies
  authority + reconciliation, VerifiAgent supplies the PASS/FAIL/PARTIAL evidence
  contract, x402-mcp-server supplies settlement evidence, LeakLock supplies billing-
  anomaly detection. Together they cover "authorize → observe → verdict → settle/bill" end
  to end. That is a coherent product line; it is not yet proof anyone will pay.



  D — Systems architecture
  The oracle sits beside the agent runtime, never inside it. The agent keeps executing in
  OpenClaw, Hermes or a Temporal workflow; the oracle issues authority before the effect
  and judges the effect after, from a separate trust domain.




                                                                                          Page 10 of 24
~~~

## Source PDF page 11

~~~text
Round 1 — A–H analysis




  Effect Oracle architecture · 4 trust domains, authorize → consume → act → observe → verdict

  The agent keeps running where it runs today. The oracle only fences the permit it
  consumes and judges the effect from the provider's own state, never from the agent's
  claim.




                                                                                                Page 11 of 24
~~~

## Source PDF page 12

~~~text
Round 1 — A–H analysis




  Components and interfaces

     Component           Domain     Input → output       Persistent state   Reuse

     Contract            Buyer      Intent (+ optional   Spec store         New, small
     compiler                       AP2 mandate /
                                    A2A task) →
                                    effect spec:
                                    target,
                                    postcondition,
                                    observation
                                    window, budget,
                                    expiry

     Authority           Buyer or   Effect spec +        Issued permits     Grantifold permit;
     issuer              oracle     policy decision →                       OPA/Cedar for
                                    signed single-use                       policy
                                    permit

     Fence               Oracle     Permit → atomic      Consumption log,   Grantifold
     (consume                       consume record       replay root,       consume_permit
     registry)                      before the side      external
                                    effect               checkpoint

     Executor            Agent      Consumed permit      None of ours       OpenClaw bridge
     hook                operator   → effect on                             (exists), Hermes via
                                    provider; agent's                       MCP, Temporal
                                    own claim                               activity wrapper

     Observer            Oracle     Effect spec →        Observation        GitHub + SQLite
     adapters                       provider read-       records            adapters exist
                                    back with read-
                                    only credentials
                                    the executor
                                    never holds

     Verdict             Oracle     Spec +               Verdict log        VerifiAgent
     engine                         observations +                          evidence contract
                                    claim → PASS /
                                    FAIL / UNKNOWN
                                    + reason code




                                                                                              Page 12 of 24
~~~

## Source PDF page 13

~~~text
Round 1 — A–H analysis




     Component           Domain   Input → output          Persistent state     Reuse

     Evidence log        Oracle   Verdicts →              Hash chain +         Adopt one IETF
                                  append-only,            anchors (Rekor       receipt/SCITT profile
                                  checkpointed,           or a public Git
                                  exportable bundle       repo)

     Consumers           Anyone   Verdict → billing       Theirs               Adapters only
                                  meter, x402
                                  facilitator gate,
                                  ERC-8004
                                  validation
                                  response, OTel
                                  span event,
                                  insurer evidence



  Trust boundaries (the non-negotiables)
         The executor never holds the observer's credentials, the verdict key or the permit-
         signing key.
         The verdict key differs from the permit key: issuing authority and judging outcomes
         are separate roles.
         The buyer pins public keys out of band; the public demo's bundled test keys prove
         nothing about origin (Grantifold's README already says this).
         The learner may propose policy changes; only a governor key promotes them.


  Failure handling

     Failure                                          Required behavior

     Executor crashes after consume, before           Observer finds no effect →
     effect                                           FAIL_NOT_EXECUTED. Authority stays spent;
                                                      a new permit is required. Never auto-retry.

     Timeout or 5xx after the provider                Observer reconciles within the window →
     committed                                        PASS if the effect is present. The agent's
                                                      "failed" claim is overruled.




                                                                                                   Page 13 of 24
~~~

## Source PDF page 14

~~~text
Round 1 — A–H analysis




     Failure                                              Required behavior

     Eventual consistency                                 Re-observe on a schedule until the window
                                                          closes; then UNKNOWN, which bills as not-
                                                          success.

     Observer or provider API outage                      Verdict deferred. Never PASS by default.

     Replay registry deleted or rolled back               Fail closed against the external checkpoint
                                                          (Grantifold REPLAY-002 covers this).

     Effect applied, then reverted before                 Postcondition must specify "holds at time T",
     observation                                          not "ever happened"; record both.

     Provider itself lies or is compromised               Out of scope; mitigate with dual sources
                                                          where they exist (webhook + API read).




  E — Integration strategy
  Build only the observer, the verdict engine and the fence; everything else is borrowed
  or adapted. All items below are free and open-source or free public services; none needs
  paid infrastructure for the first proof.


     Decision            Technology                              How we use it

     Reuse               Ed25519 signatures, DSSE / in-toto      Verdict format, so existing verifiers can
     now                 attestation envelope                    parse it

     Reuse               Sigstore Rekor (public instance) or a   Anchor log checkpoints outside our
     now                 public Git repo                         own control

     Reuse               OPA or Cedar                            Policy decisions before permit issue;
     now                                                         we don't write a policy language

     Reuse               MCP                                     Ship the oracle as an MCP server
     now                                                         (agents request permits / verdicts)

     Reuse               OpenTelemetry                           Emit each verdict as a span event
     now                                                         linked to the agent's invoke_agent /
                                                                  execute_tool spans

     Reuse               SQLite, GitHub Actions                  State and CI, as Grantifold already does
     now




                                                                                                     Page 14 of 24
~~~

## Source PDF page 15

~~~text
Round 1 — A–H analysis




     Decision            Technology                            How we use it

     Adapter             One IETF receipt profile (pick        Conform; contribute the "independent
                         between draft-thaha-scitt-agent-      observer verdict" field upstream
                         execution-evidence and draft-sahu-    instead of inventing a format
                         agent-action-receipts after reading
                         both)

     Adapter             AP2 mandate, A2A task                 Read as contract input; map mandate
                                                               fields to effect spec

     Adapter             x402 payment proof                    Accept as evidence; let a facilitator
                                                               gate release on our verdict

     Adapter             ERC-8004 Validation Registry          Post validationResponse on a testnet
                                                               only, until there is demand

     Adapter             OpenClaw, Hermes, Temporal            Executor hooks: the OpenClaw bridge
                                                               exists; Hermes via its MCP config;
                                                               Temporal as an activity interceptor

     Adapter             Stripe meter events                   Bill on verdicts, not on agent claims

     Avoid               Our own identity, OAuth server or     MCP EMA, A2A cards and KYA own
                         agent registry                        this

     Avoid               Holding funds, escrow, payouts        Regulated; x402, ACP and card
                                                               networks own rails

     Avoid               A durable workflow engine             Temporal owns it

     Avoid               A new receipt format or reputation    Commodity, or crypto-speculative
                         token

     Avoid               A sandbox                             VerifiAgent's README already
                                                               concedes Docker isn't a hostile-code
                                                               sandbox; leave isolation to the runtime

     Avoid               Screen-scraping consumer UIs as       Fragile and often against terms of
                         "observation"                         service; observe only through provider
                                                               APIs or exports




                                                                                                   Page 15 of 24
~~~

## Source PDF page 16

~~~text
Round 1 — A–H analysis




  Founder assets — what the repos actually contain
  Grantifold is a real, tested core; the other three are honest pilots; Sluzen and Duty
  Coverage were not found. I cloned the four public repos at HEAD on Nov 13 2026 and ran
  two test suites. Private repos were not inspected.


     Repo (commit,       What it is                   What I checked              Gaps it states
     date)                                                                        or I saw

     proofrail —         Signed single-use permits    pytest : 137 passed, 40     Attacks are
     now                 bound to exact action,       subtests, ~3 s.             self-authored
     "Grantifold"        target, evidence, policy,    VALIDATION_REPORT           (the report
     (afc579d, Nov       approval; consumed before    lists 13 attacks (replay,   says so). Demo
     4 2026)             the side effect; provider    forgery, clock rollback,    keys ship in the
                         reconciliation after.        ledger rewrite, role        repo. No
                         Adapters: GitHub merge,      escalation,                 independent
                         SQLite migration; an         reconciliation bypass),     issuer identity,
                         OpenClaw bridge in           all recorded PASS.          no third-party
                          integrations/openclaw .                                 review. Name
                                                                                  collision with
                                                                                  an unrelated
                                                                                  PyPI package.

     verifiagent         Operator-only verification   Read README and             Single-process
     (8c7c688, Oct       pilot with a strict FAIL /   layout; tests not run       store; not an
     11 2026)            PARTIAL / PASS evidence                                  audited
                         contract; Docker-isolated                                sandbox; no
                         command checks                                           automatic
                                                                                  target oracle on
                                                                                  the PR path

     x402-mcp-           Paid MCP server settling     npm test : 9 passed, 1      README
     server              USDC on Base via x402;       skipped                     states tests
     (5712973, Oct       settlement-evidence                                      don't establish
     11 2026)            ledger                                                   real on-chain
                                                                                  settlement,
                                                                                  refunds or
                                                                                  replay safety.
                                                                                  No XRPL route
                                                                                  found here.




                                                                                             Page 16 of 24
~~~

## Source PDF page 17

~~~text
Round 1 — A–H analysis




     Repo (commit,       What it is                    What I checked            Gaps it states
     date)                                                                       or I saw

     xzenia-             Billing-export scanner for    Read README; tests        Synthetic
     leaklock            failed payments, pricing      not run                   sample only;
     (da84e9e, Oct       drift, duplicate billing;                               estimates, not
     11 2026)            governed action lifecycle                               accounting
                                                                                 conclusions


  Not located: no repository named Sluzen (HTTP 402 / XRPL) or Duty Coverage / Audit
  Gate among the 29 repos visible to this account. They may live under other names (e.g.
  [two private repository names redacted in Round 3; see ROUND3_CLAUDE_REVIEW.md §1] ) — the founder should point us to
  them before we claim reuse.

  Reuse verdict: Grantifold's permit, fence, role separation and reconciliation are the
  oracle's kernel — keep them. Its strongest existing property for this strategy is that it
  already refuses to trust the executor's success message.


  F — First proof: the lying-operator harness
  Claim under test: an independent observer catches false-success and duplicate-effect
  claims that a strong same-operator baseline cannot, at acceptable overhead. Everything
  runs locally and in GitHub Actions with no paid services and no LLM calls (a scripted
  agent keeps runs deterministic).


  Setup
         Simulated providers with hidden ground truth: a GitHub-like merge API and a Stripe-
         like refund API. Fault injection: commit-then-timeout, commit-then-5xx, duplicate
         delivery, eventual-consistency delay of 0–5 s, partial failure.
         One real adapter check: the existing GitHub adapter against a throwaway public
         repo, replayed from recorded responses in CI.


  Arms

     Arm                    What it is

     B0 naive               Agent loop with retries; success = the agent's own
                            report




                                                                                            Page 17 of 24
~~~

## Source PDF page 18

~~~text
Round 1 — A–H analysis




     Arm                  What it is

     B1 strong baseline   Durable steps (Temporal dev server or equivalent)
                          + idempotency keys + operator-side read-back +
                          operator-signed hash-chained receipts (Signet-
                          style)

     T oracle             Grantifold permit + fence + independent observer
                          + verdict engine; operator holds no observer or
                          verdict keys



  Adversarial scenarios (the operator is the attacker)
     1. A1 — forged success report for an effect that never happened
     2. A2 — operator rewrites and re-signs its own log after the fact
     3. A3 — permit replay to double-execute (double refund)
     4. A4 — target swap: different PR head or refund amount than authorized
     5. A5 — effect applied, then reverted before the observation window ends
     6. A6 — stale or cached observation fed to the verifier
     7. A7 — crash between consume and effect, then "retry" with the same authority
     8. A8 — success claimed during a provider outage


  Metrics (ground truth = the simulator's hidden state)
         False-accept rate: claimed success accepted where the effect is absent or wrong
         Duplicate-effect count
         False-reject rate on honest runs
         UNKNOWN rate on honest runs
         Overhead per action, p50 / p95, excluding consistency waits
         Infrastructure cost (must be $0)

  Volume: 10,000 randomized honest-fault trials plus 200 seeded runs per adversarial
  scenario, per arm.




                                                                                       Page 18 of 24
~~~

## Source PDF page 19

~~~text
Round 1 — A–H analysis




  Acceptance and rejection thresholds

     Metric                          Accept T if               Reject the strategy if

     False-accept (all trials)       0                         Any non-zero that can't be fixed
                                                               without trusting the operator

     Duplicate effects               0                         Any

     False-reject (honest)           ≤ 0.5%                    > 2%

     UNKNOWN (honest, ≤ 5            ≤ 2%                      > 10% — the oracle can't see enough
     s delay)                                                  to judge

     Overhead p95                    ≤ 250 ms local            >1s

     B1 vs T on A1, A2, A5           B1 false-accept > 0       B1 also reaches 0 — then
                                     where T = 0               independence adds nothing technical
                                                               and only a neutrality brand remains


  The last row is the honest one. A good durable workflow already gives exactly-once on
  honest faults; we should expect B1 to tie T there. The oracle earns its place only on A1, A2
  and A5, where the party that writes the log is the party that lies.

  Deliverables: a make proof target, a CI workflow, a results JSON, and a report that
  preserves any FAIL rather than hiding it — the same discipline as Grantifold's
  VALIDATION_REPORT, but with ChatGPT writing at least half the adversarial cases so the
  suite isn't self-graded.


  G — Business architecture
  Sell the verdict to the party that pays for outcomes, before agents are the ones paying.
  No willingness-to-pay figure below is evidence; each price is a hypothesis to test.


  First buyer profile (two candidates, test both, build for whichever converts)

                         Buyer 1: outcome-bill auditor           Buyer 2: agent change gate

     Who                 Finance or CX-ops lead at a company     Platform / security lead letting
                         paying an AI support vendor per         coding agents merge or migrate
                         resolution (Fin $0.99/outcome;
                         Zendesk ~$1.50–2.00)



                                                                                                  Page 19 of 24
~~~

## Source PDF page 20

~~~text
Round 1 — A–H analysis




                         Buyer 1: outcome-bill auditor            Buyer 2: agent change gate

     Pain                The vendor defines and counts the        Agent success messages aren't
                         billable outcome; Intercom counts an     evidence for release or audit
                         outcome when a customer confirms,
                         stops asking, or a workflow
                         completes

     What we             Each billed outcome against the          Exact PR head / migration matched
     verify              customer's own export: reopened          the granted authority, and the
                         within N days, same customer re-         provider shows the effect
                         contacted on the same issue, handed
                         to a human after "resolution", double-
                         counted

     Existing            LeakLock's billing-anomaly scanner +     Grantifold, today
     asset               verdict engine

     Risk                Contracts may not allow disputes;        GitHub can ship this as a feature
                         export fields may be too thin



  Monetization primitive
  The paid unit is a signed verdict. Open-source the oracle core, adapters and verifier CLI
  so anyone can check a verdict for free. Charge for: the hosted independent observer (the
  part that must not be run by the operator), adapter maintenance for systems of record,
  and audit reports.


  Testable pricing hypotheses
     1. One-off outcome-bill audit: $500 fixed for up to 3 months of exports, or 20% of
        credits the customer obtains from the vendor. Test: 10 qualified conversations → at
        least 2 paid audits within 30 days.
     2. Hosted verdicts: $0.01–0.05 per verdict with a $99/month floor. Test: 3 design
        partners from OpenClaw / Hermes / MCP-server builders agree to a paid pilot.
     3. Change gate: $49 per protected repo per month. Test: 2 of 10 platform teams pay
        after a free trial.




                                                                                                 Page 20 of 24
~~~

## Source PDF page 21

~~~text
Round 1 — A–H analysis




  Acquisition route
         Buyer 1: a free, open-source "outcome bill checker" for the Intercom and Zendesk
         export formats; outreach to companies named in vendors' own public case studies;
         CX-ops communities.
         Buyer 2 and platforms: listings as an MCP server, a ClawHub skill (signed, given
         ClawHub's malware history) and a Hermes integration; one written incident post-
         mortem per month showing a caught false success.


  Unit-economics model (arithmetic, not a forecast)
  Customers needed for $100,000/month net = (100,000 + fixed costs) ÷ (average revenue
  per account × gross margin). With fixed costs near $0 and an assumed 85% gross margin:


     Average revenue per account / month          Accounts needed

     $100                                         ~1,176

     $500                                         ~235

     $2,000                                       ~59


  The $100k target needs either hundreds of mid-market accounts or a few dozen large
  ones. A solo founder can sell the latter only if the product closes itself (self-serve checker
  → paid report).


  The ten commercial questions

     #          Question                                   Answer

     1          Who has the problem today?                 Companies paying per AI outcome; teams
                                                           granting agents merge/migrate/refund
                                                           rights; agent marketplaces whose
                                                           evaluators are self-interested

     2          Why don't existing solutions solve it?     Every incumbent artifact is signed by the
                                                           claimant or the operator; none observes
                                                           the provider independently

     3          What improvement can we show?              False-accept rate on operator-lie
                                                           scenarios: target 0 vs. baseline > 0
                                                           (Section F)



                                                                                                  Page 21 of 24
~~~

## Source PDF page 22

~~~text
Round 1 — A–H analysis




     #          Question                               Answer

     4          Why would OpenClaw / Hermes            Their users need proof for third parties;
                developers adopt it?                   self-verification is discounted; adapters
                                                       are tedious

     5          Why not build it themselves?           Conflict of interest makes their own
                                                       verdict worth less; they can build the
                                                       code, not the independence

     6          What stays open-source?                Verdict format, verifier CLI, fence,
                                                       adapters, harness

     7          What do customers pay for?             Hosted independent observation,
                                                       maintained adapters, audit reports, later
                                                       Recall queries

     8          What stops commoditization?            Weakly: verdict history and calibrated
                                                       false-success rates, neutrality reputation,
                                                       Recall. Honestly, not much in year one

     9          Smallest paid use case?                One $500 outcome-bill audit for one
                                                       company

     10         What result kills the strategy?        B1 matches T on A1/A2/A5; or UNKNOWN
                                                       > 10% on real adapters; or 0 of 10 qualified
                                                       buyers pay after seeing real
                                                       discrepancies




  H — Strongest objection
  Axiom is infrastructure for a buyer who barely exists yet, in layers that consortia with
  Visa, Google, Coinbase and Microsoft are standardizing right now. A one-founder
  "control layer" built around those standards will be either duplicative (where they've
  shipped) or years early (where agent-to-agent commerce hasn't arrived).

  The evidence points the same way:

          x402's headline volume is mostly signaling, not commerce, by Forkast's reading of
          tracker data.
          Virtuals' self-reported "agentic GDP" is disputed by analysts as unverified.
          Meta Muse keeps consumer agent payments inside a closed stack.




                                                                                                Page 22 of 24
~~~

## Source PDF page 23

~~~text
Round 1 — A–H analysis




         OpenClaw and Hermes users are mostly individuals running personal agents, not
         firms hiring agents across trust boundaries.

  A seven-pillar platform also multiplies surface area for a team of one human and two
  models: every pillar needs adapters, security review and upkeep against moving specs
  (MCP changed authorization substantially in July 2026 alone).

  The alternative that overcomes it: own exactly one neutral function — independent
  verification of effects — and sell it first to humans who already pay per agent outcome.
  Ship it into the standards (A2A extension, ERC-8004 validator, MCP server, x402
  facilitator gate) rather than as a layer around them. If agent-to-agent commerce arrives,
  the oracle is already the validator those protocols reference. If it doesn't, the business still
  stands on human buyers.

  Kill criteria, agreed in advance: stop or pivot if any one holds after 90 days —

     1. Section F's baseline B1 matches the oracle on operator-lie scenarios.
     2. Real adapters return UNKNOWN on more than 10% of honest actions.
     3. Zero paid audits or pilots from 10 qualified conversations in which the buyer saw real
        discrepancies.



  For ChatGPT's review
  These are the claims I'm least sure of; please try to break them first.

         Do Fin, Zendesk and Sierra contracts let a customer dispute counted outcomes, and
         do their exports carry enough fields to recheck them?
         Is there an incumbent doing independent provider read-back for agent effects that
         my searches missed (search terms: "execution verification", "outcome oracle", "agent
         validator")?
         Which IETF receipt / SCITT draft has working-group momentum? Pick one to conform
         to.
         Can Grantifold's permit fields be mapped cleanly onto AP2 Checkout and Payment
         mandates?
         Is B1 in Section F strong enough? Propose a stronger baseline if you can; the proof is
         only as good as its baseline.
         Write at least half of the adversarial scenarios independently of me.

  For the founder: where do Sluzen and Duty Coverage / Audit Gate live? And has
  "Grantifold" (and "Axiom") been checked for trademark conflicts?



                                                                                           Page 23 of 24
~~~

## Source PDF page 24

~~~text
Round 1 — A–H analysis




  Sources
  From web search results on Nov 13 2026; most pages were read as search excerpts rather
  than fetched in full. Repo findings come from local clones and test runs.

         OpenClaw: Emergent Mind overview; Unit 42 on ClawHub supply-chain risk;
         ClawHavoc, 341 of 2,857 skills (Koi via Secureblink)
         Hermes Agent: official docs; Runtimewire on Nous's harness strategy
         Meta Muse: Meta announcement; Let's Data Science on Secure VM and credential
         store
         Temporal: AI framework integrations GA, Oct 30 2026
         MCP authorization: Start with Identity, MCP 2026-07-28; Tigera on multi-hop
         delegation; Permit.io on runtime authorization
         A2A: Linux Foundation one-year release; Waxell on A2A joining AAIF
         AP2 and card networks: Spark on AP2 and FIDO; Forkast on the KYA framework
         x402: Linux Foundation launch; Forkast on signaling vs. commerce
         Receipts and execution evidence: draft-thaha-scitt-agent-execution-evidence-01;
         draft-xkumakichi-xaip-receipts-03; draft-sahu-agent-action-receipts-00; Signet;
         Microsoft AGT receipts proposal; Archipelo Salmon EVI
         OpenTelemetry: Dash0 on GenAI conventions
         ERC-8004: EIP text
         Marketplaces: Forkast on Virtuals ACP's evaluator problem
         AIUC-1: SiliconANGLE on the $40M round
         Outcome pricing: Flexprice on Fin's outcome definition; Lorikeet on per-resolution
         prices
         Founder repos: proofrail / Grantifold; verifiagent; x402-mcp-server; xzenia-leaklock




                                                                                          Page 24 of 24
~~~
