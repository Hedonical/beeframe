(() => {
  // Public, origin-restricted browser configuration. Never place a client secret here.
  const CLIENT_ID = "383065765936-76gfqbkbrccp3btiu8sk037lgpivrtc4.apps.googleusercontent.com";
  const API_KEY = "AIzaSyCaADYsu8irX4RgvyAUf37rZdGxzsB8PZQ";
  const APP_ID = "383065765936";
  const SCOPE = "https://www.googleapis.com/auth/drive.file";
  const CHANNEL = "shinylive_google";
  const OPERATIONS = new Set(["choose_sheet", "disconnect", "load_workbook", "initialize", "append", "update_by_id", "mutate"]);
  const NAME_COLUMNS = { apiaries: "name", hives: "name", boxes: "name", frames: "name", equipment: "code" };
  const MOCK = ["localhost", "127.0.0.1"].includes(window.location.hostname) && new URLSearchParams(window.location.search).get("mock") === "seeded";
  let accessToken = null;
  let tokenClient = null;
  let selectedSpreadsheet = null;
  let pickerReady = null;
  let mockData = null;

  function mockWorkbook() {
    const ids = {
      apiary: "11111111-1111-4111-8111-111111111111", hive: "22222222-2222-4222-8222-222222222222",
      box: "33333333-3333-4333-8333-333333333333", box2: "33333333-3333-4333-8333-333333333334", box3: "33333333-3333-4333-8333-333333333335",
      frame: "44444444-4444-4444-8444-444444444444", frame2: "44444444-4444-4444-8444-444444444445", frame3: "44444444-4444-4444-8444-444444444446",
      type: "55555555-5555-4555-8555-555555555555", equipment: "66666666-6666-4666-8666-666666666666",
      note: "77777777-7777-4777-8777-777777777777", measurement: "88888888-8888-4888-8888-888888888888",
    };
    const now = new Date().toISOString();
    const base = (id) => ({ id, created_at: now, updated_at: now, is_archived: false });
    const schemas = {
      metadata: ["key", "value"],
      apiaries: ["id", "name", "grid_columns", "grid_rows", "up_direction", "created_at", "updated_at", "is_archived"],
      hives: ["id", "parent_apiary_id", "owner", "name", "grid_column", "grid_row", "status", "created_at", "updated_at", "is_archived"],
      boxes: ["id", "parent_hive_id", "position", "max_frames", "type", "name", "created_at", "updated_at", "is_archived"],
      frames: ["id", "parent_box_id", "position", "name", "created_at", "updated_at", "is_archived"],
      equipment_types: ["id", "name", "created_at", "updated_at", "is_archived"],
      equipment: ["id", "code", "equipment_type_id", "parent_hive_id", "created_at", "updated_at", "is_archived"],
      notes: ["id", "target_type", "target_id", "nature", "description", "archived", "archived_at", "created_at", "updated_at", "is_archived"],
      measurements: ["id", "parent_frame_id", "scope", "comb_color", "bees", "empty_cells", "drone_cells", "capped_brood_cells", "uncapped_brood_cells", "capped_honey_cells", "uncapped_honey_cells", "pollen_cells", "queen_cells", "created_at", "updated_at", "is_archived"],
    };
    const rows = {
      metadata: [{ key: "application_name", value: "Beeframe" }, { key: "schema_version", value: "2" }, { key: "initialized_at", value: now }],
      apiaries: [{ ...base(ids.apiary), name: "Test Yard", grid_columns: 8, grid_rows: 6, up_direction: "North" }],
      hives: [{ ...base(ids.hive), parent_apiary_id: ids.apiary, owner: "Sam", name: "Clover", grid_column: 4, grid_row: 3, status: "active" }],
      boxes: [
        { ...base(ids.box), parent_hive_id: ids.hive, position: 0, max_frames: 10, type: "deep", name: "AB" },
        { ...base(ids.box2), parent_hive_id: ids.hive, position: 1, max_frames: 10, type: "normal", name: "CD" },
        { ...base(ids.box3), parent_hive_id: ids.hive, position: 2, max_frames: 8, type: "normal", name: "EF" },
      ],
      frames: [
        { ...base(ids.frame), parent_box_id: ids.box, position: 0, name: "A1B" },
        { ...base(ids.frame2), parent_box_id: ids.box, position: 1, name: "A2B" },
        { ...base(ids.frame3), parent_box_id: ids.box, position: 2, name: "A3B" },
      ],
      equipment_types: [{ ...base(ids.type), name: "10-frame lid" }],
      equipment: [{ ...base(ids.equipment), code: "BCDF", equipment_type_id: ids.type, parent_hive_id: ids.hive }],
      notes: [{ ...base(ids.note), target_type: "frame", target_id: ids.frame, nature: "Todo", description: "Mock inspection note", archived: false, archived_at: null }],
      measurements: [{ ...base(ids.measurement), parent_frame_id: ids.frame, scope: "both", comb_color: "brown", bees: 55, empty_cells: 20, drone_cells: 5, capped_brood_cells: 35, uncapped_brood_cells: 15, capped_honey_cells: 40, uncapped_honey_cells: 10, pollen_cells: 12, queen_cells: 1 }],
    };
    const sheets = Object.fromEntries(Object.entries(schemas).map(([name, headers]) => [name, [headers, ...(rows[name] || []).map((row) => headers.map((header) => row[header] ?? ""))]]));
    return { title: "Mock Beeframe workbook", titles: Object.keys(schemas), sheets };
  }

  function mockMutate(request) {
    const changed = new Set();
    for (const item of request.updates || []) {
      const values = mockData.sheets[item.sheet];
      const headers = values?.[0] || [];
      const idColumn = headers.indexOf("id");
      const row = values?.slice(1).find((candidate) => candidate[idColumn] === item.id);
      if (!row) throw new Error(`${item.sheet}: mock record no longer exists.`);
      Object.entries(item.values).forEach(([column, value]) => {
        const index = headers.indexOf(column);
        if (index >= 0 && item.recognizedColumns.includes(column)) row[index] = value ?? "";
      });
      changed.add(item.sheet);
    }
    for (const item of request.appends || []) {
      const values = mockData.sheets[item.sheet];
      const headers = values?.[0] || [];
      item.rows.forEach((record) => values.push(headers.map((header) => record[header] ?? "")));
      changed.add(item.sheet);
    }
    return { sheets: Object.fromEntries([...changed].map((sheet) => [sheet, mockData.sheets[sheet]])) };
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`Could not load ${src}.`));
      document.head.appendChild(script);
    });
  }

  const identityReady = loadScript("https://accounts.google.com/gsi/client");
  const apiLoaderReady = loadScript("https://apis.google.com/js/api.js");

  function send(target, requestId, payload) {
    target.postMessage({ channel: CHANNEL, type: "result", requestId, ...payload }, window.location.origin);
  }

  async function authorize(prompt = "") {
    await identityReady;
    if (!window.google?.accounts?.oauth2) throw new Error("Google authentication could not be initialized.");
    if (!tokenClient) tokenClient = google.accounts.oauth2.initTokenClient({ client_id: CLIENT_ID, scope: SCOPE, callback: () => {} });
    return new Promise((resolve, reject) => {
      tokenClient.callback = (response) => {
        if (response.error) reject(new Error(response.error_description || response.error));
        else { accessToken = response.access_token; resolve(accessToken); }
      };
      tokenClient.error_callback = (error) => reject(new Error(error.type || "Google authorization failed."));
      tokenClient.requestAccessToken({ prompt });
    });
  }

  async function ensurePicker() {
    await apiLoaderReady;
    if (window.google?.picker) return;
    if (!pickerReady) pickerReady = new Promise((resolve, reject) => gapi.load("picker", {
      callback: resolve,
      onerror: () => reject(new Error("Google Picker could not load. In Firefox, turn off Enhanced Tracking Protection for this site and retry.")),
      timeout: 10000,
      ontimeout: () => reject(new Error("Google Picker timed out. In Firefox, turn off Enhanced Tracking Protection for this site and retry.")),
    }));
    await pickerReady;
  }

  async function api(path, options = {}) {
    if (!selectedSpreadsheet) throw new Error("Choose a Google Sheet first.");
    const response = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(selectedSpreadsheet.id)}${path}`, {
      ...options,
      headers: { Authorization: `Bearer ${accessToken || await authorize()}`, "Content-Type": "application/json", ...options.headers },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) accessToken = null;
      throw new Error(body.error?.message || `Google Sheets returned HTTP ${response.status}.`);
    }
    return body;
  }

  const quote = (name) => `'${String(name).replaceAll("'", "''")}'`;

  async function workbook() {
    const meta = await api("?fields=properties.title,sheets.properties(title,sheetId)");
    const titles = (meta.sheets || []).map((sheet) => sheet.properties.title);
    if (!titles.length) return { title: meta.properties?.title || selectedSpreadsheet.name, sheets: {}, titles: [] };
    const ranges = titles.map((title) => `ranges=${encodeURIComponent(quote(title))}`).join("&");
    const values = await api(`/values:batchGet?${ranges}&valueRenderOption=UNFORMATTED_VALUE`);
    const sheets = {};
    (values.valueRanges || []).forEach((range, index) => { sheets[titles[index]] = range.values || []; });
    return { title: meta.properties?.title || selectedSpreadsheet.name, sheets, titles };
  }

  function showPicker(target, requestId) {
    const view = new google.picker.DocsView(google.picker.ViewId.SPREADSHEETS).setMode(google.picker.DocsViewMode.LIST);
    new google.picker.PickerBuilder().addView(view).enableFeature(google.picker.Feature.NAV_HIDDEN)
      .setOAuthToken(accessToken).setDeveloperKey(API_KEY).setAppId(APP_ID).setOrigin(window.location.origin)
      .setCallback(async (response) => {
        if (response[google.picker.Response.ACTION] !== google.picker.Action.PICKED) return;
        const document = response[google.picker.Response.DOCUMENTS][0];
        selectedSpreadsheet = { id: document[google.picker.Document.ID], name: document[google.picker.Document.NAME] };
        try { send(target, requestId, { ok: true, selectedSpreadsheet, data: await workbook() }); }
        catch (error) { send(target, requestId, { ok: false, error: error.message }); }
      }).build().setVisible(true);
  }

  function matrix(values) {
    if (!Array.isArray(values) || values.some((row) => !Array.isArray(row))) throw new Error("Values must be a JSON matrix.");
    return values;
  }

  function validateRequest(request) {
    if (!request || typeof request !== "object" || !OPERATIONS.has(request.action)) throw new Error("Unsupported Google operation.");
    if (["append", "update_by_id"].includes(request.action) && typeof request.sheet !== "string") throw new Error("A worksheet name is required.");
    if (request.action === "append" && !Array.isArray(request.rows)) throw new Error("Append rows must be an array.");
    if (request.action === "update_by_id" && (typeof request.id !== "string" || !request.values || !Array.isArray(request.recognizedColumns))) throw new Error("The update payload is invalid.");
    if (request.action === "initialize" && !Array.isArray(request.sheets)) throw new Error("Initialization worksheets are required.");
    if (request.action === "mutate" && (!Array.isArray(request.updates) || !Array.isArray(request.appends))) throw new Error("The mutation payload is invalid.");
  }

  async function assertGlobalUnique(values = [], ignore = null) {
    if (!values.length) return;
    if (new Set(values.map((value) => value.toLowerCase())).size !== values.length) throw new Error("Generated names or codes were duplicated. Refresh and retry.");
    const sheets = Object.keys(NAME_COLUMNS);
    const ranges = sheets.map((sheet) => `ranges=${encodeURIComponent(quote(sheet))}`).join("&");
    const response = await api(`/values:batchGet?${ranges}&valueRenderOption=UNFORMATTED_VALUE`);
    const used = new Set();
    (response.valueRanges || []).forEach((range, index) => {
      const rows = range.values || [];
      const headers = rows[0] || [];
      const valueIndex = headers.indexOf(NAME_COLUMNS[sheets[index]]);
      const idIndex = headers.indexOf("id");
      const archivedIndex = headers.indexOf("is_archived");
      rows.slice(1).forEach((row) => {
        if (ignore && ignore.sheet === sheets[index] && row[idIndex] === ignore.id) return;
        if (row[archivedIndex] === true || valueIndex < 0) return;
        if (row[valueIndex]) used.add(String(row[valueIndex]).toLowerCase());
      });
    });
    const conflict = values.find((value) => used.has(String(value).toLowerCase()));
    if (conflict) throw new Error(`${conflict} is already in use. Refreshed data was not changed.`);
  }

  async function initialize(request) {
    const current = await workbook();
    if (current.titles.length && current.titles.some((title) => current.sheets[title]?.length)) throw new Error("This spreadsheet is not empty. Beeframe did not modify it.");
    const missing = request.sheets.filter((sheet) => !current.titles.includes(sheet.name));
    if (missing.length) await api(":batchUpdate", { method: "POST", body: JSON.stringify({ requests: missing.map((sheet) => ({ addSheet: { properties: { title: sheet.name } } })) }) });
    await api("/values:batchUpdate", { method: "POST", body: JSON.stringify({
      valueInputOption: "RAW", data: request.sheets.map((sheet) => ({ range: `${quote(sheet.name)}!A1`, values: matrix(sheet.values) })),
    }) });
    return workbook();
  }

  async function append(request) {
    await assertGlobalUnique(request.uniqueValues || []);
    const before = await api(`/values/${encodeURIComponent(quote(request.sheet))}?valueRenderOption=UNFORMATTED_VALUE`);
    const headers = before.values?.[0] || [];
    if (!headers.length) throw new Error(`${request.sheet} has no header row.`);
    if (request.uniqueValue) {
      const index = headers.indexOf(request.uniqueColumn);
      const exists = (before.values || []).slice(1).some((row) => String(row[index] || "").toLowerCase() === String(request.uniqueValue).toLowerCase());
      if (exists) throw new Error(`${request.uniqueValue} is already in use. Refresh and try again.`);
    }
    const rows = request.rows.map((record) => headers.map((header) => header in record ? record[header] : ""));
    await api(`/values/${encodeURIComponent(quote(request.sheet))}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`, { method: "POST", body: JSON.stringify({ values: rows }) });
    return (await api(`/values/${encodeURIComponent(quote(request.sheet))}?valueRenderOption=UNFORMATTED_VALUE`)).values || [];
  }

  async function updateById(request) {
    await assertGlobalUnique(request.uniqueValues || [], { sheet: request.sheet, id: request.id });
    const refreshed = await api(`/values/${encodeURIComponent(quote(request.sheet))}?valueRenderOption=UNFORMATTED_VALUE`);
    const values = refreshed.values || [];
    const headers = values[0] || [];
    const idColumn = headers.indexOf("id");
    const rowOffset = values.slice(1).findIndex((row) => row[idColumn] === request.id);
    if (idColumn < 0 || rowOffset < 0) throw new Error("The record changed or no longer exists. Refresh and try again.");
    const rowNumber = rowOffset + 2;
    const data = Object.entries(request.values).filter(([column]) => request.recognizedColumns.includes(column) && headers.includes(column))
      .map(([column, value]) => ({ range: `${quote(request.sheet)}!${columnLetter(headers.indexOf(column))}${rowNumber}`, values: [[value ?? ""]] }));
    if (!data.length) throw new Error("No recognized fields were supplied for update.");
    await api("/values:batchUpdate", { method: "POST", body: JSON.stringify({ valueInputOption: "RAW", data }) });
    return (await api(`/values/${encodeURIComponent(quote(request.sheet))}?valueRenderOption=UNFORMATTED_VALUE`)).values || [];
  }

  async function mutate(request) {
    await assertGlobalUnique(request.uniqueValues || []);
    const sheetNames = [...new Set([...(request.updates || []).map((item) => item.sheet), ...(request.appends || []).map((item) => item.sheet)])];
    const ranges = sheetNames.map((sheet) => `ranges=${encodeURIComponent(quote(sheet))}`).join("&");
    const batch = await api(`/values:batchGet?${ranges}&valueRenderOption=UNFORMATTED_VALUE`);
    const current = Object.fromEntries(sheetNames.map((sheet, index) => [sheet, batch.valueRanges?.[index]?.values || []]));
    const updateData = [];
    for (const item of request.updates || []) {
      const values = current[item.sheet];
      const headers = values[0] || [];
      const idColumn = headers.indexOf("id");
      const rowOffset = values.slice(1).findIndex((row) => row[idColumn] === item.id);
      if (idColumn < 0 || rowOffset < 0) throw new Error(`${item.sheet}: a record changed or no longer exists. Nothing was written.`);
      for (const [column, value] of Object.entries(item.values)) {
        if (!item.recognizedColumns.includes(column) || !headers.includes(column)) continue;
        updateData.push({ range: `${quote(item.sheet)}!${columnLetter(headers.indexOf(column))}${rowOffset + 2}`, values: [[value ?? ""]] });
      }
    }
    if (updateData.length) await api("/values:batchUpdate", { method: "POST", body: JSON.stringify({ valueInputOption: "RAW", data: updateData }) });
    for (const item of request.appends || []) {
      const headers = current[item.sheet]?.[0] || [];
      if (!headers.length) throw new Error(`${item.sheet} has no header row.`);
      const rows = item.rows.map((record) => headers.map((header) => header in record ? record[header] : ""));
      await api(`/values/${encodeURIComponent(quote(item.sheet))}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`, { method: "POST", body: JSON.stringify({ values: rows }) });
    }
    const refreshed = await api(`/values:batchGet?${ranges}&valueRenderOption=UNFORMATTED_VALUE`);
    return { sheets: Object.fromEntries(sheetNames.map((sheet, index) => [sheet, refreshed.valueRanges?.[index]?.values || []])) };
  }

  function columnLetter(index) {
    let value = "";
    for (let number = index + 1; number; number = Math.floor((number - 1) / 26)) value = String.fromCharCode(65 + (number - 1) % 26) + value;
    return value;
  }

  async function handle(target, requestId, request) {
    validateRequest(request);
    if (MOCK && request.action === "choose_sheet") {
      selectedSpreadsheet = { id: "local-mock", name: "Mock Beeframe workbook" };
      mockData = mockWorkbook();
      send(target, requestId, { ok: true, selectedSpreadsheet, data: mockData });
      return null;
    }
    if (MOCK) {
      if (request.action === "disconnect") { selectedSpreadsheet = null; return { disconnected: true }; }
      if (request.action === "load_workbook") return mockData || mockWorkbook();
      if (request.action === "mutate") return mockMutate(request);
      if (request.action === "append") {
        const result = mockMutate({ appends: [{ sheet: request.sheet, rows: request.rows }] });
        return { sheet: request.sheet, values: result.sheets[request.sheet] };
      }
      if (request.action === "update_by_id") {
        const result = mockMutate({ updates: [{ sheet: request.sheet, id: request.id, values: request.values, recognizedColumns: request.recognizedColumns }] });
        return { sheet: request.sheet, values: result.sheets[request.sheet] };
      }
      throw new Error("This write is not implemented in local mock mode.");
    }
    if (request.action === "choose_sheet") { await authorize(accessToken ? "" : "consent"); await ensurePicker(); showPicker(target, requestId); return null; }
    if (request.action === "disconnect") {
      if (accessToken) google.accounts.oauth2.revoke(accessToken, () => {});
      accessToken = null; selectedSpreadsheet = null; return { disconnected: true };
    }
    if (request.action === "load_workbook") return workbook();
    if (request.action === "initialize") return initialize(request);
    if (request.action === "append") return { sheet: request.sheet, values: await append(request) };
    if (request.action === "update_by_id") return { sheet: request.sheet, values: await updateById(request) };
    if (request.action === "mutate") return mutate(request);
  }

  window.addEventListener("message", async (event) => {
    if (event.origin !== window.location.origin || event.source === window) return;
    const message = event.data;
    if (!message || message.channel !== CHANNEL || message.type !== "request" || typeof message.requestId !== "string") return;
    try {
      const data = await handle(event.source, message.requestId, message.request);
      if (data !== null) send(event.source, message.requestId, { ok: true, data });
    } catch (error) { send(event.source, message.requestId, { ok: false, error: error.message || "Google Sheets request failed." }); }
  });
})();
