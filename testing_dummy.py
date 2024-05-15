"""
For testing code snippets
"""

import pandas as pd
from setup import config
import requests
import utils
import os
import urllib.request
import zipfile
import csv
import time
import json
import sqlite3
from io import StringIO
import numpy as np
from matplotlib import pyplot as pp
from datetime import datetime
import weather_mapping

df = weather_mapping.get_weather_data(config.params['weather']['ca_temperature_url'])

df.to_csv("on_temp.csv")