import Link from "next/link";
import { apiGet } from "@/lib/api";
import type { ExperimentsResponse } from "@/lib/types";
import { Chip, ErrorPanel, Stat, num } from "@/components/ui";

// The evidence is read live from the Python service, so never prerender it
export const dynamic = "force-dynamic";


export default async function ExperimentsPage() {
  const { data, error } = await apiGet<ExperimentsResponse>("/api/experiments");
  if (error) return <ErrorPanel message={error} />;

  const experiments = data!.experiments;
  const withRuns = experiments.filter((row) => row.run).length;
  const dirty = experiments.filter((row) => row.run?.git_dirty).length;

  return (
    <>
      <div className="topbar">
        <span>Experiments</span>
        <span className="spacer" />
        <span className="stamp">registry · configs · run records</span>
      </div>

      <h1 className="page-title">The evidence trail</h1>
      <p className="page-lede">
        One experiment is one committed config. Every run appends an immutable
        record: git SHA, config hash, data-file hashes, seed, timestamp, metrics. A
        number in the paper is a pointer into this list, and the tag on each merged
        experiment is the rollback point.
      </p>

      <div className="grid g4" style={{ marginBottom: 22 }}>
        <Stat label="Registered" value={num(experiments.length)} note="experiments in the registry" />
        <Stat label="With run records" value={num(withRuns)} tone="good" note="metrics committed" />
        <Stat
          label="Dirty-tree runs"
          value={num(dirty)}
          tone={dirty === 0 ? "good" : "warn"}
          note={dirty === 0 ? "every record is reproducible" : "record says the tree was dirty"}
        />
        <Stat
          label="Rollback"
          value="1 command"
          note="make rollback EXP=… in an isolated worktree"
        />
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Experiment</th>
              <th>Phase</th>
              <th>Newest run</th>
              <th>Headline</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {experiments.map((row) => (
              <tr key={row.id}>
                <td>
                  <Link href={`/experiments/${row.id}`}>
                    <b className="mono tiny">{row.id}</b>
                  </Link>
                  <div className="small muted" style={{ marginTop: 3, maxWidth: "46ch" }}>
                    {row.title}
                  </div>
                </td>
                <td className="tiny muted nowrap">{row.phase}</td>
                <td className="tiny mono muted">
                  {row.run ? (
                    <>
                      {row.run.timestamp?.slice(0, 16).replace("T", " ")}
                      <div style={{ marginTop: 2 }}>
                        {row.run.git_sha?.slice(0, 7)}
                        {row.run.git_dirty ? (
                          <span className="warn"> dirty</span>
                        ) : (
                          <span className="good"> clean</span>
                        )}
                      </div>
                    </>
                  ) : (
                    <span>not run</span>
                  )}
                </td>
                <td>
                  <div className="legend">
                    {row.summary.length === 0 ? (
                      <span className="small muted">no metrics</span>
                    ) : (
                      row.summary.map((item) => (
                        <span key={item.label} className="small nowrap">
                          <span className="muted tiny">{item.label} </span>
                          <b
                            className={
                              item.tone === "good"
                                ? "good mono"
                                : item.tone === "bad"
                                  ? "bad mono"
                                  : item.tone === "warn"
                                    ? "warn mono"
                                    : "mono"
                            }
                          >
                            {item.value}
                          </b>
                        </span>
                      ))
                    )}
                  </div>
                </td>
                <td>
                  <Chip
                    status={
                      row.status === "merged"
                        ? "verified"
                        : row.status === "superseded"
                          ? "inspected"
                          : "next"
                    }
                  />
                  <div className="tiny muted" style={{ marginTop: 3 }}>
                    {row.rollback_tag ?? "untagged"}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="small muted" style={{ marginTop: 14 }}>
        A registered experiment without a run record shows &ldquo;no metrics&rdquo;
        rather than a placeholder. The API deliberately returns null there: an
        absent number and a zero must never look the same.
      </p>
    </>
  );
}
