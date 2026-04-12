# Sift — Improvement Roadmap

Prioritized by impact with current data sources. No new APIs needed.

## 1. ~~SEC EDGAR Filing Content Parsing~~ (mostly done)
- ~~Subsidiary lists (Exhibit 21) — complete corporate tree with jurisdictions~~ ✓ `get_subsidiary_list` + `_parse_exhibit_21`
- ~~XBRL financial data — revenue, assets, liabilities~~ ✓ `get_company_facts` (10 metrics, annual + quarterly)
- ~~Filing document index~~ ✓ `get_filing_documents`
- Related party transactions — names, amounts, terms
- Schedule 13D/G beneficial ownership — stake percentages, intent
- Risk factor sections mentioning legal proceedings or regulatory actions

## 2. Wikidata Deep Enrichment
Extract structured biographical and relational data for PEPs and key entities.
- Political positions held with start/end dates
- Family relationships (spouse, children, parents, siblings)
- Citizenship and nationality
- Education and professional history
- Estimated net worth where available
- Board memberships and corporate roles
- Cross-reference political appointment dates with entity incorporation dates
- **Why:** Temporal correlation ("appointed minister 3 months before forming 5 BVI companies") is the most powerful investigative signal available from public data.

## 3. Companies House Accounts and Filing History
Go beyond officers/PSC — pull financial accounts and filing timeline.
- Annual accounts: net assets, revenue, profit (where filed)
- Filing history: gaps, late filings, change of registered office
- Confirmation statements and their timeliness
- Charge register (secured lending)
- **Why:** Financial data for UK entities plus filing gaps as red flags.

## 4. CourtListener Docket Enrichment
Extract substantive content from court cases, not just case names.
- Complaint/petition text (where available via RECAP)
- Amounts in dispute
- Named parties and their roles (plaintiff, defendant, third-party)
- Case type and nature of suit codes
- Related cases
- **Why:** "Federal court case filed" is useless without context. The complaint text often details the alleged scheme.

## 5. Temporal Correlation Analysis
Cross-reference dated events across sources for investigative signals.
- Entity formation dates vs political appointment dates (Wikidata)
- Entity formation dates vs sanctions listing dates (OpenSanctions)
- Filing bursts (multiple filings in a short window)
- Formation-to-dissolution timelines (rapid dissolution = red flag)
- **Why:** Timing is often the strongest evidence of intent. All the dates are already in the data.

## 6. Financial Secrecy Index Integration
Score jurisdictions using Tax Justice Network's Financial Secrecy Index.
- Per-jurisdiction secrecy score (0-100)
- Breakdown by category (banking secrecy, entity transparency, etc.)
- Network-level aggregate secrecy score
- Flag jurisdictions on FATF grey/black lists
- Basel AML Index scores
- **Why:** Replaces our simple jurisdiction list with established, peer-reviewed risk scoring. Data is public and static (updated biannually).

## 7. Network Topology Analysis
Go beyond degree counts to structural analysis.
- Betweenness centrality — who's the linchpin?
- Community detection — identify clusters within the network
- Cut vertices — whose removal disconnects the graph
- Shortest path analysis between flagged entities
- Structural hole detection — who bridges otherwise disconnected groups
- **Why:** Structural position in the network is often more revealing than individual node properties.

## 8. GLEIF Full Ownership Chain
Extract complete ownership data from LEI records.
- Ultimate parent entity
- Direct parent entity
- Reporting exceptions (entity claims exemption from reporting — itself a red flag)
- Relationship dates and status
- Fund relationships (for investment vehicles)
- **Why:** GLEIF is the only authoritative, standardized corporate ownership database. We're only using it for basic lookup.

## 9. Hypothesis Generation
Have the agent produce investigative theories, not just findings.
- "This structure appears designed to..." — state what the arrangement achieves
- Cite specific entities, jurisdictions, and patterns supporting the theory
- Identify what evidence would confirm or refute the hypothesis
- Suggest specific investigative steps to test each hypothesis
- **Why:** The gap between "here are findings" and "here's what's happening" is where investigative value lives.

## 10. Agent-Assisted Entity Resolution
Use the agent's judgment for fuzzy matching decisions the normalizer can't make.
- Review near-duplicate name clusters and assess deliberate vs incidental
- Cross-reference against known aliases in OpenSanctions
- Consider jurisdictional context (weak ID verification = more likely deliberate)
- Flag assessment in the report with reasoning
- **Why:** Automated fuzzy matching either over-merges or under-merges. The agent can apply context the normalizer can't.

## 5. Viewer: Enrichment Data Panels
Surface the new enrichment data (items 1a-4) in the investigation viewer.
- **Financials panel** — CH accounts (net assets, revenue, profit), SEC XBRL metrics, CH charges/secured lending. Table with sparklines or bar charts for multi-year data.
- **Filing timeline extension** — CH filing history + SEC filings on the existing Timeline tab. Flag gaps, late filings, and address changes as red markers.
- **Family/associates tree** — Wikidata family relationships + PEP positions. Extend Ownership Tree tab or add a new "People" tab with a family tree layout.
- **Litigation panel** — CourtListener complaint text, party roles (plaintiff/defendant), amounts in dispute, nature of suit. New tab or section in Reference.
- **Temporal correlation highlights** — Overlay political appointment dates against entity formation dates on the Timeline tab. Flag overlaps within ±6 months.

## Viewer Improvements (remaining)
- Inline entity links from narrative counts to entity index (item 4 from original list)
- End-to-end test of skill-generated next steps (item 5)
