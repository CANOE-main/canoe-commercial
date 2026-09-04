# canoe-commercial: Decision Log

Each entry covers a `(?)` table or ambiguous ownership question surfaced during Stage 3
(global vs. module-specific table classification). Format follows the template in the
design document (§13).

---

### Decision 1 — `TimeSegmentFraction` / `SeasonLabel` / `time_season_sequential`

- **Question:** The v3.2 module wrote `TimeSegmentFraction`, `TimeSeason`, and `SeasonLabel`
  rows (hourly segment fractions, seasonal sequence, and season name registry). What do the
  v4.0 equivalents look like, and who owns them?
- **Decision:** These are global (B) tables — canoe-base seeds them, commercial validates.
  The commercial module no longer writes to any of these tables. `validation.check_missing_time_slices`
  reads `time_season` and `time_of_day` to confirm the seasons and time-of-day slots the
  module expects are present before any writes occur.
- **Owner/rationale:** Decided during Stage 3 refactor. Time-slice definitions are shared
  model structure — every sector module's DSD rows are indexed against the same time grid,
  so it cannot be owned by any one sector.
- **Follow-ups:**
  - Confirm the v4.0 column names for `time_season` (`season`) and `time_of_day` (`tod`)
    match what `validation.py` queries — verify against the actual canoe-base DB once
    migration to v4.0 models is complete (Stage 4).
  - `time_season_sequential` (the v4.0 replacement for `TimeSegmentFraction`) is not yet
    validated here because commercial does not currently use it directly. If a future
    feature requires it, add a check in `validation.check_missing_time_slices`.

---

### Decision 2 — Emission commodity (`CO2eq`)

- **Question:** The v3.2 module wrote a `Commodity` row for `CO2eq` (flag='e') in
  `pre_process()`. Should commercial own this row?
- **Decision:** No. The emission commodity (`CO2eq` or whatever key `params.emission_commodity`
  holds) is a cross-sector entity — agriculture, industry, commercial, and electricity all
  produce `emission_activity` rows referencing it. canoe-base seeds this commodity row.
  Commercial validates its presence via `validation.check_emission_commodity` before writing
  any `EmissionActivity` rows.
- **Owner/rationale:** Decided during Stage 3 refactor. A commodity that appears as the
  `emis_comm` in every sector's emission activity table cannot be owned by a single sector
  module without creating a write-ordering dependency.
- **Follow-ups:**
  - When refactoring other sector modules, confirm they do not write the emission commodity
    row either — it should only ever be seeded by canoe-base.
  - If `cost_emission` (carbon price) rows are ever needed, those are also cross-sector
    policy parameters and should follow the same pattern (canoe-base or a future policy
    module owns them).

---

### Decision 3 — Existing vintage periods (`time_period` flag='e')

- **Question:** `post_process()` previously inferred existing vintage years from the
  `Efficiency` table and inserted them into `time_period` with `flag='e'`. Two options:
  (a) canoe-base seeds all historical periods, commercial validates; (b) commercial inserts
  its own vintage periods as a special case.
- **Decision:** Option (a). canoe-base seeds the full historical period range. Commercial
  validates in `post_process()` (after Efficiency rows are written, so vintage years are
  known) via `validation.validate_existing_vintage_periods`. If canoe-base is missing any
  vintage year the module needs, validation fails loudly.
- **Owner/rationale:** Decided during Stage 3 refactor (user confirmation). Keeping the
  module from writing global time structure is a hard goal — even historical periods belong
  to canoe-base. This does require canoe-base to seed a generous historical range (typically
  the base year minus max lifetime of any technology, stepping back in `period_step`
  increments).
- **Follow-ups:**
  - Document for canoe-base: commercial's technology lifetimes extend back roughly
    `base_year - max(lifetime)` years. canoe-base must seed `time_period (flag='e')` rows
    at least that far back in `period_step` increments.
  - The Efficiency query in `post_process()` uses the v3.2 table name `Efficiency`
    (CamelCase). Update to `efficiency` when migrating to v4.0 models in Stage 4.

---

### Decision 4 — `reference` / `bibliography` / `DataSource` citations

- **Question:** The `reference`/`bibliography` classes in `setup.py` are a hand-rolled
  citation management system that pre-dates Workstream 2's Pydantic approach. Citations
  already reach the DB via `DataSource.bulk_replace_into_sql` in `post_process()`.
  Should these classes be replaced now?
- **Decision:** Deferred to Stage 4 (Workstream 4, item 5). The existing classes work
  correctly and produce valid `DataSource` rows. Replacing them with a plain list of
  `DataSource(...)` Pydantic instances is lower priority than migrating write models to
  v4.0 (Stage 4), which will touch all the same callsites anyway.
- **Owner/rationale:** Deferred during Stage 3 review.
- **Follow-ups:**
  - In Stage 4, when migrating `DataSource` to v4.0 models, also replace `bibliography`/
    `reference` with a plain ordered list of `DataSource(...)` instances defined near the
    top of `post_processing.py` or a dedicated `sources.py`.
