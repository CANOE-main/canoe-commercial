# canoe-commercial: External Data Sources

For human reference only — not consumed by any tooling.

| Source | What it provides | Accessed by | Cache file |
|---|---|---|---|
| NRCan Comprehensive Energy Use Database (CEUD) | Secondary energy consumption by end-use and fuel for Canadian provinces, commercial sector tables 1, 24, 32 | `data_scraper.fetch_nrcan_ceud_table` (via `utils.get_compr_db` wrapper) | `data_cache/<region_nrcan_id>_table<n>.csv` |
| US EPA GHG Emission Factors Hub (2024) | CO2, CH4, N2O emission factors by fuel type (lb/MMBtu) | `data_scraper.fetch_emission_factors` | `data_cache/ghg-emission-factors-hub-2024.csv` |
| StatCan Table 17100009 | Historical quarterly provincial population (Q1 values used) | `data_scraper.fetch_population_projections` | `data_cache/population_historical.csv` |
| StatCan Table 17100057 | Projected provincial population by scenario, gender, age (M1 scenario used) | `data_scraper.fetch_population_projections` | `data_cache/population_projection.csv` |
| StatCan Table 25100029 | Provincial energy use by fuel type for Atlantic provinces (used to disaggregate NRCan Atlantic aggregate) | `data_scraper.fetch_statcan_table` (via `utils.get_statcan_table` wrapper) | `data_cache/statcan_atlantic_energy.csv` |
| CER Canada's Energy Future | National real GDP projections by scenario (Global Net-zero scenario used) | `data_scraper.fetch_gdp_projections` | `data_cache/gdp_projections.csv` |
| EIA AEO CDM ktekx.xlsx | Technology menu for commercial sector equipment: efficiency, lifetime, investment and O&M costs by end-use and fuel | `data_scraper.fetch_aeo_data` (local file, no download) | none (local input file) |
| NREL Comstock | Hourly commercial building energy end-use consumption by US state and building type, used to derive demand-specific distributions and annual capacity factors | `data_scraper.fetch_comstock_table` | `data_cache/<state>_<building>.csv` |
| Renewables.ninja API | API token read from `input_files/rninja_api_token.txt` for weather data (token only, not currently used in data fetching) | `setup.config._get_rninja_api` | none |

## Notes

- StatCan Table 25100029 is also fetched by `canoe-residential` (same table, likely same CSV format). Both modules download and cache it independently — a candidate for consolidation when a shared utility package is created.
- The Comstock URL is parameterized in `params.yaml` as `comstock.url` with `<su>` (state uppercase), `<sl>` (state lowercase), and `<b>` (building type) placeholders.
- `force_download: true` in `params.yaml` bypasses all local caches and re-downloads everything.
