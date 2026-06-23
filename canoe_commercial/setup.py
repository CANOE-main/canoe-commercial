"""
Configuration for commercial sector aggregation.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

import canoe_commercial.data_scraper as data_scraper


class ComstockConfig(BaseModel):
    url: str
    data_year: int
    building_types: list[str]
    reference: str


class DataQualityProfile(BaseModel):
    cred: int
    geog: int
    struc: int
    tech: int
    time: int

    def as_kwargs(self) -> dict[str, int]:
        return {f"dq_{k}": v for k, v in self.model_dump().items()}


class WeatherConfig(BaseModel):
    us_temperature_url: str
    us_humidity_url: str
    ca_temperature_url: str
    ca_humidity_url: str
    reference: str


class EpaUnitFactors(BaseModel):
    CO2: float
    CH4: float
    N2O: float


class GWPFactors(BaseModel):
    CO2: float
    CH4: float
    N2O: float


class EfficiencyFactors(BaseModel):
    EER: float


class CostFactors(BaseModel):
    aeo: float


class ConversionFactors(BaseModel):
    epa_units: EpaUnitFactors
    gwp: GWPFactors
    efficiency: EfficiencyFactors
    cost: CostFactors


class CANOECommercialConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    # Identity
    schema_version: str
    version: str
    sector_abv: str = "COM"
    sector_longname: str = "commercial"
    data_id_prefix: str
    data_version: str

    # File paths
    db_dir: str = "."
    sqlite_database: str
    excel_template: str
    excel_output: str
    input_files: str = "input_files/"
    cache_dir: str = "data_cache/"

    # Model scope
    future_periods: list[int]
    province_list: list[str]
    base_year: int
    period_step: int
    timezone: str

    # Runtime switches
    validation_behavior: Literal["error", "warning"] = "error"
    force_download: bool = False
    show_plots: bool = True
    clone_to_xlsx: bool = False
    include_dsd: bool = True
    include_emissions: bool = False
    force_generate_weather_maps: bool = False

    # Parameters
    sec_tolerance: float
    other_electrification_factor: float
    cef_note: str
    cef_reference: str
    weather_year: int

    # GDP
    gdp_url: str
    gdp_scenario: str = "Global Net-zero"
    gdp_variable: str = "Real Gross Domestic Product ($2012 Millions)"
    gdp_data_year: int
    gdp_reference: str

    # Population
    population_m_scenario: str = "Projection scenario M1: medium-growth"
    pop_reference: str

    # AEO
    aeo_installed_year: int
    aeo_reference: str

    # NRCan
    nrcan_url: str
    nrcan_reference: str

    # EPA emissions
    epa_year: int
    epa_url: str
    epa_reference: str
    emission_commodity: str
    emission_activity_units: str

    # Currency
    final_currency: str
    final_currency_year: int
    inflation_index: str
    aeo_currency_year: int
    aeo_currency: str

    # Nested config
    comstock: ComstockConfig
    weather: WeatherConfig
    conversion_factors: ConversionFactors

    # DQ profiles
    dq_demands: DataQualityProfile
    dq_efficiency: DataQualityProfile
    dq_existing_capacity: DataQualityProfile
    dq_costs: DataQualityProfile
    dq_emissions: DataQualityProfile
    dq_capacity_factor: DataQualityProfile
    dq_fuel_splits: DataQualityProfile
    dq_lifetime: DataQualityProfile

    # Runtime data — populated by _load_data(), not sourced from TOML
    regions: Optional[pd.DataFrame] = None
    new_techs: Optional[pd.DataFrame] = None
    existing_techs: Optional[pd.DataFrame] = None
    import_techs: Optional[pd.DataFrame] = None
    fuel_commodities: Optional[pd.DataFrame] = None
    end_use_demands: Optional[pd.DataFrame] = None
    time: Optional[pd.DataFrame] = None
    aeo_cdm: Optional[pd.DataFrame] = None
    gdp_index: Optional[pd.DataFrame] = None
    populations: Optional[dict] = None
    all_techs: list[str] = Field(default_factory=list)
    rninja_api: str = ""
    sources: dict = Field(default_factory=dict)
    data_ids: set = Field(default_factory=set)

    @property
    def model_periods(self) -> list[int]:
        return sorted(self.future_periods)

    @property
    def model_regions(self) -> list[str]:
        return sorted(self.province_list)

    @property
    def database_file(self) -> str:
        return str(Path(self.db_dir) / self.sqlite_database)

    @property
    def excel_template_file(self) -> str:
        return self.input_files + self.excel_template

    @property
    def excel_target_file(self) -> str:
        return str(Path(self.db_dir) / self.excel_output)

    @classmethod
    def validate_from_toml(cls, toml_dir: str = "input_files") -> "CANOECommercialConfig":
        path = Path(toml_dir) / "params.toml"
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        cfg = cls.model_validate(raw)
        cfg._load_data()
        return cfg

    def _load_data(self) -> None:
        if not os.path.exists(self.cache_dir):
            os.mkdir(self.cache_dir)

        self.regions = pd.read_csv(self.input_files + "regions.csv", index_col=0)
        self.new_techs = pd.read_csv(self.input_files + "new_technologies.csv", index_col=0)
        self.existing_techs = pd.read_csv(self.input_files + "existing_technologies.csv", index_col=0)
        self.import_techs = pd.read_csv(self.input_files + "import_technologies.csv", index_col=0)
        self.fuel_commodities = pd.read_csv(self.input_files + "fuel_commodities.csv", index_col=0)
        self.end_use_demands = pd.read_csv(self.input_files + "end_use_demands.csv", index_col=0)
        self.time = pd.read_csv(self.input_files + "time.csv", index_col=0)

        self.new_techs = self.new_techs.loc[self.new_techs["include_new"]]
        self.all_techs = [*self.new_techs.index.values, *self.existing_techs.index.values]

        self.aeo_cdm = data_scraper.fetch_aeo_data(
            aeo_file=self.input_files + "ktekx.xlsx",
            indexing_file=self.input_files + "aeo_cdm_indexing.csv",
        )

        self.populations = data_scraper.fetch_population_projections(
            regions_df=self.regions,
            cache_dir=self.cache_dir,
            force_download=self.force_download,
        )

        self.gdp_index = data_scraper.fetch_gdp_projections(
            gdp_url=self.gdp_url,
            base_year=self.base_year,
            cache_dir=self.cache_dir,
            force_download=self.force_download,
        )

        try:
            with open("input_files/rninja_api_token.txt") as token_file:
                self.rninja_api = token_file.read()
        except FileNotFoundError:
            self.rninja_api = "WARNING: rninja_api_token.txt not found"

        from canoe_commercial.sources import build_sources
        self.sources = build_sources(self)

        print("Instantiated setup config.\n")


# Instantiate on import
config: CANOECommercialConfig = CANOECommercialConfig.validate_from_toml("input_files")
