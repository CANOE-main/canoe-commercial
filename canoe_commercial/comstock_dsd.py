"""
Calculates normalised demand distributions for end uses and also by fuel (for annual capacity factors)
Written by Ian David Elder for the CANOE model
"""

import numpy as np
import pandas as pd
from matplotlib import pyplot as pp
from typing import TYPE_CHECKING

import canoe_commercial.data_scraper as data_scraper
import canoe_commercial.weather_mapping as weather_mapping

if TYPE_CHECKING:
    from canoe_commercial.setup import CANOECommercialConfig

# Module-level cache so comstock_map.csv is read once per input_files path
_comstock_map_cache: dict[str, pd.DataFrame] = {}


def _get_comstock_map(input_files: str) -> pd.DataFrame:
    if input_files not in _comstock_map_cache:
        _comstock_map_cache[input_files] = pd.read_csv(input_files + 'comstock_map.csv', index_col=0)
    return _comstock_map_cache[input_files]


def calculate_dsds(region: str, cfg: "CANOECommercialConfig") -> pd.DataFrame:

    fig, axs = pp.subplots(len(cfg.end_use_demands.index), 1, figsize=(15, 10))
    fig.tight_layout()
    fig.subplots_adjust(wspace=0.2, hspace=0.3, top=0.9, left=0.05, right=0.95, bottom=0.05)
    fig.suptitle(f"{region} demand specific distributions (blue).\nWeekly variation overlaid (red).")
    p = 0

    df_dsd = get_comstock_consumption(region, cfg)

    for end_use, eu_config in cfg.end_use_demands.iterrows():

        cols = [col for col in df_dsd.columns if end_use in str(col)]

        for col in cols:

            if eu_config['use_weather_map']:
                dsd = weather_mapping.map_data(region, df_dsd[col].to_numpy(), cfg)
                dsd = np.clip(dsd, 0, np.inf)
                dsd = dsd / dsd.sum()
                df_dsd[col] = dsd.values
            else:
                df_dsd[col] = df_dsd[col] / df_dsd[col].sum()

        df_dsd[end_use] = df_dsd[cols].sum(axis='columns')
        df_dsd[end_use] = df_dsd[end_use] / df_dsd[end_use].sum()

        tow = weather_mapping.get_weekly_variation(df_dsd[end_use].to_numpy(), cfg)

        axs[p].set_title(end_use)
        axs[p].plot(range(len(df_dsd[end_use])), df_dsd[end_use])
        axs[p].twinx().plot(range(0,8736,52), tow, 'r-') # time-of-week variation overlaid
        p += 1

    return df_dsd


def get_comstock_consumption(region: str, cfg: "CANOECommercialConfig") -> pd.DataFrame:

    buildings = cfg.comstock.building_types
    comstock_map = _get_comstock_map(cfg.input_files)

    df_comstock = _fetch_comstock_table(region, buildings[0], cfg)
    for building in buildings[1:]:
        df = _fetch_comstock_table(region, building, cfg)
        for col in df.columns:
            if col in df_comstock.columns:
                df_comstock[col] = df_comstock[col].values + df[col].values
            else:
                df_comstock[col] = df[col].values

    for com_col, euf in comstock_map.iterrows():
        euf_col = f"{euf['end_use']} {euf['fuel']}"
        if euf_col in df_comstock.columns:
            df_comstock[euf_col] += df_comstock[com_col]
        else:
            df_comstock[euf_col] = df_comstock[com_col]

    eufs = (comstock_map['end_use'] + ' ' + comstock_map['fuel']).values
    df_comstock.drop([col for col in df_comstock.columns if col not in eufs], axis='columns', inplace=True)

    return df_comstock


def _fetch_comstock_table(region: str, building: str, cfg: "CANOECommercialConfig") -> pd.DataFrame:
    return data_scraper.fetch_comstock_table(
        us_state=cfg.regions.loc[region, 'us_state'],
        building=building,
        url_template=cfg.comstock.url,
        cache_dir=cfg.cache_dir,
        timezone=cfg.timezone,
        force_download=cfg.force_download,
    )
