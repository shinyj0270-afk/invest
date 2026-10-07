# Dashboard stability and first-load contract

This change covers upgrade items 1–6. Tests use synthetic data in an isolated copy;
an operating server restart and real saved-data measurement are separate checks.

- `/health` protocol is now 2. `root_id` identifies the checkout; `build_id` is the
  hash of Python and browser source bytes captured when the handler starts.
  `source_build_id` identifies the current files. `restart_required` becomes true
  after source changes. The launcher accepts only matching protocol, root and build.
- An existing matching-root stale server produces an actionable restart message.
  It does not terminate a process based on a listening port or process name.
  On Windows the launcher keeps its existing hidden-console creation flag.
- A source change while running returns a restart page for `/` and `/dashboard`
  and 503 for API mutations; newer HTML is not combined with older Python handlers.
  An early browser error banner also covers missing modules and initialization errors.
- `merge_financials(provider, official, *, as_of=None)` supplements individual
  missing accounts. All three live callers pass the financial cutoff. Identity,
  duplicate periods, currency, period start and fiscal segmentation are checked.
  Provider zero/signed values retain priority. EPS does not use the monetary tolerance.
  `cell_provenance[field]` carries source, available_at, publication_status, source_url
  and receipt. `build_table` rechecks each cell at its own cutoff and carries usable
  provenance. An unknown provider date does not grant a future official cell visibility.
- Recommendation UI exposes `state()` with draft and selected record ID/index.
  Automatic and manual reload share this state. A mode-scoped session draft also
  survives the browser refresh button. A successful monthly check retains the draft;
  a successful exception save clears it.
- Price cards distinguish today/previous/unknown retrieval and source observation
  time. Retrieval is not a trade time. Previous/unknown retrieval has a refresh action.
  Failed/partial price refresh retains prior observations; automatic daily status may
  expose `next_retry_at` and does not show provider URLs or credentials as errors.
- `/` first returns a small visible preparation screen without fetching data or
  starting collection. Its same-origin `/dashboard` request obtains the complete
  dashboard. Connection failures expose retry/help; a 503 source mismatch retains
  the restart page. Static exports remain self-contained.
- Live full-dashboard data uses `wire_format='live-v2'`: duplicated fundamental and trend metadata
  share references reconstructed by `DashboardStability.restoreWire`. All company
  financial tables/models are deferred to the existing authenticated `/company-view`.
  The authenticated `/holdings-frame` supplies the existing iframe and holdings API;
  it loads independently after the overview. Static exports still embed complete
  data and iframe content without network dependencies.
- `export_workspace(..., trend_following_data=None)` accepts a prebuilt trend model.
  The exporter is pure; saving observations belongs to its caller.
- `market_history.DAILY_PUBLICATION_TIME=(20,30)` is the single cutoff source.
  Exported `market_contract.same_day_after` drives both UI notices.
- The live server and financial service reuse one market source version across
  requests. File identity, size and nanosecond modification time of universe,
  histories and quotes invalidate the cache; malformed or changing files return
  pending instead of an old successful result. Concurrent readers decode once.
  Full-market source bars are internal read-only input; derived builders copy
  their own rows. Selected company requests copy only their own history and the
  benchmarks, avoiding repeated decoding of the real 274 MB history file.

## Verification

New portable registrations:

```text
python -m unittest tests.test_dashboard_stability tests.test_dashboard_payload
node tests/test_dashboard_stability.js
python tests/test_dashboard_stability_ui.py
```

The synthetic 1,369-company overview is constrained below 12 MiB, keeps all common
screener metrics, carries no initial company tables/models or inline holdings frame,
and includes no discovery price histories. Static completeness is tested separately.
Browser regression covers financial/manual/native refresh draft restoration, older
record selection, deferred frame contracts, lazy company switching, old quote labels,
missing TrendFollowingUI recovery, initial loading connection failure/restart
transition, and 390/320px layouts. Existing live holdings,
recommendation, portfolio-risk, financial-monitor and trend checks remain applicable.

The old launcher unit expectation was updated to require protocol 2 and a build hash.
The trend UI fixture now obtains its fake detail API from the complete static export
because live exports intentionally contain no initial company models.
