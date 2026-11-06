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
  Polygon,
  TileLayer,
  Tooltip,
  ScaleControl,
  useMap,
  useMapEvents,
} from "react-leaflet";

import { FAMILY_SHAPE, PRIORITY_COLOR } from "@/lib/events";
import { precisionText, SEVERITY_COLOR } from "@/lib/signals";
import type { CarcuxEvent, FieldReport, Priority, Signal } from "@/lib/types";

const BANGLADESH = L.latLngBounds([20.6, 88.0], [26.65, 92.7]);
const SIZE: Record<Priority, number> = {
  critical: 22,
  high: 18,
  medium: 15,
  low: 13,
};

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
  return L.divIcon({
    html,
    className: "marker-glow",
    iconSize: [box, box],
    iconAnchor: [c, c],
  });
}

/** Public signals: a ring with a dot (a broadcast), coloured by severity. */
function signalIcon(signal: Signal): L.DivIcon {
  const color = SEVERITY_COLOR[signal.severity ?? "unknown"];
  const html = `<svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="8" fill="#0a2117" fill-opacity="0.75" stroke="${color}" stroke-width="2.5"/><circle cx="11" cy="11" r="3" fill="${color}"/></svg>`;
  return L.divIcon({
    html,
    className: "",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

/** Leaflet measures its box once; the map sits in a grid that settles after the first
 * paint (and changes with the window), which leaves grey or half-drawn tiles. Re-measure
 * after mounting and whenever the box changes size. */
function KeepSized() {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    const fit = () => map.invalidateSize({ pan: false });
    const t = setTimeout(fit, 200);
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    return () => {
      clearTimeout(t);
      observer.disconnect();
    };
  }, [map]);
  return null;
}

/** A dim veil over everything outside Bangladesh, so the country stands out on the street
 * map while the neighbours stay readable when zoomed out. The country's outlines are the
 * holes in a polygon that covers the world. */
function outsideMask(
  basemap: FeatureCollection<Geometry, BasemapProps> | null,
): L.LatLngExpression[][] | null {
  const country = basemap?.features.find((f) => f.properties.kind === "country");
  if (!country) return null;
  const g = country.geometry;
  const polys =
    g.type === "MultiPolygon" ? g.coordinates : g.type === "Polygon" ? [g.coordinates] : [];
  // Wider than one world, so the veil still covers the screen when zoomed far out.
  const world: L.LatLngExpression[] = [
    [-85, -720],
    [-85, 720],
    [85, 720],
    [85, -720],
  ];
  const holes = polys.map((p) => p[0].map(([lon, lat]) => [lat, lon] as L.LatLngTuple));
  return [world, ...holes];
}

type Cluster = { key: string; lat: number; lon: number; items: Signal[] };

/** Signals that would overlap on screen are drawn as one bubble with a count, re-grouped
 * at every zoom; clicking a bubble zooms in to its signals. */
function groupSignals(map: L.Map, signals: Signal[], radiusPx = 34): Cluster[] {
  const clusters: (Cluster & { x: number; y: number })[] = [];
  for (const s of signals) {
    const p = map.latLngToLayerPoint([s.latitude!, s.longitude!]);
    const near = clusters.find((c) => Math.hypot(c.x - p.x, c.y - p.y) < radiusPx);
    if (near) {
      near.items.push(s);
      const n = near.items.length;
      near.x += (p.x - near.x) / n;
      near.y += (p.y - near.y) / n;
      near.lat += (s.latitude! - near.lat) / n;
      near.lon += (s.longitude! - near.lon) / n;
    } else {
      clusters.push({ key: s.id, lat: s.latitude!, lon: s.longitude!, items: [s], x: p.x, y: p.y });
    }
  }
  return clusters;
}

function clusterIcon(n: number): L.DivIcon {
  const size = n < 10 ? 30 : n < 50 ? 36 : 44;
  const html = `<div class="signal-cluster" style="width:${size}px;height:${size}px">${n}</div>`;
  return L.divIcon({
    html,
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function SignalLayer({ signals, onOpen }: { signals: Signal[]; onOpen: (id: string) => void }) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) });
  // zoom is a dependency on purpose: the screen distances change with it
  const clusters = useMemo(() => groupSignals(map, signals), [map, signals, zoom]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      {clusters.map((c) =>
        c.items.length === 1 ? (
          <Marker
            key={c.key}
            position={[c.lat, c.lon]}
            icon={signalIcon(c.items[0])}
            zIndexOffset={-100}
            eventHandlers={{ click: () => onOpen(c.items[0].id) }}
            title={c.items[0].title}
          >
            <Tooltip className="carcux-tip" direction="top" offset={[0, -8]}>
              <span className="block max-w-64 truncate">{c.items[0].title}</span>
              <span className="text-xs text-muted">
                {c.items[0].source.name}
                {c.items[0].place_name ? `, ${c.items[0].place_name}` : ""}{" "}
                {precisionText(c.items[0].precision_m)}
              </span>
            </Tooltip>
          </Marker>
        ) : (
          <Marker
            key={`cluster-${c.key}`}
            position={[c.lat, c.lon]}
            icon={clusterIcon(c.items.length)}
            zIndexOffset={-50}
            eventHandlers={{
              click: () =>
                map.flyToBounds(
                  L.latLngBounds(c.items.map((s) => [s.latitude!, s.longitude!])).pad(0.4),
                  { maxZoom: 14, duration: 0.6 },
                ),
            }}
            title={`${c.items.length} signals`}
          >
            <Tooltip className="carcux-tip" direction="top" offset={[0, -12]}>
              <span className="block font-semibold">{c.items.length} public signals</span>
              {c.items.slice(0, 3).map((s) => (
                <span key={s.id} className="block max-w-64 truncate text-xs">
                  {s.title}
                </span>
              ))}
              <span className="text-xs text-muted">Click to zoom in</span>
            </Tooltip>
          </Marker>
        ),
      )}
    </>
  );
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

/** Over the street map only the country border and division lines are drawn. */
function overlayStyle(feature?: Feature<Geometry, BasemapProps>): L.PathOptions {
  switch (feature?.properties.kind) {
    case "country":
      return { color: "#3ddc84", weight: 1.8, opacity: 0.9, fill: false };
    case "division":
      return { color: "#d7eadd", weight: 0.9, opacity: 0.45, dashArray: "4 4", fill: false };
    default:
      return { stroke: false, fill: false };
  }
}

function basemapStyle(feature?: Feature<Geometry, BasemapProps>): L.PathOptions {
  switch (feature?.properties.kind) {
    case "country":
      return {
        color: "#e9f5ec",
        weight: 1.6,
        fillColor: "#1d4a30",
        fillOpacity: 1,
      };
    case "neighbour":
      return {
        color: "#21402f",
        weight: 1,
        fillColor: "#11291d",
        fillOpacity: 1,
      };
    case "division":
      return {
        color: "#d7eadd",
        weight: 0.9,
        opacity: 0.55,
        dashArray: "4 4",
        fill: false,
      };
    case "river":
      return { color: "#58b9e0", weight: 2, opacity: 0.9 };
    default:
      return {};
  }
}

export interface MapViewProps {
  events: CarcuxEvent[];
  reports: FieldReport[];
  signals: Signal[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  showReports: boolean;
  /** The detailed street map (online tiles); off gives the simple offline map. */
  streetDetail: boolean;
}

export default function MapView({
  events,
  reports,
  signals,
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

  const mask = useMemo(() => outsideMask(basemap), [basemap]);
  const selected = events.find((e) => e.id === selectedId);
  const target: [number, number] | null = selected ? [selected.latitude, selected.longitude] : null;

  return (
    <MapContainer
      bounds={BANGLADESH}
      minZoom={3}
      maxZoom={19}
      worldCopyJump
      zoomControl
      attributionControl
      className="h-full w-full"
    >
      <KeepSized />
      {streetDetail && (
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
          keepBuffer={4}
          className="tiles-night"
        />
      )}
      {streetDetail && mask && (
        <Polygon
          positions={mask}
          interactive={false}
          pathOptions={{ stroke: false, fillColor: "#04110b", fillOpacity: 0.55 }}
        />
      )}
      {areas && (
        <GeoJSON
          key={streetDetail ? "overlay" : "basemap"}
          data={areas}
          style={(streetDetail ? overlayStyle : basemapStyle) as L.StyleFunction}
          interactive={false}
          attribution="Borders: Natural Earth"
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
            eventHandlers={{
              click: () => router.push(`/field-reports/${r.id}`),
            }}
          >
            <Tooltip className="carcux-tip" direction="top" offset={[0, -4]}>
              <span className="block max-w-56 truncate">{r.text}</span>
              <span className="text-xs text-muted">Field report, {r.reporter.full_name}</span>
            </Tooltip>
          </CircleMarker>
        ))}

      <SignalLayer signals={signals} onOpen={(id) => router.push(`/signals/${id}`)} />

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
