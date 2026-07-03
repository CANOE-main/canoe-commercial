"""
Aggregates residential non-subsector-specific data
Written by Ian David Elder for the CANOE model
"""

import os
import sqlite3
import pandas as pd
from canoe_schema.v4_0.models import (
    Commodity,
    DataSet,
    DataSource,
    Efficiency,
    EmissionActivity,
    Technology,
)

from canoe_commercial.setup import config
import canoe_commercial.comstock_dsd as comstock_dsd
import canoe_commercial.existing_capacity as existing_capacity
import canoe_commercial.new_capacity as new_capacity
import canoe_commercial.utils as utils
import canoe_commercial.data_scraper as data_scraper
import canoe_commercial.validation as validation

fuel_commodities = config.fuel_commodities



def aggregate():

    pre_process()

    # Aggregate space heating and cooling
    for region in config.model_regions:

        print(f"Aggregating {region}...\n")

        df_dsd = comstock_dsd.calculate_dsds(region)
        df_exs = existing_capacity.aggregate_region(region, df_dsd)
        new_capacity.aggregate_region(region, df_exs) # existing data for annual capacity factors

        print(f"Aggregated {region}.\n")

    if config.include_emissions: aggregate_emissions()
    # if config.params['include_imports']: aggregate_imports() # No longer supported

    post_process()



# For non-regional aggregation
def pre_process():

    conn = sqlite3.connect(config.database_file)

    """
    ##############################################################
        Fuel commodities (module-specific, C table)
        Global tables (time_period, region, time_season, time_of_day,
        time_season_sequential) are seeded by canoe-base and validated
        in commercial_sector.build_database() before this runs.
    ##############################################################
    """

    for _code, comm_config in config.fuel_commodities.iterrows():
        sql, rows = Commodity.bulk_insert_or_ignore_sql(
            [
                Commodity(
                    name=comm_config['comm'],
                    flag=comm_config['flag'],
                    description=f"({comm_config['unit']}) {comm_config['description']}",
                    data_id=utils.data_id(),
                )
            ]
        )
        conn.executemany(sql, rows)

    conn.commit()
    conn.close()

    print(f"Pre-aggregation complete.\n")



# For non-regional post-subsector aggregation
def post_process():

    # Connect to the new database file
    conn = sqlite3.connect(config.database_file)
    curs = conn.cursor() # Cursor object interacts with the sqlite db


    """
    ##############################################################
        Existing vintage periods (validate, not write)
        canoe-base seeds flag='e' periods covering all historical
        vintages. See DECISIONS.md — decision 3.
    ##############################################################
    """

    exs_vints = {
        row[0]
        for row in curs.execute(f"SELECT vintage FROM {Efficiency.__table_name__}").fetchall()
        if row[0] not in config.model_periods
    }
    validation.validate_existing_vintage_periods(
        conn, exs_vints,
        behavior=config.validation_behavior,
    )


    """
    ##############################################################
        References
    ##############################################################
    """

    for src in config.sources.values():
        sql, rows = DataSource.bulk_insert_or_ignore_sql([src])
        conn.executemany(sql, rows)


    """
    ##############################################################
        Data IDs
    ##############################################################
    """

    for id in sorted(config.data_ids):
        sql, rows = DataSet.bulk_insert_or_ignore_sql([DataSet(data_id=id)])
        conn.executemany(sql, rows)

    # Check for missing data IDs
    tables = [t[0] for t in curs.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]

    for table in tables:
        cols = [c[1] for c in curs.execute(f"PRAGMA table_info({table})").fetchall()]
        if "data_id" in cols:
            bad_rows = pd.read_sql_query(f"SELECT * FROM {table} WHERE data_id is NULL", conn)
            if len(bad_rows) > 0:
                print(f"Found some rows missing data IDs in {table}")
                print(bad_rows)


    conn.commit()
    conn.close()


    print(f"Post-aggregation complete.\n")



def aggregate_emissions():

    # Connect to the new database file
    conn = sqlite3.connect(config.database_file)
    curs = conn.cursor() # Cursor object interacts with the sqlite db


    """
    ##############################################################
        Emission Activity
    ##############################################################
    """

    emis_comm = config.emission_commodity
    emis_units = config.emission_activity_units

    # Get emissions factors for fuels in ktCO2eq/PJ_in
    emis_fact = data_scraper.fetch_emission_factors(
        url=config.epa_url,
        cache_dir=config.cache_dir,
        force_download=config.force_download,
    )
    emis_fact = emis_fact[['CO2 Factor', 'CH4 Factor', 'N2O Factor']].iloc[1:].dropna()
    emis_fact = emis_fact[pd.to_numeric(emis_fact['CO2 Factor'], errors='coerce').notnull()] # Removing NaN rows
    for fact in emis_fact.columns:
        gas = fact.strip(' Factor')
        emis_fact[fact] = (
            emis_fact[fact].astype(float)
            * getattr(config.conversion_factors.epa_units, gas)
            * getattr(config.conversion_factors.gwp, gas)
        )
    emis_fact[emis_comm] = emis_fact.sum(axis=1)

    ref = config.sources['epa']

    for tech in config.all_techs:

        # Valid vintages and efficiencies from Efficiency table
        rows = curs.execute(f"SELECT region, input_comm, tech, vintage, output_comm, efficiency FROM {Efficiency.__table_name__} WHERE tech == '{tech}'").fetchall()

        for row in rows:

            # Input fuel by epa naming convention
            epa_fuel = fuel_commodities.loc[fuel_commodities['comm'] == row[1], 'epa_fuel'].iloc[0]
            if pd.isna(epa_fuel): continue # doesn't need emissions

            # EmissionActivity is tied to OUTPUT energy so divide by efficiency
            emis_act = emis_fact.loc[epa_fuel, emis_comm] / row[5]

            # Note assumed fuel
            note = f"Emissions factor using {epa_fuel} (EPA, {config.epa_year}) divided by efficiency as emissions are per output unit energy."

            sql, rows = EmissionActivity.bulk_insert_or_ignore_sql(
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
                        **config.dq_emissions.as_kwargs(),
                        data_id=utils.data_id(row[0]),
                    )
                ]
            )
            conn.executemany(sql, rows)


    conn.commit()
    conn.close()

    print(f"Emissions data aggregated into {os.path.basename(config.database_file)}\n")



def aggregate_imports():

    conn = sqlite3.connect(config.database_file)

    # Get which fuel commodities are actually being used
    df_eff = pd.read_sql_query(f"SELECT * FROM {Efficiency.__table_name__}", conn)

    for tech, row in config.import_techs.iterrows():

        # Get CANOE nomenclature for imported commodity
        out_comm = config.fuel_commodities.loc[row['out_comm']]

        # Make sure the model is using this imported commodity otherwise skip
        if out_comm['comm'] not in df_eff['input_comm'].values:
            print(out_comm['comm'])
            continue

        description = f"import dummy for {out_comm['description']}"

        sql, rows = Technology.bulk_insert_or_ignore_sql(
            [
                Technology(
                    tech=tech,
                    flag='p',
                    sector='commercial',
                    description=description,
                    data_id='COMHR001',
                )
            ]
        )
        conn.executemany(sql, rows)

        # A single vintage at first model period with no other parameters, classic dummy tech
        for region in config.model_regions:

            # Make sure the model is using this imported commodity in this region otherwise skip
            if df_eff[(df_eff['regions'] == region) & (df_eff['input_comm'] == out_comm['comm'])].empty:
                print(f"Import {tech} skipped for region {region} as the fuel isn't used.")
                continue

            sql, rows = Efficiency.bulk_insert_or_ignore_sql(
                [
                    Efficiency(
                        region=region,
                        input_comm=config.fuel_commodities.loc[row['in_comm'], 'comm'],
                        tech=tech,
                        vintage=config.model_periods[0],
                        output_comm=out_comm['comm'],
                        efficiency=1,
                        notes=f"{description})",
                        data_id='COMHR001',
                    )
                ]
            )
            conn.executemany(sql, rows)

    conn.commit()
    conn.close()

    print(f"Imports aggregated into {os.path.basename(config.database_file)}\n")



if __name__ == "__main__":

    aggregate()
