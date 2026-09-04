"""
Writes EmissionActivity rows for one province.

emis_factors is a pre-processed DataFrame (from prepare_emission_factors) with a
cfg.emission_commodity column keyed by EPA fuel name (ktCO2eq/PJ_in).
"""

import sqlite3
from typing import TYPE_CHECKING

import pandas as pd

from canoe_schema.v4_0.models import Efficiency, EmissionActivity

if TYPE_CHECKING:
    from canoe_commercial.setup import CANOECommercialConfig


def prepare_emission_factors(raw_df: pd.DataFrame, cfg: "CANOECommercialConfig") -> pd.DataFrame:
    """
    Convert the raw EPA spreadsheet DataFrame into a single CO2eq column (ktCO2eq/PJ_in)
    keyed by EPA fuel name. Call once before the region loop.
    """
    emis = raw_df[['CO2 Factor', 'CH4 Factor', 'N2O Factor']].iloc[1:].dropna()
    emis = emis[pd.to_numeric(emis['CO2 Factor'], errors='coerce').notnull()]

    for col in emis.columns:
        gas = col.strip(' Factor')
        emis[col] = (
            emis[col].astype(float)
            * getattr(cfg.conversion_factors.epa_units, gas)
            * getattr(cfg.conversion_factors.gwp, gas)
        )

    emis[cfg.emission_commodity] = emis.sum(axis=1)
    return emis


def aggregate_region(
    region: str,
    emis_factors: pd.DataFrame,
    cfg: "CANOECommercialConfig",
    db_conn: sqlite3.Connection,
) -> None:
    """
    Write EmissionActivity rows for all technologies in *region* using pre-processed
    emis_factors (output of prepare_emission_factors).
    """
    curs = db_conn.cursor()
    emis_comm = cfg.emission_commodity
    emis_units = cfg.emission_activity_units
    ref = cfg.sources['epa']
    fuel_commodities = cfg.fuel_commodities

    for tech in cfg.all_techs:

        eff_rows = curs.execute(
            f"SELECT region, input_comm, tech, vintage, output_comm, efficiency "
            f"FROM {Efficiency.__table_name__} WHERE tech = ? AND region = ?",
            (tech, region),
        ).fetchall()

        for row in eff_rows:

            epa_fuel_match = fuel_commodities.loc[fuel_commodities['comm'] == row[1], 'epa_fuel']
            if epa_fuel_match.empty:
                continue
            epa_fuel = epa_fuel_match.iloc[0]
            if pd.isna(epa_fuel):
                continue

            emis_act = emis_factors.loc[epa_fuel, emis_comm] / row[5]
            note = (
                f"Emissions factor using {epa_fuel} (EPA, {cfg.epa_year}) "
                "divided by efficiency as emissions are per output unit energy."
            )

            sql, ins_rows = EmissionActivity.bulk_insert_or_ignore_sql(
                [
                    EmissionActivity(
                        region=row[0],
                        emis_comm=emis_comm,
                        input_comm=row[1],
                        tech=row[2],
                        vintage=row[3],
                        output_comm=row[4],
                        activity=emis_act,
                        units=emis_units,
                        notes=note,
                        data_source=ref.source_id,
                        **cfg.dq_emissions.as_kwargs(),
                        data_id=cfg.data_id(row[0]),
                    )
                ]
            )
            db_conn.executemany(sql, ins_rows)

    db_conn.commit()
    print(f"Emission activities written for {region}.\n")
