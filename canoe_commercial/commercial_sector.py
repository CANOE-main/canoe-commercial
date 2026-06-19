"""
Builds commercial buildings sector database
Written by Ian David Elder for the CANOE model
"""

import os
from matplotlib import pyplot as pp

import canoe_commercial.utils as utils
import canoe_commercial.all_subsectors as all_subsectors
from canoe_commercial.setup import config



def build_database():

    print(f"Aggregating commercial sector into {os.path.basename(config.database_file)}...\n")

    all_subsectors.aggregate()

    # Convert data costs to final currency
    # currency_conversion.convert_currencies()

    if config.params['clone_to_xlsx']: utils.database_converter().clone_sqlite_to_excel()

    print(f"Commercial sector aggregated into {os.path.basename(config.database_file)}\n")

    # Show any plots that have been made
    if config.params['show_plots']: pp.show()



if __name__ == "__main__":

    build_database()
