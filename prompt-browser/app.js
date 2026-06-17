/**
 * AI4RSE Taxonomy — Prompt Browser
 * A local web tool for efficiently browsing, copying, and tracking
 * 10,542 taxonomy evaluation prompts.
 */

// ─── State ──────────────────────────────────────────────────
const STATE = {
  prompts: [],
  categoryIndex: [],
  metadata: null,
  currentIndex: 0,
  responses: {},        // { globalIndex: { response: string, timestamp: string } }
  completed: new Set(),
  filteredIndices: null, // null = show all
  listFilters: { search: '', status: 'all', decision: 'all', page: 1, limit: 100, tree: { high: null, middle: null, low: null } },
  currentView: 'list',
};

const STORAGE_KEY = 'ai4rse-prompt-browser';

// ─── Prompt Template ────────────────────────────────────────
function buildPromptText(entry) {
  return `You are an expert in Artificial Intelligence, Software Engineering, Ontology Engineering, Knowledge Organization, and Taxonomy Engineering.

Context:
We are evaluating a taxonomy for Artificial Intelligence for Research Software Engineering (AI4RSE). The current taxonomy is aligned with the IEEE Taxonomy (2025 edition). The categorization below was generated automatically and now requires validation.

Your task is not to redesign the IEEE taxonomy. Instead, evaluate whether the concept is appropriately aligned with the current taxonomy path.

Concept:
${entry.concept_name}

Definition:
${entry.concept_definition}

Current Taxonomy Path:
${entry.high_level} > ${entry.middle_level} > ${entry.low_level}

Please answer the following questions:
1. Does the concept belong to the assigned category path?
2. Is the categorization consistent with the IEEE Taxonomy?
3. If not, suggest a more appropriate category path.
4. Explain your reasoning in one short sentence.
5. Rate your confidence from 1 (very low) to 5 (very high).

Return your answer in JSON format:
{
  "alignment": "Correct | Partially Correct | Incorrect",
  "suggested path": "High-Level > Middle-Level > Low-Level (or N/A)",
  "confidence": 1-5,
  "reasoning": "Your one short sentence explanation here."
}`;
}

// ─── DOM References ─────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ─── Init ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadSavedState();
  loadPrompts();
  bindEvents();
});

// ─── Load Data ──────────────────────────────────────────────
async function loadPrompts() {
  const loadingBar = $('#loading-bar');
  const loadingStatus = $('#loading-status');

  try {
    loadingStatus.textContent = 'Loading prompts_slim.json...';
    loadingBar.style.width = '20%';

    const response = await fetch('../prompts_slim.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    loadingBar.style.width = '50%';
    loadingStatus.textContent = 'Parsing JSON (5 MB)...';

    const data = await response.json();

    loadingBar.style.width = '80%';
    loadingStatus.textContent = 'Building UI...';

    STATE.metadata = data.metadata;
    STATE.categoryIndex = data.category_index;
    STATE.prompts = data.prompts;

    // Merge completed set from saved responses
    Object.keys(STATE.responses).forEach(k => STATE.completed.add(Number(k)));

    loadingBar.style.width = '100%';
    loadingStatus.textContent = `Loaded ${STATE.prompts.length.toLocaleString()} prompts`;

    await sleep(400);
    initUI();
  } catch (err) {
    loadingStatus.textContent = `Error: ${err.message}. Make sure prompts.json is in the parent directory.`;
    loadingBar.style.background = 'var(--danger)';
    console.error('Failed to load prompts:', err);
  }
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ─── Initialize UI ──────────────────────────────────────────
function initUI() {
  // Show app, hide loading
  $('#loading-screen').classList.add('fade-out');
  setTimeout(() => {
    $('#app').classList.remove('hidden');
  }, 300);

  // Set total badge
  $('#total-badge').textContent = `${STATE.prompts.length.toLocaleString()} prompts`;
  $('#nav-total-display').textContent = STATE.prompts.length.toLocaleString();
  $('#nav-input').max = STATE.prompts.length;

  // Render Tree
  renderTree();

  // Render current prompt
  renderPrompt(STATE.currentIndex);

  // Render list view
  renderListView();

  // Show default view
  toggleView('list');

  // Update stats
  updateStats();
}

// ─── View Toggling ──────────────────────────────────────────
function toggleView(viewName) {
  STATE.currentView = viewName;
  if (viewName === 'list') {
    $('#view-list').classList.remove('hidden');
    $('#view-prompt').classList.add('hidden');
    $('#btn-back-to-list').classList.add('hidden');
    renderListView(); // refresh list when returning
  } else {
    $('#view-list').classList.add('hidden');
    $('#view-prompt').classList.remove('hidden');
    $('#btn-back-to-list').classList.remove('hidden');
  }
}

// ─── List View Rendering ────────────────────────────────────
function renderListView() {
  const tbody = $('#list-table-body');
  const filters = STATE.listFilters;
  
  // 1. Filter
  const q = filters.search.toLowerCase();
  let filtered = [];
  
  for (let i = 0; i < STATE.prompts.length; i++) {
    const p = STATE.prompts[i];
    const r = STATE.responses[i];
    const isDone = STATE.completed.has(i);
    
    // Status filter
    if (filters.status === 'done' && !isDone) continue;
    if (filters.status === 'pending' && isDone) continue;
    
    // Decision filter
    const currentDec = r ? r.decision : '';
    if (filters.decision !== 'all') {
      if (filters.decision === 'none' && currentDec) continue;
      if (filters.decision !== 'none' && currentDec !== filters.decision) continue;
    }
    
    // Search filter
    if (q) {
      if (!p.concept_name.toLowerCase().includes(q) && 
          !p.category_path.toLowerCase().includes(q)) {
        continue;
      }
    } else {
      // Tree filter (only apply if not searching)
      if (filters.tree.high && p.high_level !== filters.tree.high) continue;
      if (filters.tree.middle && p.middle_level !== filters.tree.middle) continue;
      if (filters.tree.low && p.low_level !== filters.tree.low) continue;
    }
    
    filtered.push(i);
  }
  
  STATE.filteredIndices = filtered;
  
  // 2. Pagination
  const totalItems = filtered.length;
  const totalPages = Math.ceil(totalItems / filters.limit) || 1;
  
  if (filters.page > totalPages) filters.page = totalPages;
  if (filters.page < 1) filters.page = 1;
  
  const startIdx = (filters.page - 1) * filters.limit;
  const endIdx = Math.min(startIdx + filters.limit, totalItems);
  
  const pageItems = filtered.slice(startIdx, endIdx);
  
  // 3. Render Table
  tbody.innerHTML = '';
  
  pageItems.forEach(i => {
    const p = STATE.prompts[i];
    const r = STATE.responses[i];
    const isDone = STATE.completed.has(i);
    
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>#${i + 1}</td>
      <td style="font-weight: 500;">${p.concept_name}</td>
      <td style="color: var(--text-tertiary); font-size: 0.75rem;">${p.category_path}</td>
      <td>
        <div class="status-cell">
          <span class="status-dot ${isDone ? 'done' : ''}"></span>
          ${isDone ? 'Done' : 'Pending'}
        </div>
      </td>
      <td>
        <span class="badge" style="background: var(--bg-secondary);">${r ? r.decision || '-' : '-'}</span>
      </td>
    `;
    
    tr.addEventListener('click', () => {
      jumpToPrompt(i);
      toggleView('prompt');
    });
    
    tbody.appendChild(tr);
  });
  
  if (pageItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 40px; color: var(--text-tertiary);">No concepts found matching your filters.</td></tr>`;
  }
  
  // 4. Update Pagination UI
  $('#page-info').textContent = `Showing ${startIdx + 1}-${endIdx} of ${totalItems} (Page ${filters.page} of ${totalPages})`;
  $('#btn-page-prev').disabled = filters.page === 1;
  $('#btn-page-next').disabled = filters.page === totalPages;
}

// ─── Tree Navigation ────────────────────────────────────────
function renderTree() {
  const highList = $('#tree-high-list');
  const midList = $('#tree-mid-list');
  const lowList = $('#tree-low-list');
  
  const selectedHigh = STATE.listFilters.tree.high;
  const selectedMid = STATE.listFilters.tree.middle;
  const selectedLow = STATE.listFilters.tree.low;

  // 1. Render High Level
  const highLevels = [...new Set(STATE.categoryIndex.map(c => c.path.split(' → ')[0] || 'Other'))].sort();
  highList.innerHTML = '';
  
  highLevels.forEach(hl => {
    const item = document.createElement('div');
    item.className = 'tree-item' + (selectedHigh === hl ? ' active' : '');
    item.textContent = hl;
    item.addEventListener('click', () => {
      STATE.listFilters.tree.high = selectedHigh === hl ? null : hl;
      STATE.listFilters.tree.middle = null;
      STATE.listFilters.tree.low = null;
      STATE.listFilters.page = 1;
      
      // Clear search if using tree
      if (STATE.listFilters.tree.high) {
        STATE.listFilters.search = '';
        $('#search-input').value = '';
        $('#search-clear').classList.add('hidden');
      }
      
      renderTree();
      renderListView();
    });
    highList.appendChild(item);
  });

  // 2. Render Middle Level
  if (!selectedHigh) {
    midList.innerHTML = '<div class="tree-empty">Select High Level first</div>';
    lowList.innerHTML = '<div class="tree-empty">Select Middle Level first</div>';
    return;
  }
  
  const midLevels = [...new Set(STATE.categoryIndex
    .filter(c => (c.path.split(' → ')[0] || 'Other') === selectedHigh)
    .map(c => c.path.split(' → ')[1])
    .filter(Boolean))].sort();
    
  midList.innerHTML = '';
  if (midLevels.length === 0) {
    midList.innerHTML = '<div class="tree-empty">No middle levels</div>';
  } else {
    midLevels.forEach(ml => {
      const item = document.createElement('div');
      item.className = 'tree-item' + (selectedMid === ml ? ' active' : '');
      item.textContent = ml;
      item.addEventListener('click', () => {
        STATE.listFilters.tree.middle = selectedMid === ml ? null : ml;
        STATE.listFilters.tree.low = null;
        STATE.listFilters.page = 1;
        renderTree();
        renderListView();
      });
      midList.appendChild(item);
    });
  }

  // 3. Render Low Level
  if (!selectedMid) {
    lowList.innerHTML = '<div class="tree-empty">Select Middle Level first</div>';
    return;
  }

  const lowLevels = [...new Set(STATE.categoryIndex
    .filter(c => (c.path.split(' → ')[0] || 'Other') === selectedHigh && c.path.split(' → ')[1] === selectedMid)
    .map(c => c.path.split(' → ')[2])
    .filter(Boolean))].sort();
    
  lowList.innerHTML = '';
  if (lowLevels.length === 0) {
    lowList.innerHTML = '<div class="tree-empty">No low levels</div>';
  } else {
    lowLevels.forEach(ll => {
      const item = document.createElement('div');
      item.className = 'tree-item' + (selectedLow === ll ? ' active' : '');
      item.textContent = ll;
      item.addEventListener('click', () => {
        STATE.listFilters.tree.low = selectedLow === ll ? null : ll;
        STATE.listFilters.page = 1;
        renderTree();
        renderListView();
      });
      lowList.appendChild(item);
    });
  }
}

// ─── Render Prompt ──────────────────────────────────────────
function renderPrompt(index) {
  const prompt = STATE.prompts[index];
  if (!prompt) return;

  STATE.currentIndex = index;

  // Auto-save position so it persists across browser closes
  saveState();

  // Update nav input
  $('#nav-input').value = index + 1;

  // Card meta
  $('#card-index').textContent = `#${(index + 1).toLocaleString()}`;
  $('#card-row').textContent = `Row ${prompt.original_row}`;

  const isDone = STATE.completed.has(index);
  const statusBadge = $('#card-status');
  statusBadge.textContent = isDone ? 'Done' : 'Pending';
  statusBadge.className = isDone ? 'badge badge-status done' : 'badge badge-status';

  // Toggle Reset to Pending button
  if (isDone) {
    $('#btn-mark-pending').classList.remove('hidden');
  } else {
    $('#btn-mark-pending').classList.add('hidden');
  }

  // Category breadcrumbs
  $('#crumb-high').textContent = prompt.high_level || '—';
  $('#crumb-mid').textContent = prompt.middle_level || '—';
  $('#crumb-low').textContent = prompt.low_level || '—';

  // Concept
  $('#concept-name').textContent = prompt.concept_name || '—';
  $('#concept-definition').textContent = prompt.concept_definition || '—';

  // Prompt text - build from updated template
  $('#prompt-text').textContent = buildPromptText(prompt);

  // Response
  const saved = STATE.responses[index];
  $('#response-textarea').value = saved ? saved.response : '';

  // Decision Panel
  const decisionSelect = $('#decision-select');
  const decisionReason = $('#decision-reason');
  const decisionIssues = $('#decision-issues');
  const decisionNewPathRow = $('#decision-newpath-row');
  const decisionNewPath = $('#decision-newpath');
  const decisionAutofill = $('#decision-autofill');
  
  if (saved && saved.decision) {
    decisionSelect.value = saved.decision;
    decisionSelect.dataset.decision = saved.decision;
    decisionReason.value = saved.reason || '';
    decisionIssues.value = saved.issues || '';
    if (saved.decision === 'Move') {
      decisionNewPathRow.classList.remove('hidden');
      decisionNewPath.value = saved.newPath || '';
    } else {
      decisionNewPathRow.classList.add('hidden');
      decisionNewPath.value = '';
    }
  } else {
    decisionSelect.value = '';
    decisionSelect.dataset.decision = '';
    decisionReason.value = '';
    decisionIssues.value = '';
    decisionNewPathRow.classList.add('hidden');
    decisionNewPath.value = '';
  }
  
  // Hide autofill banner by default
  decisionAutofill.classList.add('hidden');

  // Reset copy button
  const copyBtn = $('#btn-copy');
  copyBtn.classList.remove('copied');
  copyBtn.querySelector('.btn-copy-label').textContent = 'Copy Prompt';

  // Scroll to top
  $('.prompt-card-wrapper').scrollTop = 0;
}

// ─── Navigation ─────────────────────────────────────────────
function jumpToPrompt(index) {
  const effectiveList = getEffectiveList();
  if (effectiveList) {
    // If filtered, find the closest index in the filtered list
    const closest = effectiveList.reduce((prev, curr) =>
      Math.abs(curr - index) < Math.abs(prev - index) ? curr : prev
    );
    renderPrompt(closest);
  } else {
    if (index >= 0 && index < STATE.prompts.length) {
      renderPrompt(index);
    }
  }
  updateStats();
}

function navigateNext() {
  const effectiveList = getEffectiveList();
  if (effectiveList) {
    const currentPos = effectiveList.indexOf(STATE.currentIndex);
    const nextPos = currentPos + 1;
    if (nextPos < effectiveList.length) {
      renderPrompt(effectiveList[nextPos]);
    }
  } else {
    if (STATE.currentIndex < STATE.prompts.length - 1) {
      renderPrompt(STATE.currentIndex + 1);
    }
  }
}

function navigatePrev() {
  const effectiveList = getEffectiveList();
  if (effectiveList) {
    const currentPos = effectiveList.indexOf(STATE.currentIndex);
    const prevPos = currentPos - 1;
    if (prevPos >= 0) {
      renderPrompt(effectiveList[prevPos]);
    }
  } else {
    if (STATE.currentIndex > 0) {
      renderPrompt(STATE.currentIndex - 1);
    }
  }
}

function skipToNextPending() {
  const effectiveList = getEffectiveList();
  if (effectiveList) {
    const pending = effectiveList.find(i => i > STATE.currentIndex && !STATE.completed.has(i));
    if (pending !== undefined) {
      renderPrompt(pending);
    } else {
      // Wrap around
      const first = effectiveList.find(i => !STATE.completed.has(i));
      if (first !== undefined) renderPrompt(first);
      else showToast('All prompts in this filter are complete! 🎉');
    }
  } else {
    for (let i = STATE.currentIndex + 1; i < STATE.prompts.length; i++) {
      if (!STATE.completed.has(i)) {
        renderPrompt(i);
        return;
      }
    }
    // Wrap around from beginning
    for (let i = 0; i <= STATE.currentIndex; i++) {
      if (!STATE.completed.has(i)) {
        renderPrompt(i);
        return;
      }
    }
    showToast('All prompts are complete! 🎉');
  }
}

function getEffectiveList() {
  if (STATE.filteredIndices && STATE.filteredIndices.length > 0) return STATE.filteredIndices;
  return null;
}

// ─── Actions ────────────────────────────────────────────────
async function copyPrompt() {
  const prompt = STATE.prompts[STATE.currentIndex];
  if (!prompt) return;

  const text = buildPromptText(prompt);

  try {
    await navigator.clipboard.writeText(text);
    const btn = $('#btn-copy');
    btn.classList.add('copied');
    btn.querySelector('.btn-copy-label').textContent = 'Copied!';
    showToast('Prompt copied to clipboard ✓', 'success');
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.querySelector('.btn-copy-label').textContent = 'Copy Prompt';
    }, 2000);
  } catch (err) {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('Prompt copied to clipboard ✓', 'success');
  }
}

async function pasteResponse() {
  try {
    const text = await navigator.clipboard.readText();
    $('#response-textarea').value = text;
  } catch (err) {
    showToast('Could not read clipboard. Please paste manually.');
  }
}

function saveResponse() {
  const index = STATE.currentIndex;
  const response = $('#response-textarea').value.trim();
  const decision = $('#decision-select').value;
  const reason = $('#decision-reason').value.trim();
  const issues = $('#decision-issues').value.trim();
  const newPath = $('#decision-newpath').value.trim();

  STATE.responses[index] = {
    response: response,
    decision: decision,
    reason: reason,
    issues: issues,
    newPath: decision === 'Move' ? newPath : '',
    timestamp: new Date().toISOString(),
    concept_name: STATE.prompts[index].concept_name,
    category_path: STATE.prompts[index].category_path,
    original_row: STATE.prompts[index].original_row,
  };
  STATE.completed.add(index);

  saveState();
  updateStats();
  showToast(`Saved response for #${index + 1}`, 'success');
}

function markPending() {
  const index = STATE.currentIndex;
  
  delete STATE.responses[index];
  STATE.completed.delete(index);
  
  // Clear textarea
  $('#response-textarea').value = '';
  
  saveState();
  updateStats();
  renderPrompt(index); // refresh status badge & buttons
  showToast(`#${index + 1} reset to pending`, 'success');
}

function saveAndNext() {
  saveResponse();
  navigateNext();
}

// ─── Stats ──────────────────────────────────────────────────
function updateStats() {
  const total = STATE.prompts.length;
  const done = STATE.completed.size;
  const remaining = total - done;
  const pct = total > 0 ? ((done / total) * 100) : 0;

  $('#stat-done .stat-value').textContent = done.toLocaleString();
  $('#stat-remaining .stat-value').textContent = remaining.toLocaleString();

  // Progress ring
  const circumference = 2 * Math.PI * 18;
  const offset = circumference - (pct / 100) * circumference;
  $('#progress-ring-fill').style.strokeDashoffset = offset;
  $('#progress-ring-text').textContent = `${Math.round(pct)}%`;
}

// ─── Persistence (Local File via Server API) ───────────────
let _saveTimeout = null;

function saveState() {
  // Debounce saves — wait 500ms of inactivity before writing to disk
  // This prevents hammering the server during rapid navigation
  clearTimeout(_saveTimeout);
  _saveTimeout = setTimeout(() => _doSave(), 500);
}

async function _doSave() {
  const data = {
    currentIndex: STATE.currentIndex,
    responses: STATE.responses,
    completed: [...STATE.completed],
    lastSaved: new Date().toISOString(),
  };
  try {
    const res = await fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`Server responded ${res.status}`);
  } catch (e) {
    console.warn('Could not save to server, falling back to localStorage:', e);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (le) {
      console.warn('localStorage also failed:', le);
    }
  }
}

async function loadSavedState() {
  try {
    // Try loading from server first (local file)
    const res = await fetch('/api/load');
    if (res.ok) {
      const data = await res.json();
      STATE.currentIndex = data.currentIndex || 0;
      STATE.responses = data.responses || {};
      STATE.completed = new Set(data.completed || []);
      return;
    }
  } catch (e) {
    console.warn('Could not load from server, trying localStorage:', e);
  }

  // Fallback: try localStorage
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    STATE.currentIndex = data.currentIndex || 0;
    STATE.responses = data.responses || {};
    STATE.completed = new Set(data.completed || []);
  } catch (e) {
    console.warn('Could not load saved state:', e);
  }
}

// ─── Export / Import ────────────────────────────────────────
function exportResponses() {
  const exportData = {
    exported_at: new Date().toISOString(),
    total_responses: Object.keys(STATE.responses).length,
    total_completed: STATE.completed.size,
    responses: {},
  };

  // Build export with full context
  for (const [idx, resp] of Object.entries(STATE.responses)) {
    const prompt = STATE.prompts[Number(idx)];
    exportData.responses[idx] = {
      global_index: Number(idx),
      original_row: prompt?.original_row,
      concept_name: prompt?.concept_name,
      category_path: prompt?.category_path,
      response: resp.response,
      timestamp: resp.timestamp,
    };
  }

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `ai4rse-responses-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('Responses exported ✓', 'success');
}

async function exportDecisionsCSV() {
  showToast('Generating CSV export...', 'info');
  try {
    const headers = [
      "High level", "Middle level", "Low level", 
      "Concept Name", "Concept Definition", 
      "Decision", "Reason", "Issues", "New Taxonomy Path"
    ];
    
    // Helper to escape CSV fields
    const escapeCSV = (str) => {
      if (str === null || str === undefined) return '""';
      const s = String(str).replace(/"/g, '""');
      return `"${s}"`;
    };

    let csvContent = headers.map(escapeCSV).join(',') + '\n';
    
    // Output in original order
    for (let i = 0; i < STATE.prompts.length; i++) {
      const p = STATE.prompts[i];
      if (STATE.responses[i]) {
        const r = STATE.responses[i];
        const row = [
          p.high_level || '',
          p.middle_level || '',
          p.low_level || '',
          p.concept_name || '',
          p.concept_definition || '',
          r.decision || '',
          r.reason || '',
          r.issues || '',
          r.newPath || ''
        ];
        csvContent += row.map(escapeCSV).join(',') + '\n';
      }
    }
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'AI4RSE_Taxonomy_Decisions.csv';
    a.click();
    URL.revokeObjectURL(url);
    
    showToast('Decisions exported to CSV ✓', 'success');
  } catch (err) {
    console.error(err);
    showToast('Error generating CSV export', 'error');
  }
}

function importResponses(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      let imported = 0;

      if (data.responses) {
        for (const [idx, resp] of Object.entries(data.responses)) {
          const i = Number(idx);
          STATE.responses[i] = resp;
          STATE.completed.add(i);
          imported++;
        }
      }

      saveState();
      updateStats();
      renderPrompt(STATE.currentIndex);
      showToast(`Imported ${imported} responses ✓`, 'success');
    } catch (err) {
      showToast('Invalid JSON file');
    }
  };
  reader.readAsText(file);
}

function resetProgress() {
  if (!confirm('Are you sure? This will delete ALL saved responses and progress.')) return;
  STATE.responses = {};
  STATE.completed = new Set();
  localStorage.removeItem(STORAGE_KEY);
  updateStats();
  buildCategorySidebar();
  renderPrompt(0);
  showToast('Progress reset');
}

// ─── Toast ──────────────────────────────────────────────────
let toastTimeout;
function showToast(message, type = '') {
  const toast = $('#toast');
  $('#toast-message').textContent = message;
  toast.className = `toast ${type}`;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.classList.add('hidden');
  }, 3000);
}

// ─── Event Bindings ─────────────────────────────────────────
function bindEvents() {
  // Navigation
  $('#btn-prev').addEventListener('click', navigatePrev);
  $('#btn-next').addEventListener('click', navigateNext);
  $('#btn-skip-to-next-pending').addEventListener('click', skipToNextPending);

  // Nav input
  $('#nav-input').addEventListener('change', (e) => {
    const val = parseInt(e.target.value);
    if (val >= 1 && val <= STATE.prompts.length) {
      renderPrompt(val - 1);
    }
  });

  $('#nav-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.target.blur();
    }
  });

  // Category filter
  $('#category-filter-select').addEventListener('change', (e) => {
    STATE.filterCategory = e.target.value;
    STATE.filteredIndices = null; // reset custom filter
    if (STATE.filterCategory) {
      // Jump to first in category
      const cat = STATE.categoryIndex.find(c => c.path.startsWith(STATE.filterCategory));
      if (cat) renderPrompt(cat.start_index);
    }
  });

  // Copy
  $('#btn-copy').addEventListener('click', copyPrompt);

  // Paste
  $('#btn-paste').addEventListener('click', pasteResponse);

  // Clear response
  $('#btn-clear-response').addEventListener('click', () => {
    $('#response-textarea').value = '';
  });

  // Save & Next
  $('#btn-save-next').addEventListener('click', saveAndNext);

  // Reset to pending
  $('#btn-mark-pending').addEventListener('click', () => {
    markPending();
  });

  // Export
  $('#btn-export').addEventListener('click', exportResponses);
  $('#btn-export-csv').addEventListener('click', exportDecisionsCSV);
  $('#btn-export-responses').addEventListener('click', exportResponses);

  // Import
  $('#btn-import-responses').addEventListener('click', () => {
    $('#import-file').click();
  });
  $('#import-file').addEventListener('change', (e) => {
    if (e.target.files[0]) importResponses(e.target.files[0]);
  });

  // Settings
  $('#btn-settings').addEventListener('click', () => {
    $('#settings-dialog').showModal();
  });
  $('#btn-close-settings').addEventListener('click', () => {
    $('#settings-dialog').close();
  });

  // Reset
  $('#btn-reset').addEventListener('click', resetProgress);

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    // Don't trigger if typing in input/textarea
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    switch (e.key) {
      case 'ArrowLeft':
        e.preventDefault();
        navigatePrev();
        break;
      case 'ArrowRight':
        e.preventDefault();
        navigateNext();
        break;
      case 'c':
        copyPrompt();
        break;
      case 'n':
        skipToNextPending();
        break;
      case 's':
        if (e.metaKey || e.ctrlKey) {
          e.preventDefault();
          saveResponse();
        }
        break;
      case '/':
        e.preventDefault();
        $('#search-input').focus();
        break;
    }
  });

  // List View Events
  $('#btn-back-to-list').addEventListener('click', () => toggleView('list'));

  const searchInput = $('#search-input');
  const searchClear = $('#search-clear');
  
  searchInput.addEventListener('input', (e) => {
    const val = e.target.value;
    STATE.listFilters.search = val;
    STATE.listFilters.page = 1;
    
    if (val) {
      searchClear.classList.remove('hidden');
      // Clear tree selection visually and logically when searching globally
      STATE.listFilters.tree = { high: null, middle: null, low: null };
      renderTree();
    } else {
      searchClear.classList.add('hidden');
    }
    
    renderListView();
  });
  
  searchClear.addEventListener('click', () => {
    searchInput.value = '';
    STATE.listFilters.search = '';
    STATE.listFilters.page = 1;
    searchClear.classList.add('hidden');
    renderListView();
  });

  $('#list-filter-status').addEventListener('change', (e) => {
    STATE.listFilters.status = e.target.value;
    STATE.listFilters.page = 1;
    renderListView();
  });

  $('#list-filter-decision').addEventListener('change', (e) => {
    STATE.listFilters.decision = e.target.value;
    STATE.listFilters.page = 1;
    renderListView();
  });

  $('#btn-page-prev').addEventListener('click', () => {
    STATE.listFilters.page--;
    renderListView();
  });

  $('#btn-page-next').addEventListener('click', () => {
    STATE.listFilters.page++;
    renderListView();
  });

  // Auto-save on textarea change and auto-parse JSON for Decision panel
  let autoSaveTimeout;
  $('#response-textarea').addEventListener('input', () => {
    clearTimeout(autoSaveTimeout);
    
    // Try to auto-parse AI JSON and show autofill banner
    tryAutoParseJSON();
    
    autoSaveTimeout = setTimeout(() => {
      const response = $('#response-textarea').value.trim();
      if (response) {
        saveResponse(); // Uses the unified save function
      }
    }, 1000);
  });
  
  // Decision Panel Events
  $('#decision-select').addEventListener('change', (e) => {
    const val = e.target.value;
    e.target.dataset.decision = val;
    if (val === 'Move') {
      $('#decision-newpath-row').classList.remove('hidden');
    } else {
      $('#decision-newpath-row').classList.add('hidden');
    }
  });

  $('#btn-autofill').addEventListener('click', applyAutofill);

  // Search
  bindSearchEvents();
}

// ─── Search ─────────────────────────────────────────
const MAX_RESULTS = 30;
let searchSelectedIndex = -1;

function highlightMatch(text, query) {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    text.slice(0, idx) +
    '<mark>' + text.slice(idx, idx + query.length) + '</mark>' +
    text.slice(idx + query.length)
  );
}

function runSearch(query) {
  query = query.trim();
  const dropdown = $('#search-dropdown');
  const resultsEl = $('#search-results');
  const footer = $('#search-footer');
  const clearBtn = $('#search-clear');

  // Show/hide clear button
  clearBtn.classList.toggle('hidden', query.length === 0);

  if (!query) {
    dropdown.classList.add('hidden');
    return;
  }

  const q = query.toLowerCase();
  const matches = [];

  for (let i = 0; i < STATE.prompts.length; i++) {
    const p = STATE.prompts[i];
    const conceptMatch = p.concept_name.toLowerCase().includes(q);
    const catMatch = p.category_path.toLowerCase().includes(q);
    if (conceptMatch || catMatch) {
      matches.push({ prompt: p, index: i, conceptMatch, catMatch });
      if (matches.length >= MAX_RESULTS) break;
    }
  }

  searchSelectedIndex = -1;
  resultsEl.innerHTML = '';

  if (matches.length === 0) {
    resultsEl.innerHTML = `<div class="search-no-results">No results for “${query}”</div>`;
    footer.textContent = '';
  } else {
    matches.forEach(({ prompt: p, index, conceptMatch, catMatch }, i) => {
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.dataset.index = index;

      const isDone = STATE.completed.has(index);
      item.innerHTML = `
        <span class="result-index">#${index + 1}</span>
        <div class="result-body">
          <div class="result-concept">${highlightMatch(p.concept_name, conceptMatch ? query : '')}</div>
          <div class="result-category">${highlightMatch(p.category_path, catMatch ? query : '')}</div>
        </div>
        <span class="result-status ${isDone ? 'done' : ''}"></span>
      `;

      item.addEventListener('mousedown', (e) => {
        // mousedown fires before blur — use it to navigate
        e.preventDefault();
        selectSearchResult(index);
      });

      resultsEl.appendChild(item);
    });

    // Count total matches (continue scan)
    let total = matches.length;
    if (matches.length === MAX_RESULTS) {
      for (let i = matches[matches.length - 1].index + 1; i < STATE.prompts.length; i++) {
        const p = STATE.prompts[i];
        if (p.concept_name.toLowerCase().includes(q) || p.category_path.toLowerCase().includes(q)) {
          total++;
        }
      }
    }

    footer.innerHTML = `
      <span>${total > MAX_RESULTS ? `Showing ${MAX_RESULTS} of ${total.toLocaleString()}` : `${total} result${total !== 1 ? 's' : ''}`}</span>
      <span style="color: var(--text-tertiary)">↑↓ navigate &nbsp; Enter select &nbsp; Esc close</span>
    `;
  }

  dropdown.classList.remove('hidden');
}

function selectSearchResult(index) {
  renderPrompt(index);
  closeSearch();
  showToast(`Jumped to #${index + 1}: ${STATE.prompts[index].concept_name}`, 'success');
}

function closeSearch() {
  $('#search-dropdown').classList.add('hidden');
  $('#search-input').blur();
  searchSelectedIndex = -1;
}

function moveSearchSelection(dir) {
  const items = $$('#search-results .search-result-item');
  if (!items.length) return;

  items[searchSelectedIndex]?.classList.remove('selected');
  searchSelectedIndex = Math.max(0, Math.min(items.length - 1, searchSelectedIndex + dir));
  items[searchSelectedIndex].classList.add('selected');
  items[searchSelectedIndex].scrollIntoView({ block: 'nearest' });
}

function bindSearchEvents() {
  const input = $('#search-input');
  const dropdown = $('#search-dropdown');
  const clearBtn = $('#search-clear');

  // Debounced search on input
  let searchTimeout;
  input.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => runSearch(input.value), 120);
  });

  // Keyboard navigation within dropdown
  input.addEventListener('keydown', (e) => {
    if (!dropdown.classList.contains('hidden')) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveSearchSelection(1);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        moveSearchSelection(-1);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        const items = $$('#search-results .search-result-item');
        if (searchSelectedIndex >= 0 && items[searchSelectedIndex]) {
          selectSearchResult(parseInt(items[searchSelectedIndex].dataset.index));
        } else if (items.length === 1) {
          selectSearchResult(parseInt(items[0].dataset.index));
        }
        return;
      }
    }
    if (e.key === 'Escape') {
      closeSearch();
      input.value = '';
      clearBtn.classList.add('hidden');
    }
  });

  // Close when clicking outside
  document.addEventListener('click', (e) => {
    if (!$('#search-box').contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });

  // Clear button
  clearBtn.addEventListener('click', () => {
    input.value = '';
    clearBtn.classList.add('hidden');
    dropdown.classList.add('hidden');
    input.focus();
  });
}

// ─── Auto-parse JSON ────────────────────────────────────────
let autoParsedDecision = null;

function tryAutoParseJSON() {
  const text = $('#response-textarea').value.trim();
  if (!text.startsWith('{') || !text.endsWith('}')) {
    $('#decision-autofill').classList.add('hidden');
    autoParsedDecision = null;
    return;
  }

  try {
    const data = JSON.parse(text);
    if (!data.alignment) return;

    const alignment = data.alignment.toLowerCase();
    let decision = '';
    if (alignment.includes('partially')) decision = 'Discuss';
    else if (alignment.includes('incorrect')) decision = 'Move';
    else if (alignment.includes('correct')) decision = 'Keep';

    if (decision) {
      autoParsedDecision = {
        decision: decision,
        reason: data.reasoning || '',
        newPath: decision === 'Move' ? (data['suggested path'] || '') : ''
      };

      $('#decision-autofill').classList.remove('hidden');
    } else {
      $('#decision-autofill').classList.add('hidden');
      autoParsedDecision = null;
    }
  } catch (err) {
    // Not valid JSON yet
    $('#decision-autofill').classList.add('hidden');
    autoParsedDecision = null;
  }
}

function applyAutofill() {
  if (!autoParsedDecision) return;

  const { decision, reason, newPath } = autoParsedDecision;

  $('#decision-select').value = decision;
  $('#decision-select').dataset.decision = decision;
  $('#decision-reason').value = reason;
  $('#decision-issues').value = autoParsedDecision.issues || '';

  if (decision === 'Move') {
    $('#decision-newpath-row').classList.remove('hidden');
    $('#decision-newpath').value = newPath !== 'N/A' ? newPath : '';
  } else {
    $('#decision-newpath-row').classList.add('hidden');
    $('#decision-newpath').value = '';
  }

  $('#decision-autofill').classList.add('hidden');
  saveResponse(); // trigger auto-save after autofill
  showToast('Applied AI suggestion', 'info');
}
