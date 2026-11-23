import Link from "next/link";
import { apiGet } from "@/lib/api";
import type {
  ExperimentsResponse,
  Meta,
  SimulatorResponse,
  UncertaintyResponse,
} from "@/lib/types";
import { Card, Chip, ErrorPanel, Stat, num, pct, signed } from "@/components/ui";

// The evidence is read live from the Python service, so never prerender it
export const dynamic = "force-dynamic";


export default async function OverviewPage() {
  const [meta, experiments, simulator, uncertainty] = await Promise.all([
    apiGet<Meta>("/api/meta"),
    apiGet<ExperimentsResponse>("/api/experiments"),
    apiGet<SimulatorResponse>("/api/simulator"),
    apiGet<UncertaintyResponse>("/api/uncertainty"),
  ]);

  const error = meta.error ?? experiments.error ?? simulator.error ?? uncertainty.error;
  if (error) return <ErrorPanel message={error} />;

  const project = meta.data!.project;
  const counts = meta.data!.counts;
  const claim = meta.data!.claim;

  const uk = simulator.data!.uk;
  const bestUk = uk?.controllers[0] ?? null;
  const bestRule = simulator.data!.control?.best_rule_kg ?? null;
  const rolling = uncertainty.data!.rolling;
  const relative = rolling?.relative ?? null;

  return (
    <>
      <div className="topbar">
        <span>Progress review</span>
        <span className="spacer" />
        <span className="stamp">generated {project.generated_at}</span>
      </div>

      <h1 className="page-title">{project.title}</h1>
      <p className="page-lede">{project.subtitle}</p>

      <Card title="Start here: one decision, explained">
        <p className="fine" style={{ marginTop: 0 }}>
          The scheduler page replays a held-out week through the planner the project ships and answers three
          questions for a single queued item: what is waiting, where and when it was placed, and why the other
          three sites lost. Every sentence in it is generated from the planner&apos;s own ledger.
        </p>
        <p>
          <Link href="/scheduler">Open the scheduler dashboard →</Link>
        </p>
      </Card>

      <div className="legend" style={{ marginBottom: 22 }}>
        {meta.data!.legend.map((entry) => (
          <span key={entry.key} className="chip" data-tone={entry.tone}>
            {entry.label}
          </span>
        ))}
      </div>

      <div className="grid g4">
        <Stat
          label="Phases complete"
          value={project.phase}
          note="infra · data freeze · simulator"
          tone="good"
        />
        <Stat
          label="Experiments"
          value={num(counts.experiments)}
          note={`${counts.runs} immutable run record${counts.runs === 1 ? "" : "s"}`}
        />
        <Stat
          label="Carbon vs round-robin"
          value={bestUk ? `${signed(bestUk.carbon_vs_round_robin_pct)}%` : "—"}
          note="UK grid, identical demand, 7 days"
          tone="good"
        />
        <Stat
          label="Band coverage (2024)"
          value={relative ? pct(relative.mean_coverage_positive_forecast) : "—"}
          note="rolling-origin, target 90%"
          tone={
            relative && relative.mean_coverage_positive_forecast >= 0.9 ? "good" : "warn"
          }
        />
      </div>

      <h2 className="section-title">The claim</h2>
      <p className="section-sub">
        Verified against a 30-paper survey (2024–2026, every DOI checked) that the
        pieces exist separately and the combination does not.
      </p>
      <div className="grid g2">
        <Card title="What the paper claims">
          <p>{claim.body}</p>
          <ul className="tight">
            {claim.rules.map((rule) => (
              <li key={rule} className="small">
                {rule}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Why this is hard to dismiss">
          <ul className="tight">
            <li>
              <b>The problem is real:</b> no public workload trace names the grid
              region its machine sat in, so “carbon-aware” results rest on an
              unverifiable mapping. We use a region-matched UK series and disclose
              the mapping.
            </li>
            <li>
              <b>The uncertainty is measured:</b> conformal bands calibrated only
              on data the evaluation cannot see, not a noise term assumed into a
              simulator.
            </li>
            <li>
              <b>The simulator is not ours:</b> SustainCluster (HPE Labs, MIT) runs
              unpatched, so the baseline is a real control rather than our own
              straw man.
            </li>
            <li>
              <b>Everything is re-runnable:</b> each number links to a run record
              with a git SHA, config hash and data hashes.
            </li>
          </ul>
        </Card>
      </div>

      <h2 className="section-title">Where the evidence sits</h2>
      <p className="section-sub">
        Four pages, four claims — each with the number it stands on and the label
        that says how far it can be trusted.
      </p>
      <div className="grid g2">
        <Card title="Data">
          <p className="small">
            NESO half-hourly carbon for 14 DNO regions, a 16.8M-request Azure LLM
            trace, the Alibaba GPU trace inside the simulator, and a real GB
            wholesale price. Four disclosed gaps, none hidden.
          </p>
          <div className="legend" style={{ marginTop: 10 }}>
            <Chip status="verified" />
            <Chip status="assumption" />
          </div>
          <p className="small" style={{ marginTop: 10, marginBottom: 0 }}>
            <Link href="/data">Open the data page →</Link>
          </p>
        </Card>

        <Card title="Uncertainty">
          <p className="small">
            Split-conformal bands on regional carbon. The single Jan→Feb split hit{" "}
            {pct(uncertainty.data!.single_split.national?.holdout_coverage ?? null)}{" "}
            on held-out data; the 2024 walk-forward design reaches{" "}
            {relative ? pct(relative.mean_coverage_positive_forecast) : "—"} across{" "}
            {rolling ? num(rolling.n_cells) : "—"} region-months — and shows how
            often the band actually settles a routing decision.
          </p>
          <div className="legend" style={{ marginTop: 10 }}>
            <Chip status="verified" />
          </div>
          <p className="small" style={{ marginTop: 10, marginBottom: 0 }}>
            <Link href="/uncertainty">Open the uncertainty page →</Link>
          </p>
        </Card>

        <Card title="Simulator">
          <p className="small">
            Five rule controllers and four shipped SAC checkpoints on 4 data
            centres. Best rule emits {num(bestRule)} kg CO₂; the UK substitution
            emits {bestUk ? num(bestUk.carbon_kg) : "—"} kg and passes an exit test
            that the simulator really read our grid series over the window it read.
          </p>
          <div className="legend" style={{ marginTop: 10 }}>
            <Chip status="verified" />
          </div>
          <p className="small" style={{ marginTop: 10, marginBottom: 0 }}>
            <Link href="/simulator">Open the simulator page →</Link>
          </p>
        </Card>

        <Card title="Policies">
          <p className="small">
            A seven-rung ladder from round-robin to MAPPO with CVaR. Rungs 1–3 are
            the measured baselines; rung 4 isolates the value of uncertainty before
            any RL is trained; rungs 5–7 are the contribution and are marked
            <i> next</i>, not done.
          </p>
          <div className="legend" style={{ marginTop: 10 }}>
            <Chip status="verified" />
            <Chip status="next" />
          </div>
          <p className="small" style={{ marginTop: 10, marginBottom: 0 }}>
            <Link href="/policies">Open the policy ladder →</Link>
          </p>
        </Card>
      </div>

      <h2 className="section-title">How to read any number on this site</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 150 }}>Label</th>
              <th>Means</th>
              <th>Example on this site</th>
            </tr>
          </thead>
          <tbody>
            {meta.data!.legend.map((entry) => (
              <tr key={entry.key}>
                <td>
                  <span className="chip" data-tone={entry.tone}>
                    {entry.label}
                  </span>
                </td>
                <td>{entry.meaning}</td>
                <td className="small muted">
                  {entry.key === "verified" && "NESO forecast-vs-actual pairs; exp008–exp010 run records"}
                  {entry.key === "inspected" && "NLR GPU power profiles read by hand"}
                  {entry.key === "modelled" && "anything the simulator produces"}
                  {entry.key === "assumption" && "regional actuals; the four-site region mapping"}
                  {entry.key === "next" && "the MARL agents"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
