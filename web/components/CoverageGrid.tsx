import type { GridCell } from "@/lib/types";

/**
 * Coverage heatmap: one row per region, one column per month.
 *
 * Colour encodes coverage against the 90% target, and a cell that misses target
 * is outlined so the eye finds the failures before the average hides them.
 * Deliberately no tooltips: this has to read correctly as a printed figure.
 */
export function CoverageGrid({
  cells,
  target,
}: {
  cells: GridCell[];
  target: number;
}) {
  const months = Array.from({ length: 12 }, (_, i) => i + 1);
  const regions = Array.from(
    new Map(
      cells
        .slice()
        .sort((a, b) => a.regionid - b.regionid)
        .map((cell) => [cell.regionid, cell]),
    ).values(),
  );

  const byKey = new Map(cells.map((cell) => [`${cell.regionid}-${cell.month}`, cell]));

  function colour(value: number): string {
    // Two points under target is still amber; more than that is red.
    const delta = value - target;
    if (delta >= 0.02) return "#3ddc97";
    if (delta >= 0) return "#8fdc8a";
    if (delta >= -0.04) return "#f2b33d";
    return "#ff7a6b";
  }

  return (
    <div className="cov-grid">
      <div />
      {months.map((month) => (
        <div key={month} className="head">
          {new Date(Date.UTC(2024, month - 1, 1)).toLocaleString("en-GB", {
            month: "short",
            timeZone: "UTC",
          })}
        </div>
      ))}

      {regions.map((region) => (
        <FragmentRow
          key={region.regionid}
          region={region}
          months={months}
          byKey={byKey}
          colour={colour}
        />
      ))}
    </div>
  );
}

function FragmentRow({
  region,
  months,
  byKey,
  colour,
}: {
  region: GridCell;
  months: number[];
  byKey: Map<string, GridCell>;
  colour: (value: number) => string;
}) {
  return (
    <>
      <div className="rowlabel" title={region.shortname ?? `region ${region.regionid}`}>
        {region.sim_site ? <span className="good">●</span> : null}
        <span>
          {region.shortname ?? `Region ${region.regionid}`}
        </span>
      </div>
      {months.map((month) => {
        const cell = byKey.get(`${region.regionid}-${month}`);
        if (!cell) {
          return <div key={month} className="cov-cell" />;
        }
        const value = cell.relative_coverage;
        return (
          <div
            key={month}
            className="cov-cell"
            data-miss={value < 0.9}
            style={{ background: colour(value), opacity: 0.92 }}
            title={`${cell.shortname} ${month}/2024 — ${(100 * value).toFixed(1)}%`}
          >
            {Math.round(100 * value)}
          </div>
        );
      })}
    </>
  );
}
