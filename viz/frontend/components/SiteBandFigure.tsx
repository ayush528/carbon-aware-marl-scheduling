import { apiGet } from "@/lib/api";
import type { DataResponse, UncertaintyResponse } from "@/lib/types";

/**
 * Bar chart for the 2024 measured carbon intensity of the four sites, with the
 * coverage-band overlap that decides whether a routing move is defensible.
 *
 * Pure SVG, no chart library: the figure has to keep working offline in a review
 * room and be reproducible from the run record it cites.
 */
export function SiteBandFigure({
  regions,
  q,
}: {
  regions: DataResponse["regions"];
  q: number;
}) {
  if (regions.length === 0) {
    return <p className="muted small">No UK site series in the current record.</p>;
  }

  const width = 520;
  const rowHeight = 62;
  const height = regions.length * rowHeight + 46;
  const left = 96;
  const right = 470;
  const max = Math.max(...regions.map((r) => r.input_mean_gco2_per_kwh * (1 + q))) * 1.06;

  const x = (value: number) => left + ((right - left) * value) / max;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label="Regional carbon intensity with calibrated 90% bands"
      style={{ overflow: "visible" }}
    >
      {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
        const value = max * fraction;
        return (
          <g key={fraction}>
            <line
              x1={x(value)}
              y1={8}
              x2={x(value)}
              y2={height - 22}
              stroke="#1e2a37"
              strokeDasharray={fraction === 0 ? "0" : "3 5"}
            />
            <text
              x={x(value)}
              y={height - 6}
              fill="#63707f"
              fontSize="10"
              fontFamily="ui-monospace"
              textAnchor="middle"
            >
              {Math.round(value)}
            </text>
          </g>
        );
      })}

      {regions.map((site, index) => {
        const y = 20 + index * rowHeight;
        const value = site.input_mean_gco2_per_kwh;
        const lo = value * (1 - q);
        const hi = value * (1 + q);
        return (
          <g key={site.site}>
            <text
              x={0}
              y={y + 14}
              fill="#8fa1b4"
              fontSize="11.5"
              fontFamily="ui-monospace"
            >
              {site.site.replace("GB-", "")}
            </text>
            <rect
              x={x(lo)}
              y={y + 4}
              width={Math.max(2, x(hi) - x(lo))}
              height="14"
              rx="7"
              fill="#4ea1ff"
              opacity="0.22"
            />
            <line
              x1={x(value)}
              y1={y + 1}
              x2={x(value)}
              y2={y + 21}
              stroke="#4ea1ff"
              strokeWidth="2"
            />
            <text
              x={x(hi) + 8}
              y={y + 15}
              fill="#c3d2e2"
              fontSize="11"
              fontFamily="ui-monospace"
            >
              {value.toFixed(1)} ± {(value * q).toFixed(1)}
            </text>
          </g>
        );
      })}
      <text x={0} y={height - 6} fill="#63707f" fontSize="10">
        gCO₂/kWh
      </text>
    </svg>
  );
}
