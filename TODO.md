# Sift — Improvement Roadmap

Prioritized by impact with current data sources. No new APIs needed.

## ~~1. SEC EDGAR Filing Content Parsing~~ ✓
- ~~Subsidiary lists (Exhibit 21)~~ ✓ `get_subsidiary_list` + `_parse_exhibit_21`
- ~~XBRL financial data~~ ✓ `get_company_facts`
- ~~Filing document index~~ ✓ `get_filing_documents`
- ~~Related party transactions~~ ✓ `get_related_party_transactions` (Item 13 extraction + table parsing)
- ~~Schedule 13D/G beneficial ownership~~ ✓ `get_schedule_13d` (reporting person, % of class, purpose, source of funds)
- ~~Risk factor sections~~ ✓ `get_risk_factors` (Item 1A, keyword-filtered)

## ~~2. Wikidata Deep Enrichment~~ ✓
- ~~Political positions with start/end dates~~ ✓ `get_pep_info`
- ~~Family relationships~~ ✓ `get_family` (spouse, children, parents, siblings with dates)
- ~~Citizenship and nationality~~ ✓ `get_citizenship`
- ~~Education and professional history~~ ✓ `get_education_career`
- ~~Board memberships and corporate roles~~ ✓ included in `get_education_career`
- ~~Cross-reference political dates vs entity inception~~ ✓ `cross_reference_dates` (±6 month overlap detection)
- ~~Composite enrichment~~ ✓ `get_deep_enrichment` (all above in parallel)
- Estimated net worth where available (not in structured Wikidata — skip)

## ~~3. Companies House Accounts and Filing History~~ ✓
- ~~Filing history with gap analysis~~ ✓ `get_filing_history` + `_analyze_filing_gaps`
- ~~Annual accounts summary~~ ✓ `get_accounts` (type, period, next due, overdue)
- ~~Confirmation statements~~ ✓ `get_confirmation_statements` (timeliness gaps >14mo)
- ~~Charge register~~ ✓ `get_charges` (status, lender names, particulars)

## ~~4. CourtListener Docket Enrichment~~ ✓
- ~~Complaint/petition text~~ ✓ `get_complaint_text` (entry #1 RECAP document)
- ~~Amounts in dispute~~ ✓ `_extract_amount` (keyword-proximate dollar parsing)
- ~~Named parties and roles~~ ✓ `get_parties` (plaintiff/defendant/attorney)
- ~~Case type and nature of suit~~ ✓ `get_docket_detail`
- ~~Related cases~~ ✓ included in `get_docket_detail`

## 5. Temporal Correlation Analysis (partially done)
- ~~Entity formation dates vs political appointment dates~~ ✓ `wikidata_date_xref`
- Entity formation dates vs sanctions listing dates (OpenSanctions)
- Filing bursts (multiple filings in a short window)
- Formation-to-dissolution timelines (rapid dissolution = red flag)
- **Why:** Timing is often the strongest evidence of intent.

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

## ~~8. GLEIF Full Ownership Chain~~ ✓
- ~~Ultimate parent entity~~ ✓ `get_all_relationships`
- ~~Direct parent entity~~ ✓
- ~~Direct + ultimate child entities (full subsidiary tree)~~ ✓
- ~~Search filters (jurisdiction, status, legal form, category)~~ ✓ enhanced `search()`
- Reporting exceptions (entity claims exemption from reporting — itself a red flag)
- Relationship dates and status
- Fund relationships (for investment vehicles)

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

## ~~Viewer: Enrichment Data Panels~~ ✓
- ~~Financials tab~~ ✓ SEC XBRL metrics, UK accounts, charge register
- ~~Filing timeline extension~~ ✓ CH/SEC filings as swim lane, gap markers
- ~~People tab~~ ✓ family tree, career timeline, PEP badges
- ~~Litigation tab~~ ✓ case cards, parties, collapsible complaint text, bankruptcy cases
- ~~Temporal correlation highlights~~ ✓ dashed lines on timeline for ±6mo overlaps
- ~~Corporate Risk tab~~ ✓ insolvency cases, disqualified directors, filing amendments
- ~~Material Events tab~~ ✓ 8-K events, executive compensation, board members
- ~~Property tab~~ ✓ UK property transactions, price statistics, high-value purchases
- ~~Documents tab~~ ✓ Aleph leaked documents

## ~~Expanded API Coverage~~ ✓
- ~~Companies House: disqualified directors, insolvency, dissolved search~~ ✓
- ~~Aleph: entity expand, collection documents, relationships~~ ✓
- ~~GLEIF: filtered search, full relationship tree~~ ✓
- ~~Land Registry: address history, area stats, high-value search~~ ✓
- ~~CourtListener: opinions, judge/attorney search, bankruptcy~~ ✓
- ~~SEC EDGAR: proxy statements (DEF 14A), 8-K events, amendments~~ ✓
- ~~background_check phase 2 enrichment~~ ✓ insolvency, disqualified, amendments, 8-K, bankruptcy
- ~~ownership_trace full tree~~ ✓ uses `get_all_relationships`

## Viewer Improvements (remaining)
- Inline entity links from narrative counts to entity index
- End-to-end test of skill-generated next steps
