"""
Data acquisition for canoe-commercial.

All functions in this module:
  - take explicit parameters (no config singleton)
  - return plain pandas.DataFrame / dict objects
  - contain all network calls, file parsing, and caching
  - import nothing from canoe_schema
  - write no SQL

External sources accessed by this module:
  See SOURCES.md for the full table.
"""

import datetime
import os
import requests
import urllib.request
import zipfile

import pandas as pd


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def fetch_or_cache(
    url: str,
    cache_dir: str,
    name: str = None,
    force_download: bool = False,
    **kwargs,
) -> pd.DataFrame | None:
    """
    Download a CSV or Excel file from url and cache locally as CSV.

    Source: any HTTP/HTTPS URL.
    Returns: DataFrame of the downloaded file.
    Cache: cache_dir/<stem>.csv
    """
    if name is None:
        name = url.split("/")[-1].split("\\")[-1]

    file_type = url.split(".")[-1].lower()
    stem = os.path.splitext(name)[0]
    cache_file = os.path.join(cache_dir, stem + ".csv")

    if not force_download and os.path.isfile(cache_file):
        print(f"Got {name} from local cache.")
        return pd.read_csv(cache_file, index_col=0, dtype="unicode")

    print(f"Downloading {name} ...")
    try:
        if "xl" in file_type:
            data = pd.read_excel(url, **kwargs)
        else:
            data = pd.read_csv(url, **kwargs)
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None

    try:
        os.makedirs(cache_dir, exist_ok=True)
        data.to_csv(cache_file)
        print(f"Cached {name}.")
    except Exception as e:
        print(f"Failed to cache {cache_file}: {e}")

    return data


def fetch_statcan_table(
    table_id: int,
    cache_dir: str,
    save_as: str = None,
    force_download: bool = False,
    filter=None,
    **kwargs,
) -> pd.DataFrame | None:
    """
    Download a StatCan table by numeric ID via the Statistics Canada REST API.

    Source: Statistics Canada (https://www150.statcan.gc.ca/)
    Returns: DataFrame with the full table rows, with optional filter applied.
    Cache: cache_dir/<save_as>.csv
    """
    if save_as is None:
        save_as = f"statcan_{table_id}"
    if not save_as.endswith(".csv"):
        save_as += ".csv"
    cache_file = os.path.join(cache_dir, save_as)

    if not force_download and os.path.isfile(cache_file):
        try:
            df = pd.read_csv(cache_file, index_col=0)
            print(f"Got StatCan table {table_id} ({save_as}) from local cache.")
            return df
        except Exception:
            print(f"Could not read cached StatCan table {table_id}; re-downloading.")

    url = f"https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{table_id}/en"
    response = requests.get(url)
    if not response.ok:
        print(f"StatCan request for {table_id} failed. Status: {response.status_code}")
        return None

    print(f"Downloading StatCan table {table_id}...")
    filehandle, _ = urllib.request.urlretrieve(response.json()["object"])
    with zipfile.ZipFile(filehandle, "r") as zf:
        with zf.open(f"{table_id}.csv") as f:
            df = pd.read_csv(f, **kwargs)

    if filter is not None:
        df = filter(df)

    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(cache_file)
    print(f"Cached StatCan table {table_id} as {save_as}.")
    return df


# ---------------------------------------------------------------------------
# NRCan CEUD
# ---------------------------------------------------------------------------

def fetch_nrcan_ceud_table(
    region_nrcan_id: str,
    table_number: int,
    nrcan_url_template: str,
    base_year: int,
    cache_dir: str,
    first_row: int = 0,
    last_row: int = None,
    force_download: bool = False,
) -> pd.DataFrame | None:
    """
    Download an NRCan Comprehensive Energy Use Database table for one region.

    Source: NRCan CEUD (nrcan_url_template parameterized by region nrcan_id,
            base_year, and table_number).
    Returns: DataFrame with fuel names as index and integer year columns,
             values as floats (PJ unless otherwise noted in the source).
    Cache: cache_dir/<derived_name>.csv (via fetch_or_cache)
    """
    url = (
        nrcan_url_template
        .replace("<y>", str(base_year))
        .replace("<r>", region_nrcan_id.lower())
        .replace("<t>", str(table_number))
    )
    df = fetch_or_cache(url, cache_dir, force_download=force_download, skiprows=10)
    if df is None:
        return None

    df = df.iloc[first_row:] if last_row is None else df.iloc[first_row:last_row]
    df = df.drop("Unnamed: 0", axis=1, errors="ignore").set_index("Unnamed: 1").dropna()
    df.index.name = None
    df.index = [_clean_row_label(str(idx)) for idx in df.index]
    df.columns = [int(col) for col in df.columns]
    df = df.astype(float, errors="ignore")
    return df


def _clean_row_label(s: str) -> str:
    """Strip digits 1-9 and non-alphanumeric chars (except punctuation) from NRCan row labels."""
    cleaned = "".join(c for c in s if c in "- /()–" or c.isalnum())
    return "".join(c for c in cleaned if c not in "123456789").lower()


# ---------------------------------------------------------------------------
# Population and GDP projections (StatCan / CER)
# ---------------------------------------------------------------------------

def fetch_population_projections(
    regions_df: pd.DataFrame,
    cache_dir: str,
    force_download: bool = False,
    m_scenario: str = "Projection scenario M1: medium-growth",
) -> dict[str, pd.DataFrame]:
    """
    Fetch historical and projected provincial population from StatCan.

    Sources:
      - StatCan Table 17100009: historical quarterly population (Q1 only).
      - StatCan Table 17100057: projected population by scenario, gender, age.
    Returns: dict mapping region_code -> DataFrame(index=year, columns=["population"])
             Historical data is used first, followed by provincial projections, then
             Canadian projections indexed to the last provincial data point.
    Cache: cache_dir/population_historical.csv, cache_dir/population_projection.csv
    """
    df_exs = fetch_statcan_table(
        17100009,
        cache_dir,
        save_as="population_historical",
        force_download=force_download,
        filter=lambda df: df.loc[df["REF_DATE"].str.contains("-01")],
        usecols=[0, 1, 9],
    )
    df_exs["REF_DATE"] = df_exs["REF_DATE"].str.removesuffix("-01")

    df_proj = fetch_statcan_table(
        17100057,
        cache_dir,
        save_as="population_projection",
        force_download=force_download,
        filter=lambda df: df.loc[
            (df["Projection scenario"] == m_scenario)
            & (df["Gender"] == "Total - gender")
            & (df["Age group"] == "All ages")
        ],
        usecols=[0, 1, 3, 4, 5, 12],
    )
    df_proj = df_proj.copy()
    df_proj["VALUE"] *= 1000

    populations = {}
    for region, row in regions_df.iterrows():
        if not row["include"]:
            continue

        exs = df_exs.loc[df_exs["GEO"].str.upper() == row["description"].upper()].dropna()
        prov = df_proj.loc[
            (df_proj["GEO"].str.upper() == row["description"].upper())
            & (df_proj["REF_DATE"] > int(exs["REF_DATE"].values[-1]))
        ].dropna()

        ca = df_proj.loc[
            (df_proj["GEO"].str.upper() == "CANADA")
            & (df_proj["REF_DATE"] >= int(prov["REF_DATE"].values[-1]))
        ].dropna().copy()
        ca["VALUE"] = ca["VALUE"].iloc[1:] * prov["VALUE"].values[-1] / ca["VALUE"].values[0]
        ca.dropna(inplace=True)

        data = [*exs["VALUE"].tolist(), *prov["VALUE"].tolist(), *ca["VALUE"].tolist()]
        pop = pd.DataFrame(
            index=range(int(exs["REF_DATE"].values[0]), int(ca["REF_DATE"].values[-1]) + 1),
            data=[int(d) for d in data],
            columns=["population"],
        )
        pop.index.rename("year", inplace=True)
        populations[region] = pop

    return populations


def fetch_gdp_projections(
    gdp_url: str,
    base_year: int,
    cache_dir: str,
    scenario: str = "Global Net-zero",
    variable: str = "Real Gross Domestic Product ($2012 Millions)",
    force_download: bool = False,
) -> pd.DataFrame:
    """
    Fetch national GDP projections from CER and index to base_year.

    Source: CER Canada's Energy Future (gdp_url — CSV download).
    Returns: DataFrame(index=year, columns=["gdp"]) where gdp == 1.0 at base_year.
    Cache: cache_dir/gdp_projections.csv
    """
    cache_file = os.path.join(cache_dir, "gdp_projections.csv")

    if not force_download and os.path.isfile(cache_file):
        print("Got gdp_projections.csv from local cache.")
        df_gdp = pd.read_csv(cache_file, index_col=0)
    else:
        print("Downloading gdp_projections.csv...")
        df_raw = pd.read_csv(gdp_url)
        df_gdp = df_raw.loc[
            (df_raw["Variable"] == variable) & (df_raw["Scenario"] == scenario)
        ]
        df_gdp = (
            df_gdp[["Year", "Value"]]
            .rename({"Year": "year", "Value": "gdp"}, axis="columns")
            .set_index("year")
        )
        os.makedirs(cache_dir, exist_ok=True)
        df_gdp.to_csv(cache_file)
        print("Cached gdp_projections.csv locally.")

    return df_gdp / df_gdp.loc[base_year]


# ---------------------------------------------------------------------------
# AEO technology menu (local file, no network call)
# ---------------------------------------------------------------------------

def fetch_aeo_data(aeo_file: str, indexing_file: str) -> pd.DataFrame:
    """
    Load the EIA AEO CDM technology menu (ktekx.xlsx) and apply readable column mappings.

    Source: EIA Annual Energy Outlook CDM file (local input file — no network call).
    Returns: DataFrame with columns including techname, serv, fuel, reg, share,
             efficiency, life, capcst, maintcst (columns from the ktek sheet).
    Cache: none (local file).
    """
    df = pd.read_excel(aeo_file, sheet_name="ktek", skiprows=68, index_col=False).iloc[1:, 0:27]
    cdm_idx = pd.read_csv(indexing_file, index_col=0)
    for col in df.columns:
        if col in cdm_idx.columns:
            df[col] = df[col].map(lambda n: cdm_idx.loc[n, col])
    df["techname"] = df["techname"].str.lower()
    return df


# ---------------------------------------------------------------------------
# EPA emission factors
# ---------------------------------------------------------------------------

def fetch_emission_factors(
    url: str,
    cache_dir: str,
    force_download: bool = False,
) -> pd.DataFrame:
    """
    Download EPA GHG Emission Factors Hub spreadsheet and return raw factors by fuel.

    Source: US EPA GHG Emission Factors Hub (url — Excel spreadsheet).
    Returns: DataFrame(index=fuel_name, columns=["CO2 Factor", "CH4 Factor", "N2O Factor"])
             with raw numeric values as published by EPA (unit conversion to ktCO2eq/PJ
             is done at the call site using config conversion_factors).
    Cache: cache_dir/<filename>.csv
    """
    return fetch_or_cache(url, cache_dir, force_download=force_download, skiprows=14, nrows=76, index_col=2)


# ---------------------------------------------------------------------------
# NREL Comstock
# ---------------------------------------------------------------------------

def fetch_comstock_table(
    us_state: str,
    building: str,
    url_template: str,
    cache_dir: str,
    timezone: str = "UTC",
    force_download: bool = False,
) -> pd.DataFrame:
    """
    Download an NREL Comstock hourly energy use CSV for a US state and building type.

    Source: NREL Comstock (url_template parameterized by <su>=state upper, <sl>=state lower,
            <b>=building type).
    Returns: DataFrame(index=timestamp, columns=[end_use columns...]) with data
             timezone-converted to `timezone` and rolled so row 0 is 00:00 on Jan 1.
    Cache: cache_dir/<filename>.csv
    """
    url = (
        url_template
        .replace("<su>", us_state.upper())
        .replace("<sl>", us_state.lower())
        .replace("<b>", building)
    )
    file = url.split("/")[-1]
    cache_file = os.path.join(cache_dir, file)

    if not force_download and os.path.isfile(cache_file):
        print(f"Got {file} from local cache.")
        return pd.read_csv(cache_file, index_col="timestamp")

    print(f"Downloading {file}...")
    try:
        df = pd.read_csv(url, index_col="timestamp")
    except Exception as e:
        print(f"Failed to download Comstock table from {url}")
        raise e

    # Comstock starts at 01:00 and ends at 00:00; roll so row 0 is 00:00 Jan 1
    df = df.iloc[list(range(-1, len(df) - 1))]
    df = _realign_timezone(df, from_timezone="EST", to_timezone=timezone)
    df = df.loc[pd.DatetimeIndex(df.index).minute == 0]

    os.makedirs(cache_dir, exist_ok=True)
    df.to_csv(cache_file)
    print(f"Cached {file} locally.")
    return df


def _realign_timezone(
    df: pd.DataFrame,
    from_timezone: str,
    to_timezone: str,
) -> pd.DataFrame:
    """
    Convert timezone of a time-indexed DataFrame and roll so row 0 is 00:00 Jan 1.

    Handles leap-year edge cases by falling back to the first 00:00 occurrence if
    Jan 1 00:00 is not found after conversion.
    """
    df_shifted = df.copy()
    time = pd.to_datetime(df_shifted.index)

    if time.tzinfo is None:
        time = time.tz_localize(from_timezone)
    new_time = time.tz_convert(to_timezone)

    zero_hour = new_time[
        (new_time.month == 1) & (new_time.day == 1) & (new_time.time == datetime.time(0, 0))
    ]
    if len(zero_hour) == 0:
        zero_hour = new_time[new_time.time == datetime.time(0, 0)]

    n_shift = new_time.get_loc(zero_hour[-1])
    if n_shift == 0:
        return df_shifted

    df_shifted.index = new_time
    return pd.concat([df_shifted.iloc[n_shift:], df_shifted.iloc[:n_shift]])
