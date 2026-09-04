"""
Post-run registry writes: DataSource, DataSet, and vintage-period validation.
"""

import sqlite3
from typing import TYPE_CHECKING

import pandas as pd

from canoe_schema.v4_0.models import DataSet, DataSource, Efficiency

import canoe_commercial.validation as validation

if TYPE_CHECKING:
    from canoe_commercial.setup import CANOECommercialConfig


def write_data_registry(cfg: "CANOECommercialConfig", db_conn: sqlite3.Connection) -> None:
    curs = db_conn.cursor()

    """
    ##############################################################
        Existing vintage periods (validate, not write)
    ##############################################################
    """

    exs_vints = {
        row[0]
        for row in curs.execute(
            f"SELECT vintage FROM {Efficiency.__table_name__}"
        ).fetchall()
        if row[0] not in cfg.model_periods
    }
    validation.validate_existing_vintage_periods(
        db_conn, exs_vints, behavior=cfg.validation_behavior
    )

    """
    ##############################################################
        DataSource rows
    ##############################################################
    """

    for src in cfg.sources.values():
        sql, rows = DataSource.bulk_insert_or_ignore_sql([src])
        db_conn.executemany(sql, rows)

    """
    ##############################################################
        DataSet rows
    ##############################################################
    """

    for data_id in sorted(cfg.data_ids):
        sql, rows = DataSet.bulk_insert_or_ignore_sql([DataSet(data_id=data_id)])
        db_conn.executemany(sql, rows)

    # Audit for rows with missing data_ids
    tables = [
        t[0]
        for t in curs.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    ]
    for table in tables:
        cols = [c[1] for c in curs.execute(f"PRAGMA table_info({table})").fetchall()]
        if "data_id" in cols:
            bad_rows = pd.read_sql_query(f"SELECT * FROM {table} WHERE data_id IS NULL", db_conn)
            if len(bad_rows) > 0:
                print(f"Found rows missing data_ids in {table}")
                print(bad_rows)

    db_conn.commit()
    print("Data registry written.\n")
