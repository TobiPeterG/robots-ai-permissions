# robots-ai-permissions

Collection of tools to bulk-download a large corpus of domains, fetch and clean up their `robots.txt`, `ai.txt` and `llms.txt`, analyze overlap and conflicts, and generate summary reports, as well as an already gathered [data set](/data/crawl/2025-07-05).

## Use the Data Set

To use the data set, you will first need to combine the 3 file parts. For this run the following commands in the directory with the split files:

   ```bash
   cat 2025-07-05.tar.gz* > 2025-07-05.tar.gz
   ```
   
Afterwards, you can unpack the archive using:

   ```bash
   tar xf 2025-07-05.tar.gz
   ```
   
Now you can run your own analysis on the data.

## 📦 Install

1. **Clone the repo**

   ```bash
   git clone https://github.com/TobiPeterG/robots-ai-permissions.git
   cd robots-ai-permissions
   ```

2. **Create & activate a virtualenv**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **(For `fetch-all`)** provide your ICANN CZDS credentials in `config.json`:

   ```jsonc
   {
     "icann.account.username": "YOUR_USERNAME",
     "icann.account.password": "YOUR_PASSWORD",
     "authentication.base.url": "https://account-api.icann.org",
     "czds.base.url": "https://czds-api.icann.org",
     "tlds": []
   }
   ```

---

## 🚀 Scripts

### 01-fetch-1M.py

**Purpose:**
Download the Tranco Top 1 Million list, extract public-suffix domains (PLDs), sort + dedupe, and split into 10 000-line chunks.

**Usage**

```bash
./01-fetch-1M.py [--force]
```

* **Inputs:** none
* **Flags:**

  * `--force` — ignore existing output and re-download/rebuild
* **Outputs:** under `txt_downloads/YYYY-MM-DD/`:

  * `domains_sorted.txt` — all unique, sorted PLDs
  * `splits/` — `split_00000.txt`, `split_00001.txt`, … (10 000 domains each)

---

### 01-fetch-all.py

**Purpose:**
Fetch zone files from ICANN CZDS, CommonCrawl, Tranco and CitizenLab lists; extract PLDs; merge-sort + split.

**Usage**

```bash
./01-fetch-all.py [--force]
```

* **Requires** `config.json` for CZDS credentials
* **Inputs:** none
* **Outputs:** under `txt_downloads/YYYY-MM-DD/`:

  * `zones/` – raw `.zone` files
  * `domains_by_zone/` – one `.txt` per zone file
  * `domains_sorted.txt` – merged unique PLDs
  * `splits/` – 10 000-line chunks

---

### 02-download\_splits.py

**Purpose:**
For each `split_XXXXX.txt`, create a folder of per-domain subfolders and download `robots.txt`, `ai.txt`, and `llms.txt`.

**Usage**

```bash
./02-download_splits.py [--force]
```

* **Inputs:** `txt_downloads/YYYY-MM-DD/splits/*.txt`
* **Flags:** `--force` — re-fetch even if already exists
* **Outputs:** under `txt_downloads/YYYY-MM-DD/files/`:

  ```
  split_00000/
    example.com/robots.txt
    example.com/ai.txt
    example.com/llms.txt
  split_00001/
    …
  ```

---

### 03-clean\_downloads.py

**Purpose:**
Validate and prune bad downloads: remove files masquerading as HTML, missing `User-Agent` (for robots/ai), or non-Markdown `llms.txt`.

**Usage**

```bash
./03-clean_downloads.py
```

* **Inputs:** downloaded files under `txt_downloads/YYYY-MM-DD/files/split_*/<domain>/{robots.txt,ai.txt,llms.txt}`
* **Outputs:** deletes invalid files in place and prints a summary of removals

---

### 04-analyze\_downloads.py

**Purpose:**
Scan all domain subfolders and record which of the three files exist for each domain.

**Usage**

```bash
./04-analyze_downloads.py [--root txt_downloads] [--out analysis_output]
```

* **Inputs:**

  * `--root`: download root (default `txt_downloads/`)
* **Outputs:** under `analysis_output/`:

  * `domain_files_map.csv` — mapping of `domain,files`
  * `plds_with_robots.txt`, `plds_with_ai_or_llms.txt`, `plds_with_no_files.txt`

---

### 05-summarize\_counts.py

**Purpose:**
Summarize counts from `domain_files_map.csv`: how many domains have each combination of files.

**Usage**

```bash
./05-summarize_counts.py [--analysis-dir analysis_output]
```

* **Inputs:** `analysis_output/domain_files_map.csv`
* **Outputs:** printed counts for each category

---

### 06-map-permissions.py

**Purpose:**
Parse every domain’s `robots.txt` and `ai.txt` via `urllib.robotparser`, build a JSON map of per–UA “allow” and “disallow” lists.

**Usage**

```bash
./06-map-permissions.py [--root txt_downloads] [--csv analysis_output/domain_files_map.csv] [--out permissions_map.json]
```

* **Inputs:** download root & CSV of domains with both files
* **Outputs:** `permissions_map.json` (per-domain, per–UA permission maps)

---

### 07-diff-permissions.py

**Purpose:**
Diff `robots` vs `ai` rules per UA, producing a JSON of shared vs unique rules.

**Usage**

```bash
./07-diff-permissions.py
```

* **Inputs:** `permissions_map.json`
* **Outputs:** `permissions_diff.json`

---

### 08-find-ai-conflicts.py

**Purpose:**
Report line-level conflicts for known AI crawler UAs (e.g., GPTBot, ClaudeBot) between `robots.txt` and `ai.txt`.

**Usage**

```bash
./08-find-ai-conflicts.py [--root txt_downloads] [--csv analysis_output/domain_files_map.csv] [--map permissions_map.json]
```

* **Outputs:** human-readable conflict report

---

### 09-find-exp-directives.py

**Purpose:**
Scan for experimental directives `DisallowAITraining:` or `Content-Usage:` in `robots.txt` and `ai.txt`.

**Usage**

```bash
./09-find-exp-directives.py [--root txt_downloads] [--csv analysis_output/domain_files_map.csv]
```

* **Outputs:** table of domain, file, directive, value, and line

---

### 10-compare-llms.py

**Purpose:**
Check every `llms.txt` link target against `robots.txt` and `ai.txt` blocking rules.

**Usage**

```bash
./10-compare-llms.py [--root txt_downloads] [--csv analysis_output/domain_files_map.csv]
```

* **Outputs:** list of conflicts (domain, line, URL, blocking file)

---

### 11-typos.py

**Purpose:**
Detect typos in UA strings and suggest corrections based on known AI crawler names.

**Usage**

```bash
./11-typos.py [--csv analysis_output/domain_files_map.csv] [--map permissions_map.json]
```

* **Outputs:** table of domain, file, unknown UA, suggested correction

---

### 12-explicit-declarations.py

**Purpose:**
Aggregate counts of explicit UA allow/disallow occurrences and cross-file conflicts.

**Usage**

```bash
./12-explicit-declarations.py [--csv analysis_output/domain_files_map.csv] [--map permissions_map.json]
```

* **Outputs:** summary table of UA counts and conflicts

---

### 13-website-info.py

**Purpose:**
Enrich analysis of domains with AI-specific files by fetching geolocation (Whois, IP-API) and inferring industry from TLD.

**Usage**

```bash
python3 scripts/13-website-info.py [--csv analysis_output/domain_files_map.csv] [--workers N]
```

* **Inputs:**

  * `analysis_output/domain_files_map.csv` with domains and file presence
  * Optional `--workers` to set concurrent lookup threads (default 16)
* **Outputs:**

  * Printed table with columns: Files, Domain, Country (Whois), Country (ip-api), Industry (TLD)
  * Country distribution summary by Whois
  * Industry distribution summary by TLD

---

With this pipeline you can:

1. **Fetch** large domain lists (Tranco or CZDS/CC/…)
2. **Download** crawler directives and LLMS hints
3. **Clean** invalid downloads
4. **Analyze** presence/absence
5. **Map** and **diff** permissions
6. **Spot** experimental AI-specific directives
7. **Check** if any `llms.txt` links into disallowed paths
8. **Catch** typos in UA blocks
9. **Summarize** explicit allow/disallow counts and conflicts
10. **Enrich** domain metadata with country and industry information

Happy auditing!
