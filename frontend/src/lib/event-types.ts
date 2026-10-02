/**
 * Event types, grouped by family. The values mirror the backend
 * (backend/app/core/event_types.py) and the CARCUX-BD dataset schema
 * (data/schema/v1/common.schema.json); `npm run check:event-types` fails CI if
 * they drift apart. Labels are UI-only.
 */
export const EVENT_TYPE_GROUPS = [
  {
    family: "Natural calamity",
    types: [
      { value: "flood", label: "Flood" },
      { value: "flash_flood", label: "Flash flood" },
      { value: "waterlogging", label: "Waterlogging" },
      { value: "cyclone", label: "Cyclone" },
      { value: "storm_surge", label: "Storm surge" },
      { value: "landslide", label: "Landslide" },
      { value: "river_erosion", label: "River erosion" },
      { value: "heavy_rainfall", label: "Heavy rainfall" },
      { value: "earthquake", label: "Earthquake" },
    ],
  },
  {
    family: "Road and infrastructure",
    types: [
      { value: "road_blockage", label: "Road blockage" },
      { value: "road_accident", label: "Road accident" },
      { value: "road_damage", label: "Road damage" },
      { value: "bridge_damage", label: "Bridge damage" },
      { value: "power_outage", label: "Power outage" },
      { value: "gas_outage", label: "Gas outage" },
      { value: "water_outage", label: "Water outage" },
      { value: "construction_closure", label: "Construction closure" },
      { value: "rail_accident", label: "Rail accident" },
    ],
  },
  {
    family: "Urban emergency",
    types: [
      { value: "fire", label: "Fire" },
      { value: "building_collapse", label: "Building collapse" },
      { value: "building_hazard", label: "Building hazard" },
      { value: "explosion", label: "Explosion" },
    ],
  },
] as const;

const LABELS = new Map<string, string>(
  EVENT_TYPE_GROUPS.flatMap((g) => g.types.map((t) => [t.value, t.label] as const)),
);

export function eventTypeLabel(value: string | null): string {
  if (!value) return "Type not set";
  return LABELS.get(value) ?? value;
}
