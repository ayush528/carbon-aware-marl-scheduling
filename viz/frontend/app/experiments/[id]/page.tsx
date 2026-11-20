import Link from "next/link";
import { notFound } from "next/navigation";
import { apiGet } from "@/lib/api";
import type { ExperimentDetail } from "@/lib/types";
import { Card, Chip, ErrorPanel, Section, num } from "@/components/ui";

// The evidence is read live from the Python service, so never prerender it
export const dynamic = "force-dynamic";


export default async function ExperimentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { data, error } = await apiGet<ExperimentDetail>(`/api/experiments/${id}`);
  if (error) {
    if (error.includes("404")) notFound();
    return <ErrorPanel message={error} />;
  }

  const registry = data!.registry;
  const config = data!.config;
  const run = data!.run;
  const history = data!.runs;

  return (
    <>
      <div className="topbar">
        <span>
          <Link href="/experiments">Experiments</Link> / {registry.id}
        </span>
        <span className="spacer" />
        <span className="stamp">{registry.rollback_tag ?? "untagged"}</span>
      </div>

      <h1 className="page-title">{registry.title}</h1>
      <p className="page-lede">{registry.description}</p>

      <div className="legend" style={{ marginBottom: 20 }}>
        <Chip status={registry.status === "merged" ? "verified" : "next"} />
        <span className="chip">{registry.phase}</span>
        <span className="chip">{history.length} run{history.length === 1 ? "" : "s"}</span>
      </div>

      {run ? (
        <>
          <Section
            title="Newest run record"
            sub="The manifest is what makes the numbers citable: it pins the code, the config and every data file the run read."
          >
            <div className="grid g2">
              <Card title="Manifest">
                <table>
                  <tbody>
                    <tr>
                      <td className="muted small">Timestamp (UTC)</td>
                      <td className="mono tiny">{run.manifest.timestamp}</td>
                    </tr>
                    <tr>
                      <td className="muted small">Git SHA</td>
                      <td className="mono tiny">{run.manifest.git_sha}</td>
                    </tr>
                    <tr>
                      <td className="muted small">Tree state</td>
                      <td className="mono tiny">
                        {run.manifest.git_dirty ? (
                          <span className="warn">dirty — not guaranteed reproducible</span>
                        ) : (
                          <span className="good">clean</span>
                        )}
                      </td>
                    </tr>
                    <tr>
                      <td className="muted small">Config SHA-256</td>
                      <td className="mono tiny" style={{ wordBreak: "break-all" }}>
                        {run.manifest.config_hash}
                      </td>
                    </tr>
                    <tr>
                      <td className="muted small">Seed</td>
                      <td className="mono tiny">{run.manifest.seed}</td>
                    </tr>
                    <tr>
                      <td className="muted small">Python / platform</td>
                      <td className="mono tiny">
                        {run.manifest.python ?? "—"} · {run.manifest.platform ?? "—"}
                      </td>
                    </tr>
                    <tr>
                      <td className="muted small">Record directory</td>
                      <td className="mono tiny">{run.run_dir}</td>
                    </tr>
                  </tbody>
                </table>
              </Card>

              <Card title="Data files hashed into this run">
                {run.manifest.data_hashes &&
                Object.keys(run.manifest.data_hashes).length > 0 ? (
                  <table>
                    <tbody>
                      {Object.entries(run.manifest.data_hashes).map(([name, hash]) => (
                        <tr key={name}>
                          <td className="mono tiny">{name}</td>
                          <td
                            className="mono tiny muted"
                            style={{ wordBreak: "break-all" }}
                          >
                            {hash.slice(0, 32)}…
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="muted small">This run lists no data files.</p>
                )}
                <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
                  Re-running the same config on a clean tree at the recorded SHA must
                  reproduce the config hash and the metrics below. That match is the
                  proof of reproducibility.
                </p>
              </Card>
            </div>
          </Section>

          <Section
            title="Metrics"
            sub="Exactly what the experiment function returned. Raw, because a curated view would be a place to hide a bad number."
          >
            <Card>
              <details>
                <summary className="small muted" style={{ cursor: "pointer" }}>
                  Show the full metrics document
                </summary>
                <pre
                  className="mono tiny"
                  style={{
                    marginTop: 12,
                    maxHeight: 620,
                    overflow: "auto",
                    background: "#0b1117",
                    border: "1px solid var(--line)",
                    borderRadius: 8,
                    padding: 12,
                  }}
                >
                  {JSON.stringify(run.metrics, null, 2)}
                </pre>
              </details>
            </Card>
          </Section>
        </>
      ) : (
        <ErrorPanel message="This experiment is registered but has not been run, so there are no metrics to show." />
      )}

      <Section
        title="Config"
        sub="Committed before the run, never edited afterwards. A changed hypothesis becomes a new experiment id."
      >
        <Card>
          {config ? (
            <pre
              className="mono tiny"
              style={{
                margin: 0,
                maxHeight: 520,
                overflow: "auto",
                background: "#0b1117",
                border: "1px solid var(--line)",
                borderRadius: 8,
                padding: 12,
              }}
            >
              {JSON.stringify(config, null, 2)}
            </pre>
          ) : (
            <p className="muted small">No config file on disk for this experiment.</p>
          )}
        </Card>
      </Section>

      {history.length > 1 ? (
        <Section title="Run history" sub="Newest last. Each entry is an immutable record.">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Record</th>
                  <th>Timestamp</th>
                  <th>Git SHA</th>
                  <th>Tree</th>
                </tr>
              </thead>
              <tbody>
                {history.map((entry) => (
                  <tr key={entry.run_dir}>
                    <td className="mono tiny">{entry.run_dir}</td>
                    <td className="mono tiny">{entry.timestamp}</td>
                    <td className="mono tiny">{entry.git_sha?.slice(0, 7)}</td>
                    <td className="tiny">{entry.git_dirty ? "dirty" : "clean"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      ) : null}

      <p className="small muted" style={{ marginTop: 24 }}>
        {num(history.length)} record{history.length === 1 ? "" : "s"} on disk. Roll
        back to this experiment with{" "}
        <span className="mono">
          make rollback EXP={registry.id}
        </span>{" "}
        — it checks the tag out in an isolated worktree and never touches the current
        tree.
      </p>
    </>
  );
}
