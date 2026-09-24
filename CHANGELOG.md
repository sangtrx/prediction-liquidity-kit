# Changelog

This project uses a simple forward-moving changelog. Entries describe user-visible behavior and data-contract changes; internal refactors are omitted unless they affect reproducibility, compatibility, or safety boundaries.

## Version policy

The project is pre-1.0. Minor versions may include breaking API or fixture changes, but those changes must be called out here and must not silently reinterpret historical data or venue-rule versions.

A public release must identify the exact Git commit it was built from. Source-sensitive review and verification receipts apply only to that exact SHA; any source mutation requires a new candidate SHA and fresh receipts.

Venue reward rules have their own version identity and effective dates. Package version changes never replace or erase historical rule versions.

## [Unreleased]

- Contributor workflow and economic-boundary documentation.
- Public examples and first release remain pending the implementation and integration of the corresponding rule, allocation, sponsor, controller, and replay outcomes.

## [0.0.1] - 2026-09-19

- Initial public bootstrap.
- Package/CLI skeleton.
- Architecture and data-contract principles.
- Explicit simulation-only and non-live-capital boundary.
