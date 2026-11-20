import { apiGet } from "@/lib/api";
import type { PoliciesResponse } from "@/lib/types";
import { Callout, Card, Chip, ErrorPanel, Formula, Section } from "@/components/ui";

// The evidence is read live from the Python service, so never prerender it
export const dynamic = "force-dynamic";


export default async function PoliciesPage() {
  const { data, error } = await apiGet<PoliciesResponse>("/api/policies");
  if (error) return <ErrorPanel message={error} />;

  const ladder = data!.ladder;
  const agent = data!.agent;

  return (
    <>
      <div className="topbar">
        <span>Policies</span>
        <span className="spacer" />
        <span className="stamp">rungs 1–3 measured · rungs 4–7 planned</span>
      </div>

      <h1 className="page-title">From rules to decentralised MARL</h1>
      <p className="page-lede">
        Each rung must beat or match the one below it under identical demand,
        otherwise the added machinery is not justified. The ladder is ordered so
        that every claim has a control immediately beneath it.
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 40 }}>#</th>
              <th>Policy</th>
              <th>What it uses</th>
              <th>Why it is here</th>
              <th>Evidence</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {ladder.map((rung) => (
              <tr key={rung.rung}>
                <td className="mono muted">{rung.rung}</td>
                <td>
                  <b>{rung.name}</b>
                </td>
                <td>{rung.uses}</td>
                <td>{rung.purpose}</td>
                <td className="mono tiny muted">{rung.evidence || "—"}</td>
                <td>
                  <Chip status={rung.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid g3" style={{ marginTop: 16 }}>
        <Card title="Rung 4 is the key ablation">
          <p className="small">
            Same rule, with and without the conformal band. If uncertainty adds
            nothing, this row says so — before any RL is trained, and at a fraction
            of the compute.
          </p>
        </Card>
        <Card title="Rung 5 vs 6 prices decentralisation">
          <p className="small">
            Centralised PPO sees the whole plant; IPPO sees its own observation plus
            one scalar per neighbour. The gap between them is the cost of
            decentralisation, measured rather than asserted.
          </p>
        </Card>
        <Card title="Rung 7 is the claim">
          <p className="small">
            Risk-aware objective, limited communication, calibrated bands on real
            region-matched UK carbon. That combination is the novel part; none of the
            four pieces is new alone.
          </p>
        </Card>
      </div>

      <Section
        title="What an agent sees, does, and is paid for"
        sub="Fixed now so the rungs are comparable: only the policy changes between them, never the interface."
      >
        <div className="grid g3">
          <Card title="Observation (per site)">
            <ul className="tight small">
              {agent.observation.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Card>
          <Card title="Action">
            <ul className="tight small">
              {agent.action.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
              Discrete, per-site, executed locally. No central dispatcher at runtime.
            </p>
          </Card>
          <Card title="Objective">
            <Formula wrap>{agent.objective.formula}</Formula>
            <ul className="tight small">
              {agent.objective.terms.map((term) => (
                <li key={term.term}>
                  <span className="mono">{term.term}</span> — {term.meaning}
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div style={{ marginTop: 14 }}>
          <Callout tone="info">
            <b>Why CVaR and not a hard constraint.</b> {agent.cvar_note}
          </Callout>
        </div>
      </Section>

      <Section
        title="What the band changes about the observation"
        sub="The one design decision that separates this from carbon-greedy scheduling with a fancy learner."
      >
        <div className="grid g2">
          <Card title="Without the band">
            <p className="small">
              The agent sees a forecast and learns a mapping to actions. Where the
              forecast is wrong it learns the wrong mapping and cannot tell the
              difference between a genuine 20 gCO₂/kWh gap and a 20 gCO₂/kWh
              measurement artefact — the two look identical in its input.
            </p>
          </Card>
          <Card title="With the band" tone="good">
            <p className="small">
              The agent also sees how wide the interval is at that level and that
              hour. Two sites with the same point forecast but different bands are
              distinguishable, so the policy can prefer the site whose advantage is
              <i> certain</i> over the one that merely looks cheaper. The CVaR term
              charges the tail of the mistakes that follow from ignoring it.
            </p>
          </Card>
        </div>
        <p className="small muted" style={{ marginTop: 12 }}>
          {data!.note}
        </p>
      </Section>
    </>
  );
}
