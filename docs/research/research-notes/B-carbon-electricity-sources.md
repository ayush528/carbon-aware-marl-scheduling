# Research Note B — Grid Carbon Intensity Datasets & APIs (historical + forecasts)

**Project context:** B.Tech major project — carbon-aware, geo-distributed data-center scheduling.
**Candidate regions:** UK (Great Britain), USA (CAISO/ERCOT/PJM/ISO-NE + EIA), India, Japan, Nordics (FI/SE), Germany, Netherlands, Australia (+ brief Canada note).
**Date of research:** 2026-11-04. All "live-verified" items below were tested on this date with real HTTP calls; response snippets are quoted verbatim.
**Legend:** ✅ live-verified (I fetched it and received real data) · 📄 doc-verified (from an official page I fetched) · ⚠️ unverified (asserted from secondary sources or plausible-but-not-checked — flagged explicitly).

---

## 1. United Kingdom (Great Britain)

### 1.1 NESO Carbon Intensity API (carbonintensity.org.uk) — TOP PICK
- **Publisher:** National Energy System Operator (NESO) + Environmental Defense Fund Europe, Oxford Dept. of Computer Science, WWF.
- **Homepage:** https://carbonintensity.org.uk/ ✅ fetched.
- **API base:** https://api.carbonintensity.org.uk ✅ live.
- **Official docs:** http://docs.carbonintensity.org.uk (Swagger UI / OpenAPI). ⚠️ docs.carbonintensity.org.uk returned a TLS "connection reset" from our sandbox (both curl and webfetch); the API endpoints themselves responded normally. Partner agent must verify docs page directly. Note the OpenAPI spec path I tried (`/swagger.json`) returned `{"error":{"code":"400 Bad Request","message":"Please enter a valid path e.g. /intensity/"}}` — the spec is served to the docs UI, not as `/swagger.json`.
- **What it gives:** 30-minly carbon **intensity in gCO₂/kWh** (no need to compute from fuel mix) + region-level **generation mix** percentages. Covers all large metered stations, interconnector imports, T&D losses, embedded wind/solar. Forecast horizon **96+ hours ahead** (their phrasing on homepage; ML ensemble + nowcast every 30 min). Forecast history and actuals from **2017-09-26** (stated on homepage data-download widget ✅).
- **Regions:** **14 DNO regions** (regionids 1–17, not all used; sample live response maps regionid=1 → "Scottish Hydro Electric Power Distribution", shortname "North Scotland"). Regional breakdown uses AC power flow across a reduced network model (methodology PDFs linked from homepage: national + regional v2 hosted at api.neso.energy download URLs, confirming NESO branding).
- **Historical responses include forecast vs actual:** ✅ **LIVE-VERIFIED**. `GET https://api.carbonintensity.org.uk/intensity/2025-09-01T00:00Z/2025-09-01T01:00Z` returned per-half-hour objects with **both** values, e.g.:
  ```json
  {"from":"2025-09-01T00:00Z","to":"2025-09-01T00:30Z","intensity":{"forecast":62,"actual":68,"index":"low"}}
  ...
  {"from":"2025-09-01T00:30Z","to":"2025-09-01T01:00Z","intensity":{"forecast":68,"actual":66,"index":"low"}}
  ```
  **This is exactly the forecast-vs-actual pair we need to quantify uncertainty — historical national data has it built in.**
- **Regional historical:** ✅ `GET /regional/intensity/2025-10-01T00:00Z/2025-10-01T00:30Z` returned all 14 regions with `intensity.forecast` + `generationmix` (biomass, coal, imports, gas, nuclear, other, hydro…) per region and half hour. The sample past-window response contained **forecast+index but no `actual`** for regional intensity — so region-level forecast-vs-actual pairing may need to be constructed by re-querying now-through-past windows or from the website's regional CSV download. ⚠️ needs one confirmation via docs.
- **Endpoints (homepage + common spec):**
  - National window: `GET /intensity/{from}/{to}` (ISO `YYYY-MM-ddTHH:MMZ`) ✅ works with quoted dates.
  - Half-hour current: `GET /intensity`, last 24h: `GET /intensity/date`, next 48h: `GET /intensity/forecasts` ⚠️ (unverified; in docs).
  - Regional window: `GET /regional/intensity/{from}/{to}` ✅ live.
  - Region-specific: `GET /regional/regionid/{id}/intensity/{from}/{to}` and `/regional/regionid/{id}/date/{date}` ⚠️ — in our environment these returned AWS-API-Gateway `400 "Missing Authentication Token"` for several path variants (`regionid/13/intensity/...`, `regionid/1/date/...`), which is Gateway's "route not found" signature. Either the exact path differs from what I assumed, or there's a transient routing issue. **Partner agent: verify exact regionid endpoint paths against docs.carbonintensity.org.uk.**
  - Postcode: `GET /regional/postcode/{postcode}/intensity/{from}/{to}` ⚠️ same signature error in my test.
- **National CSV bulk download:** homepage widget "Download The Data" → 30-day-max chunks, from 2017-09-26 ( nationale only says "Only 30 days at a time, cannot cross years") ✅ from homepage text.
- **Key needed:** No. **Cost:** Free. **License:** CC BY 4.0 (homepage ✅). **Terms:** http://terms.carbonintensity.org.uk.
- **Rate limit:** ⚠️ NOT VERIFIED — homepage/docs claim needs checking ("Documentation → Details → Rate limit" lists an unofficial-ish limit; partner agent to capture exact number from docs page).

### 1.2 Elexon BMRS (generation mix per settlement period)
- **Modern access model:** the Insights Solution API — https://data.elexon.co.uk/bmrs/api/v1/ — **free, NO key** ✅ live-verified.
  - `GET https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH?from=2025-10-01T00:00:00Z&to=2025-10-01T01:00:00Z` → 200 JSON **half-hourly generation outturn by fuel type** (BIOMASS 3344 …) ✅
  - `GET .../datasets/FUELINST?...` → **instantaneous (5-min?) generation by fuel** ✅ live (2026-11-04 publishTime entries).
  - Docs: https://bmrs.elexon.co.uk/api-documentation (and `/introduction`, `/endpoint/datasets/FUELINST`) 📄 via search result confirmation; full page content not fetched.
- The old BMRS + REST (api.elexonportal) is being fully migrated into the Insights Solution; per Elexon announcement BMRS datasets have completed migration to Insights ✅ (Elexon news page).
- **Carbon:** BMRS gives fuel mix only — **no CO₂ values**. GB carbon intensity data comes from NESO CI API (§1.1) or Electricity Maps. A UK CI from Elexon fuel mix would need per-fuel emission factors ourselves.
- **Granularity:** GB national; fuel type level; resolution half-hourly (FUELHH) and 5-min (FUELINST).

---

## 2. United States

### 2.1 EIA Hourly Electric Grid Monitor (EIA-930) — TOP PICK
- **Publisher:** U.S. EIA. **Site:** https://www.eia.gov/electricity/gridmonitor/ (Angular app; page served as SPA).
- **Bulk CSVs are FREE, no key** ✅ live-verified:
  - Meta file listing every archive: `https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_File_List_Meta.csv` ✅ (9.9 KB; columns SURVEY,FILENAME,CONTENT_FILENAME,DESCRIPTION,YEAR,PERIOD,MONTHS,LAST_UPDATED,LAST_REVISED; last-updated timestamps 11/03/2026).
  - Real archives (categories: BALANCE, INTERCHANGE, SUBREGION) e.g.
    - `https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_BALANCE_2024_Jan_Jun.csv` ✅ (real CSV header: `"Balancing Authority","Data Date","Hour Number","Local Time at End of Hour","UTC Time at End of Hour","Demand Forecast (MW)","Demand (MW)","Net Generation (MW)","Total Interchange (MW)","Sum(Valid DIBAs) (MW)","Demand (MW) (Imputed)","Net Generation (MW) (Imputed)","Total Interchange (MW) (Imputed)","Demand (MW) (Adjusted)",...,"Net Generation (MW) from Coal","... Natural Gas","... Nuclear","... All Petroleum Products","... Hydropower and Pumped Storage","... Solar","... Wind",...`)
  - **Coverage:** from **2015 Jul–Dec** through **2026 Jul–Dec** (file list includes 2026 Jan-Jun and Jul-Dec) ✅ — i.e., ~1.5 years beyond my earlier PUDL note, continuously updated.
- **CO₂:** The per-BA Excel files contain **estimated total CO₂, CO₂ by fuel, and CO₂ for imported/exported electricity, from 2018-07-01 onwards** (documented officially — EIA references in PUDL doc I fetched: "Additional CO2 emissions data is available through the per-BA Excel spreadsheet data…"). The bulk CSVs do NOT include CO₂ columns. CO₂ from fuel-mix would need own factors otherwise. ⚠️ exact per-BA Excel URL pattern not verified; dashboard "Known issues" xls path exists (`/electricity/gridmonitor/knownissues/xls/Region_US48.xlsx` ✅ linked from eia.gov/electricity/data/eia930/). EIA page text confirms "64 balancing authorities … hourly CO2 emissions estimates" 📄.
- **Subregions:** demand-by-subregion for select BAs from 2018-07-01 (e.g., BA codes CISO, ERCT, PJM, NEWE appear as BA/regional codes; the dashboard JS itself excludes NE, NY, TEN, TEX from subregion files ✅ — i.e., ERCOT/Texas, NYISO, NEISO, ERCOT-Tennessee… don't report subregions). Codes list = the EIA-930 BA & subregion codes (PUDL `core_eia__codes_balancing_{authorities,authority_subregions}`).
- **Forecast data:** EIA-930 includes **day-ahead demand forecast** per hour ✅ (bulk CSVs + API). No published CO₂ forecast (fuel/CO₂ are realized only).
- **REST APIs:**
  - Dashboard's internal API: relative `../930-api` ⇒ `https://www.eia.gov/electricity/930-api/...` (endpoint fragment `region_data_by_fuel_type/data` found in bundle) ⚠️ unverified path contract.
  - Official API v2: `https://api.eia.gov/v2/electricity/rto/...` — **needs free API key** (register https://www.eia.gov/opendata/register.php). Live test returned: `{"error":{"code":"API_KEY_MISSING","message":"No api_key was supplied. Please register for one at https://www.eia.gov/opendata/register.php"}}` (403) ✅.
- **License/cost:** Free, US-government public data (no registration for bulk files).

### 2.2 CAISO — Today's Outlook CO₂ feeds — TOP PICK for a single-region case study
- **Anonymous, keyless, zero-cost.** Endpoints (host www.caiso.com, subject to change without notice; officially informational only "should not be used for billing"; CARB recommended for official emissions data).
- **Feed file names found in CAISO's own `outlook.js` (✅ from JS bundle theme/js/outlook/outlook.js):** report names: `demand.csv`, `netdemand.csv`, `fuelsource.csv`, `co2.csv`, `co2_YESTERDAY.csv`, `rtm_forecast.csv`, `rtm_forecast_7day.csv`, `hybrids.csv`, `storage.csv`, `wind_solar_wo_hybrids.csv`, `peak_and_daily.csv`, `peak_and_daily_hybrids.csv`, `peak_and_daily_storage.csv`, `demand_YESTERDAY.csv`, plus `stats.txt`, `/outlook/data/data-messages.json`, `/outlook/data/co2-historical.json` (a yearly-total graphic), `/outlook/data/co2-historical-chart.json` (monthly totals 2014→).
- **LIVE-VERIFIED responses:**
  - Today 5-min CO₂: `https://www.caiso.com/outlook/current/co2.csv` →
    ```
    Time,Biogas CO2,Biomass CO2,Natural Gas CO2,Coal CO2,Imports CO2,Geothermal CO2
    00:00,79,58,4566,3,1707,7
    00:05,79,57,4542,3,1657,7
    ```
    (metric tons per 5-min interval per fuel; unit documented on dashboard page, not in CSV header).
  - Yesterday: `/outlook/current/co2_YESTERDAY.csv` ✅.
  - **Historical any-day CO₂ CSV:** `https://www.caiso.com/outlook/history/YYYYMMDD/co2.csv` ✅ live for 2019-01-01, 2019-06-01, 2020-01-01 (200 OK, real data); **2018-01-01 and 2017-01-01 → 404**. So deep history at least **2019+**; exact inception year needs a binary search between 2017–2019 ⚠️.
  - Day **fuel mix** history for the same dates: `/outlook/history/20251101/fuelsource.csv` ✅ (columns: Solar,Wind,Geothermal,Biomass,Biogas,Small hydro,Coal,Nuclear,Natural Gas,Large Hydro,Batteries,Imports,Other). **CO₂/energy must be computed by us** (gas ≈ 427 gCO₂/kWh, coal ≈ 1000, geothermal ≈ 42, imports = external signal) — that's CAISO's own methodology convention; their CO₂ is ton-per-period, and MWh by fuel is in fuelsource.csv → intensity = Σ(t×1000 g)/Σ(MWh). Dashboard crosscheck possible.
  - Annual/monthly history graphic: `https://www.caiso.com/outlook/data/co2-historical-chart.json` ✅ (monthly CO₂ tonnes 2014→).
- **Forecast-vs-actual:** demand has `rtm_forecast.csv` (day-ahead demand forecast, today) and 7-day RA forecast (`rtm_forecast_7day.csv`) ✅ names from JS; **no published CO₂ forecast** — CO₂ is realized-only ⚠️ (verbs: their CO₂ page updates mid-day).
- **Rate limits:** none documented publicly ⚠️; be gentle (≤1 req/sec, cache).
- **ACES/OASIS:** official market data at `https://oasis.caiso.com/oasisapi/SingleZip?...` (queryname=SLD_FCST for forecast etc.) — anonymous, but no CO₂. apiis.io/provider/caiso confirms OASIS keyless + Today's Outlook keyless 📄 (third-party; cite carefully).

### 2.3 PJM & ISO-NE
- **PJM:** no public hourly CO₂ dataset. PJM publishes fuel mix/report data; hourly CO₂ for **PJM BA is available from EIA-930 (ID=PJM)** as CO₂ Excel and via third-party reconciliation (below). ⚠️ (negation unverified).
- **ISO-NE (New England):** ISO-NE publishes an **annual Electric Generator Air Emissions Report (CO₂, NOₓ, SO₂)** + monthly recaps + an *estimated real-time CO₂ by fuel* graphic inside ISO Express (no bulk API) 📄 (fetched https://www.iso-ne.com/genrtion_resrcs/reports/emission/index.html — real-time estimates, factors for monthly/year-to-date estimates derived from the annual report). Their underlying raw hourly CO₂ is **EPA CAMPD (Clean Air Markets Program Data)** https://campd.epa.gov/ — free hourly CEMS emission data (all US units), downloadable APIs/CSV 👉 **use CAMPD for the plausibly-best hourly US generator-level CO₂** (unverified format details in this session, well-known official source).
- **NYISO footnote:** https://www.nyiso.com/emissions-data publishes Average Emission Rates (AER) calculators/datasets (tons CO₂ per MWh; NYCA) — free.

### 2.4 ERCOT
- **No official ERCOT CO₂/emissions dataset** ⚠️ (no official ERCOT hourly CO₂ per ERCOT publications; consistent with search). Hourly CO₂ for the ERCOT/Texas BA exists via **EIA-930 BA=ERCT** (in the per-BA Excel CO₂ series, from 2018-07-01) and **EPA CAMPD** (Texas plants). ERCOT publishes fuel mix/demand data (no CO₂).

### 2.5 EPA eGRID
- **Latest release:** data year **2023** — eGRID2023 rev2 (rev 2 released 2025-06-12; rev1 2025-01-17; initial 2025-01-15) 📄 fetched https://www.epa.gov/egrid/detailed-data (page last updated 2026-09-22; **no eGRID2024 yet**).
- **Direct downloads (✅ exact URLs from that page):**
  - Main workbook: `https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx`
  - Metric-units version: `https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_metric_rev2.xlsx`
  - Release notes txt: `https://www.epa.gov/system/files/other-files/2025-06/egrid2023_release_notes.txt`
- **Content:** annual, plant-level + **eGRID subregions** (27, e.g., **CAMX** for California, ERCOT/Texas subregions, PJMW, NEWE, RFCE for the Mid-Atlantic…) with **annual average CO₂ lb/MWh and kg/MWh** emission rates, total output and resource mix. **Freely usable (US public data). Annual-only — no hourly, no forecasts.** Use as (a) static subregional factors for the US BA fuel-mix→CI conversion, and (b) sanity check.

### 2.6 Academic/free mirrors for US grid carbon (2024–2026)
- **PUDL (Catalyst Cooperative)** — free, reproducible pipeline for EIA-930 & EPA CEMS with imputed/normalized columns and Parquet outputs; docs https://docs.catalyst.coop/pudl/en/v2025.7.0/data_sources/eia930.html 📄 (fetched; full detail above). Licenses CC-BY-4.0 (per site).
- **Open Grid Emissions Initiative (Singularity Energy)** — https://github.com/singularity-energy/open-grid-emissions — reconciled hourly CO₂ per BA from EIA-930 using Stanford's "gridemissions" method (https://github.com/jdechalendar/gridemissions) 📄 (methodology cited on PUDL page). Public datasets/GitHub; free for research ⚠️ (their API "Grid Carbon API" is commercial).
- **No CAISO-specific Zenodo/HF gold dataset found in Nov 2026 searches** ⚠️ (searches returned only general carbon datasets). Workaround: our own crawler of `/outlook/history/{date}/co2.csv` + `fuelsource.csv` (one file per day, ~8 KB each) — trivial to backfill.

---

## 3. Electricity Maps (commercial — 130+ zones incl. GB-BRB variants, IN-WE/IN-SO, DE, NL, JP, no NEM AU zones)
- **Pricing (fetched https://www.electricitymaps.com/pricing ✅, prices in EUR, per country/year, hourly):**
  - Carbon intensity (real-time, incl. forecasts): **€6,000/yr** per country.
  - All grid signals bundle: €18,000/yr. Sustainability bundle: €12,000/yr. Load: €4,500/yr.
  - **Time coverage shown on pricing page:** Day-ahead price historical **2017–2024**; granularity 5m/15m/1h→1y.
  - Free **14-day API trial** (all signals, real-time + forecast, no payment info) — app.electricitymaps.com/developer-hub/playground.
  - Startup discount: <25 employees or <€2M ARR → up to 50% off. Volume/global pricing "talk to sales".
- **API (v4) — docs verified:** https://portal.electricitymaps.com/docs 📄 — endpoints per signal: `/past-range`, `/past`, `/history` (last 24h), `/latest`, **`/forecast`** ("proprietary forecasts"), plus price helpers. Auth: bearer token. Signals include carbon intensity, carbon-free %, fossil-only CI, electricity mix, flows, load/net load. (Docs listing fetched; rates not in public docs ⚠️.)
- **Free open historical dataset 2023–2026?** Search found **no official free full-history dump** on Zenodo/HF/GitHub (only derived datasets, e.g., MCSC trucking GeoJSON citing "Electricity Maps 2022–23 US hourly CI"). Portal (data-portal) offers on-map free views and small samples, plus credits for demo accounts ⚠️. **Terms for non-commercial research:** historical data is paid; academic grant-type access is ad-hoc (multiple papers thank EM for data sharing) ⚠️. Conclusion: treat EM as commercial; prefer our open pipeline. Open-source **dispatcher/parsers repo**: github.com/electricitymaps/electricitymaps-contrib (per-zone data sources & emission factors — USEFUL reference dataset of fuel EFs per zone ✅ well-known; repo snapshot not re-fetched ⚠️).

---

## 4. WattTime (US-focused marginal emissions; also global average)
- **Access model 📄 (fetched https://www.watttime.org/docs-dev/data-plans/):**
  - **Basic (free) tier:** *all signals & endpoints for one region: **CAISO_NORTH*** + CO₂ percentile for all regions; token-based auth; **historical 2+ years; forecast 72 h rolling, updated every 5 min**; general support.
  - **Analyst / Pro:** global 200+ countries/territories coverage (contact sales; prices not public).
  - CO₂ signals: **marginal** (AER/adequacy-based) and average, plus Human-Health signal (NOₓ/SO₂/PM₂.₅-driven).
- **Registration:** required (free account / register) → "API registration collects verified email, org…" (privacy page 📄). **Research access:** complimentary for approved research/non-commercial use via form https://watttime.org/noncommercial-agreement/ and https://watttime.org/data-science/for-research/ ("offers researchers complimentary access"). API at https://api.watttime.org/v3; docs https://docs.watttime.org ⚠️ endpoints unverified (no live call made — all endpoints need auth).

---

## 5. ENTSO-E Transparency Platform (Europe incl. DE, NL, SE1–SE4, FI)
- **What's in it:** day-ahead prices, load, **generation by production type per bidding-zone country (FI, SE1-4, DE-LU, NL…)**, cross-border flows, outages, intraday… **No CO₂ / carbon intensity values** — must compute from generation mix (and import shares) with our own factors ⚠️ negation = strong consensus + platform docs don't list CO₂; mark "verified-by-absence".
- **New platform R3 (renewed Transparency Platform, launched 2025).** Token-based REST API 📄:
  - **Rate limit:** **400 requests/minute per token** (per token, NOT per IP; no IP banning in R3 API; token banning (~10 min auto-unban) if exceeded; recommended ~6–7 req/sec average). Source: official Zendesk article "API Rate Limit Part 1" (https://transparencyplatform.zendesk.com/hc/en-us/articles/12783148966036) ✅ fetched.
  - File-library downloads: max 100 requests/user/min (separate section).
  - **Token:** registration at https://transparency.entsoe.eu → account settings/security token; how-to article "How to get security token?" (https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188-How-to-get-security-token) — free (EU registration).
  - Request endpoint/article: "Request Endpoint" (`data request` via POST to the R3 API; api base https://web-api.tp.entsoe.eu/api historically; exact R3 endpoint contract ⚠️ to confirm from the "Request Endpoint" article).
- **Format:** older API returned XML (documents); new R3 API returns XML/ZIP; generation data usable for DE/NL/SE/FI (15-min → hourly).

---

## 6. Nordics

### 6.1 Fingrid (Finland) — has real-time emission-factor datasets ✅
- **Portal:** https://data.fingrid.fi (Open Data) — Next.js site; API **requires a free API key** created after registration **and license approval**; live `/api/datasets?limit=10` returns **401 Unauthorized** without token ✅.
- **Rate limits 📄 (from the official "API instructions" page content):** **10,000 requests per 24 h and 1 request every 2 seconds per API key** ("These limits help… contact the administrator if you need to make more requests"); CORS restrictions noted for browser use; "be defensive, can handle API downtime gracefully".
- **CO₂/emission-factor datasets (IDs confirmed from the datasets index):**
  - **265** — *Emission factor for electricity consumed in Finland – real time data* (consumption-based; includes imports; **updates every 3 min** per description) ✅
  - **266** — *Emission factor of electricity production in Finland – real time data* ✅
  - **396** — *Emission factor for electricity consumed in Finland – updated every 15 minutes* ✅
  (i.e., direct gCO₂/kWh equivalents — no fuel-mix math needed; history depth for these series must be checked per dataset page after keying in ⚠️; related "emission datasets" like "Kärna..."? none further found — search of full index found only these three.)
- Free (license: Fingrid open data licence).

### 6.2 Sweden (and Nordic generally)
- **Svenska kraftnät (SvK):** no public hourly CI dataset/API (api.svk.se does not resolve ⚠️ verified DNS fail). Observed values / observed-number data downloadable from svk.se (Excel; fuel mix SE1–SE4) ⚠️ not verified this session (unreachable docs). Hourly fuel-mix per SE zone is available via **ENTSO-E** → compute CI ourselves. Fingrid-No/Estonia links give import flows.
- Alternative for Nordic zone CI: Electricity Maps (paid) or open project **"NordPool" …** none official. For **DE: Energy-Charts below.**

---

## 7. Germany — Fraunhofer ISE Energy-Charts (energy-charts.info) — TOP PICK for DE
- **API:** https://api.energy-charts.info — Swagger UI at root ✅; OpenAPI spec `https://api.energy-charts.info/openapi.json` ✅ (title "Energy-Charts API", version 2.0, license name "Publishing notes" → https://energy-charts.info/publishing-notes.html).
- **Endpoints (from spec, 37 paths incl. v2):** `/v2/public_power` (actual generation by source per country/bidding zone), **`/v2/public_power_forecast`**, `/v2/total_power`, `/v2/installed_power`, `/v2/price`, `/v2/price_current`, `/v2/price_next_day`, `/v2/cbet` (cross-border electricity trade), `/v2/cbpf`, `/v2/signal`, `/v2/ren_share_forecast`, share endpoints, `/v2/frequency`. **No CO₂ endpoint in the API spec.**
- **FREE, NO KEY** ✅ live-verified:
  - Actuals: `GET https://api.energy-charts.info/v2/public_power?country=de&start=2025-10-01T00:00Z&end=2025-10-01T04:00Z&resolution=hour` → 200
    ```json
    {"schema_version":"2.0","endpoint":"public_power","country":"de","bidding_zone":null,
     "timezone":"Europe/Berlin","resolution":"PT15M","interval_minutes":15,"unit":"MW",
     "generated_at":"2026-11-04T05:47:25+01:00",
     "series":[{"id":"hydro_pumped_storage_consumption",...
    ```
  - Forecast: `GET https://api.energy-charts.info/v2/public_power_forecast?country=de&start=...&resolution=15m` → 200 with `series[{"id":"solar",...` ✅ — **day-ahead-horizon generation forecast available (for forecast-vs-actual pairing)**. (Timezone/format options in spec; ISO-8601 or Unix seconds.)
- **Carbon:** power/price/share only — the website's **"Emission factor"/Emissions charts (gCO₂/kWh for DE)** are on energy-charts.info as downloadable CSVs ⚠️ (client-rendered SPA, our fetch couldn't dump the raw series; historic known to ~2002). For **forecast-vs-actual CI**, use public_power + public_power_forecast and apply fuel EFs ourselves (publishing-notes license permits with attribution ⚠️ read PDF of publishing notes).
- **Coverage years:** DE from ~2000s; European neighbors (FR, NL, IT, AT…) at varying depth ⚠️ (not enumerated).

---

## 8. India
- **No official hourly carbon-intensity API** for the Indian grid found (searches: nil on Zenodo/HF; NITI ICED dashboard and Ember give annual aggregates) ⚠️ verified-by-absence.
- **Grid Controller of India (Grid-India, ex-POSOCO) — https://grid-india.in:**
  - Site is an SPA; **free downloadable reports** (no key): "**Daily Report**, Daily PSP Report, Daily VRE Report, Weekly Report, Monthly Reports, Monthly Ancillary Services reports…" ✅ (report names enumerated from the site's own JS bundle). Old POSOCO daily/PU reports give **generation by source (thermal/hydro/wind/solar…), demand, frequency — All-India and per-RLDC (NER/WR/ER/SR/NR)** typically as XLS/web tables ⚠️ exact download URLs not fixed this session (webcdn.grid-india.in hosts files); **coverage**: long-run historical (2012→) ⚠️.
  - **No CO₂ values** — compute per-hour/5-min CI using per-fuel emission factors (CEA CO₂ Baseline Database).
- **CEA CO₂ Baseline Database 📄:** Central Electricity Authority "CO₂ Baseline Database for the Indian Power Sector" — **Version 20.0 (Dec 2024)**, later **v21.0** listed on CEA site (https://cea.nic.in/api/cdm-report-version/view-pdf/en/76 viewable; landing https://cea.nic.in/cdm-co2-baseline-database/; staging mirror cea.adgstaging.in). Provides **annual grid emission factors (combined margin, tCO₂/MWh) for All-India and the five regional grids (incl. NER rest)** — the standard factor source to convert Grid-India's fuel-mix into gCO₂/kWh. Annual only. CarbonNeeti blog says v22.0 exists ⚠️.
- **Third-party:** energymap.in "India Energy Atlas" (commercial AI grid model ⚠️), NITI ICED (iced.niti.gov.in) for state-level dashboards, **Electricity Maps covers IN-WE, IN-SO, IN-NE zones** (paid; £/€6k/yr per country under current pricing ✅ from §3).

---

## 9. Japan
- **Honest summary: no official hourly carbon-intensity API.** Annually published emission factors (Ministry of the Environment per-prefecture/per-utility; JEPX/OCCTO area data) are the official state of play ⚠️ (standard knowledge; consistent with searches).
- **Academic open dataset (excellent fallback) — Zenodo record https://zenodo.org/records/18396311** ✅ fetched in full:
  - **Title:** "*Time-Varying Grid CO2 Emission Factors Derived from TSO-Level Generation Mix in Japan*" — Waseda University (Ihara, Fujimoto, Sugano, Mitsuoka, Hayashi), published **2026-01-28**, JST/SIP-funded.
  - **Content: hourly grid carbon intensity (kgCO₂/kWh) for FY2024 (Apr 2024–Mar 2025) for the 9 TSO areas**: Hokkaido, Tohoku, TEPCO, Chubu, Hokuriku, Kansai, Chugoku, Shikoku, Kyushu — separate CSVs (~770 kB each, 15 MB total) + auxiliary ZIP (demand, fuel-wise generation, fuel-wise CO₂ from lifecycle EFs). CC **BY 4.0**. DOI 10.5281/zenodo.18396311.
  - **Limitations:** one fiscal year, historical-only (no forecasts), TSO-area (not city) granularity.
- **Other Japan pointers:** github.com/FraserTooth/japan_grid_carbon_api (community API computing Tokyo hourly average CI from public data ⚠️ unverified freshness); TEPCO/OCCTO publish area supply & demand + generation mix hourly (⏱ from which CI can be computed; TEPCO historical open CSVs ⚠️ not verified this session); Environment Ministry publishes annual utility emission factors ⚠️.

---

## 10. Australia — OpenNEM / OpenElectricity ✅
- **Rebrand (2025):** opennem.org.au → **OpenElectricity** (openelectricity.org.au); API base **https://api.opennem.org.au** with v4 API; spec at `https://api.opennem.org.au/openapi.json` ✅ ("OpenElectricity", version 4.5.20).
- **Key endpoints (spec):**
  - `GET /v4/data/network/{network_code}` — time series (5m…1y intervals) with `metrics` incl. **`emissions` (CO₂-equivalent tonnes)**, energy, power, renewable_* flows by `fueltech_group` per `network_region` (NSW1, QLD1, SA1, TAS1, VIC1, WEM/…); also `AEMO_ROOFTOP` network (current: "**Network AEMO_ROOFTOP not supported**" per live test — v4 rostering may differ from v3).
  - `GET /v4/market/network/{network_code}` — price/demand metrics (items "energy","emissions" unsupported there).
  - Badges: old v3 paths `api.opennem.org.au/v3/stats/...` now **410 Gone** ✅ (v3 sunsetted).
- **LIVE-VERIFIED, working keyless:**
  - `GET …/v4/data/network/NEM?metrics=emissions&interval=1d&date_start=2025-10-01T00:00:00&date_end=2025-10-02T00:00:00&network_region=NSW1` → **200** `{"version":"4.5.20","success":true,"data":[{"network_code":"NEM","metric":"emissions","unit":"t","interval":"1d",...` ✅
  - `GET …/v4/market/network/NEM?metrics=demand&interval=1h&date_start=...` → **200** ✅
  - Spec notes `HTTPBearer` security but unauthenticated calls succeed for the data/market endpoints (bearer likely required for account endpoints like `/v4/me`, or enforced later) ⚠️ — treat as "free with generous limits; register for higher use".
- **Emissions coverage:** NEM + WEM (WA) networks, per region (state), with per-fueltech energy/power → both **tonnes** and mix; AEMO publishes via open datasets (wem5m/NEM reports). Coverage years: NEM energy from ~2000s (OpenNEM legacy 1999 fossil records) ⚠️. v3 archives of `stats/...json` historically went back to 1998 (fossil) — replace via v4 `date_start` with 1d interval; **verify depth after building client.**
- **CSM:** no official NEM-wide gCO₂/kWh API from AEMO — OpenElectricity computes it (from fuel energy + EFs). Negative: no forecast of CO₂.

---

## 11. Canada (brief — informational only)
- ⚠️ not verified this session; standard landscape: no national hourly CI API. Ontario IESO publishes hourly generation-by-fuel CSVs (ieso.ca). Alberta AESO publishes hourly supply/dispatch map data. Canada Energy Regulator (CER) publishes annual provincial mixes; Environment and Climate Change Canada's National Inventory Report supplies annual per-province EFs. Sizeable startups outside project scope.

---

## Appendix A — Live response snippets (verbatim, abbreviated)
1. UK CI API national history ✅:
   `{"from":"2025-09-01T00:00Z","to":"2025-09-01T00:30Z","intensity":{"forecast":62,"actual":68,"index":"low"}}` …
2. UK CI API regional history ✅ (forecast-only intensity entries + generation mix per region).
3. UK CI regionid-path probes ✅ returned AWS-gateway "Missing Authentication Token" 400s.
4. CAISO `/outlook/current/co2.csv`, `/outlook/current/co2_YESTERDAY.csv`, `/outlook/history/{2019|2020}.csv` ✅ (headers/values above); 2018/2017 → 404.
5. CAISO `/outlook/data/co2-historical-chart.json` ✅ ({"name":"2014","data":[["Jan.",5615497.82],…]} monthly tonnes).
6. EIA bulk meta `EIA930_File_List_Meta.csv` ✅ + `EIA930_BALANCE_2024_Jan_Jun.csv` header ✅; 930 API key gate ✅.
7. Elexon `data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH|FUELINST` ✅ real records.
8. Fingrid `/api/datasets?limit=10` → 401 ✅ (key required); instructions text (10k/24h, 1/2s) ✅.
9. Energy-Charts `/v2/public_power` & `/v2/public_power_forecast` (de) ✅.
10. OpenElectricity v4 emissions metric (NEM/NSW1 daily t) ✅; v3 path → 410 Gone ✅.

## Appendix B — Decision matrix ("which look best for a student project")
| Region | Best free signal | Forecast-vs-actual possible? | Effort |
|---|---|---|---|
| UK (GB, national) | NESO CI API (direct gCO₂/kWh) | **YES — historical forecast+actual per 30 min, built-in** ✅ | trivial |
| UK (GB, regional×14) | same API, `/regional` | forecast built-in; actuals need re-query trick ⚠️ | low |
| USA (CAISO, single BA) | `/outlook/history/{date}/co2.csv` + `fuelsource.csv` | demand/price forecasts only; **no CO₂ forecast**; own CI math feasible | low |
| USA (all BAs) | EIA-930 bulk CSVs (2015→2026) + per-BA Excel CO₂ (2018→) | demand forecast (day-ahead) | medium |
| USA (annual anchors) | EPA eGRID2023 (subregions CAMX etc.) | n/a (annual) | trivial |
| Germany | Energy-Charts API (free, no key) generation actual+**forecast** + own EFs | YES for generation mix | medium |
| Europe (NL, SE, FI, DE) | ENTSO-E (free token) + own EFs; **Fingrid**IRECT emission-factor datasets for Finland | ENTSO-E = data-only (no forecasts of mix); Fingrid real-time only | medium |
| Japan | Zenodo Waseda FY2024 hourly by 9 TSOs | historical only | low |
| India | Grid-India daily/occasion reports + CEA annual EFs | no CI forecasts; coarse (daily) ⚠️ | high |
| Australia/NEM | OpenElectricity v4 `emissions` + `energy` (per state, hourly+) | no emission forecast | low–med |
| Paid fallback (any zone) | Electricity Maps (€6k/yr/country) incl. `/forecast` endpoint; WattTime free tier (CAISO_NORTH marginal+avg, 72h forecasts) | YES (EM forecast endpoint) | trivial |

**Suggested project data backbone:** UK NESO CI API (primary, forecasts+history+regional granularity) + US CAISO outlook history + EIA-930 bulk (USA deterministic) + Energy-Charts (DE) + ENTSO-E/Fingrid (NL/SE/FI) + OpenElectricity v4 (AU) + Zenodo Waseda (JP) + CEA-coordinate (IN). Uncertainty-quantification: UK national/regional is the only source shipping historical forecast-vs-actual pairs out of the box; everywhere else construct pseudo-forecast pairs (e.g., train our own forecaster on history) and say so honestly in the thesis.

## Appendix C — Things the partner agent should still check
1. UK docs page docs.carbonintensity.org.uk — rate-limit number + exact regionid endpoint pattern + whether regional **actuals** exist in history (connection was reset for us).
2. CAISO exact inception date of `/outlook/history/*` (between 2017-01 and 2019-01).
3. EIA per-BA Excel exact download URL pattern (dashboard "knownissues/xls/" path exists).
4. ENTSO-E R3 request endpoint contract (POST/GET shapes) — "Request Endpoint" article.
5. OpenElectricity: history depth per metric (`date_start` deep probes), and auth evolution (bearer enforcement).

*End of note B.*
