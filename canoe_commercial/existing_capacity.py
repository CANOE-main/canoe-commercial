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

from canoe_commercial.setup import config
import sqlite3
import canoe_commercial.utils as utils
import pandas as pd
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

base_year = config.base_year
aeo_year = config.aeo_installed_year
comstock_year = config.comstock.data_year


def aggregate_region(region: str, df_dsd: pd.DataFrame) -> pd.DataFrame:

    df_exs = aggregate_existing_sphc(region, df_dsd)
    aggregate_other(region, df_exs, df_dsd)

    return df_exs



def aggregate_existing_sphc(region: str, df_dsd: pd.DataFrame) -> pd.DataFrame:

    """
    ##############################################################
        Calculate data for existing technologies
    ##############################################################
    """

    ## 1. Get secondary energy consumption by end use and fuel from NRCan Comprehensive Energy Use Database
    # Table 24: Space Heating Secondary Energy Use and GHG Emissions by Energy Source
    sec_sph = utils.get_compr_db(region, 24, 3, 8)[base_year].astype(float)


    # Aggregate heavy/light oil and propane/natural gas as we dont have that technological resolution
    sec_sph['oil'] = sec_sph['light fuel oil and kerosene'] + sec_sph['heavy fuel oil']
    sec_sph['natural gas'] = sec_sph['natural gas'] + sec_sph['other']
    #sec_sph['district'] = sec_sph['steam'] # TODO dont have technoeconomic data for district schemes yet so ignore
    sec_sph.drop(['other','steam','light fuel oil and kerosene','heavy fuel oil'], inplace=True)

    # Slice up using Statcan data if its an atlantic province
    sec_sph = get_atlantic_fractions(region, sec_sph)

    df_sph = pd.DataFrame(data=sec_sph.values, columns=['sec'])
    df_sph['end_use'] = 'space heating'
    df_sph['fuel'] = sec_sph.index

    # Table 32: Space Cooling Secondary Energy Use and GHG Emissions by Energy Source
    sec_spc = utils.get_compr_db(region, 32, 3, 5)[base_year].astype(float)

    # Slice up using Statcan data if its an atlantic province
    sec_spc = get_atlantic_fractions(region, sec_spc)
    sec_spc = sec_spc.loc[sec_spc/sec_spc.sum() > config.sec_tolerance] # drop tiny energy consumptions

    df_spc = pd.DataFrame(data=sec_spc.values, columns=['sec'])
    df_spc['end_use'] = 'space cooling'
    df_spc['fuel'] = sec_spc.index

    # Getting things into a single dataframe for tidier handling
    df_exs = pd.concat([df_sph, df_spc])
    df_exs.set_index(['end_use','fuel'], inplace=True)


    ## 2. Estimate existing stock efficiencies by end use and fuel from installed market shares in AEO CDM
    cdm_exs = config.aeo_cdm.copy() # for aggregated technoeconomic data of existing capacity

    # Get installed base for space heating and cooling for this region
    cdm_exs = cdm_exs.loc[((cdm_exs['serv'] == 'space heating') | (cdm_exs['serv'] == 'space cooling'))] # space heating or cooling
    cdm_exs = cdm_exs.loc[cdm_exs['reg'] == config.regions.loc[region, 'us_census_div']] # in region
    cdm_exs = cdm_exs.loc[~cdm_exs['techname'].str.contains('chiller')] # exclude chillers because we are only interested in heat pump-relevant space cooling
    cdm_exs.rename({'share': 'serv_share'}, inplace=True, axis='columns')
    cdm_exs = cdm_exs.loc[cdm_exs['serv_share'] > 0] # service energy share > 0 is installed base

    # Convert service energy share to secondary energy consumption share by dividing by efficiencies
    # Renormalise service and secondary energy shares for each end use and fuel, to get representative values for existing stock
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
    cdm_exs['avg_eff'] = cdm_exs['efficiency'] * cdm_exs['sec_share'] # eff indexed to secondary energy share
    cdm_exs['avg_life'] = (cdm_exs['life'] * cdm_exs['serv_share']).round() # life indexed to output service energy share
    cdm_exs['avg_fixed_cost'] = cdm_exs['maintcst'] * cdm_exs['serv_share'] # fixed cost indexed to output service energy share

    cdm_exs = cdm_exs.groupby(['serv','fuel']).sum()
    df_exs = df_exs.drop([euf for euf in df_exs.index if euf not in cdm_exs.index]) # no service share so drop this end-use-fuel combo
    for col in ['avg_eff','avg_life','avg_fixed_cost']:
        df_exs[col] = df_exs.index.map(lambda euf: cdm_exs.loc[euf, col])


    ## 4. Multiply secondary energies from NRCan by average efficiencies for each end use and fuel to get demanded output energies
    df_exs['dem'] = df_exs.index.map(lambda euf: df_exs.loc[euf, 'sec'] * cdm_exs.loc[euf, 'avg_eff'])
    df_dem = df_exs['dem'].groupby('end_use').sum()


    ## 5. Calculate normalised hourly demand profile (DSD) by summing all hourly demands from comstock and normalising
    # Already done outside function


    ## 6. Assume peak demand is full utilisation of existing stock so that ACF = mean(DSD) / max(DSD)
    df_acf = pd.DataFrame(index=df_dsd.columns, columns=['acf'], data=[df_dsd[col].mean() / df_dsd[col].max() for col in df_dsd.columns])
    df_exs['acf'] = df_exs.index.map(lambda euf: df_acf.loc[f"{euf[0]} {euf[1]}", 'acf'])


    ## 7. C2A is just 1 if we match capacity and activity units (PJ vs. PJ/y)
    df_exs['c2a'] = 1


    ## 8. Calculate existing capacity as CAP = DEM / (ACF x C2A) = DEM / ACF
    df_exs['cap'] = df_exs['dem'] / df_exs['acf']


    # If energy is less than threshold, set existing capacity to zero
    df_exs['cap'] = df_exs['cap'].where(df_exs['dem']/df_exs['dem'].sum() > config.sec_tolerance, 0) # drop tiny energy consumptions


    ## Save calculated existing data to local cache for review
    df_exs.to_csv(config.cache_dir + f"calculated_existing_sphc_data_{region.lower()}.csv")
    print(f"Saved calculated {region} existing space heating and cooling data locally.")



    """
    ##############################################################
        Prepare some common data
    ##############################################################
    """

    conn = sqlite3.connect(config.database_file)
    curs = conn.cursor()

    exs_techs = config.existing_techs


    """
    ##############################################################
        Demands
    ##############################################################
    """

    for end_use, dem in df_dem.items():

        if dem == 0: continue

        eu_config = config.end_use_demands.loc[end_use]
        dsd = df_dsd[end_use].to_numpy()

        ann_dem = dem * config.gdp_index # annual demand indexed to gdp growth

        ## Commodities
        sql, rows = Commodity.bulk_insert_or_ignore_sql(
            [
                Commodity(
                    name=eu_config['comm'],
                    flag='d',
                    description=f"({eu_config['dem_unit']}) {eu_config['description']}",
                    data_id=utils.data_id(),
                )
            ]
        )
        conn.executemany(sql, rows)


        ## DemandSpecificDistribution
        if config.include_dsd:
            data = []
            ref = config.sources['comstock']
            dq_lf = config.dq_lifetime.as_kwargs()

            print(f"Adding DSD for {end_use} demand in {region}...")

            for period in config.model_periods:
                for h, row in config.time.iterrows():

                    # Data descriptors take up a good bit of storage for timeseries data so only attach to first hour of each day
                    if h % 24 == 0:
                        data.append([
                            region, period, row['season'], row['tod'], eu_config['comm'], dsd[h],
                            "Comstock hourly consumption for lighting and equipment summed over all building types and normalised",
                            ref.source_id,
                            dq_lf['dq_cred'], dq_lf['dq_geog'], dq_lf['dq_struc'], dq_lf['dq_tech'], dq_lf['dq_time'],
                            utils.data_id(region),
                        ])
                    else:
                        data.append([
                            region, period, row['season'], row['tod'], eu_config['comm'], dsd[h],
                            None, None, None, None, None, None, None,
                            utils.data_id(region),
                        ])


            dsd_rows = [
                DemandSpecificDistribution(
                    region=row[0],
                    period=row[1],
                    season=row[2],
                    tod=row[3],
                    demand_name=row[4],
                    dsd=row[5],
                    notes=row[6],
                    data_source=row[7],
                    dq_cred=row[8],
                    dq_geog=row[9],
                    dq_struc=row[10],
                    dq_tech=row[11],
                    dq_time=row[12],
                    data_id=row[13],
                )
                for row in data
            ]
            sql, rows = DemandSpecificDistribution.bulk_insert_or_ignore_sql(dsd_rows, include_nulls=True)
            conn.executemany(sql, rows)


        ## Demand
        ref = config.sources['demand']

        for period in config.model_periods:

            dem = ann_dem.loc[period].iloc[0]
            note = (f"Efficiency (AEO, {aeo_year}) times secondary energy consumption (NRCan, {base_year}) "
                    f"indexed to projected provincial gdp growth (CER, {config.gdp_data_year})")

            sql, rows = Demand.bulk_insert_or_ignore_sql(
                [
                    Demand(
                        region=region,
                        period=period,
                        commodity=eu_config['comm'],
                        demand=dem,
                        units=f"({eu_config['dem_unit']})",
                        notes=note,
                        data_source=ref.source_id,
                        **config.dq_demands.as_kwargs(),
                        data_id=utils.data_id(region),
                    )
                ]
            )
            conn.executemany(sql, rows)



    """
    ##############################################################
        Existing technologies
    ##############################################################
    """

    for tech, tech_config in exs_techs.iterrows():

        if tech_config['end_use'] != 'space heating' and tech_config['end_use'] != 'space cooling': continue
        if (tech_config['end_use'], tech_config['fuel']) not in df_exs.index: continue # no existing data for this technology

        fuel_config = config.fuel_commodities.loc[tech_config['fuel']]
        eu_config = config.end_use_demands.loc[tech_config['end_use']]
        exs_data = df_exs.loc[(tech_config['end_use'], tech_config['fuel'])]

        if exs_data['cap'] == 0: continue # no existing capacity -> no process

        # NOT CURRENTLY IN USE - omitting minACF instead
        # Annual capacity factor cannot be higher than the area under the DSD curve
        # otherwise the peak output of a process must be higher than its capacity allows (impossible)
        # since all end use outputs follow the same normalised curve as the DSD
        #dsd = df_dsd[end_use]
        #acf_lim = dsd.mean() / dsd.max() * (1 - config.params['acf_buffer'])


        ## Technologies
        sql, rows = Technology.bulk_insert_or_ignore_sql(
            [
                Technology(
                    tech=tech,
                    flag='p',
                    sector='commercial',
                    annual=1,
                    description=f"{tech_config['end_use']} {tech_config['description']}",
                    data_id=utils.data_id(),
                )
            ]
        )
        conn.executemany(sql, rows)


        ## LifetimeTech
        life = round(cdm_exs.loc[(tech_config['end_use'], tech_config['fuel']), 'avg_life'])
        note = f"Average life of installed stock indexed to shares of service demand by end use and fuel (AEO, {aeo_year})"
        ref = config.sources['aeo']
        sql, rows = LifetimeTech.bulk_insert_or_ignore_sql(
            [
                LifetimeTech(
                    region=region,
                    tech=tech,
                    lifetime=life,
                    notes=note,
                    data_source=ref.source_id,
                    **config.dq_lifetime.as_kwargs(),
                    data_id=utils.data_id(region),
                )
            ]
        )
        conn.executemany(sql, rows)


        ## CapacityToActivity
        c2a = 1 # Capacity is in PJ/y and activity is in PJ
        note = "Capacity is in PJ/y and activity is in PJ so 1"
        sql, rows = CapacityToActivity.bulk_insert_or_ignore_sql(
            [
                CapacityToActivity(
                    region=region,
                    tech=tech,
                    c2a=c2a,
                    notes=note,
                    data_id=utils.data_id(region),
                )
            ]
        )
        conn.executemany(sql, rows)


        # Spread existing capacity evenly over existing vintages
        vints, weights = utils.stock_vintages(base_year, life)

        # Only indexed by vintage
        for v in range(len(vints)):

            vint = vints[v]
            weight = weights[v]

            if vint + life <= config.model_periods[0]: continue

            ## Efficiency
            eff = exs_data['avg_eff']
            note = ("Average efficiency of installed stock estimated using shares of secondary energy consumption. "
                    f"Secondary energy consumption shares calculated from fuel share by end use (NRCan, {base_year}) "
                    f"further indexed to service demand shares divided by efficiencies for installed base technologies "
                    f"of the same end use and fuel (AEO, {aeo_year}).")
            ref = config.sources['nrcan_aeo']
            sql, rows = Efficiency.bulk_insert_or_ignore_sql(
                [
                    Efficiency(
                        region=region,
                        input_comm=fuel_config['comm'],
                        tech=tech,
                        vintage=vint,
                        output_comm=eu_config['comm'],
                        efficiency=eff,
                        notes=note,
                        data_source=ref.source_id,
                        **config.dq_efficiency.as_kwargs(),
                        data_id=utils.data_id(region),
                    )
                ]
            )
            conn.executemany(sql, rows)


            ## ExistingCapacity
            cap = weight * exs_data['cap']
            note = (f"Secondary energy consumption shares calculated from fuel share by end use (NRCan, {base_year}) "
                    f"times average efficiency for installed base technologies (AEO, {aeo_year}) "
                    f"divided by estimated annual capacity factor (NREL, {comstock_year})")
            ref = config.sources['nrcan_aeo_comstock']
            sql, rows = ExistingCapacity.bulk_insert_or_ignore_sql(
                [
                    ExistingCapacity(
                        region=region,
                        tech=tech,
                        vintage=vint,
                        capacity=cap,
                        units=f"({eu_config['cap_unit']})",
                        notes=note,
                        data_source=ref.source_id,
                        **config.dq_existing_capacity.as_kwargs(),
                        data_id=utils.data_id(region),
                    )
                ]
            )
            conn.executemany(sql, rows)


            # Indexed by period and vintage
            for period in config.model_periods:

                if vint > period or vint + life <= period: continue

                ## CostFixed
                cost_fixed = exs_data['avg_fixed_cost'] * config.conversion_factors.cost.aeo
                cost_fixed = conv_curr(cost_fixed)
                note = f"Average maintenance cost of installed stock indexed to shares of service demand by end use and fuel (AEO, {aeo_year})"
                ref = config.sources['aeo']
                sql, rows = CostFixed.bulk_insert_or_ignore_sql(
                    [
                        CostFixed(
                            region=region,
                            period=period,
                            tech=tech,
                            vintage=vint,
                            cost=cost_fixed,
                            units='M$/PJ',
                            notes=note,
                            data_source=ref.source_id,
                            **config.dq_costs.as_kwargs(),
                            data_id=utils.data_id(region),
                        )
                    ]
                )
                conn.executemany(sql, rows)


        ## AnnualCapacityFactor
        acf = exs_data['acf']
        note = f"Mean hourly demand divided by peak hourly demand from Comstock (NREL, {comstock_year})"
        ref = config.sources['comstock']

        for period in config.model_periods:

            if max(vints) + life <= period: continue # no vintage would live this long

            sql, rows = LimitAnnualCapacityFactor.bulk_insert_or_ignore_sql(
                [
                    LimitAnnualCapacityFactor(
                        region=region,
                        vintage=period,
                        tech_or_group=tech,
                        output_comm=eu_config['comm'],
                        operator='le',
                        factor=acf,
                        notes=note,
                        data_source=ref.source_id,
                        **config.dq_capacity_factor.as_kwargs(),
                        data_id=utils.data_id(region),
                    )
                ], include_nulls=True
            )
            conn.executemany(sql, rows)


    conn.commit()
    conn.close()

    return df_exs



def aggregate_other(region: str, df_exs: pd.DataFrame, df_dsd: pd.DataFrame):

    eu_config: pd.Series = config.end_use_demands.loc['other']
    tech_config: pd.Series = config.new_techs.loc[config.new_techs['end_use'] == 'other'].iloc[0]
    dsd = df_dsd['other'].to_numpy() # faster
    elc_fact = config.other_electrification_factor

    if not tech_config['include_new']: return # maybe someone will want to skip all this

    tech = tech_config.name
    vint = config.model_periods[0] # dummy tech

    """
    ##############################################################
        All demands other than space heating and cooling
    ##############################################################
    """

    # Secondary energy by fuel from space heating and cooling (already accounted for)
    sec_sphc = df_exs.groupby(['fuel']).sum()['sec']

    # Table 1: Secondary Energy Use and GHG Emissions by Energy Source
    sec: pd.Series = utils.get_compr_db(region, 1, 3, 8)[base_year].astype(float)

    # Aggregate heavy/light oil and propane/natural gas as we dont have that technological resolution
    sec['oil'] = sec['light fuel oil and kerosene'] + sec['heavy fuel oil']
    sec['natural gas'] = sec['natural gas'] + sec['other']
    #sec_sph['district'] = sec_sph['steam'] # TODO dont have technoeconomic data for district schemes yet so ignore
    sec.drop(['other','steam','light fuel oil and kerosene','heavy fuel oil'], inplace=True)

    # Slice up using Statcan data if its an atlantic province
    sec = get_atlantic_fractions(region, sec)

    # Fuel might be used for other but not sphc
    for fuel in sec.index.difference(sec_sphc.index): sec_sphc[fuel] = 0

    sec_oth = sec - sec_sphc
    sec_oth = sec_oth.loc[sec_oth/sec_oth.sum() > config.sec_tolerance] # drop tiny energy consumptions
    # Demand is sum of secondary energies minus those from space heating and cooling (already accounted for)
    ann_dem = sec_oth.sum() * config.gdp_index # annual demand indexed to gdp growth

    # TechInputSplit ratios are fuel shares of residual secondary energy consumption
    ti_splits = sec_oth / sec_oth.sum()


    """
    ##############################################################
        Add to database
    ##############################################################
    """

    conn = sqlite3.connect(config.database_file)
    curs = conn.cursor()


    ## Technologies
    sql, rows = Technology.bulk_insert_or_ignore_sql(
        [
            Technology(
                tech=tech,
                flag='p',
                sector='commercial',
                annual=1,
                unlim_cap=1,
                description=f"{tech_config['end_use']} {tech_config['description']}",
                data_id=utils.data_id(),
            )
        ]
    )
    conn.executemany(sql, rows)

    ## Commodities
    sql, rows = Commodity.bulk_insert_or_ignore_sql(
        [
            Commodity(
                name=eu_config['comm'],
                flag='d',
                description=f"({eu_config['dem_unit']}) {eu_config['description']}",
                data_id=utils.data_id(),
            )
        ]
    )
    conn.executemany(sql, rows)


    # Flows
    for fuel in sec_oth.index:

        fuel_config = config.fuel_commodities.loc[fuel]

        ## Efficiency
        note = "Dummy tech. Demand equal to secondary energy consumption"
        sql, rows = Efficiency.bulk_insert_or_ignore_sql(
            [
                Efficiency(
                    region=region,
                    input_comm=fuel_config['comm'],
                    tech=tech,
                    vintage=vint,
                    output_comm=eu_config['comm'],
                    efficiency=1,
                    notes=note,
                    data_id=utils.data_id(region),
                )
            ]
        )
        conn.executemany(sql, rows)


        ## TechInputSplit
        ref = config.sources['nrcan_cef']
        for period in config.model_periods:

            tis = ti_splits[fuel]

            # Linear interpolation towards reducing non-elc fuels by electrification factor
            lin_f = (period - base_year)/(config.model_periods[-1] - base_year) # 0 -> 1 linear factor over time
            if fuel == 'electricity': target = elc_fact + tis * ( 1 - elc_fact ) # elc increases
            else: target = tis * (1 - elc_fact) # all others decrease by elc_fact

            tis = tis + (target - tis) * lin_f # elc -> 1

            note = f"Secondary energy consumption by fuel (NRCan, {base_year}) minus space heating and cooling. {config.cef_note}"
            sql, rows = LimitTechInputSplitAnnual.bulk_insert_or_ignore_sql(
                [
                    LimitTechInputSplitAnnual(
                        region=region,
                        period=period,
                        input_comm=fuel_config['comm'],
                        tech=tech,
                        operator='le',
                        proportion=tis,
                        notes=note,
                        data_source=ref.source_id,
                        **config.dq_fuel_splits.as_kwargs(),
                        data_id=utils.data_id(region),
                    )
                ]
            )
            conn.executemany(sql, rows)


    ## DemandSpecificDistribution
    if config.include_dsd:
        data = []
        ref = config.sources['comstock']
        dq_lf = config.dq_lifetime.as_kwargs()

        print(f"Adding DSD for other demand in {region}...")

        for period in config.model_periods:
            for h, row in config.time.iterrows():

                # Data descriptors take up a good bit of storage for timeseries data so only attach to first hour of each day
                if h % 24 == 0:
                    data.append([
                        region, period, row['season'], row['tod'], eu_config['comm'], dsd[h],
                        "Comstock hourly consumption for lighting and equipment summed over all building types and normalised",
                        ref.source_id,
                        dq_lf['dq_cred'], dq_lf['dq_geog'], dq_lf['dq_struc'], dq_lf['dq_tech'], dq_lf['dq_time'],
                        utils.data_id(region),
                    ])
                else:
                    data.append([
                        region, period, row['season'], row['tod'], eu_config['comm'], dsd[h],
                        None, None, None, None, None, None, None,
                        utils.data_id(region),
                    ])


        dsd_rows = [
            DemandSpecificDistribution(
                region=row[0],
                period=row[1],
                season=row[2],
                tod=row[3],
                demand_name=row[4],
                dsd=row[5],
                notes=row[6],
                data_source=row[7],
                dq_cred=row[8],
                dq_geog=row[9],
                dq_struc=row[10],
                dq_tech=row[11],
                dq_time=row[12],
                data_id=row[13],
            )
            for row in data
        ]
        sql, rows = DemandSpecificDistribution.bulk_insert_or_ignore_sql(dsd_rows, include_nulls=True)
        conn.executemany(sql, rows)


    ## Demand
    ref = config.sources['nrcan_gdp']
    for period in config.model_periods:

        dem = ann_dem.loc[period].iloc[0]

        dem = ann_dem.loc[period].iloc[0]
        note = f"Annual secondary energy consumption summed over all fuels minus space heating and cooling (NRCan, {base_year})"

        sql, rows = Demand.bulk_insert_or_ignore_sql(
            [
                Demand(
                    region=region,
                    period=period,
                    commodity=eu_config['comm'],
                    demand=dem,
                    units=f"({eu_config['dem_unit']})",
                    notes=note,
                    data_source=ref.source_id,
                    **config.dq_demands.as_kwargs(),
                    data_id=utils.data_id(region),
                )
            ]
        )
        conn.executemany(sql, rows)

    conn.commit()
    conn.close()



def get_atlantic_fractions(region: str, sec: pd.Series) -> pd.Series:
    """
    For the comprehensive energy use database in commercial, the atlantic provinces are all aggregated.
    To slice them up, we use energy proportions from Statcan data. The system scope of the Statcan
    data is different from NRCan, including upstream energy use, so we dont want to use it directly.
    """

    if not config.regions.loc[region]['atlantic']: return sec

    # Get the primary and secondary energy use table
    df = utils.get_statcan_table(
        25100029,
        'statcan_atlantic_energy',
        usecols = ['REF_DATE','GEO','Fuel type','Supply and demand characteristics','VALUE'],
        filter = lambda df: df.loc[
            (df['REF_DATE'] == config.base_year)
            & (df['Fuel type'].isin(config.fuel_commodities['statcan_fuel']))
            & (df['Supply and demand characteristics'] == 'Commercial and other institutional')
            & (df['GEO'].str.lower().isin(config.regions['description'].loc[config.regions['atlantic']]))
        ]
    ).fillna(0)

    # Map over regions and fuels
    df['region'] = df['GEO'].str.lower().map({
        config.regions.loc[idx, 'description']: idx for idx in config.regions.index
    })
    df['fuel'] = df['Fuel type'].map({
        config.fuel_commodities.loc[idx, 'statcan_fuel']: idx for idx in config.fuel_commodities.index
    })

    # Get the total atlantic energy consumption by fuel
    df_fuel = df.groupby('fuel')['VALUE'].sum()

    # Get fractions of each atlantic province of the total by fuel
    for idx, row in df.iterrows():
        df.loc[idx, 'fraction'] = row['VALUE'] / df_fuel.loc[row['fuel']]

    # Return these fractions
    df = df.loc[df['region'] == region]
    df = df.set_index('fuel')['fraction']

    # Dice up secondary energy using Statcan proportions
    sec = sec.copy()
    for fuel in sec.index:
        if fuel in df.index:
            sec[fuel] *= df.loc[fuel]
        else:
            sec = sec.drop(fuel)

    return sec



if __name__ == "__main__":

    for region in config.model_regions: aggregate_region(region)
