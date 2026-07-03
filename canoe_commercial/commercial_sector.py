"""
Builds commercial buildings sector database
Written by Ian David Elder for the CANOE model
"""

import os
import re
import sqlite3

from matplotlib import pyplot as pp

import canoe_commercial.comstock_dsd as comstock_dsd
import canoe_commercial.data_scraper as data_scraper
import canoe_commercial.emission_activity as emission_activity
import canoe_commercial.existing_capacity as existing_capacity
import canoe_commercial.new_capacity as new_capacity
import canoe_commercial.post_processing as post_processing
import canoe_commercial.techcom as techcom
import canoe_commercial.utils as utils
import canoe_commercial.validation as validation
from canoe_commercial.setup import CANOECommercialConfig


def build_database() -> None:

    cfg = CANOECommercialConfig.validate_from_toml("input_files")
    db_conn = sqlite3.connect(cfg.database_file)

    print(f"Aggregating commercial sector into {os.path.basename(cfg.database_file)}...\n")

    # Step 0: Validate canoe-base DB structure against module config
    validation.validate_db_against_config(cfg, db_conn)

    # Step 1: Data is already loaded onto cfg by validate_from_toml → _load_data()
    aeo_data = cfg.aeo_cdm
    gdp_index = cfg.gdp_index

    emis_factors = None
    if cfg.include_emissions:
        raw_emis = data_scraper.fetch_emission_factors(
            url=cfg.epa_url,
            cache_dir=cfg.cache_dir,
            force_download=cfg.force_download,
        )
        emis_factors = emission_activity.prepare_emission_factors(raw_emis, cfg)

    # Step 2: Write module-specific commodity rows
    techcom.write_commodities(cfg, db_conn)

    # Step 3: Per-region subsector processing
    for region in cfg.province_list:

        print(f"Aggregating {region}...\n")

        df_dsd = comstock_dsd.calculate_dsds(region, cfg)
        df_exs = existing_capacity.aggregate_region(region, df_dsd, aeo_data, gdp_index, cfg, db_conn)
        new_capacity.aggregate_region(region, df_exs, aeo_data, cfg, db_conn)

        if cfg.include_emissions:
            emission_activity.aggregate_region(region, emis_factors, cfg, db_conn)

        print(f"Aggregated {region}.\n")

    # Step 4: Register data sources and datasets
    post_processing.write_data_registry(cfg, db_conn)

    db_conn.close()

    if cfg.clone_to_xlsx:
        utils.database_converter().clone_sqlite_to_excel(
            from_sqlite_file=cfg.database_file,
            to_excel_file=cfg.excel_target_file,
            excel_template_file=cfg.excel_template_file,
        )

    print(f"Commercial sector aggregated into {os.path.basename(cfg.database_file)}\n")

    if cfg.show_plots:
        save_plots()


def save_plots(output_dir='output_plots'):
    os.makedirs(output_dir, exist_ok=True)
    print("Finished and saving plots.")
    for fig_num in pp.get_fignums():
        fig = pp.figure(fig_num)
        # Try suptitle first, then first axes title, then fall back to figure number
        title = fig.get_suptitle()
        if not title and fig.axes:
            title = fig.axes[0].get_title()
        filename = title if title else f"figure_{fig_num}"
        # Sanitize filename: replace characters that are invalid in Windows filenames
        filename = re.sub(r'[\\/:*?"<>|\x00-\x1f .,]', '_', filename)
        filepath = os.path.join(output_dir, f"{filename}.pdf")
        fig.savefig(filepath, bbox_inches='tight')
        print(f"Saved {filepath}")

if __name__ == "__main__":

    build_database()
