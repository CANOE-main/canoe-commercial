"""
Writes module-specific commodity rows (fuel commodities) owned by the commercial sector.
"""

import sqlite3
from typing import TYPE_CHECKING

from canoe_schema.v4_0.models import Commodity

if TYPE_CHECKING:
    from canoe_commercial.setup import CANOECommercialConfig


def write_commodities(cfg: "CANOECommercialConfig", db_conn: sqlite3.Connection) -> None:
    for _code, comm_config in cfg.fuel_commodities.iterrows():
        sql, rows = Commodity.bulk_insert_or_ignore_sql(
            [
                Commodity(
                    name=comm_config['comm'],
                    flag=comm_config['flag'],
                    description=f"({comm_config['unit']}) {comm_config['description']}",
                    data_id=cfg.data_id(),
                )
            ]
        )
        db_conn.executemany(sql, rows)

    db_conn.commit()
    print("Module commodities written.\n")
