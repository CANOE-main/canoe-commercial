# CANOE - Commercial Sector Model

This repository contains the commercial sector model for CANOE (Canadian Opportunities for Emissions Reduction). It aggregates data primarily from the NRCan Comprehensive Energy Use Database and EIA Annual Energy Outlook technology assumptions to build a TEMOA-compatible commercial sector SQLite database.

Access comprehensive documentation: [Here](https://canoe-main.github.io/canoe-commercial/)

## Overview

The module writes commercial sector rows into a SQLite database that canoe-base has already seeded with global tables (`time_period`, `region`, `time_season`, `time_of_day`). It supports:
- Hourly demand-specific distributions derived from NREL ComStock and weather mapping.
- Existing stock characterisation from NRCan CEUD tables + AEO CDM market shares.
- New technology parameters from the EIA AEO commercial demand module.
- Optional GHG emission activities via EPA emission factors.
- Caching of all downloaded data to speed up subsequent runs.
- Optional cloning of the database to Excel.

## Prerequisites

`canoe-base` must have already created and seeded the target SQLite database before this module runs.

## Usage

### 1. Environment Setup

```bash
conda env create -f environment.yml
conda activate canoe-backend
```

### 2. Configuration

All parameters are in [`input_files/params.toml`](input_files/params.toml). Key switches:

| Key | Default | Description |
|---|---|---|
| `include_dsd` | `true` | Write hourly demand-specific distributions |
| `include_emissions` | `false` | Write emission activity rows |
| `force_download` | `false` | Re-download cached data |
| `clone_to_xlsx` | `false` | Copy database to Excel after run |
| `validation_behavior` | `"error"` | `"error"` or `"warning"` for pre-run checks |

See [`SOURCES.md`](SOURCES.md) for details on all external data sources referenced by the model.

### 3. Running the Aggregation

From the repository root:

```bash
python -m canoe_commercial
```

Or directly:

```bash
python canoe_commercial/commercial_sector.py
```

The run sequence is:
1. Load and validate config from `input_files/params.toml`
2. Validate canoe-base DB structure (periods, regions, time slices)
3. Write fuel commodity rows (`techcom`)
4. For each province: DSDs → existing stock → new technologies → (optional) emissions
5. Write DataSource and DataSet registry rows, audit for missing data IDs

## Directory Structure

| Path | Description |
|---|---|
| `input_files/params.toml` | All aggregation parameters and switches |
| `input_files/` | CSV lookup tables, AEO CDM spreadsheet, comstock map |
| `data_cache/` | Created on first run; cached downloads |
| `canoe_commercial/commercial_sector.py` | Orchestration entry point |
| `canoe_commercial/setup.py` | `CANOECommercialConfig` Pydantic config model |
| `canoe_commercial/data_scraper.py` | Pure data acquisition (no SQL) |
| `canoe_commercial/validation.py` | Pre/post-run read-only DB checks |
| `canoe_commercial/sources.py` | DataSource registry factory |
| `canoe_commercial/techcom.py` | Writes module commodity rows |
| `canoe_commercial/comstock_dsd.py` | ComStock + weather-mapped DSDs |
| `canoe_commercial/existing_capacity.py` | Existing stock parameters |
| `canoe_commercial/new_capacity.py` | New technology parameters |
| `canoe_commercial/emission_activity.py` | GHG emission activity rows |
| `canoe_commercial/post_processing.py` | DataSource / DataSet registry |
| `canoe_commercial/weather_mapping.py` | US→CA weather similarity mapping |
| `canoe_commercial/utils.py` | Utility helpers |
| `docs/` | Documentation and Mermaid diagrams |

## License

See [LICENSE](LICENSE) file for details.
