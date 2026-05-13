# Excel Report + Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `daily-price-sync` to generate an Excel with all products from PostgREST local and send it via Gmail OAuth2 at the end of the daily sync, plus a Manual Trigger that skips the scraping and sends the report on demand.

**Architecture:** Edit `n8n/workflows/daily-price-sync.json` directly to add 4 new nodes (Manual Trigger, HTTP GET /productos, Spreadsheet File, Gmail Send) and their connections. Config vars `REPORT_EMAIL_FROM` and `REPORT_EMAIL_TO` live in `.env` and are injected to n8n via `docker-compose.yml`. Gmail OAuth2 credential is created once per installation in n8n UI.

**Tech Stack:** n8n nodes (`manualTrigger`, `httpRequest` v4.2, `spreadsheetFile`, `gmail`), PostgREST local, Gmail OAuth2, Docker env vars.

---

## File Map

| File | Change |
|------|--------|
| `.env.example` | Add `REPORT_EMAIL_TO` (+ `REPORT_EMAIL_FROM` comentado como doc) |
| `docker-compose.yml` | Inject `REPORT_EMAIL_TO` to n8n service |
| `n8n/workflows/daily-price-sync.json` | Add 4 nodes + 4 connections |

No changes to `scraper/`, `db/`, or `sources.yml`.

---

### Task 1: Add email env vars to config files

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add vars to `.env.example`**

Open `.env.example` and add this block at the end (after the existing APIs section):

```
# ==========================================================================
# Email — reporte de precios
# REPORT_EMAIL_FROM: solo documentación — indica qué cuenta Gmail conectar
#   en n8n Credentials. El remitente real lo determina la cuenta OAuth2.
# REPORT_EMAIL_TO: destinatarios del reporte, separados por coma, sin espacios.
# ==========================================================================
# REPORT_EMAIL_FROM=reportes@gmail.com
REPORT_EMAIL_TO=usuario@ejemplo.com,otro@ejemplo.com
```

- [ ] **Step 2: Inject `REPORT_EMAIL_TO` into n8n service in `docker-compose.yml`**

Open `docker-compose.yml`. In the `n8n > environment` block, after `SCRAPER_URL: ${SCRAPER_URL}`, add:

```yaml
      REPORT_EMAIL_TO: ${REPORT_EMAIL_TO}
```

- [ ] **Step 3: Commit**

```bash
git add .env.example docker-compose.yml
git commit -m "feat: add email report env vars to config files"
```

---

### Task 2: Update local `.env` and restart n8n

**Files:**
- Modify: `.env` (gitignored, not committed)

- [ ] **Step 1: Add `REPORT_EMAIL_TO` to `.env`** with real values:

```
REPORT_EMAIL_TO=destinatario1@ejemplo.com,destinatario2@ejemplo.com
```

- [ ] **Step 2: Restart n8n** to pick up the new env vars:

```bash
docker-compose up -d n8n
```

Expected output: `Container bimeg-n8n  Started` or `Started`.

- [ ] **Step 3: Verify n8n is healthy**

```bash
docker-compose ps n8n
```

Expected: status `Up` and health `healthy` (or `starting`). Wait ~15 s if still starting.

---

### Task 3: Set up Gmail OAuth2 credential in n8n (manual, one-time)

This step cannot be automated — it requires browser interaction.

- [ ] **Step 1:** Open n8n at http://localhost:5678 and log in.

- [ ] **Step 2:** Click the top-right menu → **Credentials** → **Add credential**.

- [ ] **Step 3:** Search for **"Gmail OAuth2 API"** and select it.

- [ ] **Step 4:** Fill in:
  - **Client ID:** `832225155473-on6fc7atfchmllgvmphqqpelt6g4h1ov.apps.googleusercontent.com`
  - **Client Secret:** (the GOCSPX-... value — do not hard-code here, use your `.env` or the downloaded JSON)

- [ ] **Step 5:** Click **"Sign in with Google"** — a browser popup opens. Authenticate with the Gmail account that will send the reports.

- [ ] **Step 6:** Click **Save**. The credential name will default to `"Gmail OAuth2 API"` — you can rename it to `"bimeg-gmail"` for clarity.

---

### Task 4: Add 4 new nodes to `daily-price-sync.json`

**Files:**
- Modify: `n8n/workflows/daily-price-sync.json`

The strategy: edit the JSON directly to insert the new node objects and connection entries. The workflow engine reads this JSON when you import it.

**Context from reading the current JSON:**
- `"All sources processed"` node is at position `[672, 64]` — this is the entry point for the auto trigger path.
- The `"connections"` object uses node names as keys.
- Existing rightmost nodes are at x=1792 — place the new chain far right to avoid overlap.

- [ ] **Step 1: Add 4 node objects to the `"nodes"` array**

Open `n8n/workflows/daily-price-sync.json`. At the end of the `"nodes": [...]` array (before the closing `]`), add a comma after the last node, then paste these 4 objects:

```json
    {
      "id": "c7e8f9a0-b1c2-4d3e-8f9a-0b1c2d3e4f51",
      "name": "Manual Trigger",
      "type": "n8n-nodes-base.manualTrigger",
      "typeVersion": 1,
      "position": [0, -288],
      "parameters": {}
    },
    {
      "id": "c7e8f9a0-b1c2-4d3e-8f9a-0b1c2d3e4f52",
      "name": "GET /productos",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [2100, 64],
      "parameters": {
        "method": "GET",
        "url": "={{ $env.SUPABASE_URL }}/productos?order=fuente.asc,descripcion.asc",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            { "name": "apikey", "value": "={{ $env.SUPABASE_ANON_KEY }}" },
            { "name": "Authorization", "value": "=Bearer {{ $env.SUPABASE_ANON_KEY }}" }
          ]
        },
        "options": {}
      }
    },
    {
      "id": "c7e8f9a0-b1c2-4d3e-8f9a-0b1c2d3e4f53",
      "name": "Generate Excel",
      "type": "n8n-nodes-base.spreadsheetFile",
      "typeVersion": 1,
      "position": [2324, 64],
      "parameters": {
        "operation": "toFile",
        "fileFormat": "xlsx",
        "options": {
          "fileName": "=precios-{{ $now.format('yyyy-MM-dd') }}.xlsx"
        }
      }
    },
    {
      "id": "c7e8f9a0-b1c2-4d3e-8f9a-0b1c2d3e4f54",
      "name": "Send Report Email",
      "type": "n8n-nodes-base.gmail",
      "typeVersion": 2.1,
      "position": [2548, 64],
      "parameters": {
        "sendTo": "={{ $env.REPORT_EMAIL_TO }}",
        "subject": "=Precios BIMEG — {{ $now.format('dd/MM/yyyy') }}",
        "emailType": "text",
        "message": "Adjunto el reporte de precios del día.",
        "options": {
          "attachmentsUi": {
            "attachmentsBinary": [
              { "property": "data" }
            ]
          },
          "senderName": "BIMEG Precios"
        }
      }
    }
```

- [ ] **Step 2: Add connections for the 4 new nodes**

In the `"connections"` object (at the bottom of the JSON), add these 4 entries. The `"connections"` object currently ends without an entry for `"All sources processed"` — add all 4:

```json
    "All sources processed": {
      "main": [[{ "node": "GET /productos", "type": "main", "index": 0 }]]
    },
    "Manual Trigger": {
      "main": [[{ "node": "GET /productos", "type": "main", "index": 0 }]]
    },
    "GET /productos": {
      "main": [[{ "node": "Generate Excel", "type": "main", "index": 0 }]]
    },
    "Generate Excel": {
      "main": [[{ "node": "Send Report Email", "type": "main", "index": 0 }]]
    }
```

Make sure the last existing connection entry (`"INSERT new rows (Supabase)"`) has a comma before these new entries.

- [ ] **Step 3: Validate JSON syntax**

Run this to catch syntax errors before importing:

```bash
python -c "import json; json.load(open('n8n/workflows/daily-price-sync.json')); print('JSON OK')"
```

Expected output: `JSON OK`. If you get a parse error, fix the JSON (usually a missing comma or brace).

---

### Task 5: Import updated workflow into n8n and link Gmail credential

- [ ] **Step 1:** In n8n UI, go to **Workflows**.

- [ ] **Step 2:** Open the existing `daily-price-sync` workflow.

- [ ] **Step 3:** Click the **⋮ menu** (top right of the workflow editor) → **Import from file** → select `n8n/workflows/daily-price-sync.json`.

  n8n will merge the changes into the existing workflow. If it asks to overwrite, confirm.

  > **Alternative if Import doesn't update in place:** Delete the old workflow and import the JSON as a new one. Re-activate it afterwards.

- [ ] **Step 4:** Verify the 4 new nodes appear on the canvas:
  - `Manual Trigger` (top left area, above Schedule Trigger)
  - `GET /productos` (far right, connected from `All sources processed` and `Manual Trigger`)
  - `Generate Excel` (right of GET /productos)
  - `Send Report Email` (rightmost)

- [ ] **Step 5:** Click on the **Send Report Email** node → in the **Credential** field, select `"Gmail OAuth2 API"` (the credential created in Task 3).

- [ ] **Step 6:** Click **Save** (top right of the workflow editor).

---

### Task 6: Manual test — trigger report and verify email

- [ ] **Step 1: Verify local DB has data**

```bash
docker-compose exec postgres psql -U postgres -d postgres -c "SELECT fuente, COUNT(*) FROM productos GROUP BY fuente;"
```

Expected: at least one row with a count > 0. If the table is empty, run the full sync first: in n8n UI, open the workflow and click **"Test workflow"** from the Schedule Trigger node to run the full scrape cycle, or insert a test row:

```bash
docker-compose exec postgres psql -U postgres -d postgres -c "INSERT INTO productos (descripcion, precio, fuente, empresa, proveedor) VALUES ('Producto test', 100.00, 'test', 'Test SA', 'Test') RETURNING id;"
```

- [ ] **Step 2: Trigger the report manually**

In n8n UI, click the **Manual Trigger** node → click **"Execute node"** (or use the workflow Test button while the Manual Trigger is selected as start node).

- [ ] **Step 3: Check execution results in n8n**

Verify each node in the execution panel:

| Node | Expected output |
|------|----------------|
| `GET /productos` | Array of product objects (JSON) |
| `Generate Excel` | Binary field named `data` with file `precios-YYYY-MM-DD.xlsx` |
| `Send Report Email` | JSON with `messageId` field (Gmail API response) |

If `Send Report Email` shows an error, the most common causes:
- Credential not linked → redo Step 5 of Task 5
- `REPORT_EMAIL_TO` not picked up → check `docker-compose logs n8n | grep REPORT`
- Gmail API quota → wait a minute and retry

- [ ] **Step 4: Check the Gmail inbox of `REPORT_EMAIL_TO`**

- Subject: `Precios BIMEG — DD/MM/YYYY`
- Attachment: `precios-YYYY-MM-DD.xlsx`
- Open the Excel — verify it has these columns: `fuente`, `proveedor`, `empresa`, `descripcion`, `marca`, `categoria`, `precio`, `unidad_medida`, `disponibilidad`, `actualizado_en`

- [ ] **Step 5: Clean up test row if you inserted one**

```bash
docker-compose exec postgres psql -U postgres -d postgres -c "DELETE FROM productos WHERE fuente = 'test';"
```

---

### Task 7: Export final workflow JSON and commit everything

n8n may have adjusted node positions or added internal metadata during the import. Export the canonical version.

- [ ] **Step 1: Export from n8n UI**

In the workflow editor → **⋮ menu** → **Download** → saves `daily-price-sync.json` to your Downloads folder.

- [ ] **Step 2: Replace the repo file**

```bash
copy "%USERPROFILE%\Downloads\daily-price-sync.json" "n8n\workflows\daily-price-sync.json"
```

(On Linux/Mac: `cp ~/Downloads/daily-price-sync.json n8n/workflows/daily-price-sync.json`)

- [ ] **Step 3: Verify the new nodes are in the exported file**

```bash
python -c "
import json
w = json.load(open('n8n/workflows/daily-price-sync.json'))
names = [n['name'] for n in w['nodes']]
for expected in ['Manual Trigger', 'GET /productos', 'Generate Excel', 'Send Report Email']:
    status = '✓' if expected in names else '✗ MISSING'
    print(f'{status}  {expected}')
"
```

Expected: all 4 lines show `✓`.

- [ ] **Step 4: Commit everything**

```bash
git add .env.example docker-compose.yml n8n/workflows/daily-price-sync.json
git commit -m "feat: add daily Excel report generation and Gmail email delivery"
```

---

## Troubleshooting reference

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `GET /productos` returns empty array | Local DB has no data | Run full sync or insert test row (Task 6 Step 1) |
| `Send Report Email` error: "No credential" | Credential not linked in node | Task 5 Step 5 |
| `Send Report Email` error: "Invalid grant" | OAuth token expired | Reconnect credential in n8n Credentials UI |
| Excel attachment is empty | `data` field name mismatch | In `Send Report Email`, change attachment property from `data` to the actual binary field name shown in `Generate Excel` output |
| `REPORT_EMAIL_TO` resolves to empty | Var not injected to container | `docker-compose up -d n8n` after editing `.env` |
| JSON parse error in Task 4 Step 3 | Missing comma or brace | Use a JSON formatter (e.g. `python -m json.tool n8n/workflows/daily-price-sync.json`) to identify the line |
