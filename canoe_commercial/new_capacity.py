"""
Aggregates new capacity data
Written by Ian David Elder for the CANOE model
"""

from canoe_commercial.setup import config
import sqlite3
import canoe_commercial.utils as utils
import pandas as pd
from canoe_commercial.currency_conversion import conv_curr
from canoe_schema.v3_2.models import (
    CapacityToActivity,
    CostFixed,
    CostInvest,
    Efficiency,
    LifetimeTech,
    LimitAnnualCapacityFactor,
    Technology,
)



def aggregate_region(region: str, df_exs: pd.DataFrame):

    conn = sqlite3.connect(config.database_file)
    curs = conn.cursor()

    aeo_year = config.params['aeo_installed_year']
    comstock_year = config.params['comstock']['data_year']


    """
    ##############################################################
        New technologies
    ##############################################################
    """

    for tech, tech_config in config.new_techs.iterrows():

        end_use = tech_config['end_use']

        # NOT CURRENTLY IN USE - omitting minACF instead
        # Annual capacity factor cannot be higher than the area under the DSD curve
        # otherwise the peak output of a process must be higher than its capacity allows (impossible)
        # since all end use outputs follow the same normalised curve as the DSD
        #dsd = df_dsd[end_use]
        #acf_lim = dsd.mean() / dsd.max() * (1 - config.params['acf_buffer'])

        if end_use != 'space heating' and end_use != 'space cooling': continue
        if (end_use, tech_config['fuel']) not in df_exs.index: continue # insufficient data for this technology
        
        # Prepare some stuff
        fuel_config = config.fuel_commodities.loc[tech_config['fuel']]
        eu_config = config.end_use_demands.loc[end_use]

        # AEO data
        aeo_data = config.aeo_cdm.loc[config.aeo_cdm['techname'] == tech_config['aeo_tech']]
        if type(aeo_data) is pd.DataFrame:
            try: aeo_data = aeo_data.iloc[0] # if multiple rows, just take first
            except Exception as e:
                print(f"Failed. Could not find AEO data for {tech_config['aeo_tech']}.")
                raise e


        ## Technologies
        sql, rows = Technology.bulk_replace_into_sql(
            [
                Technology(
                    tech=tech,
                    flag='p',
                    sector='commercial',
                    annual=1,
                    description=f"{end_use} {tech_config['description']}",
                    data_id=utils.data_id(),
                )
            ]
        )
        conn.executemany(sql, rows)


        ## LifetimeTech
        life = round(aeo_data['life'])
        note = f"Rounded life from AEO CDM ktekx technology menu for technology {tech_config['aeo_tech']} (AEO, {aeo_year})"
        ref = config.refs.get('aeo')
        sql, rows = LifetimeTech.bulk_replace_into_sql(
            [
                LifetimeTech(
                    region=region,
                    tech=tech,
                    lifetime=life,
                    notes=note,
                    data_source=ref.id,
                    dq_cred=1,
                    dq_geog=2,
                    dq_struc=1,
                    dq_tech=2,
                    dq_time=3,
                    data_id=utils.data_id(region),
                )
            ]
        )
        conn.executemany(sql, rows)
        

        ## CapacityToActivity
        c2a = 1 # Capacity is in PJ/y and activity is in PJ
        note = "Capacity is in PJ/y and activity is in PJ so 1"
        sql, rows = CapacityToActivity.bulk_replace_into_sql(
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


        # Only indexed by vintage
        for vint in config.model_periods:

            ## Efficiency
            eff = aeo_data['efficiency']
            note = f"From AEO CDM ktekx technology menu for technology {tech_config['aeo_tech']} (AEO, {aeo_year})"
            ref = config.refs.get('aeo')
            sql, rows = Efficiency.bulk_replace_into_sql(
                [
                    Efficiency(
                        region=region,
                        input_comm=fuel_config['comm'],
                        tech=tech,
                        vintage=vint,
                        output_comm=eu_config['comm'],
                        efficiency=eff,
                        notes=note,
                        data_source=ref.id,
                        dq_cred=1,
                        dq_geog=2,
                        dq_struc=3,
                        dq_tech=2,
                        dq_time=2,
                        data_id=utils.data_id(region),
                    )
                ]
            )
            conn.executemany(sql, rows)
            

            ## CostInvest
            cost_invest = aeo_data['capcst'] * config.params['conversion_factors']['cost']['aeo']
            cost_invest = conv_curr(cost_invest)
            note = f"Capcst from AEO CDM ktekx technology menu for technology {tech_config['aeo_tech']} (AEO, {aeo_year})"
            ref = config.refs.get('aeo')
            sql, rows = CostInvest.bulk_replace_into_sql(
                [
                    CostInvest(
                        region=region,
                        tech=tech,
                        vintage=vint,
                        cost=cost_invest,
                        units='M$/PJ/y',
                        notes=note,
                        data_source=ref.id,
                        dq_cred=1,
                        dq_geog=2,
                        dq_struc=1,
                        dq_tech=2,
                        dq_time=2,
                        data_id=utils.data_id(region),
                    )
                ]
            )
            conn.executemany(sql, rows)
            

            # Indexed by period and vintage
            for period in config.model_periods:

                if vint > period or vint + life <= period: continue

                ## CostFixed
                cost_fixed = aeo_data['maintcst'] * config.params['conversion_factors']['cost']['aeo']
                cost_fixed = conv_curr(cost_fixed)
                note = f"Maintcst from AEO CDM ktekx technology menu for technology {tech_config['aeo_tech']} (AEO, {aeo_year})"
                ref = config.refs.get('aeo')
                sql, rows = CostFixed.bulk_replace_into_sql(
                    [
                        CostFixed(
                            region=region,
                            period=period,
                            tech=tech,
                            vintage=vint,
                            cost=cost_fixed,
                            units='M$/PJ',
                            notes=note,
                            data_source=ref.id,
                            dq_cred=1,
                            dq_geog=2,
                            dq_struc=1,
                            dq_tech=2,
                            dq_time=2,
                            data_id=utils.data_id(region),
                        )
                    ]
                )
                conn.executemany(sql, rows)


        ## AnnualCapacityFactor
        acf = df_exs.loc[(end_use, tech_config['fuel']), 'acf']
        note = f"Mean hourly demand divided by peak hourly demand from Comstock (NREL, {comstock_year})"
        ref = config.refs.get('comstock')
            
        for period in config.model_periods:
                
            sql, rows = LimitAnnualCapacityFactor.bulk_replace_into_sql(
                [
                    LimitAnnualCapacityFactor(
                        region=region,
                        period=period,
                        tech=tech,
                        output_comm=eu_config['comm'],
                        operator='le',
                        factor=acf,
                        notes=note,
                        data_source=ref.id,
                        dq_cred=1,
                        dq_geog=2,
                        dq_struc=5,
                        dq_tech=2,
                        dq_time=3,
                        data_id=utils.data_id(region),
                    )
                ]
            )
            conn.executemany(sql, rows)
            
    
    conn.commit()
    conn.close()