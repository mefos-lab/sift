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
```

When no flag is given, the default mode is a full cross-reference
investigation (the most comprehensive single-name analysis).

---

## Shared procedure (all modes)

These steps run regardless of mode. Mode-specific steps follow.

### Step 1: Deep traversal

Use `deep_trace` to search both databases with cross-source bridging:

```
deep_trace(names: ["<name>"], depth: <depth>, budget: <budget>)
```

| Mode | depth | budget |
|------|-------|--------|
| default / --trace | 2 | 50 |
| --trace --depth 3 | 3 | 100 |
| --patterns | 2 | 50 |
| --compliance | 1 | 30 |
| --monitor | 0 (skip deep_trace) | — |
| --jurisdiction | 2 | 50 |
| 2-4 names | 2 | 60 |
| 5+ names | 1 | 100 |

For **--monitor**, skip `deep_trace` and use `sanctions_monitor`
directly. For **multi-name** investigations, all names go into a
single `deep_trace` call as seeds — the traversal expands outward
from each seed and discovers where their networks overlap.

### Step 2: Enrich key findings

For the highest-priority nodes from the traversal:
- Sanctioned entities: `sanctions_entity` (nested=true)
- PEP matches: `sanctions_entity` for full profile
- Cross-source links (both databases): `icij_entity` + `sanctions_entity`

### Step 3: Pattern analysis

Cross-reference findings against `patterns/INDEX.yaml`:
- Starburst (hub-and-spoke)
- Matryoshka (nested jurisdiction chains)
- Nominee Shield (professional nominees)
- Intermediary Cluster (single formation agent)
- Mirror (parallel entities across jurisdictions)
- Temporal Cluster (formation bursts)
- Sanctions Evasion Structure (offshore + sanctioned)
- PEP Opacity Layer (offshore + PEP)
- Regulatory Arbitrage Chain (jurisdiction gap exploitation)

When a NEW pattern is identified, propose adding it to the library.

### Step 4: Produce report

Use the mode-specific report template below.

### Step 5: Visualization

After producing the report, ask:
"Would you like an interactive network visualization?"

If yes, the `deep_trace` result is already in the format expected by
`sift.visualizer.generate_visualization()`. Pass it
directly — it includes hop distances for visual encoding.

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

[Named patterns from patterns/INDEX.yaml]

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

1. Use `sanctions_match` with name + all provided properties,
   `threshold: 0.5`
2. For matches >= 0.5: `sanctions_entity` + `sanctions_provenance`
3. Also run shallow `deep_trace` (depth 1) for offshore context

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
   deep_trace(names: ["name1", "name2", ...], depth: 2, budget: 60)
   ```
   For 5+ names, increase budget to 100 and reduce depth to 1.

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

## Standard caveats (include in all reports)

- Appearing in the ICIJ database does not indicate illegality
- Absence from the database does not indicate absence of offshore activity
- The ICIJ database covers 5 specific leaks, not the full offshore world
- Name matching is fuzzy — verify identities through additional sources
- OpenSanctions covers 320+ public lists — some lists may not be included
- This is a point-in-time screen — sanctions lists change daily

## Notes

- The `deep_trace` tool handles cross-source bridging automatically
- Budget parameter prevents runaway API calls — increase for thorough work
- High-connectivity nodes (>25 connections) are auto-pruned
- For ongoing tracking after any investigation, suggest `/investigate <name> --monitor`
- When a new pattern is found, propose adding it to `patterns/INDEX.yaml`
