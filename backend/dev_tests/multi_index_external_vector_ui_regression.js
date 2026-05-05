const { chromium } = require('../../frontend/node_modules/@playwright/test');
const fs = require('fs');
const path = require('path');

const ROOT = '/Users/vinicios/code/tsushin';
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const EVIDENCE_DIR = path.join(
  ROOT,
  'output/playwright',
  `multi-index-external-vector-ui-regression-${stamp}`,
);
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

const BASE = process.env.TSN_UI_REGRESSION_BASE || 'https://localhost';
const AGENT_ID = Number(process.env.TSN_UI_REGRESSION_AGENT_ID || 6);
const LOGIN_EMAIL = process.env.TSN_UI_REGRESSION_EMAIL || 'test@example.com';
const LOGIN_PASSWORD = process.env.TSN_UI_REGRESSION_PASSWORD || 'test1234';
const PROVIDER = process.env.TSN_UI_REGRESSION_PROVIDER || 'gemini';
const MODEL = process.env.TSN_UI_REGRESSION_MODEL || 'gemini-embedding-2';
const DIMS = (process.env.TSN_UI_REGRESSION_DIMS || '1536,768')
  .split(',')
  .map((value) => Number(value.trim()))
  .filter((value) => Number.isFinite(value) && value > 0);

const evidence = {
  started_at: new Date().toISOString(),
  evidence_dir: EVIDENCE_DIR,
  base_url: BASE,
  agent_id: AGENT_ID,
  provider: PROVIDER,
  model: MODEL,
  dimensions: DIMS,
  screenshots: [],
  sample_files: [],
  assertions: [],
  console: [],
  network_errors: [],
  responses_4xx_5xx: [],
  api: {},
  qdrant: {},
  indexes: {},
  agent_kb: {},
  project_kb: {},
  cleanup: {},
};

function rel(absPath) {
  return path.relative(ROOT, absPath);
}

function writeEvidence() {
  fs.writeFileSync(
    path.join(EVIDENCE_DIR, 'multi-index-external-vector-ui-regression-evidence.json'),
    JSON.stringify(evidence, null, 2),
  );
}

function assertStep(condition, name, details = {}) {
  const item = { name, pass: Boolean(condition), details };
  evidence.assertions.push(item);
  if (!condition) {
    throw new Error(`Assertion failed: ${name} ${JSON.stringify(details).slice(0, 1200)}`);
  }
}

function normalize(text) {
  return String(text || '').replace(/\s+/g, ' ').trim().toLowerCase();
}

function qdrantCandidates(store) {
  const cfg = store && store.extra_config && typeof store.extra_config === 'object' ? store.extra_config : {};
  const candidates = [
    store && store.endpoint_url,
    store && store.connection_url,
    store && store.url,
    cfg.endpoint_url,
    cfg.connection_url,
    cfg.url,
    cfg.base_url,
  ].filter(Boolean);
  const port = store && (store.container_port || store.port || cfg.container_port || cfg.port);
  if (port) {
    candidates.push(`http://localhost:${port}`);
  }
  candidates.push('http://localhost:6300');
  return Array.from(new Set(candidates.map((candidate) => String(candidate).replace(/\/$/, ''))));
}

async function fetchJsonFromNode(url, options = {}) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  return { ok: res.ok, status: res.status, data };
}

async function qdrantCollection(store, collectionName) {
  if (!collectionName) return { ok: false, error: 'missing collection name' };
  const attempts = [];
  for (const base of qdrantCandidates(store)) {
    const url = `${base}/collections/${encodeURIComponent(collectionName)}`;
    try {
      const result = await fetchJsonFromNode(url);
      attempts.push({ base, status: result.status, ok: result.ok });
      if (result.ok) {
        return { ...result, base, attempts };
      }
    } catch (error) {
      attempts.push({ base, ok: false, error: String(error && error.message ? error.message : error) });
    }
  }
  return { ok: false, attempts };
}

function vectorSizeFromCollection(collection) {
  const vectors = collection && collection.data && collection.data.result
    && collection.data.result.config
    && collection.data.result.config.params
    && collection.data.result.config.params.vectors;
  if (!vectors) return null;
  if (typeof vectors.size === 'number') return vectors.size;
  const first = Object.values(vectors)[0];
  if (first && typeof first.size === 'number') return first.size;
  return null;
}

function pointsFromCollection(collection) {
  const result = collection && collection.data && collection.data.result;
  if (!result) return null;
  if (typeof result.points_count === 'number') return result.points_count;
  if (typeof result.vectors_count === 'number') return result.vectors_count;
  return null;
}

async function main() {
  let browser;
  let context;
  let page;
  let providerOption;
  let providerValue;
  let vectorStore;
  let originalAgentConfig = null;
  let createdProjectId = null;
  let cleanupFailure = null;
  const createdAgentDocIds = new Set();
  const createdAgentDocNames = new Set();
  const createdProjectDocIds = new Set();
  const collectionBaselines = new Map();

  async function shot(name) {
    const out = path.join(EVIDENCE_DIR, name);
    await page.screenshot({ path: out, fullPage: true });
    evidence.screenshots.push(rel(out));
    return out;
  }

  async function apiJson(url, options = {}) {
    const payload = {
      url,
      method: options.method || 'GET',
      body: options.body === undefined ? null : options.body,
      headers: options.headers || {},
    };
    const result = await page.evaluate(async ({ url, method, body, headers }) => {
      const init = { method, headers: { ...headers } };
      if (body !== null && body !== undefined) {
        init.headers['Content-Type'] = init.headers['Content-Type'] || 'application/json';
        init.body = typeof body === 'string' ? body : JSON.stringify(body);
      }
      const res = await fetch(url, init);
      const text = await res.text();
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = text;
      }
      return { ok: res.ok, status: res.status, data };
    }, payload);
    if (!result.ok) {
      throw new Error(`API ${payload.method} ${url} failed: ${result.status} ${JSON.stringify(result.data).slice(0, 800)}`);
    }
    return result.data;
  }

  async function dismissTour() {
    for (let i = 0; i < 5; i += 1) {
      await page.waitForTimeout(300);
      const skip = page.getByRole('button', { name: /skip tour|skip/i }).first();
      if (await skip.isVisible({ timeout: 300 }).catch(() => false)) {
        await skip.click();
        continue;
      }
      const welcome = page.getByText('Welcome to Tsushin!', { exact: true }).first();
      if (await welcome.isVisible({ timeout: 200 }).catch(() => false)) {
        await page.keyboard.press('Escape');
        continue;
      }
      break;
    }
  }

  async function login() {
    await context.clearCookies();
    await page.goto(`${BASE}/auth/login`, { waitUntil: 'domcontentloaded' });
    await shot('00-login.png');
    const emailInput = page.locator('input[type="text"], input[type="email"]').first();
    if (await emailInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await emailInput.fill(LOGIN_EMAIL);
      await page.locator('input[type="password"]').first().fill(LOGIN_PASSWORD);
      const loginResponse = page.waitForResponse((response) => (
        response.url().includes('/api/auth/login')
      ), { timeout: 10000 }).catch(() => null);
      await page.getByRole('button', { name: /sign in|login/i }).first().click();
      const response = await loginResponse;
      if (response) {
        assertStep(response.ok(), 'UI login request succeeded', {
          status: response.status(),
          url: response.url(),
        });
      }
      await page.waitForURL((url) => !url.pathname.includes('/auth/login') && !url.pathname.includes('/login'), {
        timeout: 5000,
        waitUntil: 'domcontentloaded',
      }).catch(() => null);
    }

    async function fetchMe() {
      return page.evaluate(async () => {
        const res = await fetch('/api/auth/me', { credentials: 'include' });
        return res.ok ? res.json() : null;
      }).catch(() => null);
    }

    let me = null;
    for (let attempt = 0; attempt < 12; attempt += 1) {
      me = await fetchMe();
      if (me && me.id) break;
      await page.waitForTimeout(500);
    }

    if (!me || !me.id) {
      await page.goto(`${BASE}/auth/login`, { waitUntil: 'domcontentloaded' });
      const loginResult = await page.evaluate(async ({ email, password }) => {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ email, password }),
        });
        const data = await res.json().catch(() => null);
        return { ok: res.ok, status: res.status, data };
      }, { email: LOGIN_EMAIL, password: LOGIN_PASSWORD });
      assertStep(loginResult.ok, 'browser-context fallback login succeeded', loginResult);
      for (let attempt = 0; attempt < 12; attempt += 1) {
        me = await fetchMe();
        if (me && me.id) break;
        await page.waitForTimeout(500);
      }
    }

    assertStep(Boolean(me && me.id), 'logged in user is available', me || {});
    await page.evaluate((userId) => {
      localStorage.setItem(`tsushin_onboarding_completed:${userId}`, 'true');
      localStorage.removeItem(`tsushin_onboarding_started:${userId}`);
      localStorage.setItem('tsushin_onboarding_completed', 'true');
    }, me.id);
    await dismissTour();
    await shot('01-after-login.png');
  }

  async function selectLabeled(label, value) {
    const wanted = String(value);
    await page.waitForFunction(({ label, wanted }) => {
      const labelNeedle = String(label || '').toLowerCase();
      const visible = (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      };
      const labels = Array.from(document.querySelectorAll('label'))
        .filter((node) => visible(node) && node.textContent.toLowerCase().includes(labelNeedle));
      return labels.some((labelNode) => {
        let container = labelNode.parentElement;
        for (let depth = 0; container && depth < 5; depth += 1, container = container.parentElement) {
          const select = container.querySelector('select');
          if (
            select
            && visible(select)
            && Array.from(select.options).some((option) => option.value === wanted)
          ) {
            return true;
          }
        }
        return false;
      });
    }, { label, wanted }, { timeout: 30000 });

    const index = await page.locator('select').evaluateAll((selects, { label, wanted }) => {
      const labelNeedle = String(label || '').toLowerCase();
      const visible = (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      };
      const isMatch = (select) => {
        if (!visible(select) || !Array.from(select.options).some((option) => option.value === wanted)) {
          return false;
        }
        let container = select.parentElement;
        for (let depth = 0; container && depth < 5; depth += 1, container = container.parentElement) {
          if (
            Array.from(container.querySelectorAll('label')).some((labelNode) => (
              visible(labelNode) && labelNode.textContent.toLowerCase().includes(labelNeedle)
            ))
          ) {
            return true;
          }
        }
        return false;
      };
      return selects.findIndex(isMatch);
    }, { label, wanted });
    if (index < 0) {
      throw new Error(`No visible select labeled ${label} has option value ${wanted}`);
    }
    await page.locator('select').nth(index).selectOption(wanted);
    await page.waitForTimeout(500);
  }

  async function configureAgentKb(dims) {
    await page.goto(`${BASE}/agents/${AGENT_ID}?tab=knowledge`, { waitUntil: 'domcontentloaded' });
    await dismissTour();
    await page.waitForSelector('text=Index Settings', { timeout: 30000 });
    await selectLabeled('Vector Storage', vectorStore.id);
    await selectLabeled('Embedding Provider', providerValue);
    await selectLabeled('Embedding Model', MODEL);
    await selectLabeled('Dimensions', dims);
    await shot(`10-agent-kb-${dims}-contract-selected.png`);
    await page.getByRole('button', { name: /test embedding/i }).first().click();
    await page.waitForSelector(`text=Embedding test passed: ${dims} dimensions`, { timeout: 120000 });
    await page.getByRole('button', { name: /^save settings$/i }).first().click();
    await page.waitForSelector('text=Saved KB indexing settings.', { timeout: 30000 });
    const config = await apiJson(`/api/agents/${AGENT_ID}/knowledge-base/config`);
    evidence.agent_kb[`config_${dims}`] = config;
    assertStep(config.embedding_provider === PROVIDER, `agent KB ${dims}: provider saved`, config);
    assertStep(config.embedding_model === MODEL, `agent KB ${dims}: model saved`, config);
    assertStep(Number(config.embedding_dims) === dims, `agent KB ${dims}: dimensions saved`, config);
    assertStep(Number(config.vector_store_instance_id) === Number(vectorStore.id), `agent KB ${dims}: external vector store saved`, config);
    return config;
  }

  function createSampleFile(prefix, dims, facts) {
    const filename = `${prefix}-${dims}-${stamp}.txt`;
    const filePath = path.join(EVIDENCE_DIR, filename);
    fs.writeFileSync(
      filePath,
      [
        `${prefix} regression document for ${MODEL} with ${dims} dimensions.`,
        `Owner: ${facts.owner}.`,
        `Secret phrase: ${facts.secret}.`,
        `Queue: ${facts.queue}.`,
        `Review date: ${facts.date}.`,
        `Vector store: external Qdrant multi-index instance.`,
      ].join('\n'),
    );
    evidence.sample_files.push(rel(filePath));
    return { filename, filePath, dims, facts };
  }

  async function uploadAgentDoc(sample) {
    createdAgentDocNames.add(sample.filename);
    await page.goto(`${BASE}/agents/${AGENT_ID}?tab=knowledge`, { waitUntil: 'domcontentloaded' });
    await dismissTour();
    await page.waitForSelector('text=Upload Knowledge Documents', { timeout: 30000 });
    await page.locator('input[type=file]').first().setInputFiles(sample.filePath);
    await page.waitForTimeout(1000);

    let doc = null;
    for (let attempt = 0; attempt < 90; attempt += 1) {
      const docs = await apiJson(`/api/agents/${AGENT_ID}/knowledge-base`);
      doc = docs.find((candidate) => candidate.document_name === sample.filename) || null;
      if (doc && doc.id) createdAgentDocIds.add(doc.id);
      if (
        doc
        && doc.status === 'completed'
        && Number(doc.embedding_dims) === sample.dims
        && doc.vector_store_index_id
        && doc.vector_collection_name
      ) {
        break;
      }
      await page.waitForTimeout(2000);
    }
    assertStep(Boolean(doc), `agent KB ${sample.dims}: uploaded document is listed`, { filename: sample.filename });
    evidence.agent_kb[`document_${sample.dims}`] = doc;
    assertStep(doc.status === 'completed', `agent KB ${sample.dims}: document completed`, doc);
    assertStep(doc.embedding_provider === PROVIDER, `agent KB ${sample.dims}: provider snapshot`, doc);
    assertStep(doc.embedding_model === MODEL, `agent KB ${sample.dims}: model snapshot`, doc);
    assertStep(Number(doc.embedding_dims) === sample.dims, `agent KB ${sample.dims}: dimensions snapshot`, doc);
    assertStep(Number(doc.vector_store_instance_id) === Number(vectorStore.id), `agent KB ${sample.dims}: vector store snapshot`, doc);
    assertStep(Boolean(doc.vector_store_index_id), `agent KB ${sample.dims}: vector store index snapshot`, doc);
    assertStep(Boolean(doc.vector_collection_name), `agent KB ${sample.dims}: physical collection snapshot`, doc);
    await page.waitForSelector(`text=${sample.filename}`, { timeout: 30000 });
    await shot(`11-agent-kb-${sample.dims}-document-completed.png`);
    return { ...sample, doc };
  }

  async function searchAgentKb(entry, label) {
    const query = `${entry.facts.owner} ${entry.facts.queue} ${entry.facts.secret}`;
    await page.goto(`${BASE}/agents/${AGENT_ID}?tab=knowledge`, { waitUntil: 'domcontentloaded' });
    await dismissTour();
    await page.waitForSelector('input[placeholder="Enter search query..."]', { timeout: 30000 });
    await page.locator('input[placeholder="Enter search query..."]').fill(query);
    await page.getByRole('button', { name: /^search$/i }).first().click();
    await page.waitForSelector(`text=${entry.facts.secret}`, { timeout: 90000 });
    await shot(`12-agent-kb-${label}-search-ui.png`);
    const results = await apiJson(`/api/agents/${AGENT_ID}/knowledge-base/search`, {
      method: 'POST',
      body: { query, max_results: 8 },
    });
    evidence.agent_kb[`search_${label}`] = results;
    assertStep(
      results.some((item) => item.document_name === entry.filename && String(item.content || '').includes(entry.facts.secret)),
      `agent KB ${label}: API search returns canary`,
      results,
    );
    return results;
  }

  async function createProjectWithContract(dims) {
    const projectName = `Multi Index Vector Regression ${stamp}`;
    await page.goto(`${BASE}/studio/projects`, { waitUntil: 'domcontentloaded' });
    await dismissTour();
    await page.waitForSelector('text=Projects', { timeout: 30000 });
    await page.getByRole('button', { name: /new project/i }).click();
    await page.waitForSelector('text=Create Project', { timeout: 30000 });
    await page.locator('.fixed input[type="text"]').first().fill(projectName);
    const agentSelectIndex = await page.locator('.fixed select').evaluateAll((selects, agentId) => (
      selects.findIndex((select) => Array.from(select.options).some((option) => option.value === String(agentId)))
    ), AGENT_ID);
    if (agentSelectIndex >= 0) {
      await page.locator('.fixed select').nth(agentSelectIndex).selectOption(String(AGENT_ID));
    }
    await selectLabeled('Vector Store', vectorStore.id);
    await selectLabeled('Embedding Provider', providerValue);
    await selectLabeled('Embedding Model', MODEL);
    await selectLabeled('Dimensions', dims);
    await shot(`20-project-create-${dims}-contract-selected.png`);
    await page.getByRole('button', { name: /^create project$/i }).last().click();
    await page.waitForURL(/\/studio\/projects\/\d+/, { timeout: 30000 });
    const match = page.url().match(/\/studio\/projects\/(\d+)/);
    createdProjectId = match ? Number(match[1]) : null;
    assertStep(Boolean(createdProjectId), 'project created from UI', { url: page.url() });
    const project = await apiJson(`/api/projects/${createdProjectId}`);
    evidence.project_kb.created_project = project;
    assertStep(Number(project.kb_vector_store_instance_id) === Number(vectorStore.id), `project KB ${dims}: external vector store saved on create`, project);
    assertStep(project.kb_embedding_provider === PROVIDER, `project KB ${dims}: provider saved on create`, project);
    assertStep(project.kb_embedding_model === MODEL, `project KB ${dims}: model saved on create`, project);
    assertStep(Number(project.kb_embedding_dims) === dims, `project KB ${dims}: dimensions saved on create`, project);
    await shot(`21-project-${dims}-detail-created.png`);
    return project;
  }

  async function configureProjectKb(dims) {
    await page.goto(`${BASE}/studio/projects/${createdProjectId}`, { waitUntil: 'domcontentloaded' });
    await dismissTour();
    await page.getByRole('button', { name: /knowledge base/i }).click();
    await page.waitForSelector('text=Index Contract', { timeout: 30000 });
    await selectLabeled('Vector Store', vectorStore.id);
    await selectLabeled('Embedding Provider', providerValue);
    await selectLabeled('Embedding Model', MODEL);
    await selectLabeled('Dimensions', dims);
    await shot(`22-project-kb-${dims}-contract-selected.png`);
    await page.getByRole('button', { name: /save changes/i }).first().click();
    await page.waitForSelector('text=Project saved successfully', { timeout: 30000 });
    const project = await apiJson(`/api/projects/${createdProjectId}`);
    evidence.project_kb[`config_${dims}`] = project;
    assertStep(Number(project.kb_vector_store_instance_id) === Number(vectorStore.id), `project KB ${dims}: external vector store saved`, project);
    assertStep(project.kb_embedding_provider === PROVIDER, `project KB ${dims}: provider saved`, project);
    assertStep(project.kb_embedding_model === MODEL, `project KB ${dims}: model saved`, project);
    assertStep(Number(project.kb_embedding_dims) === dims, `project KB ${dims}: dimensions saved`, project);
    return project;
  }

  async function uploadProjectDoc(sample) {
    await page.goto(`${BASE}/studio/projects/${createdProjectId}`, { waitUntil: 'domcontentloaded' });
    await dismissTour();
    await page.getByRole('button', { name: /knowledge base/i }).click();
    await page.waitForSelector('text=Upload Document', { timeout: 30000 });
    await page.locator('input[type=file]').first().setInputFiles(sample.filePath);
    await page.waitForTimeout(1000);

    let doc = null;
    for (let attempt = 0; attempt < 90; attempt += 1) {
      const docs = await apiJson(`/api/projects/${createdProjectId}/knowledge`);
      doc = docs.find((candidate) => candidate.name === sample.filename) || null;
      if (doc && doc.id) createdProjectDocIds.add(doc.id);
      if (
        doc
        && doc.status === 'completed'
        && Number(doc.embedding_dims) === sample.dims
        && doc.vector_store_index_id
        && doc.vector_collection_name
      ) {
        break;
      }
      await page.waitForTimeout(2000);
    }
    assertStep(Boolean(doc), `project KB ${sample.dims}: uploaded document is listed`, { filename: sample.filename });
    evidence.project_kb[`document_${sample.dims}`] = doc;
    assertStep(doc.status === 'completed', `project KB ${sample.dims}: document completed`, doc);
    assertStep(doc.embedding_provider === PROVIDER, `project KB ${sample.dims}: provider snapshot`, doc);
    assertStep(doc.embedding_model === MODEL, `project KB ${sample.dims}: model snapshot`, doc);
    assertStep(Number(doc.embedding_dims) === sample.dims, `project KB ${sample.dims}: dimensions snapshot`, doc);
    assertStep(Number(doc.vector_store_instance_id) === Number(vectorStore.id), `project KB ${sample.dims}: vector store snapshot`, doc);
    assertStep(Boolean(doc.vector_store_index_id), `project KB ${sample.dims}: vector store index snapshot`, doc);
    assertStep(Boolean(doc.vector_collection_name), `project KB ${sample.dims}: physical collection snapshot`, doc);
    await page.waitForSelector(`text=${sample.filename}`, { timeout: 30000 });
    await shot(`23-project-kb-${sample.dims}-document-completed.png`);
    return { ...sample, doc };
  }

  async function searchProjectKb(entry, label) {
    const query = `${entry.facts.owner} ${entry.facts.queue} ${entry.facts.secret}`;
    const results = await apiJson(`/api/projects/${createdProjectId}/knowledge/search`, {
      method: 'POST',
      body: { query, max_results: 8 },
    });
    evidence.project_kb[`search_${label}`] = results;
    assertStep(
      results.some((item) => item.document_name === entry.filename && String(item.content || '').includes(entry.facts.secret)),
      `project KB ${label}: API search returns canary`,
      results,
    );
    return results;
  }

  async function inspectCollectionForDoc(doc, dims, label) {
    const collectionName = doc.vector_collection_name;
    if (!collectionBaselines.has(collectionName)) {
      const before = await qdrantCollection(vectorStore, collectionName);
      collectionBaselines.set(collectionName, pointsFromCollection(before) || 0);
    }
    const collection = await qdrantCollection(vectorStore, collectionName);
    evidence.qdrant[label] = collection;
    assertStep(collection.ok, `${label}: Qdrant collection exists`, { collectionName, collection });
    assertStep(vectorSizeFromCollection(collection) === dims, `${label}: Qdrant vector size matches ${dims}`, {
      collectionName,
      vector_size: vectorSizeFromCollection(collection),
    });
    assertStep((pointsFromCollection(collection) || 0) > 0, `${label}: Qdrant collection has vectors`, {
      collectionName,
      points: pointsFromCollection(collection),
    });
    return collection;
  }

  async function inspectIndexes() {
    const indexes = await apiJson(`/api/vector-stores/${vectorStore.id}/indexes`);
    evidence.indexes.after_uploads = indexes;
    for (const purpose of ['agent_kb', 'project_kb']) {
      for (const dims of DIMS) {
        assertStep(
          indexes.some((index) => (
            index.purpose === purpose
            && index.embedding_provider === PROVIDER
            && index.embedding_model === MODEL
            && Number(index.embedding_dims) === dims
          )),
          `vector store indexes include ${purpose} ${MODEL} ${dims}d`,
          indexes,
        );
      }
    }
    const agentIndexIds = DIMS.map((dims) => evidence.agent_kb[`document_${dims}`].vector_store_index_id);
    const projectIndexIds = DIMS.map((dims) => evidence.project_kb[`document_${dims}`].vector_store_index_id);
    assertStep(new Set(agentIndexIds).size === DIMS.length, 'agent KB dimensions resolve to distinct indexes', agentIndexIds);
    assertStep(new Set(projectIndexIds).size === DIMS.length, 'project KB dimensions resolve to distinct indexes', projectIndexIds);
    assertStep(
      DIMS.every((dims) => Number(evidence.agent_kb[`document_${dims}`].vector_store_instance_id) === Number(vectorStore.id))
        && DIMS.every((dims) => Number(evidence.project_kb[`document_${dims}`].vector_store_instance_id) === Number(vectorStore.id)),
      'agent and project KB use the same external vector store instance',
      { vector_store_id: vectorStore.id },
    );
    return indexes;
  }

  try {
    assertStep(DIMS.length >= 2, 'at least two dimensions are configured', DIMS);

    browser = await chromium.launch({ headless: process.env.TSN_UI_REGRESSION_HEADED !== '1' });
    context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1440, height: 1050 },
      acceptDownloads: true,
    });
    page = await context.newPage();

    page.on('console', (msg) => {
      if (['error', 'warning'].includes(msg.type())) {
        evidence.console.push({ type: msg.type(), text: msg.text() });
      }
    });
    page.on('requestfailed', (req) => {
      const failure = req.failure();
      evidence.network_errors.push({
        url: req.url(),
        method: req.method(),
        failure: failure && failure.errorText,
      });
    });
    page.on('response', (res) => {
      const status = res.status();
      const url = res.url();
      if (status >= 500 || (status >= 400 && !url.includes('/_next/'))) {
        evidence.responses_4xx_5xx.push({ url, status });
      }
    });
    page.on('dialog', async (dialog) => {
      evidence.dialog = evidence.dialog || [];
      evidence.dialog.push({ type: dialog.type(), message: dialog.message() });
      await dialog.accept();
    });

    await login();
    evidence.api.me = await apiJson('/api/auth/me');
    evidence.api.embedding_options = await apiJson('/api/embedding-providers/options');
    evidence.api.vector_stores = await apiJson('/api/vector-stores');
    providerOption = evidence.api.embedding_options.providers.find((option) => (
      option.provider === PROVIDER
      && option.models.some((model) => (
        model.model === MODEL
        && DIMS.every((dims) => (model.supported_dimensions || []).includes(dims))
      ))
    ));
    assertStep(Boolean(providerOption), `${PROVIDER}/${MODEL} supports required dimensions`, evidence.api.embedding_options.providers);
    providerValue = `${providerOption.provider}:${providerOption.provider_instance_id ?? 'local'}`;
    vectorStore = evidence.api.vector_stores.find((store) => (
      String(store.vendor || '').toLowerCase() === 'qdrant'
      && ['healthy', 'unknown', null, undefined].includes(store.health_status)
    ));
    assertStep(Boolean(vectorStore), 'Qdrant vector store instance is available', evidence.api.vector_stores);
    evidence.api.selected_provider_value = providerValue;
    evidence.api.selected_vector_store = vectorStore;
    originalAgentConfig = await apiJson(`/api/agents/${AGENT_ID}/knowledge-base/config`);
    evidence.api.original_agent_kb_config = originalAgentConfig;

    const agentEntries = [];
    await configureAgentKb(DIMS[0]);
    agentEntries.push(await uploadAgentDoc(createSampleFile('agent-kb', DIMS[0], {
      owner: 'Selene Vega',
      secret: `AGENT-${DIMS[0]}-QUARTZ`,
      queue: 'argent-lane',
      date: '2026-05-03',
    })));
    await searchAgentKb(agentEntries[0], `${DIMS[0]}-initial`);
    await inspectCollectionForDoc(agentEntries[0].doc, DIMS[0], `agent_${DIMS[0]}_after_upload`);

    await configureAgentKb(DIMS[1]);
    agentEntries.push(await uploadAgentDoc(createSampleFile('agent-kb', DIMS[1], {
      owner: 'Ilya Moreno',
      secret: `AGENT-${DIMS[1]}-CEDAR`,
      queue: 'verdant-bridge',
      date: '2026-05-03',
    })));
    await searchAgentKb(agentEntries[1], `${DIMS[1]}-initial`);
    await inspectCollectionForDoc(agentEntries[1].doc, DIMS[1], `agent_${DIMS[1]}_after_upload`);
    await searchAgentKb(agentEntries[0], `${DIMS[0]}-after-active-${DIMS[1]}`);

    await createProjectWithContract(DIMS[0]);
    const projectEntries = [];
    projectEntries.push(await uploadProjectDoc(createSampleFile('project-kb', DIMS[0], {
      owner: 'Mara Chen',
      secret: `PROJECT-${DIMS[0]}-EMBER`,
      queue: 'blue-harbor',
      date: '2026-05-03',
    })));
    await searchProjectKb(projectEntries[0], `${DIMS[0]}-initial`);
    await inspectCollectionForDoc(projectEntries[0].doc, DIMS[0], `project_${DIMS[0]}_after_upload`);

    await configureProjectKb(DIMS[1]);
    projectEntries.push(await uploadProjectDoc(createSampleFile('project-kb', DIMS[1], {
      owner: 'Niko Alves',
      secret: `PROJECT-${DIMS[1]}-MICA`,
      queue: 'silver-ridge',
      date: '2026-05-03',
    })));
    await searchProjectKb(projectEntries[1], `${DIMS[1]}-initial`);
    await inspectCollectionForDoc(projectEntries[1].doc, DIMS[1], `project_${DIMS[1]}_after_upload`);
    await searchProjectKb(projectEntries[0], `${DIMS[0]}-after-active-${DIMS[1]}`);

    await inspectIndexes();

    await page.goto(`${BASE}/settings/vector-stores`, { waitUntil: 'domcontentloaded' });
    await dismissTour();
    await page.locator('select').first().selectOption(String(vectorStore.id));
    await page.waitForSelector('text=Indexes', { timeout: 30000 });
    assertStep(
      await page.getByText(MODEL, { exact: false }).first().isVisible({ timeout: 5000 }).catch(() => false),
      'vector store settings UI shows resolved index contracts',
      { model: MODEL, vector_store_id: vectorStore.id },
    );
    await shot('30-vector-store-indexes-ui.png');

    evidence.completed_at = new Date().toISOString();
  } catch (error) {
    evidence.error = {
      message: String(error && error.message ? error.message : error),
      stack: String(error && error.stack ? error.stack : ''),
    };
    if (page) {
      try {
        await shot('99-error-state.png');
      } catch {}
    }
    throw error;
  } finally {
    if (page) {
      try {
        const docs = await apiJson(`/api/agents/${AGENT_ID}/knowledge-base`).catch(() => []);
        const deleted = [];
        for (const doc of Array.isArray(docs) ? docs : []) {
          if (createdAgentDocIds.has(doc.id) || createdAgentDocNames.has(doc.document_name)) {
            await apiJson(`/api/agents/${AGENT_ID}/knowledge-base/${doc.id}`, { method: 'DELETE' }).catch((error) => ({ error: String(error) }));
            deleted.push({ id: doc.id, name: doc.document_name });
          }
        }
        evidence.cleanup.deleted_agent_docs = deleted;
      } catch (error) {
        evidence.cleanup.agent_doc_delete_error = String(error && error.message ? error.message : error);
      }

      try {
        if (createdProjectId) {
          const projectDocs = await apiJson(`/api/projects/${createdProjectId}/knowledge`).catch(() => []);
          const deleted = [];
          for (const doc of Array.isArray(projectDocs) ? projectDocs : []) {
            if (createdProjectDocIds.has(doc.id)) {
              await apiJson(`/api/projects/${createdProjectId}/knowledge/${doc.id}`, { method: 'DELETE' }).catch((error) => ({ error: String(error) }));
              deleted.push({ id: doc.id, name: doc.name });
            }
          }
          evidence.cleanup.deleted_project_docs = deleted;
          evidence.cleanup.deleted_project = await apiJson(`/api/projects/${createdProjectId}`, { method: 'DELETE' }).catch((error) => ({ error: String(error) }));
        }
      } catch (error) {
        evidence.cleanup.project_delete_error = String(error && error.message ? error.message : error);
      }

      try {
        if (originalAgentConfig) {
          evidence.cleanup.restored_agent_kb_config = await apiJson(`/api/agents/${AGENT_ID}/knowledge-base/config`, {
            method: 'PUT',
            body: {
              embedding_provider_instance_id: originalAgentConfig.embedding_provider_instance_id,
              embedding_provider: originalAgentConfig.embedding_provider,
              embedding_model: originalAgentConfig.embedding_model,
              embedding_dims: originalAgentConfig.embedding_dims,
              embedding_metric: originalAgentConfig.embedding_metric,
              vector_store_instance_id: originalAgentConfig.vector_store_instance_id,
              chunk_strategy: originalAgentConfig.chunk_strategy,
              chunk_size: originalAgentConfig.chunk_size,
              chunk_overlap: originalAgentConfig.chunk_overlap,
              parser: originalAgentConfig.parser,
              search_top_k: originalAgentConfig.search_top_k,
              similarity_threshold: originalAgentConfig.similarity_threshold,
            },
          });
        }
      } catch (error) {
        evidence.cleanup.restore_agent_config_error = String(error && error.message ? error.message : error);
      }

      try {
        let after = {};
        for (let attempt = 0; attempt < 12; attempt += 1) {
          after = {};
          for (const collectionName of collectionBaselines.keys()) {
            const collection = await qdrantCollection(vectorStore, collectionName);
            after[collectionName] = {
              ok: collection.ok,
              points: pointsFromCollection(collection),
              vector_size: vectorSizeFromCollection(collection),
              points_before_cleanup: collectionBaselines.get(collectionName),
            };
          }
          if (Object.values(after).every((entry) => Number(entry.points || 0) === 0)) {
            break;
          }
          await page.waitForTimeout(500);
        }
        evidence.cleanup.qdrant_after_cleanup = after;
        const nonEmptyCollections = Object.entries(after)
          .filter(([, entry]) => Number(entry.points || 0) !== 0)
          .map(([collectionName, entry]) => ({ collectionName, ...entry }));
        evidence.cleanup.qdrant_zero_after_cleanup = nonEmptyCollections.length === 0;
        if (nonEmptyCollections.length > 0) {
          cleanupFailure = new Error(
            `Qdrant cleanup left non-empty collections: ${JSON.stringify(nonEmptyCollections).slice(0, 1200)}`,
          );
        }
      } catch (error) {
        evidence.cleanup.qdrant_after_cleanup_error = String(error && error.message ? error.message : error);
      }
    }
    writeEvidence();
    if (context) await context.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
    if (cleanupFailure) {
      throw cleanupFailure;
    }
  }
}

main()
  .then(() => {
    writeEvidence();
    console.log(`PASS multi-index external vector UI regression`);
    console.log(`Evidence: ${path.join(EVIDENCE_DIR, 'multi-index-external-vector-ui-regression-evidence.json')}`);
  })
  .catch((error) => {
    writeEvidence();
    console.error(`FAIL multi-index external vector UI regression: ${error && error.stack ? error.stack : error}`);
    console.error(`Evidence: ${path.join(EVIDENCE_DIR, 'multi-index-external-vector-ui-regression-evidence.json')}`);
    process.exit(1);
  });
