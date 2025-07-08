# robots-ai-permissions

Collection of tools to bulk-download a large corpus of domains, fetch and clean up their `robots.txt`, `ai.txt` and `llms.txt`, analyze overlap and conflicts, and generate summary reports.

## 📦 Install

1. **Clone the repo**

   ```bash
   git clone https://github.com/yourorg/robots-ai-permissions.git
   cd robots-ai-permissions
   ```

2. **Create & activate a virtualenv**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python dependencies**

   ```bash
   pip install requests tqdm publicsuffix2
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
Download the Tranco Top 1 Million list, extract public-suffix domains (PLDs), sort + dedupe, and split into 10 000-line chunks.

**Usage**

```bash
./01-fetch-1M.py [--force]
```

* **Inputs**: none
* **Optional flags**:

  * `--force` — ignore existing output and re-download/rebuild
* **Outputs** (under `txt_downloads/YYYY-MM-DD/`):

  * `domains_sorted.txt` — all unique, sorted PLDs
  * `splits/` — `split_00000.txt`, `split_00001.txt`, … (10 000 domains each)

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
* **Outputs** (in `txt_downloads/YYYY-MM-DD/`):

  * `zones/` – raw `.zone` files
  * `domains_by_zone/` – one `.txt` per zone file
  * `domains_sorted.txt` – merged unique PLDs
  * `splits/` – 10 000-line chunks

---

### 02-download\_splits.py

**Purpose:**
For each `split_XXXXX.txt`, create a folder of per-domain subfolders and download `robots.txt`, `ai.txt`, and `llms.txt`.

**Usage**

```bash
./02-download_splits.py [--force]
```

* **Inputs:**

  * `txt_downloads/YYYY-MM-DD/splits/*.txt`
* **Optional flags:**

  * `--force` — re-fetch even if already exists
* **Outputs** (under `txt_downloads/YYYY-MM-DD/files/`):

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

* **Inputs:**

  * `txt_downloads/YYYY-MM-DD/files/split_*/<domain>/{robots.txt,ai.txt,llms.txt}`
* **Outputs:**

  * Deletes invalid files in place
  * Prints a summary report of removals

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
* **Outputs** (in `analysis_output/`):

  * `domain_files_map.csv` — `domain,files` mapping
  * `plds_with_robots.txt`, `plds_with_ai_or_llms.txt`, `plds_with_no_files.txt`

---

### 05-summarize\_counts.py

**Purpose:**
Summarize counts from `domain_files_map.csv`: how many domains have each combination of files.

**Usage**

```bash
./05-summarize_counts.py [--analysis-dir analysis_output]
```

* **Inputs:**

  * `analysis_output/domain_files_map.csv`
* **Outputs:**

  * Printed counts for each category

---

### 06-map-permissions.py

**Purpose:**
Parse every domain’s `robots.txt` and `ai.txt` via `urllib.robotparser`, build a JSON map of per–UA “allow” and “disallow” lists.

**Usage**

```bash
./06-map-permissions.py [--root txt_downloads] [--csv analysis_output/domain_files_map.csv] [--out permissions_map.json]
```

* **Inputs:**

  * Download root & splits under `txt_downloads/YYYY-MM-DD/files/`
  * CSV with domains that have both files
* **Outputs:**

  * `permissions_map.json` —

    ```json
    {
      "example.com": {
        "robots": { "User-Agent1": {"allow":[…],"disallow":[…]}, … },
        "ai":     { … }
      },
      …
    }
    ```

---

### 07-diff-permissions.py

**Purpose:**
Diff `robots` vs `ai` rules per UA, producing a JSON of shared vs unique rules.

**Usage**

```bash
./07-diff-permissions.py
```

* **Inputs:**

  * `permissions_map.json`
* **Output:**

  * `permissions_diff.json` — lists of `allow_equal`, `allow_only_robots`, etc.

---

### 08-find-ai-conflicts.py

**Purpose:**
For a fixed list of AI crawler UAs (e.g. GPTBot, ClaudeBot, …), show exactly which lines and domains where `robots.txt` and `ai.txt` disagree (allow vs disallow).

**Usage**

```bash
./08-find-ai-conflicts.py [--root txt_downloads] [--csv analysis_output/domain_files_map.csv] [--map permissions_map.json]
```

* **Inputs:**

  * `domain_files_map.csv`, `permissions_map.json`
* **Output:**

  * Summary report + drill-down with file names and line numbers

---

### 09-find-exp-directives.py

**Purpose:**
Scan all `robots.txt` and `ai.txt` for experimental directives `DisallowAITraining:` or `Content-Usage:`.

**Usage**

```bash
./09-find-exp-directives.py [--root txt_downloads] [--csv analysis_output/domain_files_map.csv]
```

* **Inputs:**

  * CSV + downloaded files
* **Output:**

  * A table of each domain, filename, directive name, value, and line number

---

### 10-compare-llms.py

**Purpose:**
Check that every link in `llms.txt` isn’t pointing to a path blocked by that domain’s `robots.txt` or `ai.txt`.

**Usage**

```bash
./10-compare-llms.py [--root txt_downloads] [--csv analysis_output/domain_files_map.csv]
```

* **Inputs:**

  * CSV mapping + downloaded folder structure
* **Output:**

  * List of conflicts: domain, line, URL, which file blocks it

---

### 11-typos.py

**Purpose:**
Detect likely typos in UA strings: if a UA in `robots.txt` or `ai.txt` doesn’t match any known AI-crawler substring, suggest the closest match.

**Usage**

```bash
./11-typos.py [--csv analysis_output/domain_files_map.csv] [--map permissions_map.json]
```

* **Inputs:**

  * CSV + `permissions_map.json`
* **Output:**

  * Table of domain, file, unknown UA, and one close suggestion

---

### 12-explicit-declarations.py

**Purpose:**
Aggregate, across all domains, how many times each **explicit** UA string was allowed vs disallowed in `robots.txt` and `ai.txt`, and count cross-file conflicts.

**Usage**

```bash
./12-explicit-declarations.py [--csv analysis_output/domain_files_map.csv] [--map permissions_map.json]
```

* **Inputs:**

  * CSV + `permissions_map.json`
* **Output:**

  * A summary table sorted by most conflicts:

    ```
    UA                            R+   R-   A+   A-    C
    ----------------------------------------------------
    GPTBot                         10    0    1    2    1
    anthropic-ai                    5    0    0    3    0
    …
    ```

---

With this pipeline you can:

1. **Fetch** large domain lists (Tranco or CZDS/CC/…)
2. **Download** crawler directives and LLMS hints
3. **Clean** invalid downloads
4. **Analyze** presence/absence
5. **Map** and **diff** permissions
6. **Spot** experimental AI‐specific directives
7. **Check** if any `llms.txt` link into disallowed paths
8. **Catch** typos in UA blocks
9. **Summarize** explicit allow/disallow counts and conflicts

Happy auditing!
