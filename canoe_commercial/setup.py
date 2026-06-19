"""
Sets up configuration for buildings sector aggregation
Written by Ian David Elder for the CANOE model
"""

import os
import pandas as pd
import yaml
import sqlite3
from canoe_schema import get_sql_schema
import canoe_commercial.data_scraper as data_scraper


def instantiate_database():
    
    # Check if database exists or needs to be built
    build_db = not os.path.exists(config.database_file)

    # Connect to the new database file
    conn = sqlite3.connect(config.database_file)
    curs = conn.cursor() # Cursor object interacts with the sqlite db

    # Build the database if it doesn't exist. Otherwise clear all data if forced
    sql_schema = get_sql_schema(config.params['canoe_schema'])
    if config.params['force_wipe_database']:
        tables = [t[0] for t in curs.execute("""SELECT name FROM sqlite_master WHERE type='table';""").fetchall()]
        for table in tables:
            curs.execute(f"DELETE FROM '{table}'")
        print("Database wiped prior to aggregation. See params.\n")
    if build_db or config.params['force_wipe_database']:
        curs.executescript(sql_schema)

    # VACUUM operation to clean up any empty rows
    conn.execute("VACUUM;")
    conn.commit()

    conn.close()



class reference:
    """
    Stores a single reference and its attributes
    - id: the unique id for the source_id column
    - citation: the full citation to go in the DataSource table
    """

    id: str
    citation: str

    def __init__(self, id: str, citation: str):
        self.id = id
        self.citation = citation


class bibliography:
    """This class stores references and handles unique indexing"""

    references: dict[str, reference] = dict()

    def __iter__(self):
        for name, ref in self.references.items():
            yield ref

    def add(cls, name: str, citation: str) -> reference | None:
        """Add a reference to the log and return the reference object"""

        if name in cls.references:
            return cls.references[name]
        else:
            num = len(cls.references.keys()) + 1
            id = f"C{num}" if num >= 10 else f"C0{num}" # C01 -> C99 unique IDs
            ref = reference(id=id, citation=citation)
            cls.references[name] = ref
            return ref
    
    def get(cls, name: str) -> reference | None:
        """Returns a reference by its semantic name"""

        if name not in cls.references:
            print(f"Tried to get a reference that had not been added yet: {name}")
            return
        else:
            return cls.references[name]



class config:

    # File locations
    _this_dir = "./"
    input_files = _this_dir + 'input_files/'
    cache_dir = _this_dir + "data_cache/"

    refs: bibliography = bibliography()
    data_ids = set(['COMHR001', 'COMHR001'])

    if not os.path.exists(cache_dir): os.mkdir(cache_dir)

    tech_vints = {}
    lifetimes = {}

    _instance = None # singleton pattern


    def __new__(cls, *args, **kwargs):

        if isinstance(cls._instance, cls): return cls._instance
        cls._instance = super(config, cls).__new__(cls, *args, **kwargs)

        cls._get_params(cls._instance)
        cls._get_files(cls._instance)
        cls._get_aeo_data(cls._instance)
        cls._get_population_projections(cls._instance)
        cls._get_gdp_projections(cls._instance)
        cls._get_rninja_api(cls._instance)
        cls._get_references(cls._instance)

        print('Instantiated setup config.\n')

        return cls._instance


    def _get_params(cls):
        
        stream = open(config.input_files + "params.yaml", 'r')
        config.params = dict(yaml.load(stream, Loader=yaml.Loader))

        config.new_techs = pd.read_csv(config.input_files + 'new_technologies.csv', index_col=0)
        config.existing_techs = pd.read_csv(config.input_files + 'existing_technologies.csv', index_col=0)
        config.import_techs = pd.read_csv(config.input_files + 'import_technologies.csv', index_col=0)
        config.regions = pd.read_csv(config.input_files + 'regions.csv', index_col=0)
        config.fuel_commodities = pd.read_csv(config.input_files + 'fuel_commodities.csv', index_col=0)
        config.end_use_demands = pd.read_csv(config.input_files + 'end_use_demands.csv', index_col=0)
        config.time = pd.read_csv(config.input_files + 'time.csv', index_col=0)

        config.new_techs = config.new_techs.loc[config.new_techs['include_new']]
        config.all_techs = [*config.new_techs.index.values, *config.existing_techs.index.values]

        # Included regions and future periods
        config.model_periods = list(config.params['model_periods'])
        config.model_periods.sort()
        config.model_regions = config.regions.loc[(config.regions['include'])].index.unique().to_list()
        config.model_regions.sort()



    def _get_files(cls):

        # config.schema_file = config.input_files + config.params['sqlite_schema']
        config.database_file = config.params['sqlite_database']
        config.excel_template_file = config.input_files + config.params['excel_template']
        config.excel_target_file = config._this_dir + config.params['excel_output']


    
    def _get_references(cls):

        config.refs.add('aeo', config.params['aeo_reference'])



    def _get_aeo_data(cls):

        config.aeo_cdm = data_scraper.fetch_aeo_data(
            aeo_file=config.input_files + 'ktekx.xlsx',
            indexing_file=config.input_files + 'aeo_cdm_indexing.csv',
        )


    
    def _get_population_projections(cls) -> pd.DataFrame:

        config.populations = data_scraper.fetch_population_projections(
            regions_df=config.regions,
            cache_dir=config.cache_dir,
            force_download=config.params.get('force_download', False),
        )


    
    def _get_gdp_projections(cls) -> pd.DataFrame:

        config.gdp_index = data_scraper.fetch_gdp_projections(
            gdp_url=config.params['gdp_url'],
            base_year=config.params['base_year'],
            cache_dir=config.cache_dir,
            force_download=config.params.get('force_download', False),
        )

        



    def _get_rninja_api(cls):

        with open('input_files/rninja_api_token.txt') as token_file:
            token = token_file.read()
        config.rninja_api = token



# Instantiate on import
config()