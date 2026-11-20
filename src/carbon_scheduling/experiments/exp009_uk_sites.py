"""exp009 -- SustainCluster on four UK sites with NESO regional carbon.

Phase 2, part 2: replace upstream's five non-UK sites with four UK sites fed by
real NESO regional carbon (our derived series) and real GB wholesale prices
(Elexon MID), then re-run the rule-based baselines.

What is real and what is disclosed:
  * Carbon per site is our documented regional estimate
    ``national_actual x regional_forecast / national_forecast`` -- NESO's
    regional endpoint ships forecasts only (verified live: `actual` is null on
    every regional row).
  * Price is the national GB series replicated to every site, so cost cannot
    differentiate sites. ``lowest_price`` therefore has nothing to choose on
    and the result must be read as a degeneracy, not a finding about price.
  * Weather is GB 2024 (the only GB weather upstream ships), applied to a
    Jan-2024 window; timezone shift 0 (GMT in January).
  * Equal population weights and identical hardware per site, so carbon is the
    only axis that differs between sites.

Verification (this is the exit test): the per-site intensity implied by the
simulator's own accounting (carbon_kg / energy_kwh) is compared against the
intensity in the input CSV over the same window, and the sites must rank in the
same order in the run as in the input series. They must agree -- otherwise the
simulator is not consuming the NESO data we think it is.

One upstream behaviour the verification has to respect: the cluster reset
jitters the data window to a random day within +/-7 of the configured one and a
random hour, so the reported ``carbon_window_start_utc`` -- not the configured
date -- is what the series are checked against. The jitter is seeded, so every
controller in a run sees the identical window (asserted); the workload clock
stays on the configured date (``workload_clock_start_utc``), which is an
upstream quirk we disclose rather than patch.
"""

from __future__ import annotations

import csv
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from carbon_scheduling.runner import REPO_ROOT
from carbon_scheduling.sim import sustaincluster

KEEP = (
    "carbon_kg",
    "energy_kwh",
    "energy_cost_usd",
    "transmission_cost_usd",
    "sla_violation_rate",
    "tasks_finished",
    "mean_gpu_util_percent",
)


def _window_mean_intensity(csv_path: Path, start: datetime, hours: int) -> float:
    """Mean gCO2/kWh in the input series over [start, start+hours).

    Every hour of the window must be present, otherwise the comparison would be
    against a partial window and prove nothing -- so a short window raises.
    """
    wanted = {start + timedelta(hours=i) for i in range(hours)}
    values: list[float] = []
    with Path(csv_path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            ts = datetime.strptime(row["Datetime (UTC)"], "%Y-%m-%d %H:%M:%S")
            if ts in wanted:
                values.append(float(row["Carbon Intensity gCO₂eq/kWh (direct)"]))
    if len(values) != hours:
        raise ValueError(
            f"{Path(csv_path).name}: only {len(values)} of the {hours} hours from "
            f"{start:%Y-%m-%dT%H:%M} are in the series"
        )
    return sum(values) / len(values)


def _write_configs(config: dict[str, Any], scratch: Path) -> None:
    sim = dict(config["simulation"])
    (scratch / "sim_config.yaml").write_text(yaml.safe_dump({"simulation": sim}))
    (scratch / "datacenters.yaml").write_text(yaml.safe_dump({"datacenters": config["sites"]}))
    (scratch / "reward_config.yaml").write_text(yaml.safe_dump({"reward": config["reward"]}))


def _require_installed(checkout: Path, config: dict[str, Any]) -> None:
    """Fail early, with the fix, if the UK series are not in the checkout.

    ``make exp-run`` alone cannot work on a fresh clone: the pulled series have
    to be materialised into the simulator's hardcoded paths first.
    """
    year = config["simulation"]["year"]
    missing = [
        site["location"]
        for site in config["sites"]
        if not (
            checkout
            / "data"
            / "carbon_intensity"
            / site["location"]
            / str(year)
            / f"{site['location']}_{year}_hourly.csv"
        ).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            f"UK inputs not installed for {missing}; run `make sc-uk-data` "
            "then `make sc-uk-install`"
        )


def run(config: dict[str, Any]) -> dict[str, Any]:
    sc_cfg = config["sustaincluster"]
    sim = config["simulation"]
    checkout = sustaincluster.checkout_dir(sc_cfg)
    _require_installed(checkout, config)
    python = sustaincluster.resolve_python(checkout, sc_cfg)
    days = float(sim["duration_days"])
    seed = int(config["seed"])

    # The data index is passed directly; make sure it matches the clock.
    configured_start = datetime(sim["year"], sim["month"], sim["init_day"], sim["init_hour"])
    expected_index = (
        int((configured_start - datetime(sim["year"], 1, 1)).total_seconds() // 3600) // 24
    )
    if int(sim["init_day_of_year"]) != expected_index:
        raise ValueError(
            f"init_day_of_year={sim['init_day_of_year']} does not match "
            f"{configured_start:%Y-%m-%d} (expected {expected_index})"
        )

    scratch = Path(tempfile.mkdtemp(prefix=f"{config['id']}-"))
    _write_configs(config, scratch)

    results: list[dict[str, Any]] = []
    for strategy in sc_cfg["baselines"]:
        results.append(
            sustaincluster.run_strategy(
                checkout,
                python,
                strategy,
                days=days,
                seed=seed,
                out_path=scratch / f"{strategy}.json",
                init_day_of_year=int(sim["init_day_of_year"]),
                sim_config=scratch / "sim_config.yaml",
                datacenters=scratch / "datacenters.yaml",
                reward_config=scratch / "reward_config.yaml",
            )
        )

    rows: dict[str, dict[str, Any]] = {}
    for result in results:
        rows[result["controller"]] = {
            **{k: round(result[k], 4) if isinstance(result[k], float) else result[k] for k in KEEP},
            "per_dc": {
                name: {k: round(v, 2) for k, v in bucket.items()}
                for name, bucket in result["per_dc"].items()
            },
        }

    reference = rows["round_robin"]
    best = min(rows, key=lambda k: rows[k]["carbon_kg"])

    # --- exit test: does the simulator consume the NESO series? ---
    # Upstream's cluster reset jitters the data window (+/-7 days, random hour),
    # so verify against the window it actually read, not the configured date.
    windows = {json.dumps(r["window"], sort_keys=True) for r in results}
    if len(windows) != 1:
        raise RuntimeError(f"controllers ran on different data windows: {sorted(windows)}")
    window = results[0]["window"]
    if not window:
        raise RuntimeError("driver did not report the simulator's data window")
    start = datetime(window["year"], 1, 1) + timedelta(
        days=window["start_day_index"], hours=window["start_hour_utc"]
    )

    sites = config["sites"]
    data_paths = [REPO_ROOT / rel for rel in config["data"]]
    carbon_by_slug = {
        path.name.split(f"_{sim['year']}_hourly.csv")[0]: path
        for path in data_paths
        if "carbon" in path.parts
    }
    provenance = json.loads(next(p for p in data_paths if p.name == "provenance.json").read_text())
    hours = int(days * 24)
    regional: dict[str, dict[str, Any]] = {}
    for site in sites:
        slug = site["location"]
        expected = _window_mean_intensity(carbon_by_slug[slug], start, hours)
        bucket = rows["round_robin"]["per_dc"][f"DC{site['dc_id']}"]
        observed = (
            bucket["carbon_kg"] * 1000.0 / bucket["energy_kwh"] if bucket["energy_kwh"] else 0.0
        )
        regional[slug] = {
            "neso_region_id": provenance["sites"][slug]["neso_region_id"],
            "neso_region_name": provenance["sites"][slug]["neso_region_name"],
            "input_mean_gco2_per_kwh": round(expected, 2),
            # Energy-weighted by construction (carbon = energy x intensity), so
            # it need not equal the plain time mean; 2% / 2 g covers weighting.
            "simulated_gco2_per_kwh": round(observed, 2),
            "within_tolerance": abs(observed - expected) <= max(2.0, 0.02 * expected),
        }

    max_error = max(
        abs(v["simulated_gco2_per_kwh"] - v["input_mean_gco2_per_kwh"]) for v in regional.values()
    )
    # Sites must rank in the same order in the run as in the input series: the
    # simulator has to be reading *our* per-region series, not one shared zone.
    by_input = sorted(regional, key=lambda s: regional[s]["input_mean_gco2_per_kwh"])
    by_simulated = sorted(regional, key=lambda s: regional[s]["simulated_gco2_per_kwh"])
    ordering_matches = by_input == by_simulated
    exit_passed = all(v["within_tolerance"] for v in regional.values()) and ordering_matches

    return {
        "sustaincluster_commit": results[0]["sustaincluster_commit"],
        # The window the carbon/price/weather data came from (simulator's own
        # jittered choice), and the clock the workload was dispatched against.
        "carbon_window_start_utc": start.strftime("%Y-%m-%dT%H:%MZ"),
        "carbon_window_hours": hours,
        "workload_clock_start_utc": configured_start.strftime("%Y-%m-%dT%H:%MZ"),
        "days": days,
        "seed": seed,
        "n_sites": len(sites),
        "controllers": rows,
        "carbon_vs_round_robin_pct": {
            name: round((row["carbon_kg"] / reference["carbon_kg"] - 1) * 100, 2)
            for name, row in rows.items()
            if name != "round_robin"
        },
        "best_carbon_controller": best,
        "best_carbon_kg": rows[best]["carbon_kg"],
        "min_sla_violation_rate": min(v["sla_violation_rate"] for v in rows.values()),
        "regional_intensity": regional,
        "regional_spread_gco2_per_kwh": round(
            max(v["input_mean_gco2_per_kwh"] for v in regional.values())
            - min(v["input_mean_gco2_per_kwh"] for v in regional.values()),
            2,
        ),
        "max_intensity_error_gco2_per_kwh": round(max_error, 2),
        "regional_ordering_matches_input": ordering_matches,
        "exit_test_passed": exit_passed,
        "price_identical_across_sites": True,
    }
