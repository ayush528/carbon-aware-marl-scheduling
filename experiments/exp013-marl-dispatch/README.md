# exp013 run lineage

Three run records remain, and only one is canonical. Each earlier one is kept
because it is the measurement that exposed a defect, which is more useful than a
clean-looking directory.

| run | config hash | what it is |
|---|---|---|
| `20261122T104152Z-01e183d3` | `01e183d3` | **Superseded.** First run, learning rate 3e-3. The learner diverged: it beat carbon-greedy by 4.9% while missing 16.7% of work, and the multi-seed repeat could not reproduce it. Exposed the learning rate (see `20261122T113107Z`). |
| `20261122T113107Z-6588d350` | `6588d350` | **Superseded.** Same rates fixed to 3e-4, but the holding price was 0.01 kg per GPU-hour *per slot*, which charges an hour held to its deadline 0.08 kg against the 0.093 kg it emits. `run_now` won every arm on the objective. Exposed the double charge (`site_energy_kwh` already bills the idle floor every slot). |
| `20261122T121747Z-1047d39f` | `1047d39f` | **Canonical.** Holding price 0, prices swept at and around the parity price (0.093 kg per GPU-hour), `learning_gate` scoring against the best rule on the learner's own objective, `git_dirty: false`. |

No run record is ever edited. `config_hash` in each `manifest.json` says which
config produced it, and only the canonical record's hash matches the committed
`config.yaml`.

The two superseded records are also why the module keeps
`parity_price_kg_per_gpu_hour` in its output: without a price scale, "the agent
cuts carbon 26%" and "the agent served a quarter less work" are the same
sentence.
