---
name: investigate
description: Search ICIJ Offshore Leaks and OpenSanctions, cross-reference findings, detect patterns, and produce structured intelligence reports.
---

# Investigate

The unified investigation skill. Searches ICIJ Offshore Leaks and
OpenSanctions, cross-references findings, detects patterns, and
produces structured intelligence reports.

**Before running**, load `patterns/INDEX.yaml` from the project root.

## Usage

```
/investigate <name>                          — full cross-reference (default)
/investigate <name> --trace                  — network traversal (2 hops)
/investigate <name> --trace --depth 3        — deep network walk (3 hops)
/investigate <name> --patterns               — structural pattern analysis
/investigate <name> --compliance             — rigorous sanctions/PEP screening
/investigate <name> --compliance --dob 1970-05-15 --nationality RU
/investigate <name> --monitor                — new sanctions since 30 days
/investigate <name> --monitor --since 2026-01-01
/investigate <name> --jurisdiction           — jurisdictional footprint
/investigate <name1>, <name2>                — compare connections
/investigate <name1>, <name2>, <name3>, ...  — batch exposure screening
/investigate --scan <pattern>                — exploratory pattern hunt (no target)
/investigate --scan all                      — run all 14 scan types
/investigate <name> --scan <pattern>         — targeted investigation + focused scan
```

Valid scan types: `sanctions-evasion`, `pep-opacity`, `nominee-shield`,
`mass-registration`, `intermediary-cluster`, `rapid-dissolution`,
`llp-opacity`, `beneficial-ownership-gap`

When no flag is given, the default mode is a full cross-reference
investigation (the most comprehensive single-name analysis).

For `--scan` mode, see the dedicated section at the end.

---

## Shared procedure (all targeted modes)

These steps run for all modes that have a target name. The `--scan`
mode (standalone, no target) has its own procedure — see below.

### Step 1: Deep traversal + independent searches (parallel)

Launch all of the following in **parallel** — they are independent:

**1a. `deep_trace`** — cross-source network traversal:

```
deep_trace(names: ["<name>"], depth: <depth>, budget: <budget>)
```

| Mode | depth | budget |
|------|-------|--------|
| default / --trace | 2 | 200 |
| --trace --depth 3 | 3 | 200 |
| --patterns | 2 | 200 |
| --compliance | 1 | 100 |
| --monitor | 0 (skip deep_trace) | — |
| --jurisdiction | 2 | 200 |
| 2-4 names | 2 | 200 |
| 5+ names | 1 | 200 |
| name + --scan | 2 | 200 |

For **--monitor**, skip `deep_trace` and use `sanctions_monitor`
directly. For **multi-name** investigations, all names go into a
single `deep_trace` call as seeds — the traversal expands outward
from each seed and discovers where their networks overlap.

**1b. `sanctions_match`** — structured matching (threshold 0.5):

```
sanctions_match(name: "<name>", threshold: 0.5)
```

Include any known properties (nationality, DOB) for better matching.

**1c. `icij_investigate`** — full ICIJ network expansion (max_results 5):

```
icij_investigate(name: "<name>", max_results: 5)
```

**1d. `sanctions_search`** — broad sanctions/PEP search:

```
sanctions_search(query: "<name>", limit: 20)
```

All four calls are independent — launch them in a single parallel
tool call block. This dramatically reduces wall-clock time.

### Step 2: Enrich key findings (parallel)

Once Step 1 completes, identify the highest-priority nodes and
launch **all enrichment calls in parallel**:

- Sanctioned entities: `sanctions_entity` (for each match with score > 0.7)
- ICIJ officer nodes: `icij_entity` (for each high-confidence officer match)
- Wikidata PEP check: `wikidata_pep_check` (if wikidataId is known)
- Sanctions provenance: `sanctions_provenance` (for confirmed sanctions matches)
- GLEIF full tree: `gleif_related` (for entities with LEIs — returns full subsidiary tree)
- Aleph network: `aleph_expand` / `aleph_relationships` (for Aleph entities — ownership, directorship)
- UK insolvency: `uk_insolvency` (for UK companies found)
- UK disqualified: `uk_disqualified` (search officers against disqualified register)
- SEC material events: `sec_8k` (for SEC entities — acquisitions, officer departures)
- SEC amendments: `sec_amendments` (for SEC entities — filing corrections as risk signal)
- SEC proxy: `sec_proxy` (for SEC entities — board members, executive compensation)
- Court opinions: `court_opinion` (for court cases with relevant opinions)
- Bankruptcy: `court_bankruptcy` (search for bankruptcy filings)
- Property: `land_high_value` / `land_transaction_chain` (for UK addresses — high-value purchases)
- Documents: `aleph_documents` (search leaked documents within relevant collections)

All enrichment calls for different entities are independent — batch
them into a single parallel tool call block.

### Step 3: Pattern probes (conditional, parallel)

Analyze Steps 1-2 results for **signals** that indicate specific
patterns. For each signal found, fire a targeted probe to confirm
or discover the pattern. Probes only fire when their trigger is
present. **Launch all triggered probes in a single parallel batch.**

Budget for probes: up to 50 calls total from this step.

#### 3a. PEP Opacity probe

**Trigger**: Any node with `role.rca` in topics at hop 0 or 1.

**Procedure** (3-5 calls):
1. Identify the PEP associated with the `role.rca` node.
2. `wikidata_family(entity_id)` on the PEP to get family member
   names (1 call).
3. For each family member (up to 3): `icij_search(query=family_name)`
   (up to 3 calls).
4. Check: do family members appear as ICIJ officers on entities
   where the PEP's name does NOT appear?

**Confirmed when**: Family member is ICIJ officer AND PEP name
absent from that entity's officer list. Upgrades `pep_opacity_layer`
pattern confidence to **HIGH**.

#### 3b. Sanctions Evasion probe

**Trigger**: Any node with `sanctioned: true` or `"sanction"` in
topics, at hop 0-2.

**Procedure** (2-3 calls):
1. `icij_search(query=sanctioned_person_name)` (1 call).
2. If ICIJ results found: `icij_investigate(name=sanctioned_name,
   max_results=3)` to map their offshore network (1 call).

**Confirmed when**: Sanctioned person connected (directly or via
intermediary) to an offshore entity. Upgrades `sanctions_evasion`
pattern confidence to **HIGH**.

#### 3c. Intermediary Cluster probe

**Trigger**: Any ICIJ node with type `Intermediary`.

**Procedure** (1-2 calls):
1. `icij_investigate(name=intermediary_name, max_results=10)` (1 call).
2. Count connected entities in results.

**Confirmed when**: Intermediary connected to 20+ entities.
Upgrades `intermediary_cluster` confidence to **HIGH**.

#### 3d. Nominee Shield probe

**Trigger**: Any officer/person node with degree >= 5 in the
graph, OR any officer whose name contains "nominee", "services",
"corporate director", or similar patterns.

**Procedure** (2-3 calls):
1. `icij_investigate(name=suspect_officer, max_results=10)` (1 call).
2. If 20+ results: `icij_search(query=suspect_officer)` to verify
   breadth across investigations (1 call).
3. Optionally: `sanctions_match(name=suspect_officer, threshold=0.5)`
   to check if the nominee is flagged (1 call).

**Confirmed when**: Officer found across 20+ unrelated entities in
different jurisdictions/investigations. Upgrades `nominee_shield`
confidence to **HIGH**.

#### 3e. Beneficial Ownership Gap probe

**Trigger**: Any entity node from GLEIF source, or any UK company
node from Companies House.

**Procedure** (3-5 calls):
1. For GLEIF entities: `gleif_ownership(lei=entity_lei)` (1 call
   per entity, max 2).
2. For UK companies: `beneficial_owner(company=company_number)`
   (1 call per company, max 2).
3. Trace: if ownership chain contains only corporate entities
   (no natural person), flag as gap.

**Confirmed when**: No natural person identified as ultimate
beneficial owner after tracing chain. Upgrades
`beneficial_ownership_gap` confidence to **HIGH**.

#### 3f. Mass Registration probe

**Trigger**: Any ICIJ address node in results.

**Procedure** (2-3 calls):
1. `icij_search(query=address_text)` to find co-registered
   entities at the same address (1 call).
2. `icij_entity(node_id)` on the address node for full entity
   count (1 call).

**Confirmed when**: 10+ entities at same address. 100+ entities
upgrades to CRITICAL severity. Upgrades `mass_registration`
confidence to **HIGH**.

#### 3g. LLP Opacity probe

**Trigger**: Any UK company node where company name or type
contains "LLP" or "Limited Liability Partnership".

**Procedure** (2-3 calls):
1. `uk_company(company_number=number)` — get partner info (1 call).
2. `uk_filing_history(company_number=number)` — check for
   dormant accounts, short filing history (1 call).
3. Examine partner jurisdictions against secrecy list
   (BZ, SC, MH, WS, PA, VG, KY).

**Confirmed when**: LLP has corporate partners in secrecy
jurisdictions AND no UK-based individual partner. Upgrades
`llp_opacity_vehicle` confidence to **HIGH**.

#### 3h. Rapid Dissolution probe

**Trigger**: Any UK company node found in results.

**Procedure** (2-3 calls):
1. `uk_company(company_number=number)` — get incorporation date,
   dissolution date, status (1 call).
2. `uk_filing_history(company_number=number)` — check accounts
   filings (1 call).
3. `uk_officer_appointments(officer_id=officer_id)` — check
   director nationality and other appointments (1 call).

**Confirmed when**: Entity dissolved within 730 days of
incorporation AND directors exclusively foreign AND no/dormant
accounts filed. Upgrades `rapid_dissolution` confidence to **HIGH**.

### Step 4: Pattern analysis

Cross-reference all findings (including probe results from Step 3)
against `patterns/INDEX.yaml`:
- Starburst (hub-and-spoke)
- Matryoshka (nested jurisdiction chains)
- Nominee Shield (professional nominees)
- Intermediary Cluster (single formation agent)
- Mirror (parallel entities across jurisdictions)
- Temporal Cluster (formation bursts)
- Sanctions Evasion Structure (offshore + sanctioned)
- PEP Opacity Layer (offshore + PEP)
- Regulatory Arbitrage Chain (jurisdiction gap exploitation)

**Incorporate probe results**: When a probe confirmed a pattern
with specific evidence, upgrade its confidence to HIGH and include
the probe evidence in the pattern match. When a probe found no
confirmation despite a relevant trigger, note this and keep the
confidence at whatever the post-hoc matcher assigned (or lower it).

When a NEW pattern is identified, propose adding it to the library.

### Step 5: Collect timeline events

Before producing the report, scan ALL data gathered in Steps 1-4
and extract every dated event into a `timeline_events` list. This
list is attached to the investigation data dict and drives the
timeline visualization.

**Events to extract** (scan all enrichment responses):

| Source | Event type | Where to find the date |
|--------|-----------|----------------------|
| OpenSanctions | Sanctions designation | `sanctions[].properties.startDate` |
| OpenSanctions | Sanctions modified | `sanctions[].properties.modifiedAt` |
| OpenSanctions | Director disqualification | Parse from `notes` ("imposed on DD/MM/YYYY") |
| OpenSanctions | First flagged | `first_seen` on entity |
| OpenSanctions | Record updated | `last_change` on entity |
| ICIJ | Leak publication | Investigation name → known year |
| ICIJ | Entity incorporation | `incorporation_date` |
| ICIJ | Entity dissolution | `dissolution_date` |
| Companies House | Filing event | Filing history dates |
| Companies House | Incorporation | Company profile |
| Companies House | Dissolution | Company profile |
| SEC EDGAR | Filing date | Filing metadata |
| CourtListener | Case filed | `dateFiled` |
| CourtListener | Case terminated | `dateTerminated` |
| Wikidata | Position started/ended | PEP check / career dates |
| Wikidata | Birth/death dates | Entity enrichment |

Each event is a dict:
```python
{"date": "2025-04-09", "label": "Drex Technologies S.A.",
 "source": "opensanctions", "type": "Director Disqualification",
 "detail": "Imposed under Sanctions and Anti-Money Laundering Act 2018"}
```

Add the list to the data dict:
```python
data["timeline_events"] = events
```

The visualizer will merge these with client-side events and
display them on the swim-lane timeline and narrative chronology.

### Step 6: Produce report

Use the mode-specific report template below.

### Step 7: Generate next steps

Based on the specific findings, generate a `next_steps` list and
attach it to the investigation data dict before visualization.
Each step is a dict with `priority`, `title`, and `description`.

Priorities: `CRITICAL` (sanctions/legal exposure requiring
immediate action), `HIGH` (enhanced due diligence, specific
leads to pursue), `RECOMMENDED` (investigative actions that
would deepen understanding), `ONGOING` (monitoring, verification).

Next steps must be **specific to this investigation** — reference
actual entity names, jurisdictions found, gaps in data, specific
people or companies to investigate further, and concrete commands
to run. Do not use generic boilerplate.

Example:
```python
data["next_steps"] = [
    {"priority": "CRITICAL", "title": "Legal review: OFAC exposure",
     "description": "Isabel dos Santos is on the US Kleptocracy/HR visa list and UK FCDO sanctions. Any financial relationship requires immediate legal counsel."},
    {"priority": "HIGH", "title": "Trace Sindika Dokolo network",
     "description": "Run /investigate Isabel dos Santos, Sindika Dokolo to map shared offshore structures with her late husband."},
    {"priority": "RECOMMENDED", "title": "Expand with Aleph API key",
     "description": "Aleph returned no results — Luanda Leaks source documents are hosted there. Register at aleph.occrp.org and set ALEPH_API_KEY in .env."},
]
```

### Step 8: Visualization

After producing the report, ask:
"Would you like an interactive network visualization?"

If yes, the `deep_trace` result is already in the format expected by
`sift.visualizer.generate_visualization()`. Pass it
directly — it includes hop distances for visual encoding.
The `next_steps` list will appear in the Reference tab.

---

## Mode: Default (full cross-reference)

The most comprehensive single-name analysis. Combines network
traversal, sanctions screening, pattern detection, and jurisdictional
profiling.

```
## Cross-reference report: [name]

Date: [YYYY-MM-DD]

### Executive summary

[2-3 sentences: who is this entity, what did we find, what is the
risk level? Lead with the most significant finding.]

### Traversal summary
- Depth: [N] hops | Nodes: [total] | API calls: [N]/[budget]
- Hop 0: [N] | Hop 1: [N] | Hop 2: [N]

### Sanctions exposure

[Sanctions matches, or "No sanctions exposure found"]

| Match | Score | Lists | Topics | Hop |
|-------|-------|-------|--------|-----|

### Offshore holdings (ICIJ)

| Entity | Type | Jurisdiction | Investigation | Hop |
|--------|------|-------------|---------------|-----|

### Cross-links

[Entities in BOTH databases — the investigative core.]

| Name | ICIJ role | Sanctions status | Lists |
|------|----------|-----------------|-------|

### Critical paths

[For sanctioned/PEP nodes at hop 1+, trace the chain:]
> **Subject** → *officer of* → **Entity X** (BVI)
> → *co-officer* → **Person Y** (sanctioned, OFAC SDN)

### Pattern matches

[Named patterns from patterns/INDEX.yaml, with probe evidence
where available. Show confidence level for each.]

### Jurisdictional profile

| Jurisdiction | ICIJ entities | Sanctions exposure | Risk |
|-------------|--------------|-------------------|------|

### Risk assessment

| Factor | Finding | Risk |
|--------|---------|------|
| Sanctions | [status] | [level] |
| Offshore structure | [pattern] | [level] |
| Jurisdictions | [count] | [level] |
| Cross-links | [count] | [level] |
| Network depth | [sanctioned at hop N] | [level] |
| **Overall** | | **[level]** |

### Recommended next steps

[Based on risk: CRITICAL/HIGH/MEDIUM/LOW guidance]
```

---

## Mode: --trace

Network-focused. Emphasizes the graph structure, hop-by-hop
expansion, and path analysis. Uses deeper traversal.

```
## Network trace: [name]

### Traversal summary
- Depth: [N] hops | Nodes: [total] | Budget: [used]/[total]
- Pruned: [N] high-connectivity nodes

### Seed entity
[Name, type, jurisdiction, sanctions status]

### Network map by hop

#### Hop 1 — Direct connections
| Name | Type | Relationship | Jurisdiction | Sanctioned |
|------|------|-------------|-------------|------------|

#### Hop 2 — Second-degree
| Name | Type | Path from seed | Jurisdiction | Sanctioned |
|------|------|---------------|-------------|------------|

### Critical paths

[Full chains from seed to flagged persons]

### Pattern matches
### Network summary

- Total nodes: [N] across [N] hops
- Sanctioned: [N] (at which hops?)
- Jurisdictions: [list]
- Key officers: [multi-entity names]
- Intermediaries: [formation agents]
- Risk level: [assessment]
```

---

## Mode: --patterns

Structure-focused. Analyzes jurisdictional, intermediary, officer,
and temporal patterns across all findings.

```
## Pattern analysis: [name]

### Data summary
- ICIJ entities: [N] | OpenSanctions matches: [N]
- Jurisdictions: [list with counts]
- Investigations: [which leaks]
- Intermediaries: [list with counts]

### Patterns identified

#### [Pattern name] (from patterns/INDEX.yaml)
- Evidence: [entities/connections]
- Probe result: [confirmed/not tested/no confirmation]
- Significance: [what it indicates]
- Confidence: HIGH/MEDIUM/LOW

### Sanctions overlay

| Entity/Officer | ICIJ role | Sanctioned | Lists | Hop |
|---------------|-----------|-----------|-------|-----|

### Red flags
[Specific indicators warranting investigation]

### New patterns
[Propose any structure not in the current library]
```

---

## Mode: --compliance

Rigorous structured screening for KYC/AML. Uses all available
identifying properties for precise matching.

Parse additional flags: `--dob`, `--nationality`, `--id`, `--jurisdiction`, `--reg`

1. Run in **parallel**: `sanctions_match` (with all provided properties,
   threshold 0.5) + `deep_trace` (depth 1, budget 100) + `icij_investigate`
2. For matches >= 0.5: `sanctions_entity` + `sanctions_provenance` (parallel)

```
## Compliance screening: [name]

### Subject details provided
- Name / DOB / Nationality / ID

### Risk assessment: [HIGH / MEDIUM / LOW / CLEAR]

### Sanctions matches

| Match | Score | Schema | Lists | Topics | Last changed |
|-------|-------|--------|-------|--------|-------------|

### Match provenance
[Which datasets contributed which facts]

### Offshore exposure (ICIJ)
[Entity holdings, officer positions]

### Recommended next steps
[HIGH: legal review | MEDIUM: escalate | LOW: gather more info | CLEAR: document]
```

---

## Mode: --monitor

Check for new sanctions listings since a date.

1. Parse `--since` date (default: 30 days ago)
2. Use `sanctions_monitor` with name and date
3. For results: `sanctions_entity` for full details

```
## Monitoring report: [name]

Period: [since] to [today]

### Status: [NEW LISTINGS FOUND / NO NEW LISTINGS]

| Date listed | Match | Score | Lists | Topics |
|------------|-------|-------|-------|--------|

### Details
[For each: list, reason, connected entities]

### Recommended action
[New listings: investigate | None: continue monitoring]
```

---

## Mode: --jurisdiction

Jurisdictional footprint analysis.

1. From `deep_trace` results, group all entities by jurisdiction
2. For each jurisdiction with ICIJ entities, check sanctions exposure
   in that jurisdiction using `sanctions_search` with `countries` filter

```
## Jurisdictional profile: [name]

### Summary: [N] entities across [N] jurisdictions

| Jurisdiction | ICIJ entities | Types | Sanctions | Risk |
|-------------|--------------|-------|-----------|------|

### Jurisdictional risk profile
[For each: secrecy ranking, sanctions exposure, common uses]

### Cross-reference findings
[Jurisdictions with BOTH offshore and sanctions exposure]
```

---

## Mode: Multiple names (2+ names, comma-separated)

All multi-name investigations use a **single unified `deep_trace`**
with all names as seeds. This produces one merged network graph that
reveals where the subjects' offshore structures and sanctions exposure
**intersect**.

1. Split input on commas, trim whitespace.
2. Run a single `deep_trace` with all names:
   ```
   deep_trace(names: ["name1", "name2", ...], depth: 2, budget: 200)
   ```
   For 5+ names, reduce depth to 1 (budget stays at 200).

3. From the merged graph, identify **connection points** — nodes
   reachable from multiple seeds. These are the investigative core:
   - **Shared entities**: Both subjects are officers of the same company
   - **Shared intermediaries**: Same law firm or registered agent
   - **Shared jurisdictions**: Entities in the same offshore jurisdictions
   - **Shared associates**: A third person connected to both subjects
   - **Sanctions bridges**: A sanctioned entity connecting two subjects

4. For each subject, note their individual sanctions status.

5. Produce a connection report:

```
## Connection analysis: [name1], [name2], ...

Date: [YYYY-MM-DD]

### Subjects

| Name | Sanctioned | PEP | ICIJ entities | Hop 0 status |
|------|-----------|-----|--------------|-------------|

### Unified network summary
- Seeds: [N] names | Depth: [N] hops
- Total nodes: [N] | Total edges: [N]
- API calls: [N]/[budget]

### Connection points

[This is the most important section. For each node reachable from
multiple seed entities, describe the connection:]

#### [Connection point name]
- **Reached from**: [name1] via [path], [name2] via [path]
- **Type**: Shared entity / Shared intermediary / Shared associate
- **Significance**: [What this shared connection means]

### Individual findings per subject

#### [name1]
- ICIJ entities: [N] across [jurisdictions]
- Sanctions status: [status]
- Key connections: [list]

#### [name2]
- ICIJ entities: [N] across [jurisdictions]
- Sanctions status: [status]
- Key connections: [list]

### Sanctions bridges

[If a sanctioned entity connects two or more subjects, flag it
prominently:]

> **[name1]** → *officer of* → **Entity X** (BVI)
> ← *also officer of* ← **[name2]**
> Entity X → *intermediary* → **Sanctioned Firm Y** (OFAC SDN)

### Pattern matches
[Cross-reference against patterns/INDEX.yaml]

### Risk assessment

| Subject | Sanctions | Offshore | Connections | Overall |
|---------|-----------|----------|------------|---------|

### Recommended next steps
```

6. **Visualization**: The unified `deep_trace` result produces a single
   merged graph. When visualized, seed nodes (hop 0) appear as large
   colored hubs, and shared connection points are highlighted where
   paths from multiple seeds converge. Use the depth slider to
   progressively reveal the merged network.

---

## Mode: --scan (exploratory pattern hunt)

Scan mode hunts for structural patterns across the data sources
**without requiring a target name**. Each scan type has a search
strategy that generates seeds, cross-references findings, and
confirms pattern instances. Scans track history so that repeated
runs progressively cover new ground.

### Scan syntax

```
/investigate --scan <type>               — run one scan type
/investigate --scan all                  — run all 14 scan types
/investigate <name> --scan <type>        — targeted investigation + focused scan
```

### Budget

| Mode | Budget |
|------|--------|
| `--scan <type>` (standalone) | full budget for that scan type |
| `--scan all` | 500 total, allocated per scan (see table below) |
| `<name> --scan <type>` | 200 for investigation + 150 for scan |

### Combined mode (`<name> --scan <type>`)

When a target name is provided with `--scan`:
1. Run the normal targeted investigation (Steps 1-4) with
   `deep_trace` budget of 200.
2. Use the investigation results as **seeds** for the scan —
   the entities, officers, and intermediaries discovered in Step 1
   become the starting points for the scan probes.
3. Run the scan strategy with 150 calls.
4. Merge findings: the investigation report includes the scan
   results in a dedicated "Scan findings" section, and the
   visualization adds a "Scan Findings" tab.

This is more efficient than a standalone scan because the
investigation has already built the relevant network.

### Shared scan procedure (standalone, no target name)

1. Parse `--scan <type>` argument.
2. **Health check**: `scan_health_check()` — verify API
   connectivity before spending budget. If any source required
   by the chosen scan type is degraded or not configured, warn
   the investigator and suggest skipping affected scan types.
3. Skip Steps 1-4 (no `deep_trace`, no enrichment, no probes).
4. Execute the scan strategy for the specified type(s).
5. For `--scan all`, run scans sequentially in priority order.
   If a scan finishes under budget, reallocate its remainder to
   the next scan.
6. Deduplicate: if the same entity triggers multiple scan types,
   consolidate into one finding and note all patterns matched.
7. Produce the scan report (see template below).
8. Offer scan visualization.

### Scan history (progressive coverage)

Scans track their seed history locally so that repeated runs
cover new ground instead of re-scanning the same entities.

**Before each scan**:
1. `scan_history_read(scan_type=<type>)` — returns prior seeds,
   last pagination offsets, run count, and metadata.
2. Filter out any seeds that appear in `seeds_used`.
3. Use `last_offset` values for pagination parameters (see
   individual strategies below).
4. Use `last_metadata` for state like search term rotation index.

**After each scan**:
1. `scan_history_write(scan_type=<type>, seeds_used=[...],
   findings_count=N, offsets={...}, metadata={...})` — record
   the seeds used, findings, final offsets, and any rotation state.

### Date computation

When scan instructions reference relative dates like
"<90 days ago>" or "<1 year ago>", compute the ISO date from
today's date. For example, if today is 2026-04-19 and the
instruction says "90 days ago", use "2026-01-19".

### Scan strategies

#### sanctions-evasion (budget: 80 calls)

Find sanctioned persons who appear in ICIJ offshore leaks.

1. Read scan history: `scan_history_read(scan_type="sanctions-evasion")`.
2. `sanctions_search(query="", topics=["sanction"], schema="Person",
   sort="properties.createdAt:desc", limit=20,
   offset=<last_offset.opensanctions or 0>)` — fetch sanctioned
   persons sorted by designation date, most recent first (1 call).
   The `sort` parameter is critical: without it, the API returns
   perennial top-10 names (Gaddafi, Al-Qaeda) regardless of other
   filters. With it, results are genuinely recent designations
   (days/weeks old) that are far more likely to have undiscovered
   offshore connections.
3. For the top 10 recently designated persons NOT in prior seeds
   (prioritize those with `crime.fin` or `crime` topics):
   `icij_search(query=sanctioned_name)` (up to 10 calls).
4. For each ICIJ hit: `icij_investigate(name=match_name,
   max_results=3)` to map connected entities (up to 15 calls).
5. For officers found on those entities:
   `sanctions_match(name=officer_name, threshold=0.5,
   topics=["sanction"])` — are co-officers also sanctioned?
   (up to 15 calls).
6. Cross-reference jurisdictions: `icij_entity(node_id)` on
   key entities to check secrecy jurisdiction presence
   (up to 10 calls).
7. Save: `scan_history_write(scan_type="sanctions-evasion",
   seeds_used=[names used], findings_count=N,
   offsets={"opensanctions": <new offset>})`.

**Hit**: Sanctioned person linked to offshore entity through
0-3 intermediary hops. Severity = CRITICAL if direct link,
HIGH if through intermediary.

#### pep-opacity (budget: 80 calls)

Find PEP family members hiding behind offshore structures.

1. Read scan history: `scan_history_read(scan_type="pep-opacity")`.
2. `sanctions_search(query="", topics=["role.rca"],
   sort="properties.createdAt:desc", limit=20,
   offset=<last_offset.opensanctions or 0>)` — PEP associates
   sorted by designation date, most recent first (1 call).
3. For the top 10 `role.rca` entries NOT in prior seeds, with
   known `wikidataId`:
   `wikidata_family(entity_id)` to get family member names
   (up to 10 calls).
4. For each family member name (up to 3 per PEP):
   `icij_search(query=family_member_name)` (up to 20 calls).
5. For each ICIJ hit: `icij_entity(node_id)` to get officer
   list — check if the PEP name is ABSENT (up to 15 calls).
6. For confirmed hits: `sanctions_entity(entity_id)` on the
   PEP to get full sanctions/positions detail (up to 5 calls).
7. Save: `scan_history_write(scan_type="pep-opacity",
   seeds_used=[names used], findings_count=N,
   offsets={"opensanctions": <new offset>})`.

**Hit**: PEP family member is an ICIJ officer AND the PEP's
own name does not appear as officer on the same entities.
Severity = HIGH.

#### nominee-shield (budget: 60 calls)

Find professional nominee directors serving on mass entities.

1. Read scan history: `scan_history_read(scan_type="nominee-shield")`.
2. `icij_search(query="nominee director")` +
   `icij_search(query="nominee services")` +
   `icij_search(query="corporate directors")` (3 calls).
3. For each officer result NOT in prior seeds (up to 10):
   `icij_investigate(name=officer_name, max_results=10)` to
   count directorships and list connected entities (up to 10 calls).
4. For officers with 20+ directorships:
   `icij_entity(node_id)` on a sample of their entities to
   verify diversity of jurisdiction and investigation source
   (up to 15 calls).
5. `sanctions_batch_match(names=[high_degree_officers],
   threshold=0.5)` — check if any nominees are themselves
   flagged (1 call).
6. Save: `scan_history_write(scan_type="nominee-shield",
   seeds_used=[officer names used], findings_count=N)`.

**Hit**: Officer holding 20+ directorships across unrelated
entities in different jurisdictions. Severity = HIGH if 50+,
MEDIUM if 20+.

#### intermediary-cluster (budget: 60 calls)

Find formation agents managing large entity portfolios.

1. Read scan history: `scan_history_read(scan_type="intermediary-cluster")`.
2. Discover intermediaries dynamically:
   `icij_search(query="intermediary")` +
   `icij_search(query="trust company")` +
   `icij_search(query="corporate services")` (3 calls).
   Pick the top 5 intermediaries NOT in prior seeds.
   If fewer than 3 new results, supplement with:
   `icij_search(query="formation agent")` (1 extra call).
3. For each intermediary found:
   `icij_investigate(name=intermediary_name, max_results=10)` —
   how many entities do they manage? (up to 10 calls).
4. For high-volume intermediaries (20+ entities):
   `icij_entity(node_id)` on a sample of managed entities
   to profile jurisdictions and officer patterns (up to 20 calls).
5. Check for sanctions connections among managed entities:
   `sanctions_batch_match(names=[entity_officer_names],
   threshold=0.5)` (up to 3 calls).
6. Save: `scan_history_write(scan_type="intermediary-cluster",
   seeds_used=[intermediary names], findings_count=N)`.

**Hit**: Intermediary managing 20+ entities. Severity = HIGH
if any managed entities have sanctioned officers, MEDIUM
otherwise.

#### rapid-dissolution (budget: 60 calls)

Find short-lived UK companies with suspicious characteristics.

1. Read scan history: `scan_history_read(scan_type="rapid-dissolution")`.
2. `uk_advanced_search(company_status="dissolved",
   dissolved_from="<6 months ago>",
   incorporated_from="<3 years ago>",
   size=10,
   start_index=<last_offset.companies_house or 0>)` — find
   recently dissolved companies that were also recently
   incorporated, i.e. short-lived entities (1 call).
3. For each result NOT in prior seeds:
   `uk_company(company_number=number)` to get
   incorporation/dissolution dates and officer info
   (up to 15 calls).
4. For short-lifespan companies (dissolved < 730 days after
   incorporation): `uk_officer_appointments(officer_id)` to
   check director nationality and other directorships
   (up to 15 calls).
5. `uk_filing_history(company_number=number)` to check for
   missing/dormant accounts (up to 10 calls).
6. For short-lifespan companies: `uk_insolvency(company_number)`
   — was it wound up involuntarily? (up to 5 calls).
7. For each director: `uk_disqualified(query=director_name)` —
   were they subsequently banned? (up to 5 calls).
8. Cross-check directors against sanctions:
   `sanctions_match(name=director_name, threshold=0.5)`
   (up to 5 calls).
9. Save: `scan_history_write(scan_type="rapid-dissolution",
   seeds_used=[company names], findings_count=N,
   offsets={"companies_house": <new offset>},
   metadata={"search_term_index": <next index>})`.

**Hit**: Entity dissolved within 2 years, foreign-only
directors, no/dormant accounts. Severity = CRITICAL if
involuntary insolvency + disqualified director, HIGH if
either one or sanctioned, MEDIUM otherwise.

#### llp-opacity (budget: 55 calls)

Find UK LLPs with opaque corporate partners.

1. Read scan history: `scan_history_read(scan_type="llp-opacity")`.
2. `uk_advanced_search(company_type="llp",
   company_status="active",
   incorporated_from="<2 years ago>",
   size=10,
   start_index=<last_offset.companies_house or 0>)` — recently
   incorporated active LLPs (1 call).
3. For each LLP NOT in prior seeds:
   `uk_company(company_number=number)` to get partner types
   and jurisdictions (up to 15 calls).
4. For LLPs with corporate partners: check partner jurisdiction
   codes against secrecy list (BZ, SC, MH, WS, PA, VG, KY) —
   no extra calls, data analysis only.
5. `uk_filing_history(company_number=number)` for dormant
   accounts indicator (up to 10 calls).
6. `beneficial_owner(company=company_number)` to check PSC
   status (up to 10 calls).
7. Save: `scan_history_write(scan_type="llp-opacity",
   seeds_used=[LLP names], findings_count=N,
   offsets={"companies_house": <new offset>})`.

**Hit**: LLP with corporate partners in secrecy jurisdictions
AND no UK individual partner. Severity = HIGH if dormant
accounts also present, MEDIUM otherwise.

#### beneficial-ownership-gap (budget: 55 calls)

Find entities with no disclosed beneficial owner.

Jurisdiction rotation: cycle through secrecy jurisdictions on
each run, tracked in scan history metadata as `jurisdiction_index`:
`["VG", "KY", "BZ", "PA", "SC", "MH", "WS"]`

1. Read scan history: `scan_history_read(scan_type="beneficial-ownership-gap")`.
   Get `jurisdiction_index` from `last_metadata` (default 0).
   Pick the next jurisdiction from the rotation list.
2. `gleif_search(query="", jurisdiction=<jurisdiction>,
   created_since="<1 year ago>",
   sort="-entity.creationDate")` — search for recently created
   entities in the chosen secrecy jurisdiction, newest first
   (up to 5 calls).
3. For each entity NOT in prior seeds:
   `gleif_ownership(lei=lei)` to trace parent/UBO chain
   (up to 15 calls).
4. For entities with corporate-only ownership (no natural
   person in chain): `beneficial_owner(company=company_name)`
   in Companies House (up to 10 calls).
5. Cross-reference with ICIJ: `icij_search(query=entity_name)`
   to check offshore presence (up to 10 calls).
6. Save: `scan_history_write(scan_type="beneficial-ownership-gap",
   seeds_used=[entity names], findings_count=N,
   metadata={"jurisdiction_index": <next index>})`.

**Hit**: Entity with no disclosed natural-person beneficial
owner after tracing through ownership chain. Severity = HIGH
if also in ICIJ, MEDIUM if only in GLEIF/CH.

#### mass-registration (budget: 50 calls)

Find addresses hosting large numbers of registered entities.

1. Read scan history: `scan_history_read(scan_type="mass-registration")`.
2. Search for known shell-mill indicators:
   `icij_search(query="registered agent")` +
   `icij_search(query="registered office")` (2 calls).
3. For top address nodes NOT in prior seeds:
   `icij_entity(node_id)` to get full entity count
   (up to 10 calls).
4. For addresses with 10+ entities:
   `icij_extend(node_ids=[address_ids],
   properties=["countries"])` to profile jurisdictions
   (up to 5 calls).
5. UK cross-check: `uk_search(query=address_text,
   type="company")` for UK-based addresses (up to 5 calls).
6. Save: `scan_history_write(scan_type="mass-registration",
   seeds_used=[address descriptions], findings_count=N)`.

**Hit**: Address hosting 10+ entities. Severity = CRITICAL
if 100+, HIGH if 50+, MEDIUM if 10+.

#### disqualified-director (budget: 60 calls) — UK

Find disqualified directors still connected to active companies.

1. Read scan history: `scan_history_read(scan_type="disqualified-director")`.
2. `uk_disqualified(query="fraud")` +
   `uk_disqualified(query="breach")` — get disqualified
   directors by common CDDA grounds (2 calls).
3. For each disqualified person NOT in prior seeds (up to 8):
   `uk_search(query=director_name, type="officer")` — find
   current appointments (up to 8 calls).
4. For each company found: `uk_company(company_number)` —
   check if active (up to 15 calls).
5. For active companies with disqualified officers:
   `uk_insolvency(company_number)` (up to 10 calls).
6. Cross-ref: `sanctions_match(name=director_name)` +
   `icij_search(query=director_name)` (up to 10 calls).
7. Save: `scan_history_write(scan_type="disqualified-director",
   seeds_used=[director names], findings_count=N)`.

**Hit**: Disqualified director connected to active company.
Severity = CRITICAL if also sanctioned/ICIJ, HIGH otherwise.

**So what**: Operating as a director while disqualified is a
criminal offence under s.13 CDDA 1986. These individuals may
be fronting for others or continuing fraud through new vehicles.

#### phoenix-company (budget: 65 calls) — UK

Find dissolved companies reborn at the same address.

1. Read scan history: `scan_history_read(scan_type="phoenix-company")`.
2. `uk_advanced_search(company_status="dissolved",
   dissolved_from="<6 months ago>",
   size=10,
   start_index=<last_offset.companies_house or 0>)` — recently
   dissolved companies (1 call).
3. For each NOT in prior seeds (up to 10):
   `uk_company(company_number)` — get address, directors,
   dates (up to 10 calls).
4. For each address: `uk_search(query=address_snippet,
   type="company")` — find active companies there
   (up to 10 calls).
5. For same-address matches: `uk_company(company_number)` —
   check formation date is after dissolution (up to 10 calls).
6. For phoenix candidates:
   `uk_officer_appointments(officer_id)` — same directors?
   (up to 10 calls).
7. `land_transaction_chain` at the address — asset transfers?
   (up to 5 calls).
8. `icij_search(query=director_name)` — offshore connections
   (up to 5 calls).
9. Save: `scan_history_write(scan_type="phoenix-company",
   seeds_used=[company names], findings_count=N,
   offsets={"companies_house": <new offset>},
   metadata={"search_term_index": <next index>})`.

**Hit**: New company at same address as dissolved, formed
within 6 months, overlapping directors. Severity = HIGH if
directors on other dissolved companies too, MEDIUM otherwise.

**So what**: Phoenix fraud leaves creditors (including HMRC)
unpaid while the directors continue the same business through
a clean entity. The Insolvency Service actively pursues these.

#### property-layering (budget: 55 calls) — UK

Find high-value property purchases with offshore ownership.

1. Read scan history: `scan_history_read(scan_type="property-layering")`.
2. `land_high_value(town="LONDON", min_price=5000000,
   limit=10, date_from="<1 year ago>")` +
   `land_high_value(town="MANCHESTER",
   min_price=2000000, limit=5, date_from="<1 year ago>")`
   — recent high-value transactions only (2 calls).
3. For each address NOT in prior seeds:
   `uk_search(query=address_snippet, type="company")` —
   companies at that address (up to 15 calls).
4. For companies found: `uk_company(company_number)` — PSCs
   and jurisdiction (up to 10 calls).
5. For overseas-owned: `gleif_search(query=company_name)` —
   corporate structure (up to 5 calls).
6. `icij_search(query=company_name)` — offshore connections
   (up to 10 calls).
7. `sanctions_match(name=psc_name)` — flagged beneficial
   owners (up to 5 calls).
8. Save: `scan_history_write(scan_type="property-layering",
   seeds_used=[address descriptions], findings_count=N)`.

**Hit**: High-value property associated with company owned by
secrecy jurisdiction entity. Severity = HIGH if ICIJ/sanctions,
MEDIUM if offshore ownership only.

**So what**: UK property is a primary laundering endpoint.
Transparency International estimates £1.5B+ of UK property
connected to suspicious wealth, much held through offshore
shell companies.

#### sec-amendment-cluster (budget: 55 calls) — US

Find public companies with excessive filing amendments.

1. Read scan history: `scan_history_read(scan_type="sec-amendment-cluster")`.
2. `sec_search(query="10-K/A", count=10,
   start=<last_offset.sec or 0>,
   start_date="<1 year ago>", end_date="<today>")` +
   `sec_search(query="10-Q/A", count=10,
   start_date="<1 year ago>", end_date="<today>")` — find
   recent amendments only (2 calls). Note: use start_date/
   end_date, NOT date_range (EDGAR ignores Elasticsearch-style
   range syntax).
3. For each amending company NOT in prior seeds (up to 8 unique
   CIKs): `sec_amendments(cik)` — full history (up to 8 calls).
4. For companies with 3+ amendments: `sec_8k(cik, limit=3)` —
   check for Item 4.02 (non-reliance) or 4.01 (auditor
   change) (up to 8 calls).
5. `sec_proxy(cik)` — executive turnover (up to 5 calls).
6. Cross-ref: `sanctions_match(name=company_name)` +
   `icij_search(query=company_name)` (up to 10 calls).
7. `gleif_search(query=company_name)` — ownership structure
   (up to 5 calls).
8. Save: `scan_history_write(scan_type="sec-amendment-cluster",
   seeds_used=[company names], findings_count=N,
   offsets={"sec": <new offset>})`.

**Hit**: Company with 3+ amendments AND auditor change or
non-reliance disclosure. Severity = HIGH if also sanctions/ICIJ,
MEDIUM if amendment cluster alone.

**So what**: Frequent amendments often signal accounting
irregularities, SEC comment letters, or auditor disagreements.
Non-reliance (Item 4.02) means prior financials cannot be
trusted — a precursor to enforcement actions and fraud
charges.

#### sec-officer-churn (budget: 50 calls) — US

Find companies with rapid executive departures.

1. Read scan history: `scan_history_read(scan_type="sec-officer-churn")`.
2. `sec_search(query="8-K", forms=["8-K"], count=20,
   start=<last_offset.sec or 0>,
   start_date="<6 months ago>", end_date="<today>")` —
   recent 8-K filings only (1 call).
3. For each NOT in prior seeds (up to 15):
   `sec_8k(cik, limit=5)` — extract Item 5.02 (officer
   departures) (up to 15 calls).
4. For companies with 2+ departures in 12 months:
   `sec_proxy(cik)` — current vs departed (up to 5 calls).
5. `sec_amendments(cik)` — departures + corrections?
   (up to 5 calls).
6. Cross-ref: `sanctions_match(name=departed_officer)` +
   `icij_search(query=departed_officer)` (up to 10 calls).
7. Save: `scan_history_write(scan_type="sec-officer-churn",
   seeds_used=[company names], findings_count=N,
   offsets={"sec": <new offset>})`.

**Hit**: Company with 2+ officer departures within 12 months.
Severity = HIGH if coinciding with amendments or auditor
changes, MEDIUM otherwise.

**So what**: Rapid C-suite turnover can signal internal
discovery of fraud, regulatory pressure, or governance
breakdown. Officers leaving before bad news surfaces is a
documented pattern in SEC enforcement cases.

#### bankruptcy-network (budget: 55 calls) — US

Find related entities filing bankruptcy with shared officers.

1. Read scan history: `scan_history_read(scan_type="bankruptcy-network")`.
2. `court_bankruptcy(query="chapter 11",
   filed_after="<1 year ago>")` +
   `court_bankruptcy(query="chapter 7",
   filed_after="<1 year ago>")` — recent filings only
   (2 calls).
3. For each case NOT in prior seeds (up to 8):
   `court_docket_detail(docket_id)` — parties + related
   cases (up to 8 calls).
4. For defendants/debtors: `sec_search(query=debtor_name,
   count=3)` — SEC registered? (up to 10 calls).
5. For SEC matches: `sec_proxy(cik)` — board members to
   find officer overlap (up to 5 calls).
6. `court_judge(query=debtor_name)` — serial filers
   across cases (up to 5 calls).
7. Cross-ref: `sanctions_match(name=officer_name)` +
   `icij_search(query=officer_name)` (up to 10 calls).
8. Save: `scan_history_write(scan_type="bankruptcy-network",
   seeds_used=[debtor names], findings_count=N)`.

**Hit**: Shared officers across 2+ bankruptcy filings.
Severity = HIGH if sanctions/ICIJ linked, MEDIUM otherwise.

**So what**: Serial bankruptcy by related entities with the
same officers is a fraud pattern — directors accumulate debt,
extract assets through related parties, then file for
protection. The US Trustee Program specifically monitors for
this.

### `--scan all` budget allocation

Run scans sequentially in this priority order:

| Order | Scan type | Budget | Risk | Jurisdiction |
|-------|-----------|--------|------|---|
| 1 | sanctions-evasion | 80 | CRITICAL | International |
| 2 | pep-opacity | 80 | HIGH | International |
| 3 | disqualified-director | 60 | HIGH | UK |
| 4 | nominee-shield | 60 | HIGH | International |
| 5 | intermediary-cluster | 60 | HIGH | International |
| 6 | rapid-dissolution | 60 | HIGH | UK |
| 7 | phoenix-company | 65 | HIGH | UK |
| 8 | sec-amendment-cluster | 55 | HIGH | US |
| 9 | sec-officer-churn | 50 | HIGH | US |
| 10 | bankruptcy-network | 55 | MEDIUM | US |
| 11 | llp-opacity | 55 | HIGH | UK |
| 12 | beneficial-ownership-gap | 55 | HIGH | International |
| 13 | property-layering | 55 | MEDIUM | UK |
| 14 | mass-registration | 50 | MEDIUM | International |
| | **Total** | **840** | | |

If a scan finishes under its budget, carry the remainder to the
next scan in the sequence.

### Scan report template

For a single scan type:

```
## Scan report: [scan-type]

Date: [YYYY-MM-DD]
Budget: [used]/[allocated] calls

### Executive summary

[1-2 sentences: how many instances found, severity distribution]

### Confirmed findings

#### Finding 1: [entity/person name] — [CRITICAL/HIGH/MEDIUM]

**Designated**: [YYYY-MM-DD] (from `properties.createdAt`)
**Datasets**: [N] lists (e.g. us_ofac_sdn, eu_fsf, ...)
**First indexed**: [YYYY-MM-DD] (from `first_seen`)

**Evidence**: [specific findings — names, node IDs, relationships]

**Chain**:
> [Person A] → *officer of* → [Entity B] (BVI, incorporated [date])
> → *intermediary* → [Firm C] (Panama, incorporated [date])

**Jurisdictions**: [list]
**Pattern**: [pattern name from INDEX.yaml]
**Confidence**: HIGH
**Follow-up**: `/investigate [name] --trace`

#### Finding 2: ...

### Summary

| Metric | Count |
|--------|-------|
| Seeds examined | [N] |
| Findings confirmed | [N] |
| CRITICAL | [N] |
| HIGH | [N] |
| MEDIUM | [N] |
| API calls used | [N]/[budget] |

### Standard caveats
[Include standard caveats]
```

For `--scan all`:

```
## Comprehensive scan report

Date: [YYYY-MM-DD]
Budget: [used]/500 calls

### Executive summary

[Overall findings across all 14 scan types]

### Results by scan type

| Scan type | Findings | CRITICAL | HIGH | MEDIUM | Calls |
|-----------|----------|----------|------|--------|-------|
| sanctions-evasion | [N] | [N] | [N] | [N] | [N]/80 |
| pep-opacity | [N] | [N] | [N] | [N] | [N]/80 |
| nominee-shield | [N] | [N] | [N] | [N] | [N]/60 |
| ... | | | | | |

### Top findings (ranked by severity)

[Top 10 findings across all scan types, ranked by severity
then confidence. If an entity appears in multiple scans,
note all matching patterns.]

### Detailed findings per scan type

#### sanctions-evasion
[Finding list]

#### pep-opacity
[Finding list]

...

### Standard caveats
[Include standard caveats]
```

### Scan visualization

After the scan report, ask:
"Would you like an interactive scan dashboard?"

If yes, build the scan data structure:

```python
scan_data = {
    "mode": "scan",
    "scan_types": ["sanctions-evasion"],   # or list of all types run
    "query": None,                          # None for standalone scan
    "generated_at": "2026-04-11 14:30 UTC",
    "budget": {"used": 312, "total": 500},
    "findings": [
        {
            "id": "finding-1",
            "scan_type": "sanctions-evasion",
            "severity": "CRITICAL",
            "confidence": "HIGH",
            "title": "Ahmad Santos — OFAC SDN linked to BVI entity",
            "summary": "Sanctioned person connected to offshore entity",
            "entities": [
                {"id": "os-NK-U8se...", "name": "Ahmad Santos",
                 "type": "Person", "sanctioned": True},
                {"id": "icij-10004476", "name": "SANTOS CMI LLP",
                 "type": "Entity", "sanctioned": False}
            ],
            "chain": [
                {"from": "Ahmad Santos", "rel": "officer_of",
                 "to": "Santos CMI Construction"},
                {"from": "Santos CMI Construction",
                 "rel": "registered_at", "to": "UK"}
            ],
            "jurisdictions": ["PH", "GB"],
            "pattern": "sanctions_evasion",
            "follow_up": "/investigate Ahmad Santos --trace"
        }
    ],
    "summary": {
        "total_findings": 8,
        "by_severity": {"CRITICAL": 2, "HIGH": 3, "MEDIUM": 3},
        "by_scan_type": {"sanctions-evasion": 3, "pep-opacity": 2},
        "jurisdictions_seen": ["GB", "BVI", "PA", "PH"],
        "calls_by_scan": {"sanctions-evasion": 72, "pep-opacity": 65}
    }
}
```

Pass this to `generate_visualization(scan_data, slug="scan-...",
open_browser=True)`. The visualizer detects `mode: "scan"` and
renders a scan dashboard instead of a network graph.

For combined mode (`<name> --scan <type>`), the scan findings are
added as a `"scan_findings"` key in the normal investigation data.
The visualizer renders the standard investigation graph plus a
"Scan Findings" tab.

---

## Standard caveats (include in all reports)

- Appearing in the ICIJ database does not indicate illegality
- Absence from the database does not indicate absence of offshore activity
- The ICIJ database covers 5 specific leaks, not the full offshore world
- Name matching is fuzzy — verify identities through additional sources
- OpenSanctions covers 320+ public lists — some lists may not be included
- This is a point-in-time screen — sanctions lists change daily

## Notes

- The `deep_trace` tool handles cross-source bridging automatically
- Total budget is 500 API calls across all phases
- High-connectivity nodes (>25 connections) are auto-pruned
- For ongoing tracking after any investigation, suggest `/investigate <name> --monitor`
- When a new pattern is found, propose adding it to `patterns/INDEX.yaml`
- Pattern probes (Step 3) are conditional — they only fire when
  relevant signals are present in Step 1-2 results
- Scan mode operates without a target name — it uses hardcoded
  search strategies to hunt for structural patterns
