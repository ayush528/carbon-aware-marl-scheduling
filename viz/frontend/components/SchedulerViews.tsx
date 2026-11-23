import type { Frame, Site } from "@/lib/scheduler";
import { carbonColour, fmt, slotClock } from "@/lib/scheduler";

/* Server-rendered SVG/CSS views. No client JS: the page is a deterministic
   render of one replay payload, so every pixel comes from a committed artifact
   or a replay of committed code. */

const WIDTH = 520;
const HEIGHT = 640;

/* A deliberately coarse Great Britain outline, in (lon, lat). It is decoration:
   the sites are placed from real coordinates and the carbon values are real, but
   the coastline is a hand-drawn approximation and is labelled as such. */
const GB_OUTLINE: [number, number][] = [
  [-5.72, 50.05], [-3.5, 50.2], [-1.3, 50.7], [0.9, 51.4], [1.72, 52.62],
  [0.34, 53.5], [-0.2, 54.1], [-1.2, 54.7], [-1.8, 55.6], [-2.1, 56.0],
  [-2.5, 57.2], [-1.8, 57.6], [-3.0, 58.6], [-5.0, 58.6], [-5.4, 57.5],
  [-5.7, 56.5], [-5.0, 55.0], [-4.8, 54.6], [-3.1, 54.9], [-3.0, 54.0],
  [-3.4, 53.3], [-4.7, 53.3], [-4.2, 52.4], [-5.2, 51.8], [-3.9, 51.5],
  [-3.2, 51.4], [-4.2, 50.5],
];

const LON = { min: -6.6, max: 2.4 };
const LAT = { min: 49.7, max: 59.2 };

function project(lon: number, lat: number): [number, number] {
  const x = ((lon - LON.min) / (LON.max - LON.min)) * WIDTH;
  const y = ((LAT.max - lat) / (LAT.max - LAT.min)) * HEIGHT;
  return [x, y];
}

export function UkMap({
  sites,
  frame,
  selectedSlot,
  chosenSlot,
  chosenSite,
  servedShare,
}: {
  sites: Site[];
  frame: Frame;
  selectedSlot: number;
  chosenSlot: number | null;
  chosenSite: string | null;
  servedShare: number[];
}) {
  const values = frame.forecast_g_per_kwh;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const maxShare = Math.max(...servedShare, 1e-9);
  const outline = GB_OUTLINE.map(([lon, lat]) => project(lon, lat).join(",")).join(" ");

  return (
    <figure className="map-figure">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="UK data centre map">
        {[50, 52, 54, 56, 58].map((lat) => {
          const [, y] = project(LON.min, lat);
          return (
            <g key={lat}>
              <line x1={0} x2={WIDTH} y1={y} y2={y} stroke="var(--line)" strokeDasharray="2 6" />
              <text x={6} y={y - 4} fill="var(--faint)" fontSize={11}>
                {lat}°N
              </text>
            </g>
          );
        })}
        {[-6, -4, -2, 0, 2].map((lon) => {
          const [x] = project(lon, LAT.min);
          return (
            <g key={lon}>
              <line y1={0} y2={HEIGHT} x1={x} x2={x} stroke="var(--line)" strokeDasharray="2 6" />
              <text x={x + 4} y={HEIGHT - 8} fill="var(--faint)" fontSize={11}>
                {Math.abs(lon)}°{lon < 0 ? "W" : "E"}
              </text>
            </g>
          );
        })}
        <polygon points={outline} fill="var(--panel-2)" stroke="var(--line-strong)" strokeWidth={1.5} />
        {sites.map((site, j) => {
          const [x, y] = project(site.lon, site.lat);
          const value = values[j] ?? 0;
          const share = servedShare[j] / maxShare;
          const r = 10 + 16 * Math.sqrt(Math.max(share, 0));
          const isChosen = chosenSite === site.name;
          return (
            <g key={site.name}>
              {isChosen ? (
                <circle cx={x} cy={y} r={r + 9} fill="none" stroke="var(--accent)" strokeWidth={2} strokeDasharray="4 4" />
              ) : null}
              <circle cx={x} cy={y} r={r} fill={carbonColour(value, lo, hi)} fillOpacity={0.85} stroke="var(--bg)" strokeWidth={2} />
              <text x={x} y={y + 4} textAnchor="middle" fontSize={12} fontWeight={600} fill="#0a0e13">
                {fmt(value, 0)}
              </text>
              <text x={x} y={y + r + 16} textAnchor="middle" fontSize={12} fill="var(--text)">
                {site.short}
              </text>
              <text x={x} y={y + r + 30} textAnchor="middle" fontSize={10} fill="var(--faint)">
                {fmt(servedShare[j] / 3600, 0)} GPU-h served
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="map-legend">
        <span>
          Bubble colour and number = forecast intensity at slot {selectedSlot} ({frame.at}); bubble area =
          GPU-seconds served in that slot. The coastline is a hand-drawn approximation and carries no data.
        </span>
        <span className="map-scale">
          <span style={{ background: carbonColour(lo, lo, hi) }} /> {fmt(lo, 0)} g/kWh
          <span style={{ background: carbonColour((lo + hi) / 2, lo, hi) }} />
          <span style={{ background: carbonColour(hi, lo, hi) }} /> {fmt(hi, 0)} g/kWh
        </span>
      </figcaption>
    </figure>
  );
}

/** Sites x slots intensity grid for the whole week, plus the selected item's plan. */
export function ForecastGrid({
  sites,
  frames,
  selectedSlot,
  chosenBlocks,
  slotMinutes,
  windowStart,
}: {
  sites: Site[];
  frames: Frame[];
  selectedSlot: number;
  chosenBlocks: { site: string; slot: number }[];
  slotMinutes: number;
  windowStart: string;
}) {
  const all = frames.flatMap((f) => f.forecast_g_per_kwh);
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const cell = 3;
  const labelW = 104;
  const height = 26 * sites.length;
  const width = frames.length * cell;

  return (
    <div className="grid-scroll">
      <div className="grid-inner" style={{ minWidth: labelW + width }}>
        <div className="grid-row grid-head" style={{ paddingLeft: labelW }}>
          {frames
            .filter((f) => f.slot % 48 === 0)
            .map((f) => (
              <span key={f.slot} style={{ left: labelW + f.slot * cell }}>
                {slotClock(windowStart, f.slot, slotMinutes).slice(5, 10)}
              </span>
            ))}
        </div>
        {sites.map((site, j) => (
          <div className="grid-row" key={site.name}>
            <span className="grid-label">{site.short}</span>
            <svg width={width} height={height / sites.length} style={{ display: "block" }}>
              {frames.map((f) => (
                <rect
                  key={f.slot}
                  x={f.slot * cell}
                  y={0}
                  width={cell}
                  height={height / sites.length}
                  fill={carbonColour(f.forecast_g_per_kwh[j] ?? 0, lo, hi)}
                />
              ))}
              <rect
                x={selectedSlot * cell}
                y={0}
                width={2}
                height={height / sites.length}
                fill="var(--text)"
                opacity={0.9}
              />
              {chosenBlocks
                .filter((b) => b.site === site.name)
                .map((b) => (
                  <rect
                    key={`chosen-${b.slot}`}
                    x={b.slot * cell}
                    y={height / sites.length - 3}
                    width={cell}
                    height={3}
                    fill="var(--accent)"
                  />
                ))}
            </svg>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Sites x slots served volume as a share of block capacity. */
export function Timeline({
  sites,
  frames,
  selectedSlot,
  slotMinutes,
  windowStart,
}: {
  sites: Site[];
  frames: Frame[];
  selectedSlot: number;
  slotMinutes: number;
  windowStart: string;
}) {
  const cell = 3;
  const labelW = 104;
  const rowH = 22;
  const width = frames.length * cell;

  return (
    <div className="grid-scroll">
      <div className="grid-inner" style={{ minWidth: labelW + width }}>
        <div className="grid-row grid-head" style={{ paddingLeft: labelW }}>
          {frames
            .filter((f) => f.slot % 48 === 0)
            .map((f) => (
              <span key={f.slot} style={{ left: labelW + f.slot * cell }}>
                {slotClock(windowStart, f.slot, slotMinutes).slice(5, 10)}
              </span>
            ))}
        </div>
        {sites.map((site, j) => (
          <div className="grid-row" key={site.name}>
            <span className="grid-label">{site.short}</span>
            <svg width={width} height={rowH} style={{ display: "block" }}>
              {frames.map((f) => {
                const capacity = f.capacity_gpu_s[j] ?? 0;
                const share = capacity > 0 ? Math.min(1, (f.served_gpu_s[j] ?? 0) / capacity) : 0;
                return (
                  <rect
                    key={f.slot}
                    x={f.slot * cell}
                    y={rowH - rowH * share}
                    width={cell}
                    height={rowH * share}
                    fill="var(--info)"
                    opacity={0.35 + 0.65 * share}
                  />
                );
              })}
              <rect x={selectedSlot * cell} y={0} width={2} height={rowH} fill="var(--text)" opacity={0.9} />
            </svg>
          </div>
        ))}
      </div>
    </div>
  );
}
