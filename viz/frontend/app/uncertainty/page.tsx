import { apiGet } from "@/lib/api";
import type { DataResponse, UncertaintyResponse } from "@/lib/types";
import { CoverageGrid } from "@/components/CoverageGrid";
import { SiteBandFigure } from "@/components/SiteBandFigure";
import {

  Callout,
  Card,
  Chip,
  ErrorPanel,
  Formula,
  Section,
  Stat,
  num,
  pct,
} from "@/components/ui";

// The evidence is read live from the Python service, so never prerender it
export const dynamic = "force-dynamic";

export default async function UncertaintyPage() {
  const [uncertainty, data] = await Promise.all([
    apiGet<UncertaintyResponse>("/api/uncertainty"),
    apiGet<DataResponse>("/api/data"),
  ]);
  const error = uncertainty.error ?? data.error;
  if (error) return <ErrorPanel message={error} />;

  const target = uncertainty.data!.target;
  const national = uncertainty.data!.single_split.national;
  const regional = uncertainty.data!.single_split.regional;
  const rolling = uncertainty.data!.rolling;

  return (
    <>
      <div className="topbar">
        <span>Uncertainty</span>
        <span className="spacer" />
        <span className="stamp">
          split conformal · distribution-free · {pct(target, 0)} target
        </span>
      </div>

      <h1 className="page-title">Uncertainty as an input, not a caveat</h1>
      <p className="page-lede">
        A grid carbon forecast is a point estimate of a quantity that misses by
        tens of grams during a ramp. If a scheduler routes on that point estimate
        it will move work on noise. This page measures how wrong the forecast is
        allowed to be, and how often the band actually settles a decision.
      </p>

      <div className="grid g4">
        <Stat
          label="Target coverage"
          value={pct(target, 0)}
          note={`α = ${uncertainty.data!.alpha}`}
        />
        <Stat
          label="2024 walk-forward"
          value={rolling ? pct(rolling.relative.mean_coverage_positive_forecast) : "—"}
          note={rolling ? `${num(rolling.n_cells)} region-months` : "no run"}
          tone={
            rolling && rolling.relative.mean_coverage_positive_forecast >= target
              ? "good"
              : "warn"
          }
        />
        <Stat
          label="Cells at target"
          value={rolling ? `${rolling.relative.cells_at_target_pct.toFixed(0)}%` : "—"}
          note="per-month coverage is not guaranteed"
          tone="warn"
        />
        <Stat
          label="Mean band width"
          value={
            rolling ? `${rolling.relative.mean_half_width_pct_of_forecast.toFixed(1)}%` : "—"
          }
          note="of the forecast, ±"
          tone="info"
        />
      </div>

      <Section
        title="The method"
        sub="Split conformal prediction: distribution-free, finite-sample, and dependent on no assumption about the shape of the forecast error."
      >
        <div className="grid g2">
          <Card title="One line of arithmetic">
            <Formula>q = sorted(|actual − forecast|)[⌈(n+1)(1−α)⌉ − 1]</Formula>
            <ul className="tight">
              <li>
                Calibrate on a window the evaluation never sees — 28 days of
                history for each month of 2024.
              </li>
              <li>
                Band = <span className="mono">forecast ± q</span> for a national
                series; a region inherits it scaled by its own forecast, so one
                calibration covers all 14 regions.
              </li>
              <li>
                Deterministic and stdlib-only: re-running the experiment
                reproduces the same quantile to the last digit.
              </li>
            </ul>
          </Card>
          <Card title="Why not an error bar">
            <p className="small">
              An RMSE error bar assumes symmetric, homoscedastic, usually Gaussian
              residuals. Measured on this data, none of those hold: the absolute
              error grows with intensity while the relative error falls from ~18%
              at 30 gCO₂/kWh to ~3% at 250. Conformal makes no such assumption and
              still delivers a finite-sample guarantee.
            </p>
            <p className="small" style={{ marginBottom: 0 }}>
              The guarantee is <i>marginal</i>: over the calibration draw, at least{" "}
              {pct(target, 0)} of slots are covered. It does not promise that every
              month is covered, and the grid below shows exactly that gap instead
              of hiding it behind one average.
            </p>
          </Card>
        </div>
      </Section>

      <Section
        title="What the first test proved"
        sub="Calibrate January 2025, evaluate the held-out February. This is the Phase 1 exit test."
      >
        <div className="grid g2">
          <Card title="National bands (exp004)">
            {national ? (
              <dl className="kv">
                <dt>Held-out coverage</dt>
                <dd className="mono good">{pct(national.holdout_coverage)}</dd>
                <dt>Band half-width</dt>
                <dd className="mono">{national.band_half_width_gco2_per_kwh.toFixed(1)} g/kWh</dd>
                <dt>Hold-out MAE</dt>
                <dd className="mono">{national.holdout_mae_gco2_per_kwh.toFixed(2)} g/kWh</dd>
                <dt>Verdict</dt>
                <dd>
                  <Chip status="verified" /> exit test passed
                </dd>
              </dl>
            ) : (
              <p className="muted small">No exp004 record.</p>
            )}
          </Card>
          <Card title="Regional bands (exp005)">
            {regional ? (
              <>
                <dl className="kv">
                  <dt>Mean coverage</dt>
                  <dd className="mono good">{pct(regional.mean_coverage)}</dd>
                  <dt>Regions at target</dt>
                  <dd className="mono">
                    {regional.n_regions_at_target} / {regional.n_regions}
                  </dd>
                  <dt>Worst region</dt>
                  <dd className="mono">{pct(regional.min_coverage)}</dd>
                </dl>
                <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
                  Two of fourteen regions miss 90% on a one-month hold-out. That is
                  the honest result of a single split, and the reason the design was
                  rebuilt below.
                </p>
              </>
            ) : (
              <p className="muted small">No exp005 record.</p>
            )}
          </Card>
        </div>
      </Section>

      {rolling ? (
        <>
          <Section
            title="The stronger design: walk forward through 2024"
            sub={`Every month is calibrated on the ${rolling.calibration_days} days before it and evaluated on itself. ${num(
              rolling.n_cells,
            )} region-months, ${num(rolling.n_evaluation_slots)} slots, no month ever sees its own future.`}
          >
            <Card title="Relative-band coverage per region and month (%, target 90)">
              <CoverageGrid cells={rolling.grid} target={target} />
              <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
                Green ≥ 92%, light green ≥ 90%, amber within 4 points, red below.
                A red outline marks a cell that misses the target. Four of the
                fourteen rows are the sites the simulator actually runs, marked{" "}
                <span className="good">●</span>.
              </p>
              <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
                The rows are near-identical by construction, and that is the point
                of national scaling: the band scales with each region&apos;s own
                forecast, so one calibration covers all fourteen. North Scotland is
                the visible exception — {rolling.by_region.find((r) => r.regionid === 1)?.zero_forecast_pct?.toFixed(0) ?? "64"}%
                of its slots carry a zero forecast, so the informative figure is
                measured on a different (windier) subset of hours. It is a
                property of the estimator, not evidence that Scotland calibrates
                better.
              </p>
            </Card>

            <div style={{ marginTop: 14 }}>
              <Callout tone="warn">
                <b>Read the grid, not the mean.</b> Mean coverage is{" "}
                {pct(rolling.relative.mean_coverage_positive_forecast)} against a{" "}
                {pct(target, 0)} target, but only{" "}
                {rolling.relative.cells_at_target_pct.toFixed(0)}% of the{" "}
                {num(rolling.n_cells)} cells reach it. Conformal gives a marginal
                guarantee; 28 days of calibration does not buy a per-month one. We
                report both, because a scheduler that trusts a per-month band will
                be wrong more often than the headline suggests.
              </Callout>
            </div>
          </Section>

          <Section
            title="Four ways to shape the same band"
            sub="The shape matters more than the quantile: a band that scales with the forecast is not the same object as one that does not."
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Construction</th>
                    <th className="num">Mean coverage</th>
                    <th className="num">Cells at target</th>
                    <th className="num">Mean width</th>
                    <th className="num">Worst cell</th>
                    <th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    {
                      key: "relative",
                      name: "Relative (q × forecast)",
                      block: rolling.relative,
                      verdict: "Headline: best coverage per unit width",
                      tone: "good" as const,
                    },
                    {
                      key: "regime_relative",
                      name: "Relative, per national regime",
                      block: rolling.regime_relative,
                      verdict: "Tightest, but under-covers on average",
                      tone: "warn" as const,
                    },
                    {
                      key: "constant",
                      name: "Constant (national q)",
                      block: rolling.constant,
                      verdict: "Fails where carbon is low — the worst cell is 5%",
                      tone: "bad" as const,
                    },
                    {
                      key: "regime_conditional",
                      name: "Per regional regime (rejected)",
                      block: rolling.regime_conditional,
                      verdict:
                        "Buckets the wrong scale: 2× the width, less coverage",
                      tone: "bad" as const,
                    },
                  ].map((row) => (
                    <tr
                      key={row.key}
                      data-highlight={row.key === "relative"}
                    >
                      <td>
                        <b>{row.name}</b>
                      </td>
                      <td className="num">
                        {pct(row.block.mean_coverage_positive_forecast)}
                      </td>
                      <td className="num">{row.block.cells_at_target_pct.toFixed(0)}%</td>
                      <td className="num">
                        {row.block.mean_half_width_pct_of_forecast.toFixed(1)}%
                      </td>
                      <td className="num">
                        {pct(row.block.min_cell_coverage ?? null)}
                      </td>
                      <td className="small muted">{row.verdict}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted" style={{ marginTop: 10 }}>
              This is a negative result we kept. Bucketing on the regional level
              was tried first and fails for a reason worth stating: under national
              scaling a regional residual is{" "}
              <span className="mono">national_error × f_region ÷ f_national</span>, so
              a high-carbon region carries a residual roughly twice the national
              one while a low-carbon region carries a fraction of it. One bucket
              edge cannot serve both. Bucketing the national level fixes the scale
              but gives up too much width to per-regime noise on 28 days. The single
              pooled relative quantile wins, and now we know why.
            </p>
          </Section>

          <Section
            title="Does the band change a decision?"
            sub="A proportional band cannot reorder regions. What it does is set how large a carbon gap must be before the routing is defensible."
          >
            <div className="grid g2">
              <Card title="The rule the simulation measures">
                <Formula>move only if  f_clean / f_dirty &lt; (1 − q) / (1 + q)</Formula>
                <p className="small">
                  With the 2024 mean q of{" "}
                  <span className="mono">
                    {rolling.decision_relevance.mean_national_relative_q.toFixed(3)}
                  </span>
                  , the bar is a ratio below{" "}
                  <span className="mono">
                    {rolling.decision_relevance.mean_threshold_ratio.toFixed(3)}
                  </span>
                  : the cleaner site must be about{" "}
                  {Math.round(
                    100 * (1 - rolling.decision_relevance.mean_threshold_ratio),
                  )}
                  % greener before uncertainty lets the scheduler commit.
                </p>
                <p className="small" style={{ marginBottom: 0 }}>
                  Across the year, the best-vs-runner-up ranking survives the band on{" "}
                  <b>
                    {rolling.decision_relevance.mean_band_robust_pct.toFixed(1)}%
                  </b>{" "}
                  of slots — that is the share of decisions a risk-aware rule may take
                  with confidence, and the rest are where a naive rule moves on noise.
                </p>
              </Card>
              <Card title="The four sites against their bands">
                <SiteBandFigure
                  regions={data.data!.regions}
                  q={rolling.decision_relevance.mean_national_relative_q}
                />
                <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
                  Bars are the calibrated 90% band. South Scotland&apos;s band does
                  not reach South Wales&apos; point estimate in any month, so that
                  move is always safe; the middle pair overlap and are where the
                  band earns its keep.
                </p>
              </Card>
            </div>

            <div className="table-wrap" style={{ marginTop: 14 }}>
              <table>
                <thead>
                  <tr>
                    <th>Month</th>
                    <th className="num">Calibration start</th>
                    <th className="num">q</th>
                    <th className="num">National coverage</th>
                    <th className="num">Threshold ratio</th>
                    <th className="num">Band-robust slots</th>
                    <th className="num">Median best/2nd</th>
                  </tr>
                </thead>
                <tbody>
                  {rolling.by_month.map((row) => (
                    <tr key={row.month}>
                      <td className="mono">
                        {new Date(Date.UTC(2024, row.month - 1, 1)).toLocaleString("en-GB", {
                          month: "short",
                          timeZone: "UTC",
                        })}
                      </td>
                      <td className="num tiny muted">
                        {row.calibration_start_utc.slice(0, 10)}
                      </td>
                      <td className="num">{row.national_relative_q.toFixed(3)}</td>
                      <td
                        className={`num ${row.national_coverage >= target ? "good" : "warn"}`}
                      >
                        {pct(row.national_coverage)}
                      </td>
                      <td className="num">{row.threshold_ratio.toFixed(3)}</td>
                      <td className="num">{row.band_robust_pct?.toFixed(1) ?? "—"}%</td>
                      <td className="num">
                        {row.median_best_to_second_ratio?.toFixed(3) ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section
            title="Why one band shape does not fit"
            sub="The residual is not proportional to the level, which is what decides whether a relative band is even the right object."
          >
            <div className="grid g2">
              <Card title="Measured error by intensity regime (2024)">
                <table>
                  <thead>
                    <tr>
                      <th>Forecast (g/kWh)</th>
                      <th className="num">Slots</th>
                      <th className="num">Mean |error|</th>
                      <th className="num">p90 |error|</th>
                      <th className="num">Mean |error| / forecast</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rolling.residual_structure.by_bucket.map((bucket) => (
                      <tr key={bucket.lo}>
                        <td className="mono tiny">
                          {bucket.lo.toFixed(0)}–{bucket.hi === null ? "∞" : bucket.hi.toFixed(0)}
                        </td>
                        <td className="num">{num(bucket.n)}</td>
                        <td className="num">{bucket.mean_abs_error.toFixed(2)}</td>
                        <td className="num">{bucket.q90_abs_error.toFixed(2)}</td>
                        <td className="num">{(100 * bucket.mean_relative_error).toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
              <Card title="A timestamp diagnostic we report but do not use">
                <p className="small">
                  Pairing forecast to actual in the same slot is the documented
                  convention, and every number on this page uses it. Shifting the
                  pairing improves the fit — to a minimum at{" "}
                  <span className="mono">
                    {rolling.residual_structure.alignment.best_shift_slots ?? "—"} slots
                  </span>{" "}
                  — which means part of the measured error could be a reporting
                  convention rather than forecast skill.
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Shift (slots)</th>
                      {Object.keys(rolling.residual_structure.alignment.by_shift_slots).map(
                        (shift) => (
                          <th key={shift} className="num">
                            {shift}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>MAE (g/kWh)</td>
                      {Object.values(
                        rolling.residual_structure.alignment.by_shift_slots,
                      ).map((value, index) => (
                        <td key={index} className="num">
                          {value.toFixed(2)}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
                <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
                  The optimum is not stable across windows (−2 slots on 2024, −1 on
                  February 2025), so applying it would be fitting the artefact. It is
                  reported as a limitation, not corrected.
                </p>
              </Card>
            </div>
          </Section>

          <Section
            title="Integrity of the join"
            sub="Coverage is only as good as the number of slots that actually paired. This block makes a silent join failure visible."
          >
            <div className="grid g4">
              <Stat
                label="Minimum paired"
                value={`${rolling.pairing.min_paired_pct?.toFixed(2) ?? "—"}%`}
                note="regional slot ↔ national actual"
                tone="good"
              />
              <Stat
                label="Duplicate slots dropped"
                value={num(
                  (rolling.pairing.duplicate_slots_dropped?.national ?? 0) +
                    (rolling.pairing.duplicate_slots_dropped?.regional ?? 0),
                )}
                note="weekly window boundaries"
              />
              <Stat
                label="Zero-forecast slots"
                value={`${rolling.relative.zero_forecast_slot_pct?.toFixed(1) ?? "—"}%`}
                note="excluded from the headline figure"
                tone="warn"
              />
              <Stat
                label="Cov. standard error"
                value={rolling.relative.coverage_stderr?.toFixed(4) ?? "—"}
                note="not noise at this sample size"
                tone="good"
              />
            </div>
          </Section>
        </>
      ) : (
        <ErrorPanel message="exp010 has no run record yet — run `make exp-run EXP=exp010-rolling-bands`." />
      )}
    </>
  );
}
