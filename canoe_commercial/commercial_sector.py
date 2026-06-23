"""
Builds commercial buildings sector database
Written by Ian David Elder for the CANOE model
"""

import os
import sqlite3
from matplotlib import pyplot as pp

import canoe_commercial.utils as utils
import canoe_commercial.all_subsectors as all_subsectors
import canoe_commercial.validation as validation
from canoe_commercial.setup import config



def build_database():

    print(f"Aggregating commercial sector into {os.path.basename(config.database_file)}...\n")

    # Step 0: validate canoe-base DB structure against module config
    conn = sqlite3.connect(config.database_file)
    validation.validate_db_against_config(config, conn)
    conn.close()

    all_subsectors.aggregate()

    # Convert data costs to final currency
    # currency_conversion.convert_currencies()

    if config.clone_to_xlsx: utils.database_converter().clone_sqlite_to_excel()

    print(f"Commercial sector aggregated into {os.path.basename(config.database_file)}\n")

    # Show any plots that have been made
    if config.show_plots: pp.show()



if __name__ == "__main__":

    build_database()
