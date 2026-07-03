import os
import numpy as np
import pandas as pd
import requests
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING

import canoe_commercial.data_scraper as data_scraper

if TYPE_CHECKING:
    from canoe_commercial.setup import CANOECommercialConfig

weather_maps: dict = {}  # cached 8760x8760 maps keyed by region
initialised: bool = False
df_us_tmp: pd.DataFrame = None
df_us_hum: pd.DataFrame = None
df_ca_tmp: pd.DataFrame = None
df_ca_hum: pd.DataFrame = None


def get_weather_data(url: str, cfg: "CANOECommercialConfig") -> pd.DataFrame:

    file_name = os.path.splitext(url.split("/")[-1].split("\\")[-1])[0] + f"_{cfg.weather_year}.csv"

    if os.path.isfile(cfg.cache_dir + file_name):

        print(f"Got {file_name} from local cache.")
        df = pd.read_csv(cfg.cache_dir + file_name, index_col=0)
        df.index = pd.to_datetime(df.index)

    else:

        print(f"Downloading {file_name} from Renewables Ninja API...")

        if cfg.rninja_api[:7] == 'WARNING':
            raise ValueError('Failed. You must add your own Renewables Ninja API token to input_files/rninja_api_token.txt')

        s = requests.session()
        s.headers = {'Authorization': 'Token ' + cfg.rninja_api}
        r = s.get(url, params={'format': 'json'})
        data = StringIO(r.text)
        df = pd.read_csv(data, skiprows=3, index_col=0)
        df.index = pd.to_datetime(df.index)
        df = df.loc[df.index.year == cfg.weather_year]
        df.to_csv(cfg.cache_dir + file_name)

    df = data_scraper._realign_timezone(df, from_timezone='UTC', to_timezone=cfg.timezone)
    return df


def initialise_weather_data(cfg: "CANOECommercialConfig") -> None:

    global initialised, df_us_tmp, df_us_hum, df_ca_tmp, df_ca_hum

    if initialised:
        return

    df_us_tmp = get_weather_data(cfg.weather.us_temperature_url, cfg)
    df_us_hum = get_weather_data(cfg.weather.us_humidity_url, cfg)
    df_ca_tmp = get_weather_data(cfg.weather.ca_temperature_url, cfg)
    df_ca_hum = get_weather_data(cfg.weather.ca_humidity_url, cfg)

    initialised = True


def map_data(region: str, us_data: np.ndarray, cfg: "CANOECommercialConfig") -> pd.Series:

    reg_config = cfg.regions.loc[region]
    map_file = f"weather_map_{reg_config['us_state']}-{region}_{cfg.weather_year}_{cfg.timezone}.npz"

    if region in weather_maps:
        return apply_map(region, us_data)

    if not cfg.force_generate_weather_maps and os.path.isfile(cfg.cache_dir + map_file):
        print(f"Loading weather map {map_file} from local cache...")
        with open(cfg.cache_dir + map_file, 'rb') as file:
            weather_maps[region] = np.load(file)['arr_0']
        try:
            return apply_map(region, us_data)
        except Exception as e:
            print(f"Failed to apply weather map from local cache. Regenerating. Error:\n{e}")

    print(f"\nGenerating a weather-based data map from {reg_config['us_state']} to {region}...")

    weather_maps[region] = np.zeros((8760, 8760))

    initialise_weather_data(cfg)

    df_ca = pd.concat([df_ca_tmp[reg_config['ca_rninja']], df_ca_hum[reg_config['ca_rninja']]], axis=1).astype(float)
    df_us = pd.concat([df_us_tmp[f"US.{reg_config['us_state']}"], df_us_hum[f"US.{reg_config['us_state']}"]], axis=1).astype(float)
    df_ca.columns = ['temp', 'hum']
    df_us.columns = ['temp', 'hum']

    unmatched = 0.0
    for h in range(8760):

        ca_row = df_ca.iloc[h]

        row_map = 1.0 * np.array(
            (ca_row['temp'] <= df_us['temp'] + 1) &
            (ca_row['temp'] >= df_us['temp'] - 1) &
            (ca_row['hum'] == df_us['hum'])
        ).transpose()

        if np.sum(row_map) == 0:
            unmatched += 1
            if ca_row['temp'] > np.max(df_us['temp']):
                row_map = 1.0 * np.array(df_us['temp'] == np.max(df_us['temp'])).transpose()
            elif ca_row['temp'] < np.min(df_us['temp']):
                row_map = 1.0 * np.array(df_us['temp'] == np.min(df_us['temp'])).transpose()

        row_map *= np.nan if np.sum(row_map) == 0 else 1 / np.sum(row_map)
        weather_maps[region][h, :] = row_map.copy()

    print(f"{round((1 - unmatched / 8760) * 100, 1)}% of hours found +-1C temperature match.")

    with open(cfg.cache_dir + map_file, 'wb') as file:
        np.savez_compressed(file, weather_maps[region])
    print(f"Weather map generated and cached as {map_file}")

    return apply_map(region, us_data)


def apply_map(region: str, us_data: np.ndarray) -> pd.Series:

    print(f"Applying weather map for {region}...")
    ca_data = pd.Series(np.matmul(weather_maps[region], us_data)).interpolate(method='linear')
    return ca_data


def get_weekly_variation(data: np.ndarray, cfg: "CANOECommercialConfig"):

    jan_1_us = datetime.weekday(datetime.fromisoformat(f"{cfg.weather_year}-01-01"))
    jan_1_ca = datetime.weekday(datetime.fromisoformat(f"{cfg.weather_year}-01-01"))

    daily_avg = np.array([np.mean(data[24 * d:24 * d + 23]) for d in range(364)])
    weekly_avg = np.array([np.mean(data[7 * 24 * w:7 * 24 * w + 7 * 24 - 1]) for w in range(52)])
    day_of_week = [np.mean(daily_avg[d:52 * 7:7] / weekly_avg) for d in range(7)]
    hour_of_day = [np.mean(data[h:24 * 7 * 52:24] / daily_avg) for h in range(24)]
    time_of_week = [day_of_week[h // 24] * hour_of_day[h % 24] for h in range(24 * 7)]

    time_of_week_zeroed = time_of_week[-24 * jan_1_us::] + time_of_week[0:-24 * jan_1_us]
    tow_mults = time_of_week_zeroed[24 * jan_1_ca::] + time_of_week_zeroed[0:24 * jan_1_ca]
    tow_mults = tow_mults * 52 + tow_mults[0:24]
    tow_mults /= np.mean(tow_mults)

    return time_of_week_zeroed
