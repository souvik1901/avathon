import { MapContainer, TileLayer, Marker, Polyline, Tooltip, useMap } from "react-leaflet";
import { Fragment, useEffect, useMemo } from "react";
import type { ReactNode } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Assignment, Order, Scenario, Truck } from "../types";

interface Props {
  scenario: Scenario;
  assignments: Assignment[];
  color: string;
  height?: number;
  onPick?: (a: Assignment) => void;
  showLegend?: boolean;
  interactive?: boolean;
}

// ---- inline SVG glyphs (stroke = currentColor, coloured via the wrapper) ----
const TRUCK_SVG =
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 4h12v11H1z"/><path d="M13 8h4l4 4v3h-8z"/><circle cx="5.5" cy="17.5" r="2"/><circle cx="17.5" cy="17.5" r="2"/></svg>`;
const PKG_SVG =
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8l-9-5-9 5 9 5 9-5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/></svg>`;
const PIN_SVG =
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0116 0z"/><circle cx="12" cy="10" r="2.5"/></svg>`;

const truckIcon = (used: boolean, color: string) =>
  L.divIcon({
    className: "mk",
    html: `<div class="g-truck ${used ? "used" : "idle"}" style="--g:${color}">${TRUCK_SVG}</div>`,
    iconSize: [30, 30], iconAnchor: [15, 15], tooltipAnchor: [0, -16],
  });

const pickupIcon = (assigned: boolean, color: string, priority: number) => {
  const s = 20 + priority * 2;
  return L.divIcon({
    className: "mk",
    html: `<div class="g-pkg ${assigned ? "on" : "off"}" style="--g:${assigned ? color : "#ff5d72"};width:${s}px;height:${s}px">${PKG_SVG}</div>`,
    iconSize: [s, s], iconAnchor: [s / 2, s / 2], tooltipAnchor: [0, -s / 2 - 2],
  });
};

const dropoffIcon = (color: string) =>
  L.divIcon({
    className: "mk",
    html: `<div class="g-drop" style="--g:${color}">${PIN_SVG}</div>`,
    iconSize: [18, 18], iconAnchor: [9, 16], tooltipAnchor: [0, -14],
  });

const hhmm = (iso: string) => {
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
};

function Row({ k, v, accent }: { k: string; v: ReactNode; accent?: boolean }) {
  return (
    <div className="tt-row"><span>{k}</span><b style={accent ? { color: "var(--accent)" } : undefined}>{v}</b></div>
  );
}

// Recenters/zooms the map to fit all points whenever the scenario changes.
function FitBounds({ scenario }: { scenario: Scenario }) {
  const map = useMap();
  useEffect(() => {
    const pts: [number, number][] = [];
    scenario.trucks.forEach((t) => pts.push([t.location.lat, t.location.lon]));
    scenario.orders.forEach((o) => {
      pts.push([o.pickup.lat, o.pickup.lon]);
      pts.push([o.dropoff.lat, o.dropoff.lon]);
    });
    if (pts.length) map.fitBounds(pts, { padding: [36, 36] });
  }, [scenario, map]);
  return null;
}

export default function MapView({
  scenario, assignments, color, height = 460, onPick,
  showLegend = true, interactive = true,
}: Props) {
  const orderById = useMemo(
    () => Object.fromEntries(scenario.orders.map((o) => [o.id, o] as const)),
    [scenario],
  );
  const truckById = useMemo(
    () => Object.fromEntries(scenario.trucks.map((t) => [t.id, t] as const)),
    [scenario],
  );
  const assignedOrderIds = new Set(assignments.map((a) => a.order_id));
  const usedTruckIds = new Set(assignments.map((a) => a.truck_id));
  const orderToTruck = useMemo(
    () => Object.fromEntries(assignments.map((a) => [a.order_id, a.truck_id] as const)),
    [assignments],
  );

  return (
    <div className="map-wrap" style={{ ["--accent" as string]: color }}>
      <MapContainer
        center={[22.63, 88.40]} zoom={11}
        style={{ height, width: "100%" }}
        zoomControl={interactive} dragging={interactive}
        scrollWheelZoom={interactive} doubleClickZoom={interactive}
        attributionControl={false}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains={["a", "b", "c", "d"]}
        />
        <FitBounds scenario={scenario} />

        {/* assignment routes: deadhead (empty) leg dashed + dim, loaded leg solid + bright */}
        {assignments.map((a) => {
          const t = truckById[a.truck_id] as Truck | undefined;
          const o = orderById[a.order_id] as Order | undefined;
          if (!t || !o) return null;
          const tip = (
            <Tooltip sticky className="map-tip">
              <div className="tt-title"><span className="dotc" style={{ background: color }} />{a.truck_id} → {a.order_id}</div>
              <Row k="cost" v={a.cost.toFixed(1)} accent />
              <Row k="travel" v={`${a.travel_km.toFixed(1)} km`} />
              <Row k="ETA" v={hhmm(a.eta)} />
              {a.predicted_lateness_min > 0 && <Row k="late" v={`${a.predicted_lateness_min.toFixed(0)} min`} />}
            </Tooltip>
          );
          return (
            <Fragment key={`route-${a.truck_id}-${a.order_id}`}>
              <Polyline
                positions={[[t.location.lat, t.location.lon], [o.pickup.lat, o.pickup.lon]]}
                pathOptions={{ color, weight: 1.5, opacity: 0.35, dashArray: "3 7", lineCap: "round" }}
                eventHandlers={onPick ? { click: () => onPick(a) } : undefined}
              >{tip}</Polyline>
              <Polyline
                positions={[[o.pickup.lat, o.pickup.lon], [o.dropoff.lat, o.dropoff.lon]]}
                pathOptions={{ color, weight: 3, opacity: 0.9, lineCap: "round" }}
                eventHandlers={onPick ? { click: () => onPick(a) } : undefined}
              >{tip}</Polyline>
            </Fragment>
          );
        })}

        {/* dropoff pins (only for assigned orders — they're the route destination) */}
        {scenario.orders.filter((o) => assignedOrderIds.has(o.id)).map((o) => (
          <Marker key={`drop-${o.id}`} position={[o.dropoff.lat, o.dropoff.lon]} icon={dropoffIcon(color)}>
            <Tooltip direction="top" className="map-tip">
              <div className="tt-title"><span className="dotc" style={{ background: color }} />Dropoff · {o.id}</div>
              <Row k="for truck" v={orderToTruck[o.id]} accent />
            </Tooltip>
          </Marker>
        ))}

        {/* trucks (icon; tinted when working, dimmed when idle/unused) */}
        {scenario.trucks.map((t) => {
          const used = usedTruckIds.has(t.id);
          return (
            <Marker key={t.id} position={[t.location.lat, t.location.lon]} icon={truckIcon(used, color)}>
              <Tooltip direction="top" className="map-tip">
                <div className="tt-title">🚚 {t.id} {used ? <span className="tt-badge on">working</span> : <span className="tt-badge">idle</span>}</div>
                <Row k="capacity" v={`${t.capacity_weight_kg} kg · ${t.capacity_volume_m3} m³`} />
                {t.capacity_orders > 1 && <Row k="can batch" v={`up to ${t.capacity_orders} orders`} accent />}
                <Row k="speed" v={`${t.avg_speed_kmph.toFixed(0)} km/h · ₹${t.cost_per_km.toFixed(2)}/km`} />
                <Row k="capabilities" v={t.capabilities.length ? t.capabilities.join(", ") : "none"} />
                <Row k="shift" v={`${hhmm(t.shift_start)}–${hhmm(t.shift_end)}`} />
              </Tooltip>
            </Marker>
          );
        })}

        {/* order pickups (package; accent when assigned, red pulsing when not) */}
        {scenario.orders.map((o) => {
          const assigned = assignedOrderIds.has(o.id);
          return (
            <Marker key={o.id} position={[o.pickup.lat, o.pickup.lon]} icon={pickupIcon(assigned, color, o.priority)}>
              <Tooltip direction="top" className="map-tip">
                <div className="tt-title">
                  📦 {o.id}
                  <span className={`tt-badge prio p${o.priority}`}>P{o.priority}</span>
                  {assigned ? <span className="tt-badge on">assigned</span> : <span className="tt-badge off">unassigned</span>}
                </div>
                <Row k="demand" v={`${o.weight_kg} kg · ${o.volume_m3} m³`} />
                {o.required_capabilities.length > 0 && <Row k="needs" v={o.required_capabilities.join(", ")} accent />}
                <Row k="due by" v={hhmm(o.due_by)} />
                {assigned && <Row k="served by" v={orderToTruck[o.id]} accent />}
              </Tooltip>
            </Marker>
          );
        })}
      </MapContainer>

      {showLegend && (
        <div className="legend">
          <div className="lr"><span className="lg-truck" /> truck (bright = working)</div>
          <div className="lr"><span className="lg-pkg" /> pickup (size = priority)</div>
          <div className="lr"><span className="lg-pkg red" /> unassigned</div>
          <div className="lr"><span className="lg-pin" /> dropoff</div>
          <div className="lr"><span className="lg-dead" /> empty leg · <span className="lg-load" style={{ background: color }} /> loaded</div>
        </div>
      )}
    </div>
  );
}
