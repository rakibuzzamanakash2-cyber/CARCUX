import {
  Activity,
  Bomb,
  Building,
  Building2,
  CarFront,
  CloudRain,
  Construction,
  DropletOff,
  Droplets,
  Flame,
  Mountain,
  TrafficCone,
  TrainFront,
  Tornado,
  Waves,
  ZapOff,
  type LucideIcon,
} from "lucide-react";

/** One icon per event type, so a list can be scanned by shape as well as words. */
const ICONS: Record<string, LucideIcon> = {
  flood: Waves,
  flash_flood: Waves,
  waterlogging: Droplets,
  cyclone: Tornado,
  storm_surge: Waves,
  landslide: Mountain,
  river_erosion: Waves,
  heavy_rainfall: CloudRain,
  earthquake: Activity,
  road_blockage: Construction,
  road_accident: CarFront,
  road_damage: Construction,
  bridge_damage: Construction,
  power_outage: ZapOff,
  gas_outage: Flame,
  water_outage: DropletOff,
  construction_closure: TrafficCone,
  rail_accident: TrainFront,
  fire: Flame,
  building_collapse: Building2,
  building_hazard: Building,
  explosion: Bomb,
};

export function eventTypeIcon(type: string | null): LucideIcon {
  return (type && ICONS[type]) || Activity;
}
