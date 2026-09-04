"""
Factory for the DataSource registry — called once during config initialisation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from canoe_schema.v4_0.models import DataSource

if TYPE_CHECKING:
    from canoe_commercial.setup import CANOECommercialConfig


def build_sources(cfg: CANOECommercialConfig) -> dict[str, DataSource]:
    base_id = f"{cfg.data_id_prefix}{cfg.data_version}"
    cfg.data_ids.add(base_id)

    return {
        "aeo": DataSource(source_id="COM-AEO", source=cfg.aeo_reference, data_id=base_id),
        "nrcan": DataSource(source_id="COM-NRCAN", source=cfg.nrcan_reference, data_id=base_id),
        "comstock": DataSource(source_id="COM-COMSTOCK", source=cfg.comstock.reference, data_id=base_id),
        "epa": DataSource(source_id="COM-EPA", source=cfg.epa_reference, data_id=base_id),
        "gdp": DataSource(source_id="COM-GDP", source=cfg.gdp_reference, data_id=base_id),
        "cef": DataSource(source_id="COM-CEF", source=cfg.cef_reference, data_id=base_id),
        "pop": DataSource(source_id="COM-POP", source=cfg.pop_reference, data_id=base_id),
        "demand": DataSource(
            source_id="COM-DEMAND",
            source=f"{cfg.nrcan_reference}; {cfg.aeo_reference}; {cfg.gdp_reference}",
            data_id=base_id,
        ),
        "nrcan_aeo": DataSource(
            source_id="COM-NRCAN-AEO",
            source=f"{cfg.nrcan_reference}; {cfg.aeo_reference}",
            data_id=base_id,
        ),
        "nrcan_aeo_comstock": DataSource(
            source_id="COM-NRCAN-AEO-COMSTOCK",
            source=f"{cfg.nrcan_reference}; {cfg.aeo_reference}; {cfg.comstock.reference}",
            data_id=base_id,
        ),
        "nrcan_cef": DataSource(
            source_id="COM-NRCAN-CEF",
            source=f"{cfg.nrcan_reference}; {cfg.cef_reference}",
            data_id=base_id,
        ),
        "nrcan_gdp": DataSource(
            source_id="COM-NRCAN-GDP",
            source=f"{cfg.nrcan_reference}; {cfg.gdp_reference}",
            data_id=base_id,
        ),
    }
