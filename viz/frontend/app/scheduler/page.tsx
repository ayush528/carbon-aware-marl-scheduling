import Link from "next/link";

import { ForecastGrid, Timeline, UkMap } from "@/components/SchedulerViews";
import { Callout, Card, Chip, ErrorPanel, Section, Stat } from "@/components/ui";
import { apiGet } from "@/lib/api";
import { fmt, type Replay, signPct, slotClock } from "@/lib/scheduler";
import "./scheduler.css";

export const dynamic = "force-dynamic";

type Params = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}

function query(params: Params, overrides: Record<string, string | number | undefined> = {}): string {
  const merged: Record<string, string> = {};
  for (const [key, value] of Object.entries(params)) {
    const single = one(value);
    if (single !== undefined && single !== "") merged[key] = single;
  }
  for (const [key, value] of Object.entries(overrides)) {
    if (value === undefined) continue;
    merged[key] = String(value);
  }
  return new URLSearchParams(merged).toString();
}

export default async function SchedulerPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const { data, error } = await apiGet<Replay>(`/api/schedule/replay?${query(params)}`);
  if (error) return <ErrorPanel message={error} />;
  if (!data!.available) {
    return (
      <ErrorPanel
        message={`The replay is not available: ${data!.reason ?? "unknown reason"}. It needs a committed exp017 run record; run \`make exp-show EXP=exp017-hybrid-scheduler\` to check.`}
      />
    );
  }

  const replay = data!;
  const meta = replay.meta;
  const slot = replay.slot_decision;
  const frame = replay.frames[slot.slot];
  const decision =
    slot.decisions.find((d) => d.id === replay.selection.item) ?? slot.decisions[0] ?? null;
  const chosen = decision?.chosen ?? null;

  const servedShare = replay.sites.map((_, j) =>
    replay.frames.reduce((total, f) => total + (f.served_gpu_s[j] ?? 0), 0),
  );
  const queueTotal = slot.decisions.reduce((total, d) => total + d.volume_gpu_s, 0);

  return (
    <>
      <div className="topbar">
        <span>Scheduler</span>
        <span className="spacer" />
        <span className="stamp">
          replay of {meta.exp_id} · run {meta.run.run_dir} · git {meta.run.git_sha.slice(0, 8)}
          {meta.run.git_dirty ? " (dirty)" : ""}
        </span>
      </div>

      <h1 className="page-title">Why did the scheduler place this work here?</h1>
      <p className="page-lede">
        This page replays one held-out week through the scheduler the project actually ships. Every number
        below is either read from a committed artifact or produced by that replay. Each decision shows the
        candidates it rejected and the numbers that rejected them — the explanation is computed from the
        planner&apos;s own ledger, not written afterwards.
      </p>

      <form className="controls" method="get">
        <label>
          Week
          <select name="week" defaultValue={replay.week}>
            {meta.weeks.map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
        </label>
        <label>
          Fleet
          <select name="fleet" defaultValue={replay.fleet.name}>
            {meta.fleets.map((f) => (
              <option key={f.name} value={f.name}>
                {f.name} · {f.n_gpus_per_site} GPUs/site
              </option>
            ))}
          </select>
        </label>
        <label>
          Miss price (kg / GPU-h)
          <select name="price" defaultValue={String(replay.price)}>
            {meta.prices.map((p) => (
              <option key={p} value={p}>
                {p} {p === 0.1 ? "· parity 0.093" : p === 1.0 ? "· service obligation" : "· crossover"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Band in price
          <select name="robust" defaultValue={String(replay.knobs.robust)}>
            <option value="0">0 · point forecast</option>
            <option value="1">1 · forecast + whole band</option>
          </select>
        </label>
        <label>
          Reserve
          <select name="reserve" defaultValue={String(replay.knobs.reserve)}>
            {[0, 0.1, 0.2, 0.3].map((r) => (
              <option key={r} value={r}>
                {Math.round(r * 100)}% of each block
              </option>
            ))}
          </select>
        </label>
        <label>
          Slot
          <input name="slot" type="number" min={0} max={meta.n_slots - 1} defaultValue={slot.slot} />
        </label>
        <button type="submit">Replay</button>
      </form>

      <div className="kpis">
        <Stat label="Carbon, whole week" value={`${fmt(replay.summary.carbon_kg, 1)} kg`} note="variable + idle floor" />
        <Stat label="Missed work" value={`${fmt(replay.summary.missed_fraction * 100, 2)}%`} note={`${fmt(replay.summary.missed_gpu_hours, 0)} GPU-hours`} />
        <Stat label="Objective" value={fmt(replay.summary.objective, 1)} note={`carbon + ${replay.price} × missed`} />
        <Stat label="Queued at this slot" value={`${fmt(queueTotal / 3.6e6, 2)} GWh`} note={`${slot.decisions.length} open items`} />
        <Stat label="Clock" value={frame.at.slice(0, 16).replace("T", " ")} note={`slot ${slot.slot} of ${meta.n_slots}`} />
      </div>

      <div className="dash">
        <Card title="The decision">
          {decision && chosen ? (
            <>
              <div className="decision-head">
                <div>
                  <div className="decision-site">{chosen.site_label}</div>
                  <div className="mono muted">
                    {chosen.at.slice(0, 16).replace("T", " ")}Z · slot {chosen.slot}
                  </div>
                </div>
                <div className="decision-figures">
                  <div>
                    <span className="label">predicted</span>
                    <span className="value">{fmt(decision.predicted_emissions_kg, 4)} kg</span>
                  </div>
                  <div>
                    <span className="label">vs worst feasible</span>
                    <span className="value">
                      −{fmt(decision.reduction_pct, 1)}%
                    </span>
                  </div>
                  <div>
                    <span className="label">realized</span>
                    <span className="value">{fmt(decision.realized_emissions_kg, 4)} kg</span>
                  </div>
                </div>
              </div>

              <ul className="reasons">
                <li>
                  <Chip status="modelled" /> <span className="mono">{decision.id}</span> —{" "}
                  {fmt(decision.volume_gpu_s / 3600, 2)} GPU-hours, {decision.class_label} deadline, arrived{" "}
                  {decision.age_slots} slot(s) ago, {decision.slots_left} slot(s) of slack left.
                </li>
                <li>
                  Placed: {fmt(decision.executed_now_gpu_s / 3600, 2)} GPU-hours now
                  {decision.deferred_gpu_s > 0 ? `, ${fmt(decision.deferred_gpu_s / 3600, 2)} GPU-hours deferred` : ""}
                  {decision.unassigned_gpu_s > 0 ? `, ${fmt(decision.unassigned_gpu_s / 3600, 2)} GPU-hours unplaced` : ""}.
                  {decision.split.deadline_forced ? " The deadline forced this slot: it is the last legal one." : ""}
                </li>
                {decision.alternatives
                  .filter((a) => a.status === "rejected")
                  .map((a) => (
                    <li key={a.site}>
                      <Chip tone="bad" /> {a.reason}
                    </li>
                  ))}
              </ul>
            </>
          ) : (
            <Callout>
              No decision in this slot. The queue is empty, or every item was placed by an earlier slot&apos;s
              reservation. Move the slot control to a busier part of the week.
            </Callout>
          )}
        </Card>

        <Card title="Where the sites are">
          <UkMap
            sites={replay.sites}
            frame={frame}
            selectedSlot={slot.slot}
            chosenSlot={chosen?.slot ?? null}
            chosenSite={chosen?.site ?? null}
            servedShare={servedShare}
          />
        </Card>
      </div>

      <Card title="Candidates the planner saw for this item">
        {decision && decision.alternatives.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Site</th>
                  <th>Forecast</th>
                  <th>Band</th>
                  <th>Robust price</th>
                  <th>Free capacity</th>
                  <th>Placed</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {decision.alternatives.map((a) => (
                  <tr key={a.site} data-chosen={a.status === "chosen"}>
                    <td>
                      {a.label} <span className="mono faint">{a.site}</span>
                    </td>
                    <td className="mono">{fmt(a.forecast_g_per_kwh, 1)} g/kWh</td>
                    <td className="mono">± {fmt(a.band_g_per_kwh, 1)}</td>
                    <td className="mono">{fmt(a.price_g_per_kwh, 1)}</td>
                    <td className="mono">
                      {fmt((a.free_gpu_s ?? 0) / 3600, 2)} / {fmt((a.block_capacity_gpu_s ?? 0) / 3600, 2)} h
                    </td>
                    <td className="mono">{fmt(a.take_gpu_s / 3600, 2)} h</td>
                    <td>
                      <span className="chip" data-tone={a.status === "chosen" ? "good" : "muted"}>
                        {a.code}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Callout>No candidates to compare for this item.</Callout>
        )}
        <p className="fine">
          <Chip status="modelled" /> The robust price is <span className="mono">forecast + robust × band</span>, which
          is the ordering the planner uses. Deadlines and per-block capacity are applied before the price, so a
          cheap site with no room is never a candidate — it is excluded, not out-priced.
        </p>
      </Card>

      <Card title="The backlog at this slot">
        <div className="queue">
          {slot.queue.by_class.map((group) => (
            <div key={group.class_index} className="queue-class">
              <div className="queue-head">
                <strong>{group.label} deadline</strong>
                <span className="mono faint">
                  {fmt(group.gpu_s / 3600, 1)} GPU-h · {group.n_items} items · oldest {group.oldest_slots_left} slots left
                </span>
              </div>
              <ul>
                {group.items.map((item) => (
                  <li key={item.id} data-selected={item.selected}>
                    <Link href={`/scheduler?${query(params, { item: item.id })}`}>
                      <span className="mono">{item.id}</span>
                    </Link>{" "}
                    <span className="mono faint">
                      {fmt(item.volume_gpu_s / 3600, 2)} GPU-h · {item.slots_left} slots left
                      {item.expired ? " · expired" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Card>

      <Section title="Carbon forecast, and when the week was served">
        <p className="fine">
          <Chip status="verified" /> Regional forecast from NESO, half-hourly. <Chip status="assumption" /> The
          realized series is estimated as <span className="mono">national_actual × regional_forecast / national_forecast</span>{" "}
          because NESO ships no regional actuals. The white line is the slot above; the purple ticks are the
          execution slots the selected item was assigned.
        </p>
        <ForecastGrid
          sites={replay.sites}
          frames={replay.frames}
          selectedSlot={slot.slot}
          chosenBlocks={chosen ? chosen.blocks.map((b) => ({ site: b.site, slot: b.slot })) : []}
          slotMinutes={replay.meta.slot_minutes}
          windowStart={replay.window_start_utc}
        />
        <p className="fine" id="timeline">
          Served GPU-seconds as a share of each site&apos;s block capacity. Empty rows are idle capacity, and the
          idle floor is billed in the carbon total regardless — so a row with no blue still emits.
        </p>
        <Timeline
          sites={replay.sites}
          frames={replay.frames}
          selectedSlot={slot.slot}
          slotMinutes={replay.meta.slot_minutes}
          windowStart={replay.window_start_utc}
        />
      </Section>

      <Card title="Policy inspector — what this scheduler actually optimises">
        <div className="policy">
          <div>
            <h3>Objective</h3>
            <p className="mono">{replay.policy.objective.formula}</p>
            <p className="fine">{replay.policy.objective.note}</p>
            <p className="fine">
              Parity price: {fmt(replay.policy.objective.parity_price_kg_per_gpu_hour, 3)} kg per GPU-hour — the
              carbon a served GPU-hour emits. The price here is {replay.price}.
            </p>
          </div>
          <div>
            <h3>Hard constraints</h3>
            <ul className="plain">
              {replay.policy.hard_constraints.map((c) => (
                <li key={c.label}>
                  <strong>{c.label}</strong> — <span className="mono">{c.value}</span>. {c.note}
                </li>
              ))}
            </ul>
            <p className="fine">
              These are not weights. There is no slider that trades a deadline for carbon, because the scheduler
              does not implement one.
            </p>
          </div>
          <div>
            <h3>Knobs in this replay</h3>
            <ul className="plain mono">
              <li>robust = {replay.knobs.robust}</li>
              <li>reserve = {Math.round(replay.knobs.reserve * 100)}% per block</li>
              <li>price = {replay.price} kg / missed GPU-hour</li>
            </ul>
            <p className="fine">{replay.policy.note}</p>
          </div>
        </div>
      </Card>

      <Callout tone="warn">
        <strong>What this page does not claim.</strong> {meta.notes.band} {meta.notes.relative}{" "}
        <Chip status="assumption" /> {meta.labels.mapping.what}
      </Callout>

      <p className="fine">
        Trace check:{" "}
        {replay.trace.matches_planner
          ? "the replay reproduces the planner's own totals"
          : `the replay differs from the planner in ${replay.trace.mismatch_slots.length} slot(s)`}
        . {replay.trace.note}
      </p>
      <p className="fine">
        Served GPU-hours over the week:{" "}
        {replay.sites
          .map((s, j) => ({ label: s.short, hours: servedShare[j] / 3600 }))
          .sort((a, b) => b.hours - a.hours)
          .map((x) => `${x.label} ${fmt(x.hours, 0)}`)
          .join(" · ")}
        . Mean forecast intensity over the same week:{" "}
        {replay.sites
          .map((s, j) => ({
            label: s.short,
            mean:
              replay.frames.reduce((total, f) => total + (f.forecast_g_per_kwh[j] ?? 0), 0) /
              replay.frames.length,
          }))
          .sort((a, b) => a.mean - b.mean)
          .map((x) => `${x.label} ${fmt(x.mean, 1)} g/kWh`)
          .join(" · ")}
        .
      </p>
    </>
  );
}
