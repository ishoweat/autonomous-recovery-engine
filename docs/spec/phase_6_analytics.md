# Phase 6: Analytics & Learning Report

## Objective
Ensure the UI properly surfaces real persisted incident data in the Analytics and Learning Report tabs without resorting to mock, duplicate, or templated placeholder data.

## Technical Requirements
1. **Database Aggregation:**
   - Create or update an endpoint (e.g., `/api/v1/roi/records` or `/api/v1/incidents/analytics`) that queries the Postgres `Incident` table.
   - Calculate MTTR strictly from genuine start-to-resolve timestamps of completed incidents.
   - Aggregate "Incidents Prevented" or "Cost Saved" strictly using an established heuristic applied to actual records, not static UI constants.
2. **Learning Report Integrity:**
   - Ensure `get_weekly_learning_report` only returns successfully resolved incidents.
   - Filter out duplicate logs and placeholder repositories (`owner/repo`, `test-org/test-repo`).
   - Use the actual `root_cause` and patch explanation from the database.
3. **UI Labeling:**
   - For presentation purposes, if the genuine count is 0 because of an empty database, the UI should reflect 0.
   - Any seeded or mocked demo data used explicitly for presentation *must* be labeled visually as `[BENCHMARK]` or `[DEMO DATA]`.

## Acceptance Criteria
- Analytics correctly reflect 1 completed incident if only 1 end-to-end test was run.
- The UI contains no hardcoded `$9,317` or `49 incidents` unless dynamically calculated from records.
- Learning Report cleanly lists genuine resolved incidents without placeholder repo names.
