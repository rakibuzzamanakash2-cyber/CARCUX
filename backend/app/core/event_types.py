"""Event types, mirroring the CARCUX-BD dataset schema (data/schema/v1/common.schema.json).

A test keeps this list identical to the dataset schema, so field reports and the
research dataset always speak the same vocabulary.
"""

EVENT_TYPE_FAMILY: dict[str, str] = {
    **dict.fromkeys(
        [
            "flood", "flash_flood", "waterlogging", "cyclone", "storm_surge", "landslide",
            "river_erosion", "heavy_rainfall", "earthquake",
        ],
        "natural_calamity",
    ),
    **dict.fromkeys(
        [
            "road_blockage", "road_accident", "road_damage", "bridge_damage", "power_outage",
            "gas_outage", "water_outage", "construction_closure", "rail_accident",
        ],
        "road_infrastructure",
    ),
    **dict.fromkeys(
        ["fire", "building_collapse", "building_hazard", "explosion"], "urban_emergency"
    ),
}  # fmt: skip

EVENT_TYPES = frozenset(EVENT_TYPE_FAMILY)

# Bangladesh bounding box, as in the dataset schema.
BD_LON = (88.0, 92.7)
BD_LAT = (20.5, 26.7)
