# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Scan history tracking — repeated scans cover new ground instead of re-scanning
  the same seeds (`scan_history_read`/`scan_history_write` MCP tools)
- API health check before scans — validates API keys and reports degraded sources
  before burning scan budget (`scan_health_check` MCP tool)
- Seed rotation via pagination offsets for OpenSanctions, Companies House, SEC, CourtListener
- Recency bias in scan seeding — prefer recently sanctioned entities, recent filings,
  recent dissolutions
- Dynamic seed generation — replace hardcoded intermediary lists with discovery-based
  queries; rotate search terms for dissolved company scans
- Versioning system with CHANGELOG and bump script
- Version reported in HTML visualizations, JSON exports, and Markdown reports
- OpenSanctions `sort` parameter — enables `properties.createdAt:desc` to find
  recently designated entities instead of perennial top-10 names

### Fixed
- Sanctions-evasion scan now surfaces genuinely recent designations (days old)
  instead of Gaddafi/Al-Qaeda by using server-side sort on designation date
- `court_bankruptcy` now searches actual bankruptcy courts (nysb, deb, casb, etc.)
  instead of using nature_of_suit codes that returned appeals from district courts

### Changed
- Centralized version string in `sift/__init__.py` (was hardcoded in 8 client files)

## [0.4.0]

### Added
- Renamed to Sift
- 4 new data sources: CourtListener, Aleph, Land Registry, Wikidata
- 4 new visualization types
- 14 scan types for untargeted pattern hunting
- Interactive D3 network visualization with 8 analytical views
- Pattern matching engine with 24 detection patterns
- Multi-hop graph traversal across 9 data sources
- Background check tool for quick single-name screening
- Export to JSON and Markdown reports

## [0.3.0]

### Changed
- Renamed to open-investigator
- Full README and MIT license

## [0.2.0]

### Added
- OpenSanctions client and 12 MCP tools

## [0.1.0]

### Added
- Initial scaffold: MCP server for ICIJ Offshore Leaks Database
