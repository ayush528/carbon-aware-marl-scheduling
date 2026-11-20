import { apiGet } from "@/lib/api";
import type { DataResponse } from "@/lib/types";
import {

  Callout,
  Card,
  Chip,
  ErrorPanel,
  Section,
  Stat,
  num,
} from "@/components/ui";

// The evidence is read live from the Python service, so never prerender it
export const dynamic = "force-dynamic";

export default async function DataPage() {
  const { data, error } = await apiGet<DataResponse>("/api/data");
  if (error) return <ErrorPanel message={error} />;

  const sources = data!.sources;
  const gaps = data!.gaps;
  const regions = data!.regions;
  const spread = data!.spread_gco2_per_kwh;
  const demand = data!.demand;
  const energy = data!.energy;

  const maxIntensity = Math.max(...regions.map((row) => row.input_mean_gco2_per_kwh), 1);

  return (
    <>
      <div className="topbar">
        <span>Data</span>
        <span className="spacer" />
        <span className="stamp">region-matched · re-fetchable · hashed</span>
      </div>

      <h1 className="page-title">Data that makes the claim checkable</h1>
      <p className="page-lede">
        Public workload traces never say which grid region their machines sat in.
        So the first job is not a scheduler — it is a region-matched series with a
        stated provenance and a stated set of gaps. Everything below is either a
        real feed or is labelled as an estimate.
      </p>

      <div className="grid g4">
        <Stat label="Grid regions" value="14" note="NESO DNO regions, 30-min slots" />
        <Stat
          label="LLM requests"
          value={demand ? num(demand.n_requests) : "—"}
          note="Azure production trace, 1 week"
        />
        <Stat
          label="Regional spread"
          value={spread ? `${Math.round(spread)} g` : "—"}
          note="CO₂/kWh across the 4 sites"
          tone="info"
        />
        <Stat
          label="AWS regions in GB"
          value="1"
          note="so transmission cost is 0 — disclosed"
          tone="warn"
        />
      </div>

      <Section
        title="Sources"
        sub="Six inputs. Five are real feeds; the sixth is the mapping that connects them and is declared, not derived."
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>What it gives</th>
                <th>Granularity</th>
                <th>Role here</th>
                <th>Evidence</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.name}>
                  <td>
                    <b>{source.name}</b>
                  </td>
                  <td>{source.what}</td>
                  <td className="mono tiny">{source.granularity}</td>
                  <td>{source.role}</td>
                  <td className="mono tiny muted">{source.evidence}</td>
                  <td>
                    <Chip status={source.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        title="The four UK sites"
        sub="Mean carbon intensity over the simulated window, and the intensity implied by the simulator's own energy accounting for the same window. The two must agree — that agreement is what makes the run a test of our series rather than of our intentions."
      >
        <div className="card">
          {regions.length === 0 ? (
            <p className="muted small">No UK run record found.</p>
          ) : (
            <>
              {regions.map((site) => (
                <div className="bar-row" key={site.site}>
                  <span>
                    {site.site.replace("GB-", "")}{" "}
                    <span className="tiny muted mono">NESO {site.neso_region_id}</span>
                  </span>
                  <span className="bar-track">
                    <span
                      className="bar-fill"
                      style={{
                        width: `${(100 * site.input_mean_gco2_per_kwh) / maxIntensity}%`,
                        background:
                          site.input_mean_gco2_per_kwh > 250
                            ? "var(--bad)"
                            : site.input_mean_gco2_per_kwh < 100
                              ? "var(--good)"
                              : "var(--info)",
                      }}
                    />
                  </span>
                  <span className="value">
                    {site.input_mean_gco2_per_kwh.toFixed(1)}
                  </span>
                </div>
              ))}

              <div className="table-wrap" style={{ marginTop: 16 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Site</th>
                      <th className="num">Input mean (g/kWh)</th>
                      <th className="num">Simulator implied</th>
                      <th className="num">Difference</th>
                      <th>Within tolerance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {regions.map((site) => {
                      const diff =
                        site.simulated_gco2_per_kwh - site.input_mean_gco2_per_kwh;
                      return (
                        <tr key={site.site}>
                          <td className="mono tiny">{site.site}</td>
                          <td className="num">{site.input_mean_gco2_per_kwh.toFixed(2)}</td>
                          <td className="num">{site.simulated_gco2_per_kwh.toFixed(2)}</td>
                          <td className={`num ${Math.abs(diff) < 1 ? "good" : "bad"}`}>
                            {diff > 0 ? "+" : ""}
                            {diff.toFixed(2)}
                          </td>
                          <td>
                            <Chip
                              status={site.within_tolerance ? "verified" : "next"}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
                A spread of {spread ? spread.toFixed(0) : "—"} gCO₂/kWh between South
                Scotland and South Wales is the room a scheduler has to work with.
                It is also why a scheduler that merely chases the forecast gets a
                real win — and why beating it is the actual bar.
              </p>
            </>
          )}
        </div>
      </Section>

      <Section
        title="Demand and energy envelope"
        sub="The workload side, measured on the real trace before any scheduling decision is made."
      >
        <div className="grid g2">
          <Card title="Azure LLM inference demand">
            {demand ? (
              <dl className="kv">
                <dt>Requests</dt>
                <dd className="mono">{num(demand.n_requests)}</dd>
                <dt>Slots</dt>
                <dd className="mono">{num(demand.n_slots)} × 30 min</dd>
                <dt>Mean per slot</dt>
                <dd className="mono">{num(demand.mean_requests_per_slot)}</dd>
                <dt>Peak slot</dt>
                <dd className="mono">{num(demand.peak_requests_per_slot)}</dd>
                <dt>Status</dt>
                <dd>
                  <Chip status="verified" />
                </dd>
              </dl>
            ) : (
              <p className="muted small">No exp006 record.</p>
            )}
          </Card>
          <Card title="Cluster energy envelope (exp007)">
            {energy ? (
              <dl className="kv">
                <dt>Mean utilisation</dt>
                <dd className="mono">{energy.mean_utilization.toFixed(3)}</dd>
                <dt>Saturated slots</dt>
                <dd className="mono">
                  {energy.n_saturated_slots} / {energy.n_slots}
                </dd>
                <dt>Energy per request</dt>
                <dd className="mono">{energy.wh_per_request.toFixed(3)} Wh</dd>
                <dt>Status</dt>
                <dd>
                  <Chip status="inspected" />
                </dd>
              </dl>
            ) : (
              <p className="muted small">No exp007 record.</p>
            )}
          </Card>
        </div>
      </Section>

      <Section
        title="What the data does not give us"
        sub="Each of these is handled explicitly; none is left to the reader to discover."
      >
        <div className="grid g2">
          {gaps.map((gap) => (
            <Card key={gap.title} title={gap.title}>
              <p className="small">{gap.detail}</p>
              <Chip status={gap.status} />
            </Card>
          ))}
        </div>

        <div style={{ marginTop: 14 }}>
          <Callout tone="info">
            <b>The mapping is the assumption.</b> Two of the four sites are
            unambiguous (London → NESO 13, South Scotland → NESO 2). South Wales
            (NESO 7) and North West England (NESO 3) sit inside multi-region
            distribution areas, so the choice is a modelling decision, stated in
            the abstract rather than a footnote. No traced request is claimed to
            have been served in the UK.
          </Callout>
        </div>
      </Section>
    </>
  );
}
