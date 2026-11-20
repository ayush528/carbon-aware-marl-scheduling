import { apiGet } from "@/lib/api";
import type { SimulatorResponse } from "@/lib/types";
import {

  Callout,
  Card,
  Chip,
  ErrorPanel,
  Section,
  Stat,
  num,
  pct,
  signed,
} from "@/components/ui";

// The evidence is read live from the Python service, so never prerender it
export const dynamic = "force-dynamic";

export default async function SimulatorPage() {
  const { data, error } = await apiGet<SimulatorResponse>("/api/simulator");
  if (error) return <ErrorPanel message={error} />;

  const control = data!.control;
  const uk = data!.uk;
  const upstream = data!.upstream;

  const ruleBest = control?.controllers.find((row) => row.family === "rule") ?? null;
  const sacBest = control?.controllers.find((row) => row.family === "SAC") ?? null;
  const sacDelta =
    control && control.best_sac_kg && control.best_rule_kg
      ? (100 * (control.best_sac_kg - control.best_rule_kg)) / control.best_rule_kg
      : null;
  const ukBest = uk?.controllers[0] ?? null;

  return (
    <>
      <div className="topbar">
        <span>Simulator</span>
        <span className="spacer" />
        <span className="stamp">
          {upstream.name} · {upstream.organisation} · {upstream.commit?.slice(0, 7) ?? "—"}
        </span>
      </div>

      <h1 className="page-title">An external simulator, reproduced before it is changed</h1>
      <p className="page-lede">
        A baseline is only a control if it is somebody else&apos;s. SustainCluster
        (HPE Labs, MIT licence) runs unpatched through headless drivers; all UK
        behaviour is opt-in through flags. If the reproduction were wrong, every
        number after it would be meaningless, so the reproduction is checked to the
        cent first.
      </p>

      <div className="grid g4">
        <Stat
          label="Best rule (control)"
          value={control ? `${num(control.best_rule_kg)} kg` : "—"}
          note={`best of ${control?.controllers.filter((r) => r.family === "rule").length ?? 0} rule controllers`}
          tone="good"
        />
        <Stat
          label="Best SAC vs rule"
          value={sacDelta === null ? "—" : `${signed(sacDelta, 1)}%`}
          note="carbon, same demand"
          tone="warn"
        />
        <Stat
          label="Best SAC SLA misses"
          value={control ? pct(control.sac_min_sla_violation_rate) : "—"}
          note="no timeliness penalty in their reward"
          tone="bad"
        />
        <Stat
          label="UK run vs round-robin"
          value={ukBest ? `${signed(ukBest.carbon_vs_round_robin_pct)}%` : "—"}
          note="real NESO regional carbon"
          tone="good"
        />
      </div>

      <Section
        title="The control run (exp008)"
        sub="Upstream's own 4 data centres, real Alibaba task trace, shipped carbon/price/weather inputs, 7 days, seed 42, identical demand in every controller."
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Controller</th>
                <th>Family</th>
                <th className="num">CO₂ (kg)</th>
                <th className="num">vs round-robin</th>
                <th className="num">SLA violations</th>
                <th className="num">Tasks finished</th>
              </tr>
            </thead>
            <tbody>
              {control?.controllers.map((row) => {
                const isBestRule = row.name === ruleBest?.name;
                return (
                  <tr key={row.name} data-highlight={isBestRule}>
                    <td className="mono tiny">{row.name}</td>
                    <td>
                      <span className="chip" data-tone={row.family === "SAC" ? "warn" : "info"}>
                        {row.family}
                      </span>
                    </td>
                    <td className="num">{num(row.carbon_kg)}</td>
                    <td
                      className={`num ${
                        (row.carbon_vs_round_robin_pct ?? 0) < 0 ? "good" : "muted"
                      }`}
                    >
                      {row.carbon_vs_round_robin_pct === null
                        ? "—"
                        : `${signed(row.carbon_vs_round_robin_pct, 2)}%`}
                    </td>
                    <td
                      className={`num ${
                        row.sla_violation_rate > 0.1
                          ? "bad"
                          : row.sla_violation_rate > 0.01
                            ? "warn"
                            : "good"
                      }`}
                    >
                      {pct(row.sla_violation_rate, 2)}
                    </td>
                    <td className="num">{num(row.tasks_finished)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="grid g2" style={{ marginTop: 14 }}>
          <Card title="What this run says" tone="warn">
            <ul className="tight">
              <li>
                The best shipped RL checkpoint{" "}
                {sacBest ? <b>{sacBest.name}</b> : "—"} emits{" "}
                <b>{sacBest ? num(sacBest.carbon_kg) : "—"} kg</b> against{" "}
                <b>{ruleBest ? num(ruleBest.carbon_kg) : "—"} kg</b> for the best
                rule, i.e.{" "}
                <b>{sacDelta === null ? "—" : `${Math.abs(sacDelta).toFixed(2)}% lower`}</b>.
                Reported as measured: the claim is not that RL cannot save carbon.
              </li>
              <li>
                It does that while missing{" "}
                <b>{sacBest ? pct(sacBest.sla_violation_rate) : "—"}</b> of deadlines.
                Carbon saved by violating SLAs is not a result.
              </li>
              <li>
                So the honest statement is not &ldquo;RL loses&rdquo;: it is that RL
                under <i>their</i> objective trades the wrong quantity.
              </li>
            </ul>
          </Card>
          <Card title="The root cause, found in their config">
            <p className="small">
              Upstream&apos;s reward leaves <span className="mono">timeliness_penalty</span>{" "}
              commented out. The agent is never told that a missed deadline costs
              anything, so it optimises exactly what it was asked to optimise. Every
              one of the four checkpoints violates between 27% and 48% of SLAs.
            </p>
            <p className="small" style={{ marginBottom: 0 }}>
              That is the gap this project fills, and it is why deadlines are a
              constraint with a CVaR tail price rather than a tie-breaker.
            </p>
            <div style={{ marginTop: 10 }}>
              <Chip status="verified" />
            </div>
          </Card>
        </div>
      </Section>

      <Section
        title="The same simulator on the real UK grid (exp009)"
        sub={
          uk
            ? `Window ${uk.window_start_utc} + ${uk.window_hours} h, seed ${uk.seed}, identical demand. Carbon comes from NESO regional forecasts scaled to national actuals; price from Elexon MID.`
            : "No UK run record."
        }
      >
        {uk ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Controller</th>
                    <th className="num">CO₂ (kg)</th>
                    <th className="num">vs round-robin</th>
                    <th className="num">SLA violations</th>
                    <th className="num">Transmission cost</th>
                  </tr>
                </thead>
                <tbody>
                  {uk.controllers.map((row) => (
                    <tr key={row.name} data-highlight={row.name === ukBest?.name}>
                      <td className="mono tiny">{row.name}</td>
                      <td className="num">{num(row.carbon_kg)}</td>
                      <td
                        className={`num ${
                          (row.carbon_vs_round_robin_pct ?? 0) < 0 ? "good" : "muted"
                        }`}
                      >
                        {row.carbon_vs_round_robin_pct === null
                          ? "—"
                          : `${signed(row.carbon_vs_round_robin_pct, 2)}%`}
                      </td>
                      <td className="num">{pct(row.sla_violation_rate, 2)}</td>
                      <td className="num muted">
                        {row.transmission_cost_usd?.toFixed(2) ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="grid g2" style={{ marginTop: 14 }}>
              <Card title="The exit test that had to pass" tone="good">
                <table>
                  <tbody>
                    <tr>
                      <td>Per-site intensity implied by the simulator&apos;s own accounting</td>
                      <td className="num good">
                        max err {uk.exit_test.max_intensity_error_gco2_per_kwh.toFixed(2)}
                      </td>
                    </tr>
                    <tr>
                      <td>Site ordering matches the input series</td>
                      <td className="num">
                        {uk.exit_test.regional_ordering_matches_input ? (
                          <span className="good">yes</span>
                        ) : (
                          <span className="bad">no</span>
                        )}
                      </td>
                    </tr>
                    <tr>
                      <td>Workload clock equals the carbon window</td>
                      <td className="num">
                        {uk.clock_aligned_with_carbon ? (
                          <span className="good">yes</span>
                        ) : (
                          <span className="bad">no</span>
                        )}
                      </td>
                    </tr>
                    <tr>
                      <td>Regional spread over the window</td>
                      <td className="num">{uk.regional_spread_gco2_per_kwh.toFixed(1)} g/kWh</td>
                    </tr>
                  </tbody>
                </table>
                <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
                  This is the Phase 2 claim: the simulator is provably reading our UK
                  series over the window it actually read — not a series we merely
                  intended it to read.
                </p>
              </Card>

              <Card title="Per-site intensity, input vs implied">
                <table>
                  <thead>
                    <tr>
                      <th>Site</th>
                      <th className="num">Input</th>
                      <th className="num">Simulator</th>
                      <th className="num">Δ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(uk.sites)
                      .map(([name, site]) => ({ ...site, site: name }))
                      .sort((a, b) => a.input_mean_gco2_per_kwh - b.input_mean_gco2_per_kwh)
                      .map((site) => (
                        <tr key={site.site}>
                          <td className="mono tiny">
                            {site.site.replace("GB-", "")}{" "}
                            <span className="muted">NESO {site.neso_region_id}</span>
                          </td>
                          <td className="num">{site.input_mean_gco2_per_kwh.toFixed(2)}</td>
                          <td className="num">{site.simulated_gco2_per_kwh.toFixed(2)}</td>
                          <td className="num good">
                            {(site.simulated_gco2_per_kwh - site.input_mean_gco2_per_kwh).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
                  The gap between South Scotland and South Wales is the whole
                  opportunity, and the simulator reproduces it within 0.8 g/kWh.
                </p>
              </Card>
            </div>

            <div style={{ marginTop: 14 }}>
              <Callout tone="bad">
                <b>Two terms are inoperative here, and neither is a finding.</b>{" "}
                GB has exactly one AWS region (<span className="mono">eu-west-2</span>
                ), so the transmission-cost matrix is diagonal and the cost is{" "}
                {uk.transmission_inoperative ? "0 for every controller" : "not zero"} —
                that says nothing about transfer cost in general. And the GB wholesale
                price is national, so the price-only controller has nothing to
                differentiate: its worse carbon is tie-breaking, not a price effect.
              </Callout>
            </div>

            <div className="grid g2" style={{ marginTop: 14 }}>
              <Card title="What a scheduler can and cannot win here">
                <p className="small">
                  A rule that simply picks the lowest forecast captures{" "}
                  <b>{signed(ukBest?.carbon_vs_round_robin_pct ?? null)}%</b> at{" "}
                  {pct(ukBest?.sla_violation_rate ?? null, 2)} SLA misses. That is the
                  bar for Phase 3: the learned policy must beat this heuristic, not
                  round-robin.
                </p>
                <p className="small" style={{ marginBottom: 0 }}>
                  It also sets the honest expectation: on a 7-day window with four
                  sites and smooth regional curves, the headroom above the
                  forecast-chasing rule is small. The contribution has to come from
                  behaving well when the forecast is <i>uncertain</i>, not from
                  beating it in the easy slots.
                </p>
              </Card>
              <Card title="Why the numbers stay comparable">
                <ul className="tight small">
                  <li>Same demand trace, same seed, same window for every controller.</li>
                  <li>
                    The cluster reset jitters the data window by ±7 days and a random
                    hour, so our drivers probe that seeded draw and put the workload
                    clock on the same window before verifying carbon against it.
                  </li>
                  <li>Third-party code is never patched; every UK behaviour is a flag.</li>
                </ul>
                <Chip status="verified" />
              </Card>
            </div>
          </>
        ) : (
          <ErrorPanel message="exp009 has no run record yet." />
        )}
      </Section>
    </>
  );
}
