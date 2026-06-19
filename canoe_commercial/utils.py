"""
Various tools
Written by Ian David Elder for the TEMOA Canada / CANOE model
"""


import os
import shutil
from openpyxl import load_workbook
import sqlite3
import pandas as pd
from canoe_commercial.setup import config
import canoe_commercial.data_scraper as data_scraper



# Gets a formatted dataset ID
def data_id(text: str = ''):

    id = f"{config.params['data_id_prefix']}{text}{config.params['data_version']}"
    config.data_ids.add(id)
    return id



def get_compr_db(region, table_number, first_row=0, last_row=None) -> pd.DataFrame:
    """Thin wrapper — delegates to data_scraper.fetch_nrcan_ceud_table."""
    return data_scraper.fetch_nrcan_ceud_table(
        region_nrcan_id=config.regions.loc[region, 'nrcan_id'],
        table_number=table_number,
        nrcan_url_template=config.params['nrcan_url'],
        base_year=config.params['base_year'],
        cache_dir=config.cache_dir,
        first_row=first_row,
        last_row=last_row,
        force_download=config.params.get('force_download', False),
    )



def get_statcan_table(table, save_as=None, filter=None, **kwargs):
    """Thin wrapper — delegates to data_scraper.fetch_statcan_table."""
    return data_scraper.fetch_statcan_table(
        table_id=table,
        cache_dir=config.cache_dir,
        save_as=save_as,
        force_download=config.params.get('force_download', False),
        filter=filter,
        **kwargs,
    )



# Gives data quality time-related indicator based on time gap from data
def dq_time(from_year, to_year):
    diff = abs(from_year - to_year)

    data_quality = {
        3: 1,
        6: 2,
        10: 3,
        15: 4
    }

    for key in data_quality.keys():
        if diff <= key: return data_quality[key]

    return 5 # greater than 15 years time difference



def stock_vintages(stock_year, lifetime, vint_interval=config.params['period_step']) -> tuple[list, list]:

    vint_last = stock_year - stock_year % vint_interval # first stepped back vint

    # Return any stepped back vintages that are feasible
    vints = list(range(int(vint_last), int(stock_year-lifetime), -int(vint_interval)))
    vints.sort()

    if stock_year not in vints: vints.append(stock_year)

    # Only one vintage so all weight in there
    if len(vints) == 1: weights = [1]
    # Stock year lands on a stepped vintage so divide evenly
    elif stock_year == vint_last: weights = [1 / len(vints)] * len(vints)
    # Stock year is after last stepped vintage so give it a lesser weighting proportional to time interval
    else: weights = [vint_interval / (vints[-1]-vints[0])] * (len(vints) - 1) + [stock_year%vint_interval / (vints[-1]-vints[0])]

    return vints, weights



class database_converter:

    # Singleton pattern
    _instance = None

    def __new__(cls, *args, **kwargs):

        if isinstance(cls._instance, cls): return cls._instance

        cls._instance = super(database_converter, cls).__new__(cls, *args, **kwargs)

        print('Instantiated database converter.')

        return cls._instance

    def clone_sqlite_to_excel(self, from_sqlite_file: str = config.database_file, to_excel_file: str = config.excel_target_file, excel_template_file: str = config.excel_template_file):

        print(f"\nCloning {os.path.basename(from_sqlite_file)} into target {os.path.basename(to_excel_file)}."\
              "\nThis may take a minute...")

        # Check that the target file or template file exists
        if (excel_template_file is None):
            print("Aborted. Must provide a template excel file in input files. Check name is correct in res_config.yaml.")
            return

        # Handle numbering if existing excel file
        if os.path.isfile(to_excel_file):
            name, ext = os.path.splitext(to_excel_file)
            n = 1
            while os.path.isfile(f"{name} ({n}){ext}"): n+=1
            to_excel_file = f"{name} ({n}){ext}"

        # Copy template to make target file if target doesn't yet exist
        shutil.copy(excel_template_file, to_excel_file)

        # Load the target workbook
        wb = load_workbook(to_excel_file)

        # Connect to the sqlite from file and get data table names
        conn = sqlite3.connect(from_sqlite_file)
        curs = conn.cursor()
        fetched = curs.execute("""SELECT name FROM sqlite_master WHERE type='table'""").fetchall()

        # Skipping output tables, since this was written for input data
        all_tables = [table[0] for table in fetched if (not table[0].startswith('Output'))]

        for sheet in wb.sheetnames:
            if sheet not in all_tables: print(f"Target sheet {sheet} missing from sqlite database.")

        # Copy tables from sqlite to excel target
        for table_name in all_tables:

            if table_name not in wb.sheetnames:
                print(f"Table {table_name} missing from target workbook and was ignored.")
                continue

            # Get sqlite column names and all data rows, put into pandas dataframe
            rows = curs.execute(f"SELECT * FROM '{table_name}'")
            sql_cols = [desc[0] for desc in rows.description]
            sql_df = pd.DataFrame(data=rows.fetchall(), columns=sql_cols)

            # Get this table from the target excel workbook and its headers (might not be same as sql)
            ws = wb[table_name]
            xl_headers = [cell.value for cell in ws[1]]

            # Flag a warning if a sqlite column does not have a counterpart in the target excel workbook
            for sql_col in sql_cols:
                if sql_col not in xl_headers: print(f"Sqlite column {sql_col} missing from spreadsheet table {table_name} and was ignored.")

            # Prepare a target dataframe matching the target excel workbook template
            xl_df = pd.DataFrame(columns=xl_headers)
            for xl_head in xl_headers:

                # Flag a warning if sqlite table is missing a column that is in the excel workbook
                if xl_head not in sql_cols:
                    print(f"Spreadsheet column {xl_head} missing from sqlite table {table_name}.")
                    continue

                # Fill target workbook dataframe with data from sqlite dataframe
                xl_df[xl_head] = sql_df[xl_head]

            # Clear the target excel table
            ws.delete_rows(2, ws.max_row)

            # Refill the target excel table with data from sqlite
            for index, row in xl_df.iterrows():
                ws.append(row.values.tolist())

        wb.save(to_excel_file)
