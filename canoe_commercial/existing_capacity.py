"""
Aggregates existing stock space heating and cooling data and demand

To fully define this sub-sector, we must fully define existing stock with the equation:

    DEM = SEC x EFF = CAP x C2A x ACF

where:

    DEM = annual output energy, space heating (PJ out)
    SEC = annual secondary energy consumed (PJ in)
    EFF = efficiency of existing stock (PJ out / PJ in)
    CAP = existing capacity (PJ/y)
    C2A = capacity-to-activity ratio, the annual output energy if 100% utilised (PJ / PJ/y.y)
    ACF = annual capacity factor, the actual annual utilisation (PJ/y actual / PJ/y max)

Procedure:

    1. Annual secondary energy consumption (SEC) by end-use / fuel from NRCan comprehensive energy use database
    2. Assume technology shares using analogous region market shares from AEO commercial demand module
    3. Calculate average efficiency (EFF) of natural gas / electricity space heating from (3.)
    4. Use (2. and 4.) to calculate annual end-use service demand (DEM) as DEM = SEC x EFF
    5. Calculate normalised hourly demand profile (DSD) by summing all hourly demands from comstock and normalising
    6. Assume peak demand is full utilisation of existing stock so that ACF = mean(DSD) / max(DSD)
    7. C2A is just 1 if we match capacity and activity units (PJ vs. PJ/y)
    8. Calculate existing capacity as CAP = DEM / (ACF x C2A)

Written by Ian David Elder for the CANOE model
"""

import sqlite3
from typing import TYPE_CHECKING

import pandas as pd

import canoe_commercial.data_scraper as data_scraper
import canoe_commercial.utils as utils
from canoe_commercial.currency_conversion import conv_curr
from canoe_schema.v4_0.models import (
    CapacityToActivity,
    Commodity,
    CostFixed,
    Demand,
    DemandSpecificDistribution,
    Efficiency,
    ExistingCapacity,
    LifetimeTech,
    LimitAnnualCapacityFactor,
    LimitTechInputSplitAnnual,
    Technology,
)

if TYPE_CHECKING:
    from canoe_commercial.setup import CANOECommercialConfig


def aggregate_region(
    region: str,
    df_dsd: pd.DataFrame,
    aeo_data: pd.DataFrame,
    gdp_index: pd.DataFrame,
    cfg: "CANOECommercialConfig",
    db_conn: sqlite3.Connection,
) -> pd.DataFrame:

    df_exs = aggregate_existing_sphc(region, df_dsd, aeo_data, gdp_index, cfg, db_conn)
    aggregate_other(region, df_exs, df_dsd, gdp_index, cfg, db_conn)

    return df_exs


def aggregate_existing_sphc(
    region: str,
    df_dsd: pd.DataFrame,
    aeo_data: pd.DataFrame,
    gdp_index: pd.DataFrame,
    cfg: "CANOECommercialConfig",
    db_conn: sqlite3.Connection,
) -> pd.DataFrame:

    base_year = cfg.base_year
    aeo_year = cfg.aeo_installed_year
    comstock_year = cfg.comstock.data_year

    """
    ##############################################################
        Calculate data for existing technologies
    ##############################################################
    """

    ## 1. Get secondary energy consumption by end use and fuel from NRCan Comprehensive Energy Use Database
    # Table 24: Space Heating Secondary Energy Use and GHG Emissions by Energy Source
    sec_sph = data_scraper.fetch_nrcan_ceud_table(
        region_nrcan_id=cfg.regions.loc[region, 'nrcan_id'],
        table_number=24,
        nrcan_url_template=cfg.nrcan_url,
        base_year=base_year,
        cache_dir=cfg.cache_dir,
        first_row=3,
        last_row=8,
        force_download=cfg.force_download,
    )[base_year].astype(float)

    # Aggregate heavy/light oil and propane/natural gas as we dont have that technological resolution
    sec_sph['oil'] = sec_sph['light fuel oil and kerosene'] + sec_sph['heavy fuel oil']
    sec_sph['natural gas'] = sec_sph['natural gas'] + sec_sph['other']
    sec_sph.drop(['other', 'steam', 'light fuel oil and kerosene', 'heavy fuel oil'], inplace=True)

    # Slice up using Statcan data if its an atlantic province
    sec_sph = get_atlantic_fractions(region, sec_sph, cfg)

    df_sph = pd.DataFrame(data=sec_sph.values, columns=['sec'])
    df_sph['end_use'] = 'space heating'
    df_sph['fuel'] = sec_sph.index

    # Table 32: Space Cooling Secondary Energy Use and GHG Emissions by Energy Source
    sec_spc = data_scraper.fetch_nrcan_ceud_table(
        region_nrcan_id=cfg.regions.loc[region, 'nrcan_id'],
        table_number=32,
        nrcan_url_template=cfg.nrcan_url,
        base_year=base_year,
        cache_dir=cfg.cache_dir,
        first_row=3,
        last_row=5,
        force_download=cfg.force_download,
    )[base_year].astype(float)

    # Slice up using Statcan data if its an atlantic province
    sec_spc = get_atlantic_fractions(region, sec_spc, cfg)
    sec_spc = sec_spc.loc[sec_spc / sec_spc.sum() > cfg.sec_tolerance]

    df_spc = pd.DataFrame(data=sec_spc.values, columns=['sec'])
    df_spc['end_use'] = 'space cooling'
    df_spc['fuel'] = sec_spc.index

    # Getting things into a single dataframe for tidier handling
    df_exs = pd.concat([df_sph, df_spc])
    df_exs.set_index(['end_use', 'fuel'], inplace=True)


    ## 2. Estimate existing stock efficiencies by end use and fuel from installed market shares in AEO CDM
    cdm_exs = aeo_data.copy()

    # Get installed base for space heating and cooling for this region
    cdm_exs = cdm_exs.loc[((cdm_exs['serv'] == 'space heating') | (cdm_exs['serv'] == 'space cooling'))]
    cdm_exs = cdm_exs.loc[cdm_exs['reg'] == cfg.regions.loc[region, 'us_census_div']]
    cdm_exs = cdm_exs.loc[~cdm_exs['techname'].str.contains('chiller')]
    cdm_exs.rename({'share': 'serv_share'}, inplace=True, axis='columns')
    cdm_exs = cdm_exs.loc[cdm_exs['serv_share'] > 0]

    # Convert service energy share to secondary energy consumption share by dividing by efficiencies
    cdm_exs['sec_share'] = cdm_exs['serv_share']
    for end_use in cdm_exs['serv'].unique():
        for fuel in cdm_exs['fuel'].unique():

            df = cdm_exs.loc[(cdm_exs['serv'] == end_use) & (cdm_exs['fuel'] == fuel)].copy()
            df['sec_share'] = df['serv_share'] / df['efficiency']
            df['sec_share'] = df['sec_share'] / df['sec_share'].sum()
            df['serv_share'] = df['serv_share'] / df['serv_share'].sum()
            cdm_exs.loc[(cdm_exs['serv'] == end_use) & (cdm_exs['fuel'] == fuel), 'sec_share'] = df['sec_share']
            cdm_exs.loc[(cdm_exs['serv'] == end_use) & (cdm_exs['fuel'] == fuel), 'serv_share'] = df['serv_share']


    ## 3. Get average efficiency (and life) for each end use and fuel
    cdm_exs['avg_eff'] = cdm_exs['efficiency'] * cdm_exs['sec_share']
    cdm_exs['avg_life'] = (cdm_exs['life'] * cdm_exs['serv_share']).round()
    cdm_exs['avg_fixed_cost'] = cdm_exs['maintcst'] * cdm_exs['serv_share']

    cdm_exs = cdm_exs.groupby(['serv', 'fuel']).sum()
    df_exs = df_exs.drop([euf for euf in df_exs.index if euf not in cdm_exs.index])
    for col in ['avg_eff', 'avg_life', 'avg_fixed_cost']:
        df_exs[col] = df_exs.index.map(lambda euf: cdm_exs.loc[euf, col])


    ## 4. Multiply secondary energies by average efficiencies to get demanded output energies
    df_exs['dem'] = df_exs.index.map(lambda euf: df_exs.loc[euf, 'sec'] * cdm_exs.loc[euf, 'avg_eff'])
    df_dem = df_exs['dem'].groupby('end_use').sum()


    ## 5. DSD calculated outside this function


    ## 6. ACF = mean(DSD) / max(DSD)
    df_acf = pd.DataFrame(
        index=df_dsd.columns,
        columns=['acf'],
        data=[df_dsd[col].mean() / df_dsd[col].max() for col in df_dsd.columns],
    )
    df_exs['acf'] = df_exs.index.map(lambda euf: df_acf.loc[f"{euf[0]} {euf[1]}", 'acf'])


    ## 7. C2A = 1 (capacity in PJ/y, activity in PJ)
    df_exs['c2a'] = 1


    ## 8. CAP = DEM / ACF
    df_exs['cap'] = df_exs['dem'] / df_exs['acf']

    # Drop tiny energy consumptions
    df_exs['cap'] = df_exs['cap'].where(df_exs['dem'] / df_exs['dem'].sum() > cfg.sec_tolerance, 0)

    ## Save calculated existing data to local cache for review
    df_exs.to_csv(cfg.cache_dir + f"calculated_existing_sphc_data_{region.lower()}.csv")
    print(f"Saved calculated {region} existing space heating and cooling data locally.")


    """
    ##############################################################
        Prepare some common data
    ##############################################################
    """

    exs_techs = cfg.existing_techs


    """
    ##############################################################
        Demands
    ##############################################################
    """

    for end_use, dem in df_dem.items():

        if dem == 0:
            continue

        eu_config = cfg.end_use_demands.loc[end_use]
        dsd = df_dsd[end_use].to_numpy()

        ann_dem = dem * gdp_index

        ## Commodities
        sql, rows = Commodity.bulk_insert_or_ignore_sql(
            [
                Commodity(
                    name=eu_config['comm'],
                    flag='d',
                    description=f"({eu_config['dem_unit']}) {eu_config['description']}",
                    data_id=cfg.data_id(),
                )
            ]
        )
        db_conn.executemany(sql, rows)


        ## DemandSpecificDistribution
        if cfg.include_dsd:
            data = []
            ref = cfg.sources['comstock']
            dq_lf = cfg.dq_lifetime.as_kwargs()

            print(f"Adding DSD for {end_use} demand in {region}...")

            for period in cfg.model_periods:
                for h, row in cfg.time.iterrows():

                    if h % 24 == 0:
                        data.append([
                            region, period, row['season'], row['tod'], eu_config['comm'], dsd[h],
                            "Comstock hourly consumption for lighting and equipment summed over all building types and normalised",
                            ref.source_id,
                            dq_lf['dq_cred'], dq_lf['dq_geog'], dq_lf['dq_struc'], dq_lf['dq_tech'], dq_lf['dq_time'],
                            cfg.data_id(region),
                        ])
                    else:
                        data.append([
                            region, period, row['season'], row['tod'], eu_config['comm'], dsd[h],
                            None, None, None, None, None, None, None,
                            cfg.data_id(region),
                        ])

            dsd_rows = [
                DemandSpecificDistribution(
                    region=row[0], period=row[1], season=row[2], tod=row[3],
                    demand_name=row[4], dsd=row[5], notes=row[6], data_source=row[7],
                    dq_cred=row[8], dq_geog=row[9], dq_struc=row[10], dq_tech=row[11], dq_time=row[12],
                    data_id=row[13],
                )
                for row in data
            ]
            sql, rows = DemandSpecificDistribution.bulk_insert_or_ignore_sql(dsd_rows, include_nulls=True)
            db_conn.executemany(sql, rows)


        ## Demand
        ref = cfg.sources['demand']

        for period in cfg.model_periods:
            yr = utils.data_year(period)
            dem_val = ann_dem.loc[yr].iloc[0]
            note = (f"Efficiency (AEO, {aeo_year}) times secondary energy consumption (NRCan, {base_year}) "
                    f"indexed to projected provincial gdp growth by {yr} (CER, {cfg.gdp_data_year})")

            sql, rows = Demand.bulk_insert_or_ignore_sql(
                [
                    Demand(
                        region=region, period=period, commodity=eu_config['comm'],
                        demand=dem_val, units=f"({eu_config['dem_unit']})",
                        notes=note, data_source=ref.source_id,
                        **cfg.dq_demands.as_kwargs(),
                        data_id=cfg.data_id(region),
                    )
                ]
            )
            db_conn.executemany(sql, rows)


    """
    ##############################################################
        Existing technologies
    ##############################################################
    """

    for tech, tech_config in exs_techs.iterrows():

        if tech_config['end_use'] != 'space heating' and tech_config['end_use'] != 'space cooling':
            continue
        if (tech_config['end_use'], tech_config['fuel']) not in df_exs.index:
            continue

        fuel_config = cfg.fuel_commodities.loc[tech_config['fuel']]
        eu_config = cfg.end_use_demands.loc[tech_config['end_use']]
        exs_data = df_exs.loc[(tech_config['end_use'], tech_config['fuel'])]

        if exs_data['cap'] == 0:
            continue


        ## Technologies
        sql, rows = Technology.bulk_insert_or_ignore_sql(
            [
                Technology(
                    tech=tech, flag='p', sector='commercial', annual=1,
                    description=f"{tech_config['end_use']} {tech_config['description']}",
                    data_id=cfg.data_id(),
                )
            ]
        )
        db_conn.executemany(sql, rows)


        ## LifetimeTech
        life = round(cdm_exs.loc[(tech_config['end_use'], tech_config['fuel']), 'avg_life'])
        note = f"Average life of installed stock indexed to shares of service demand by end use and fuel (AEO, {aeo_year})"
        ref = cfg.sources['aeo']
        sql, rows = LifetimeTech.bulk_insert_or_ignore_sql(
            [
                LifetimeTech(
                    region=region, tech=tech, lifetime=life,
                    notes=note, data_source=ref.source_id,
                    **cfg.dq_lifetime.as_kwargs(),
                    data_id=cfg.data_id(region),
                )
            ]
        )
        db_conn.executemany(sql, rows)


        ## CapacityToActivity
        sql, rows = CapacityToActivity.bulk_insert_or_ignore_sql(
            [
                CapacityToActivity(
                    region=region, tech=tech, c2a=1,
                    notes="Capacity is in PJ/y and activity is in PJ so 1",
                    data_id=cfg.data_id(region),
                )
            ]
        )
        db_conn.executemany(sql, rows)


        # Spread existing capacity evenly over existing vintages
        vints, weights = utils.stock_vintages(life)

        for v in range(len(vints)):

            vint = vints[v]
            weight = weights[v]

            if vint + life <= cfg.model_periods[0]:
                continue

            ## Efficiency
            eff = exs_data['avg_eff']
            note = (
                "Average efficiency of installed stock estimated using shares of secondary energy consumption. "
                f"Secondary energy consumption shares calculated from fuel share by end use (NRCan, {base_year}) "
                f"further indexed to service demand shares divided by efficiencies for installed base technologies "
                f"of the same end use and fuel (AEO, {aeo_year})."
            )
            ref = cfg.sources['nrcan_aeo']
            sql, rows = Efficiency.bulk_insert_or_ignore_sql(
                [
                    Efficiency(
                        region=region, input_comm=fuel_config['comm'], tech=tech,
                        vintage=vint, output_comm=eu_config['comm'], efficiency=eff,
                        notes=note, data_source=ref.source_id,
                        **cfg.dq_efficiency.as_kwargs(),
                        data_id=cfg.data_id(region),
                    )
                ]
            )
            db_conn.executemany(sql, rows)


            ## ExistingCapacity
            cap = weight * exs_data['cap']
            note = (
                f"Secondary energy consumption shares calculated from fuel share by end use (NRCan, {base_year}) "
                f"times average efficiency for installed base technologies (AEO, {aeo_year}) "
                f"divided by estimated annual capacity factor (NREL, {comstock_year})"
            )
            ref = cfg.sources['nrcan_aeo_comstock']
            sql, rows = ExistingCapacity.bulk_insert_or_ignore_sql(
                [
                    ExistingCapacity(
                        region=region, tech=tech, vintage=vint,
                        capacity=cap, units=f"({eu_config['cap_unit']})",
                        notes=note, data_source=ref.source_id,
                        **cfg.dq_existing_capacity.as_kwargs(),
                        data_id=cfg.data_id(region),
                    )
                ]
            )
            db_conn.executemany(sql, rows)


            # Indexed by period and vintage
            for period in cfg.model_periods:

                if vint > period or vint + life <= period:
                    continue

                ## CostFixed
                cost_fixed = exs_data['avg_fixed_cost'] * cfg.conversion_factors.cost.aeo
                cost_fixed = conv_curr(cost_fixed)
                note = f"Average maintenance cost of installed stock indexed to shares of service demand by end use and fuel (AEO, {aeo_year})"
                ref = cfg.sources['aeo']
                sql, rows = CostFixed.bulk_insert_or_ignore_sql(
                    [
                        CostFixed(
                            region=region, period=period, tech=tech, vintage=vint,
                            cost=cost_fixed, units='M$/PJ',
                            notes=note, data_source=ref.source_id,
                            **cfg.dq_costs.as_kwargs(),
                            data_id=cfg.data_id(region),
                        )
                    ]
                )
                db_conn.executemany(sql, rows)


        ## AnnualCapacityFactor
        acf = exs_data['acf']
        note = f"Mean hourly demand divided by peak hourly demand from Comstock (NREL, {comstock_year})"
        ref = cfg.sources['comstock']

        for vint in vints:

            if vint + life <= cfg.model_periods[0]: continue # this vintage never lives

            sql, rows = LimitAnnualCapacityFactor.bulk_insert_or_ignore_sql(
                [
                    LimitAnnualCapacityFactor(
                        region=region, vintage=vint, tech_or_group=tech,
                        output_comm=eu_config['comm'], operator='le', factor=acf,
                        notes=note, data_source=ref.source_id,
                        **cfg.dq_capacity_factor.as_kwargs(),
                        data_id=cfg.data_id(region),
                    )
                ], include_nulls=True
            )
            db_conn.executemany(sql, rows)


    db_conn.commit()

    return df_exs


def aggregate_other(
    region: str,
    df_exs: pd.DataFrame,
    df_dsd: pd.DataFrame,
    gdp_index: pd.DataFrame,
    cfg: "CANOECommercialConfig",
    db_conn: sqlite3.Connection,
) -> None:

    base_year = cfg.base_year
    aeo_year = cfg.aeo_installed_year
    comstock_year = cfg.comstock.data_year

    eu_config: pd.Series = cfg.end_use_demands.loc['other']
    tech_config: pd.Series = cfg.new_techs.loc[cfg.new_techs['end_use'] == 'other'].iloc[0]
    dsd = df_dsd['other'].to_numpy()
    elc_fact = cfg.other_electrification_factor

    if not tech_config['include_new']:
        return

    tech = tech_config.name
    vint = cfg.model_periods[0]

    """
    ##############################################################
        All demands other than space heating and cooling
    ##############################################################
    """

    sec_sphc = df_exs.groupby(['fuel']).sum()['sec']

    # Table 1: Secondary Energy Use and GHG Emissions by Energy Source
    sec: pd.Series = data_scraper.fetch_nrcan_ceud_table(
        region_nrcan_id=cfg.regions.loc[region, 'nrcan_id'],
        table_number=1,
        nrcan_url_template=cfg.nrcan_url,
        base_year=base_year,
        cache_dir=cfg.cache_dir,
        first_row=3,
        last_row=8,
        force_download=cfg.force_download,
    )[base_year].astype(float)

    sec['oil'] = sec['light fuel oil and kerosene'] + sec['heavy fuel oil']
    sec['natural gas'] = sec['natural gas'] + sec['other']
    sec.drop(['other', 'steam', 'light fuel oil and kerosene', 'heavy fuel oil'], inplace=True)

    sec = get_atlantic_fractions(region, sec, cfg)

    for fuel in sec.index.difference(sec_sphc.index):
        sec_sphc[fuel] = 0

    sec_oth = sec - sec_sphc
    sec_oth = sec_oth.loc[sec_oth / sec_oth.sum() > cfg.sec_tolerance]
    ann_dem = sec_oth.sum() * gdp_index

    ti_splits = sec_oth / sec_oth.sum()


    """
    ##############################################################
        Add to database
    ##############################################################
    """

    ## Technologies
    sql, rows = Technology.bulk_insert_or_ignore_sql(
        [
            Technology(
                tech=tech, flag='p', sector='commercial', annual=1, unlim_cap=1,
                description=f"{tech_config['end_use']} {tech_config['description']}",
                data_id=cfg.data_id(),
            )
        ]
    )
    db_conn.executemany(sql, rows)

    ## Commodities
    sql, rows = Commodity.bulk_insert_or_ignore_sql(
        [
            Commodity(
                name=eu_config['comm'],
                flag='d',
                description=f"({eu_config['dem_unit']}) {eu_config['description']}",
                data_id=cfg.data_id(),
            )
        ]
    )
    db_conn.executemany(sql, rows)


    # Flows
    for fuel in sec_oth.index:

        fuel_config = cfg.fuel_commodities.loc[fuel]

        ## Efficiency
        sql, rows = Efficiency.bulk_insert_or_ignore_sql(
            [
                Efficiency(
                    region=region, input_comm=fuel_config['comm'], tech=tech,
                    vintage=vint, output_comm=eu_config['comm'], efficiency=1,
                    notes="Dummy tech. Demand equal to secondary energy consumption",
                    data_id=cfg.data_id(region),
                )
            ]
        )
        db_conn.executemany(sql, rows)


        ## TechInputSplit
        ref = cfg.sources['nrcan_cef']
        for period in cfg.model_periods:
            yr = utils.data_year(period) # year is end of period not beginning
            tis = ti_splits[fuel]

            # Linear interpolation towards reducing non-elc fuels by electrification factor
            lin_f = (yr - base_year)/(utils.data_year(cfg.model_periods[-1]) - base_year)
            if fuel == 'electricity': target = elc_fact + tis * ( 1 - elc_fact ) # elc increases
            else: target = tis * (1 - elc_fact) # all others decrease by elc_fact

            tis = tis + (target - tis) * lin_f

            note = f"Secondary energy consumption by fuel (NRCan, {base_year}) minus space heating and cooling. {cfg.cef_note}"
            sql, rows = LimitTechInputSplitAnnual.bulk_insert_or_ignore_sql(
                [
                    LimitTechInputSplitAnnual(
                        region=region, period=period, input_comm=fuel_config['comm'],
                        tech=tech, operator='le', proportion=tis,
                        notes=note, data_source=ref.source_id,
                        **cfg.dq_fuel_splits.as_kwargs(),
                        data_id=cfg.data_id(region),
                    )
                ]
            )
            db_conn.executemany(sql, rows)


    ## DemandSpecificDistribution
    if cfg.include_dsd:
        data = []
        ref = cfg.sources['comstock']
        dq_lf = cfg.dq_lifetime.as_kwargs()

        print(f"Adding DSD for other demand in {region}...")

        for period in cfg.model_periods:
            for h, row in cfg.time.iterrows():

                if h % 24 == 0:
                    data.append([
                        region, period, row['season'], row['tod'], eu_config['comm'], dsd[h],
                        "Comstock hourly consumption for lighting and equipment summed over all building types and normalised",
                        ref.source_id,
                        dq_lf['dq_cred'], dq_lf['dq_geog'], dq_lf['dq_struc'], dq_lf['dq_tech'], dq_lf['dq_time'],
                        cfg.data_id(region),
                    ])
                else:
                    data.append([
                        region, period, row['season'], row['tod'], eu_config['comm'], dsd[h],
                        None, None, None, None, None, None, None,
                        cfg.data_id(region),
                    ])

        dsd_rows = [
            DemandSpecificDistribution(
                region=row[0], period=row[1], season=row[2], tod=row[3],
                demand_name=row[4], dsd=row[5], notes=row[6], data_source=row[7],
                dq_cred=row[8], dq_geog=row[9], dq_struc=row[10], dq_tech=row[11], dq_time=row[12],
                data_id=row[13],
            )
            for row in data
        ]
        sql, rows = DemandSpecificDistribution.bulk_insert_or_ignore_sql(dsd_rows, include_nulls=True)
        db_conn.executemany(sql, rows)


    ## Demand
    ref = cfg.sources['nrcan_gdp']
    for period in cfg.model_periods:
        
        yr = utils.data_year(period)
        dem_val = ann_dem.loc[yr].iloc[0]
        note = (
            "Annual secondary energy consumption summed over all "
            f"fuels minus space heating and cooling (NRCan, {base_year}) "
            f"indexed to projected provincial gdp growth by {yr} (CER, {cfg.gdp_data_year})"
        )

        sql, rows = Demand.bulk_replace_into_sql(
            [
                Demand(
                    region=region, period=period, commodity=eu_config['comm'],
                    demand=dem_val, units=f"({eu_config['dem_unit']})",
                    notes=note, data_source=ref.source_id,
                    **cfg.dq_demands.as_kwargs(),
                    data_id=cfg.data_id(region),
                )
            ]
        )
        db_conn.executemany(sql, rows)

    db_conn.commit()


def get_atlantic_fractions(region: str, sec: pd.Series, cfg: "CANOECommercialConfig") -> pd.Series:
    """
    For the comprehensive energy use database in commercial, the atlantic provinces are all aggregated.
    To slice them up, we use energy proportions from Statcan data. The system scope of the Statcan
    data is different from NRCan, including upstream energy use, so we dont want to use it directly.
    """

    if not cfg.regions.loc[region]['atlantic']:
        return sec

    df = data_scraper.fetch_statcan_table(
        table_id=25100029,
        cache_dir=cfg.cache_dir,
        save_as='statcan_atlantic_energy',
        force_download=cfg.force_download,
        filter=lambda df: df.loc[
            (df['REF_DATE'] == cfg.base_year)
            & (df['Fuel type'].isin(cfg.fuel_commodities['statcan_fuel']))
            & (df['Supply and demand characteristics'] == 'Commercial and other institutional')
            & (df['GEO'].str.lower().isin(cfg.regions['description'].loc[cfg.regions['atlantic']]))
        ],
        usecols=['REF_DATE', 'GEO', 'Fuel type', 'Supply and demand characteristics', 'VALUE'],
    ).fillna(0)

    df['region'] = df['GEO'].str.lower().map({
        cfg.regions.loc[idx, 'description']: idx for idx in cfg.regions.index
    })
    df['fuel'] = df['Fuel type'].map({
        cfg.fuel_commodities.loc[idx, 'statcan_fuel']: idx for idx in cfg.fuel_commodities.index
    })

    df_fuel = df.groupby('fuel')['VALUE'].sum()

    for idx, row in df.iterrows():
        df.loc[idx, 'fraction'] = row['VALUE'] / df_fuel.loc[row['fuel']]

    df = df.loc[df['region'] == region]
    df = df.set_index('fuel')['fraction']

    sec = sec.copy()
    for fuel in sec.index:
        if fuel in df.index:
            sec[fuel] *= df.loc[fuel]
        else:
            sec = sec.drop(fuel)

    return sec
