"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  TileLayer,
  Tooltip,
  ScaleControl,
  useMap,
  useMapEvents,
} from "react-leaflet";

import { FAMILY_SHAPE, PRIORITY_COLOR } from "@/lib/events";
import type { CarcuxEvent, FieldReport, Priority } from "@/lib/types";

const BANGLADESH = L.latLngBounds([20.6, 88.0], [26.65, 92.7]);
const BOUNDS = L.latLngBounds([19.6, 86.0], [27.8, 94.8]);
const SIZE: Record<Priority, number> = { critical: 22, high: 18, medium: 15, low: 13 };

type BasemapProps = { kind: string; name?: string; rank?: number };

function shapePath(shape: string, s: number): string {
  const c = s / 2;
  const r = s / 2 - 2;
  if (shape === "diamond") return `M${c} ${c - r} L${c + r} ${c} L${c} ${c + r} L${c - r} ${c} Z`;
  if (shape === "triangle") {
    const h = r * 1.15;
    return `M${c} ${c - h} L${c + h * 0.95} ${c + h * 0.7} L${c - h * 0.95} ${c + h * 0.7} Z`;
  }
  return `M${c - r} ${c} a${r} ${r} 0 1 0 ${2 * r} 0 a${r} ${r} 0 1 0 ${-2 * r} 0`;
}

function eventIcon(event: CarcuxEvent, selected: boolean): L.DivIcon {
  const s = SIZE[event.priority];
  const pad = 18; // room for the pulse and selection ring
  const box = s + pad * 2;
  const color = PRIORITY_COLOR[event.priority];
  const shape = FAMILY_SHAPE[event.family] ?? "circle";
  const c = box / 2;
  const pulse =
    event.priority === "critical"
      ? `<circle class="pulse-ring" cx="${c}" cy="${c}" r="${s / 2}" fill="none" stroke="${color}" stroke-width="2"/>`
      : "";
  const ring = selected
    ? `<circle cx="${c}" cy="${c}" r="${s / 2 + 6}" fill="none" stroke="#ffffff" stroke-width="2.5"/>`
    : "";
  const html = `<svg width="${box}" height="${box}" viewBox="0 0 ${box} ${box}" aria-hidden="true">${pulse}${ring}<g transform="translate(${pad} ${pad})"><path d="${shapePath(shape, s)}" fill="${color}" stroke="#ffffff" stroke-width="2.5"/></g></svg>`;
  return L.divIcon({ html, className: "marker-glow", iconSize: [box, box], iconAnchor: [c, c] });
}

function FlyTo({ target }: { target: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo(target, Math.max(map.getZoom(), 9), { duration: 0.8 });
  }, [map, target]);
  return null;
}

/** Small towns only when zoomed in, so labels never pile up at country scale. */
function useZoom(): number {
  const [zoom, setZoom] = useState(7);
  const map = useMapEvents({ zoomend: () => setZoom(map.getZoom()) });
  return zoom;
}

type CityFeature = Feature<Geometry, BasemapProps>;

function Cities({ cities }: { cities: CityFeature[] }) {
  const zoom = useZoom();
  return (
    <>
      {cities
        .filter((c) => (c.properties.rank ?? 9) <= (zoom >= 8 ? 8 : 6))
        .map((c) => {
          const [lon, lat] = (c.geometry as GeoJSON.Point).coordinates;
          return (
            <CircleMarker
              key={c.properties.name}
              center={[lat, lon]}
              radius={(c.properties.rank ?? 9) <= 2 ? 3 : 2}
              pathOptions={{ color: "#ffffff", weight: 0, fillOpacity: 0.85 }}
              interactive={false}
            >
              <Tooltip permanent direction="right" offset={[4, 0]} className="city-label">
                {c.properties.name}
              </Tooltip>
            </CircleMarker>
          );
        })}
    </>
  );
}

function basemapStyle(feature?: Feature<Geometry, BasemapProps>): L.PathOptions {
  switch (feature?.properties.kind) {
    case "country":
      return { color: "#e9f5ec", weight: 1.6, fillColor: "#1d4a30", fillOpacity: 1 };
    case "neighbour":
      return { color: "#21402f", weight: 1, fillColor: "#11291d", fillOpacity: 1 };
    case "division":
      return { color: "#d7eadd", weight: 0.9, opacity: 0.55, dashArray: "4 4", fill: false };
    case "river":
      return { color: "#58b9e0", weight: 2, opacity: 0.9 };
    default:
      return {};
  }
}

export interface MapViewProps {
  events: CarcuxEvent[];
  reports: FieldReport[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  showReports: boolean;
  streetDetail: boolean;
}

export default function MapView({
  events,
  reports,
  selectedId,
  onSelect,
  showReports,
  streetDetail,
}: MapViewProps) {
  const router = useRouter();
  const [basemap, setBasemap] = useState<FeatureCollection<Geometry, BasemapProps> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/geo/bangladesh.json")
      .then((r) => r.json())
      .then((data) => !cancelled && setBasemap(data))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const areas = useMemo(
    () =>
      basemap && {
        ...basemap,
        features: basemap.features.filter((f) => f.properties.kind !== "city"),
      },
    [basemap],
  );
  const cities = useMemo(
    () => basemap?.features.filter((f) => f.properties.kind === "city") ?? [],
    [basemap],
  );

  const selected = events.find((e) => e.id === selectedId);
  const target: [number, number] | null = selected ? [selected.latitude, selected.longitude] : null;

  return (
    <MapContainer
      bounds={BANGLADESH}
      minZoom={6}
      maxZoom={17}
      maxBounds={BOUNDS}
      maxBoundsViscosity={0.8}
      zoomControl
      attributionControl
      className="h-full w-full"
    >
      {areas && (
        <GeoJSON
          data={areas}
          style={basemapStyle as L.StyleFunction}
          interactive={false}
          attribution="Basemap: Natural Earth"
        />
      )}
      {streetDetail && (
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          subdomains="abcd"
          opacity={0.85}
        />
      )}
      {!streetDetail && <Cities cities={cities} />}

      {showReports &&
        reports.map((r) => (
          <CircleMarker
            key={r.id}
            center={[r.latitude, r.longitude]}
            radius={4}
            pathOptions={{
              color: "#0a2117",
              weight: 1.5,
              fillColor: r.integrity_flags.length ? "#ef3b42" : "#3ddc84",
              fillOpacity: 0.9,
            }}
            eventHandlers={{ click: () => router.push(`/field-reports/${r.id}`) }}
          >
            <Tooltip className="carcux-tip" direction="top" offset={[0, -4]}>
              <span className="block max-w-56 truncate">{r.text}</span>
              <span className="text-xs text-muted">Field report, {r.reporter.full_name}</span>
            </Tooltip>
          </CircleMarker>
        ))}

      {events.map((e) => (
        <Marker
          key={e.id}
          position={[e.latitude, e.longitude]}
          icon={eventIcon(e, e.id === selectedId)}
          zIndexOffset={e.id === selectedId ? 1000 : e.priority === "critical" ? 500 : 0}
          eventHandlers={{ click: () => onSelect(e.id) }}
          title={e.title}
        >
          <Tooltip className="carcux-tip" direction="top" offset={[0, -14]}>
            {e.title}
          </Tooltip>
        </Marker>
      ))}
      <FlyTo target={target} />
      <ScaleControl position="topleft" imperial={false} />
    </MapContainer>
  );
}
