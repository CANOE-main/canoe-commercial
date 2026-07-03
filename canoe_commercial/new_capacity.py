"""
Aggregates new capacity data
Written by Ian David Elder for the CANOE model
"""

import sqlite3
from typing import TYPE_CHECKING

import pandas as pd

import canoe_commercial.utils as utils
from canoe_commercial.currency_conversion import conv_curr
from canoe_schema.v4_0.models import (
    CapacityToActivity,
    CostFixed,
    CostInvest,
    Efficiency,
    LifetimeTech,
    LimitAnnualCapacityFactor,
    Technology,
)

if TYPE_CHECKING:
    from canoe_commercial.setup import CANOECommercialConfig


def aggregate_region(
    region: str,
    df_exs: pd.DataFrame,
    aeo_data: pd.DataFrame,
    cfg: "CANOECommercialConfig",
    db_conn: sqlite3.Connection,
) -> None:

    aeo_year = cfg.aeo_installed_year
    comstock_year = cfg.comstock.data_year

    """
    ##############################################################
        New technologies
    ##############################################################
    """

    for tech, tech_config in cfg.new_techs.iterrows():

        end_use = tech_config['end_use']

        if end_use != 'space heating' and end_use != 'space cooling':
            continue
        if (end_use, tech_config['fuel']) not in df_exs.index:
            continue

        fuel_config = cfg.fuel_commodities.loc[tech_config['fuel']]
        eu_config = cfg.end_use_demands.loc[end_use]

        aeo_slice = aeo_data.loc[aeo_data['techname'] == tech_config['aeo_tech']]
        if type(aeo_slice) is pd.DataFrame:
            try:
                aeo_slice = aeo_slice.iloc[0]
            except Exception as e:
                print(f"Failed. Could not find AEO data for {tech_config['aeo_tech']}.")
                raise e


        ## Technologies
        tech_end_uses = cfg.new_techs.loc[[tech], 'end_use'].tolist()
        if 'space heating' in tech_end_uses and 'space cooling' in tech_end_uses:
            tech_eu_label = 'space heating/cooling'
        else:
            tech_eu_label = end_use
        sql, rows = Technology.bulk_insert_or_ignore_sql(
            [
                Technology(
                    tech=tech, flag='p', sector='commercial', annual=1,
                    description=f"{tech_eu_label} {tech_config['description']}",
                    data_id=cfg.data_id(),
                )
            ]
        )
        db_conn.executemany(sql, rows)


        ## LifetimeTech
        life = round(aeo_slice['life'])
        note = f"Rounded life from AEO CDM ktekx technology menu for technology {tech_config['aeo_tech']} (AEO, {aeo_year})"
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


        for vint in cfg.model_periods:

            ## Efficiency
            eff = aeo_slice['efficiency']
            note = f"From AEO CDM ktekx technology menu for technology {tech_config['aeo_tech']} (AEO, {aeo_year})"
            ref = cfg.sources['aeo']
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


            ## CostInvest
            cost_invest = aeo_slice['capcst'] * cfg.conversion_factors.cost.aeo
            cost_invest = conv_curr(cost_invest)
            note = f"Capcst from AEO CDM ktekx technology menu for technology {tech_config['aeo_tech']} (AEO, {aeo_year})"
            ref = cfg.sources['aeo']
            sql, rows = CostInvest.bulk_insert_or_ignore_sql(
                [
                    CostInvest(
                        region=region, tech=tech, vintage=vint,
                        cost=cost_invest, units='M$/PJ/y',
                        notes=note, data_source=ref.source_id,
                        **cfg.dq_costs.as_kwargs(),
                        data_id=cfg.data_id(region),
                    )
                ]
            )
            db_conn.executemany(sql, rows)


            for period in cfg.model_periods:

                if vint > period or vint + life <= period:
                    continue

                ## CostFixed
                cost_fixed = aeo_slice['maintcst'] * cfg.conversion_factors.cost.aeo
                cost_fixed = conv_curr(cost_fixed)
                note = f"Maintcst from AEO CDM ktekx technology menu for technology {tech_config['aeo_tech']} (AEO, {aeo_year})"
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
            acf = df_exs.loc[(end_use, tech_config['fuel']), 'acf']
            note = f"Mean hourly demand divided by peak hourly demand from Comstock (NREL, {comstock_year})"
            ref = cfg.sources['comstock']
                    
            sql, rows = LimitAnnualCapacityFactor.bulk_replace_into_sql(
                [
                    LimitAnnualCapacityFactor(
                        region=region, vintage=vint, tech_or_group=tech,
                        output_comm=eu_config['comm'], operator='le', factor=acf,
                        notes=note, data_source=ref.source_id,
                        **cfg.dq_capacity_factor.as_kwargs(),
                        data_id=cfg.data_id(region),
                    )
                ]
            )
            db_conn.executemany(sql, rows)


    db_conn.commit()
