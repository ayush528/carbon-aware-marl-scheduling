import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { RoadmapResponse } from "@/lib/types";
import { Callout, Card, Chip, ErrorPanel, Formula, Section } from "@/components/ui";

// The evidence is read live from the Python service, so never prerender it
export const dynamic = "force-dynamic";


export default async function RoadmapPage() {
  const { data, error } = await apiGet<RoadmapResponse>("/api/roadmap");
  if (error) return <ErrorPanel message={error} />;

  const phases = data!.phases;
  const limits = data!.limits;
  const next = data!.next;
  const claim = data!.claim;

  return (
    <>
      <div className="topbar">
        <span>Roadmap</span>
        <span className="spacer" />
        <span className="stamp">phases · limits · what happens next</span>
      </div>

      <h1 className="page-title">Where this goes, and what could sink it</h1>
      <p className="page-lede">
        The plan is ordered so every step produces the evidence the next one needs.
        The limits are listed with the same prominence as the results, because a
        reviewer will find them anyway and finding them first is cheaper.
      </p>

      <Section title="Phases" sub="Each phase has an exit test; a phase is done when the test passes, not when the code runs.">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 60 }}>Phase</th>
                <th>Name</th>
                <th>Work</th>
                <th>Exit test</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {phases.map((phase) => (
                <tr key={phase.phase} data-highlight={phase.state === "done"}>
                  <td className="mono muted">{phase.phase}</td>
                  <td>
                    <b>{phase.name}</b>
                  </td>
                  <td className="small">{phase.work}</td>
                  <td className="small muted">{phase.exit_test}</td>
                  <td>
                    <Chip status={phase.state === "done" ? "verified" : "next"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        title="The reproducibility contract"
        sub="Stated as a contract because that is what makes a claim checkable by someone who was not in the room."
      >
        <div className="grid g2">
          <Card title="One experiment, one config">
            <Formula>experiments/&lt;id&gt;/config.yaml</Formula>
            <ul className="tight small">
              <li>Committed before the run, never edited afterwards.</li>
              <li>A changed hypothesis gets a new id; it does not overwrite history.</li>
              <li>
                Every data file the run reads is listed in the config and hashed
                into the manifest.
              </li>
            </ul>
          </Card>
          <Card title="One run, one immutable record">
            <Formula>
              runs/&lt;UTC-stamp&gt;-&lt;hash&gt;/manifest.json + metrics.json
            </Formula>
            <ul className="tight small">
              <li>Git SHA, config SHA-256, data SHA-256s, seed, timestamp, metrics.</li>
              <li>
                A run on a dirty tree is recorded as dirty — it is not silently
                presented as reproducible.
              </li>
              <li>Records are committed: they are the evidence, not build output.</li>
            </ul>
          </Card>
          <Card title="One merged experiment, one tag">
            <Formula>exp/&lt;id&gt; ← the rollback point</Formula>
            <ul className="tight small">
              <li>Tagged when config and results merge to main.</li>
              <li>
                <span className="mono">make rollback EXP=…</span> checks it out in an
                isolated worktree; the working tree is never touched.
              </li>
              <li>Re-running there must reproduce the recorded hash and metrics.</li>
            </ul>
          </Card>
          <Card title="Why this matters for the claim">
            <p className="small">
              The contribution is a measurement setup, so the setup has to be
              auditable by a reader. Everything on this site traces back to a record
              like the ones on the{" "}
              <Link href="/experiments">experiments page</Link>, and each record names
              the exact code and data behind it.
            </p>
            <Chip status="verified" />
          </Card>
        </div>
      </Section>

      <Section title="What happens next" sub="Ordered by dependency: nothing later is claimed before the thing it rests on has passed.">
        <ol className="tight">
          {next.map((step) => (
            <li key={step.title}>
              <b>{step.title}.</b> <span className="muted">{step.detail}</span>
            </li>
          ))}
        </ol>
      </Section>

      <Section
        title="Limits that will be in the paper"
        sub="Quantified where possible. None of these is a footnote."
      >
        <div className="grid g2">
          {limits.map((limit) => (
            <Card key={limit.title} title={limit.title}>
              <p className="small" style={{ marginBottom: 0 }}>
                {limit.detail}
              </p>
            </Card>
          ))}
        </div>
      </Section>

      <Section title="The claim, restated precisely" sub="Because the imprecise version would be easy to dismiss.">
        <Card>
          <p>{claim.body}</p>
          <ul className="tight small">
            {claim.rules.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
        </Card>
        <div style={{ marginTop: 14 }}>
          <Callout tone="good">
            <b>The one-line version.</b> Every design decision here protects a single
            property: the uncertainty is measured, never assumed. A band is
            calibrated only on data the evaluation cannot see; a simulator result is
            accepted only if the simulator&apos;s own accounting reproduces the input
            series; a gap is estimated with a stated identity or declared missing.
            Anything that would quietly strengthen a number is rejected.
          </Callout>
        </div>
      </Section>
    </>
  );
}
