"""
Pre-run and post-run validation for canoe-commercial.

All functions here are read-only against the database. They check that the DB
produced by canoe-base contains the structure this module's config expects,
and fail loudly (or warn) rather than silently writing wrong data.

Decisions recorded in DECISIONS.md:
  - time_season / time_of_day / time_season_sequential: seeded by canoe-base, validated here
  - Emission commodity: seeded by canoe-base, validated here
  - Existing vintage periods: seeded by canoe-base, validated in post_process()

Table names use v4.0 lowercase conventions; validated against the live DB schema
canoe-base creates. Column names should be confirmed against v4.0 schema when
the module is fully migrated to v4.0 models (Stage 4).
"""

import logging

logger = logging.getLogger(__name__)


def validate_db_against_config(config, db_conn):
    """
    Validate the canoe-base DB against this module's config before any writes.
    Raises ValueError on missing structure unless validation_behavior='warning'.
    """
    behavior = config.params.get('validation_behavior', 'error')

    check_missing_periods(db_conn, config.model_periods, behavior)
    check_missing_regions(db_conn, config.model_regions, behavior)

    if config.params.get('include_dsd', True):
        check_missing_time_slices(db_conn, config.time, behavior)

    if config.params.get('include_emissions', True):
        check_emission_commodity(
            db_conn, config.params['emission_commodity'], behavior
        )


def check_missing_periods(db_conn, model_periods, behavior='error'):
    """
    Checks that every future model period exists in time_period with flag='f'.

    These periods define the optimization horizon and are seeded by canoe-base.
    """
    cursor = db_conn.cursor()
    db_periods = {
        row[0]
        for row in cursor.execute(
            "SELECT period FROM time_period WHERE flag = 'f'"
        ).fetchall()
    }
    missing = [p for p in model_periods if p not in db_periods]
    if missing:
        _handle(
            f"Future periods {missing} are absent from time_period (flag='f'). "
            "canoe-base must seed all model periods before this module runs.",
            behavior,
        )


def check_missing_regions(db_conn, model_regions, behavior='error'):
    """
    Checks that every province in the module's region list exists in the region table.

    Regions are seeded by canoe-base.
    """
    cursor = db_conn.cursor()
    db_regions = {
        row[0] for row in cursor.execute("SELECT region FROM region").fetchall()
    }
    missing = [r for r in model_regions if r not in db_regions]
    if missing:
        _handle(
            f"Regions {missing} are absent from the region table. "
            "canoe-base must seed all regions before this module runs.",
            behavior,
        )


def check_missing_time_slices(db_conn, time_df, behavior='error'):
    """
    Checks that every season and time-of-day value used by this module's DSD rows
    exists in the time_season and time_of_day tables respectively.

    Both tables are seeded by canoe-base. See DECISIONS.md — decision 1.
    """
    cursor = db_conn.cursor()

    db_seasons = {
        row[0] for row in cursor.execute("SELECT season FROM time_season").fetchall()
    }
    db_tods = {
        row[0] for row in cursor.execute("SELECT tod FROM time_of_day").fetchall()
    }

    missing_seasons = [s for s in time_df['season'].unique() if s not in db_seasons]
    missing_tods = [t for t in time_df['tod'].unique() if t not in db_tods]

    if missing_seasons:
        _handle(
            f"Seasons {missing_seasons} are absent from time_season. "
            "canoe-base must seed all seasons before this module runs.",
            behavior,
        )
    if missing_tods:
        _handle(
            f"Time-of-day values {missing_tods} are absent from time_of_day. "
            "canoe-base must seed all time-of-day entries before this module runs.",
            behavior,
        )


def check_emission_commodity(db_conn, emission_commodity, behavior='error'):
    """
    Checks that the emission commodity (e.g. CO2eq) exists in the commodity table.

    This commodity spans all sectors and is seeded by canoe-base. See DECISIONS.md — decision 2.
    """
    cursor = db_conn.cursor()
    row = cursor.execute(
        "SELECT name FROM commodity WHERE name = ?", (emission_commodity,)
    ).fetchone()
    if row is None:
        _handle(
            f"Emission commodity '{emission_commodity}' is absent from the commodity table. "
            "canoe-base must seed this cross-sector commodity. See DECISIONS.md — decision 2.",
            behavior,
        )


def validate_existing_vintage_periods(db_conn, vintage_years, behavior='error'):
    """
    Called from post_process() after Efficiency rows have been written.

    Checks that every existing vintage year inferred from this module's technologies
    already exists in time_period with flag='e'. canoe-base is expected to seed
    the full historical period range. See DECISIONS.md — decision 3.
    """
    if not vintage_years:
        return

    cursor = db_conn.cursor()
    db_existing = {
        row[0]
        for row in cursor.execute(
            "SELECT period FROM time_period WHERE flag = 'e'"
        ).fetchall()
    }
    missing = [v for v in vintage_years if v not in db_existing]
    if missing:
        _handle(
            f"Existing vintage periods {sorted(missing)} are absent from time_period (flag='e'). "
            "canoe-base must seed historical periods that cover all technology vintage years. "
            "See DECISIONS.md — decision 3.",
            behavior,
        )


def _handle(msg, behavior):
    if behavior == 'error':
        raise ValueError(msg)
    else:
        logger.warning(msg)
