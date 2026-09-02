# Beeframe

Beeframe is a phone-first apiary manager that runs entirely in the browser. Python Shiny Core and Polars run in Shinylive/WebAssembly; Google OAuth, Picker, and Sheets requests run in the top-level page and communicate with Shiny through a same-origin JSON bridge. There is no application server, client secret, service account, or database.

## Architecture

- `app.py`: Shiny application state, hierarchy, dialogs, and workflows.
- `beeframe/schemas.py`: worksheet fields, Polars types, defaults, labels, choices, and editability.
- `beeframe/validation.py`: workbook and record validation with worksheet, row, column, value, and rule errors.
- `beeframe/naming.py`: UUIDs, local plant names, and codes that exclude `O` and zero.
- `beeframe/domain.py`: transactional archive, restore, move, ordering, uniqueness, occupancy, and captured-ID edit logic.
- `beeframe/hierarchy.py` and `operations.py`: hierarchy display helpers, notes, and measurements.
- `beeframe/sheets.py`: Google matrix ↔ Polars conversion and recognized-column updates.
- `beeframe/modules/`: reusable connection and fixed-navigation Shiny modules.
- `www/google-sheets-parent.js`: top-level OAuth, Picker, Sheets I/O, refresh-before-write logic, and localhost mock.
- `www/shiny-bridge.js`: validated iframe messaging.
- `www/app-ui.js`: entity selection plus client-side grid, search, and notes-table interactions.
- `scripts/export.sh`: creates a minimal Shinylive bundle without tests or an old generated site.

The workbook is loaded into Polars DataFrames once after validation. Navigation filters those in-memory frames. Before a write, the parent page refreshes the affected worksheet and locates records by immutable ID. Updates write only recognized cells, preserving unknown columns and values. Successful writes return refreshed matrices for the affected frames.

## Workbook schema

Every primary record has `id`, `created_at`, `updated_at`, and `is_archived`. IDs are canonical URL-safe UUID strings; timestamps are UTC ISO 8601 values. Times display in `America/New_York` with daylight-saving rules.

- `metadata`: `key`, `value`; includes `application_name`, `schema_version`, and `initialized_at`.
- `apiaries`: name, grid columns, grid rows, and the cardinal direction shown at the top.
- `hives`: apiary ID, owner, name, grid column/row, and status.
- `boxes`: hive ID, position, capacity, type, and generated name.
- `frames`: box ID, position, generated name.
- `equipment_types`: user-defined name.
- `equipment`: generated code, type ID, and nullable hive ID (`null` means Archived).
- `notes`: target type/ID, nature, description, archive fields.
- `measurements`: frame ID, scope, comb color, eight independent percentages, queen-cell count.

Additional worksheet columns are ignored by validation and preserved by updates. Empty optional cells become Polars nulls. This grid schema intentionally does not migrate older geographic workbooks. Beeframe never auto-modifies an incompatible workbook.

## Google Cloud setup

1. Enable the Google Sheets API, Google Drive API, and Google Picker API in the existing Cloud project.
2. Configure Google Auth Platform branding, audience, and test users if the app remains in Testing.
3. Request only `https://www.googleapis.com/auth/drive.file`.
4. Use a Web application OAuth client. Authorized JavaScript origins should include `http://localhost:8008` and the GitHub Pages origin, without a repository path.
5. Restrict the Picker browser API key to the local/GitHub Pages website patterns and the Google Picker API.

The existing public browser client ID, restricted API key, and project number remain in `www/google-sheets-parent.js`. They are not secrets. Never add a client secret. Access tokens remain in memory and disappear on refresh.

Firefox may block Google Picker cross-site storage. If Picker fails or times out, turn off Enhanced Tracking Protection for the Beeframe site and retry. The app reports this guidance on Picker failure.

## Local build and tests

Python 3.12 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
BEEFRAME_SHINYLIVE=.venv/bin/shinylive bash scripts/export.sh build-site
python scripts/serve.py build-site
```

The export command safely replaces an existing generated `build-site` but refuses to replace an unrelated directory. The local server disables browser caching. Open <http://localhost:8008/>. For a no-auth seeded smoke workbook, use <http://localhost:8008/?mock=seeded>. Mock mode is accepted only on `localhost`/`127.0.0.1` and refuses writes.

## Manual end-to-end test

1. Open the exported app on a phone-sized viewport and confirm the connection screen and privacy link.
2. Connect Google and choose an empty test spreadsheet you own.
3. Confirm initialization creates exactly the nine worksheets and metadata.
4. Create an apiary grid, place a hive in a cell, then create bulk boxes, frames, an equipment type, and bulk equipment.
5. Verify generated codes, positions, equipment assignment, Archived mode, search ancestry, and the fixed toolbar.
6. Add/edit/archive a note; record a measurement and verify the one-hour warning on a second attempt.
7. Move sibling boxes/frames, move equipment, and verify refreshed positions.
8. Archive a frame, box, and hive in a disposable workbook and inspect the retained Sheet rows and recursive archive flags.
9. Add a custom worksheet column manually, edit an object in Beeframe, and confirm the custom value remains unchanged.
10. Make one incompatible manual edit and confirm Beeframe reports the exact worksheet/row/column/value/rule without changing the workbook.

The final real-Google test requires the user to authenticate and select a Sheet. Automated tests never authenticate or write to a real Google account.

## Concurrency and reliability

Google Sheets has no reliable row-level lock or compare-and-swap operation for this design. Beeframe refreshes relevant data before each write, resolves rows by immutable ID, and then uses last-write-wins. Rare simultaneous edits can overwrite one another. The app does not claim to lock records.

Reads may be safely retried. Ambiguous writes are not retried automatically. For bulk equipment, Beeframe refreshes the equipment worksheet and reports which proposed codes exist. Submit controls are disabled while writes are active.

## Grids and privacy

Apiaries are abstract letter-by-number grids. Users choose the grid dimensions and the cardinal direction shown at the top. Hive locations occupy one grid cell and require no map or location service.

See the [privacy policy](privacy.html). Archived records remain recoverable through valid hierarchy moves; permanent deletion and schema migration are intentionally not provided.

## GitHub Pages deployment

1. In **Settings → Pages**, choose **GitHub Actions** as the source.
2. Push to `main`, or run **Deploy Shinylive to GitHub Pages** from the Actions tab.
3. The workflow installs `requirements-dev.txt`, runs `scripts/export.sh site`, uploads `site`, and deploys it.
4. Confirm the Pages URL, `/privacy.html`, Google authorized origin, and API-key referrer restriction after deployment.

For this repository the expected URL is <https://hedonical.github.io/beeframe/>.
