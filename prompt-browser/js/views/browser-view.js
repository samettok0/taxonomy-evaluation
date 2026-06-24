/**
 * AI4RSE Taxonomy — Browser & Decision View
 */

import { STATE, saveState, STORAGE_KEY } from '../state.js';
import { toggleView } from '../router.js';
import { renderTree } from '../components/tree-nav.js';
import { showToast } from '../components/modal.js';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let updateStatsCallback = null;

export function initBrowserView(statsCallback) {
  updateStatsCallback = statsCallback;
  bindEvents();
}

export function onShowBrowser() {
  renderListView();
}

// ─── List View Rendering ────────────────────────────────────
export function renderListView() {
  const tbody = $('#list-table-body');
  if (!tbody) return;

  const filters = STATE.listFilters;
  const q = filters.search.toLowerCase();
  let filtered = [];
  
  for (let i = 0; i < STATE.prompts.length; i++) {
    const p = STATE.prompts[i];
    const r = STATE.responses[i];
    const isDone = STATE.completed.has(i);
    
    if (filters.status === 'done' && !isDone) continue;
    if (filters.status === 'pending' && isDone) continue;
    
    const currentDec = r ? r.decision : '';
    if (filters.decision !== 'all') {
      if (filters.decision === 'none' && currentDec) continue;
      if (filters.decision !== 'none' && currentDec !== filters.decision) continue;
    }
    
    if (q) {
      if (!p.concept_name.toLowerCase().includes(q) && 
          !p.category_path.toLowerCase().includes(q)) {
        continue;
      }
    } else {
      if (filters.tree.high && p.high_level !== filters.tree.high) continue;
      if (filters.tree.middle && p.middle_level !== filters.tree.middle) continue;
      if (filters.tree.low && p.low_level !== filters.tree.low) continue;
    }
    
    filtered.push(i);
  }
  
  STATE.filteredIndices = filtered;
  
  const totalItems = filtered.length;
  const totalPages = Math.ceil(totalItems / filters.limit) || 1;
  
  if (filters.page > totalPages) filters.page = totalPages;
  if (filters.page < 1) filters.page = 1;
  
  const startIdx = (filters.page - 1) * filters.limit;
  const endIdx = Math.min(startIdx + filters.limit, totalItems);
  
  const pageItems = filtered.slice(startIdx, endIdx);
  
  tbody.innerHTML = '';
  
  pageItems.forEach(i => {
    const p = STATE.prompts[i];
    const r = STATE.responses[i];
    const isDone = STATE.completed.has(i);
    
    const tr = document.createElement('tr');
    tr.dataset.index = i;
    if (i === STATE.currentIndex) {
      tr.classList.add('selected-row');
    }
    
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
    });
    
    tbody.appendChild(tr);
  });
  
  if (pageItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 40px; color: var(--text-tertiary);">No concepts found matching your filters.</td></tr>`;
  }
  
  const pageInfo = $('#page-info');
  if (pageInfo) pageInfo.textContent = `Showing ${startIdx + 1}-${endIdx} of ${totalItems} (Page ${filters.page} of ${totalPages})`;
  
  const btnPrev = $('#btn-page-prev');
  const btnNext = $('#btn-page-next');
  if (btnPrev) btnPrev.disabled = filters.page === 1;
  if (btnNext) btnNext.disabled = filters.page === totalPages;
}

// ─── Render Prompt View ─────────────────────────────────────
export function renderPrompt(index) {
  const prompt = STATE.prompts[index];
  if (!prompt) return;

  STATE.currentIndex = index;
  saveState();

  // Highlight active row in table if list view is rendered
  $$('#list-table-body tr').forEach(row => {
    if (parseInt(row.dataset.index) === index) {
      row.classList.add('selected-row');
    } else {
      row.classList.remove('selected-row');
    }
  });

  const navInput = $('#nav-input');
  if (navInput) navInput.value = index + 1;

  const cardIndex = $('#card-index');
  if (cardIndex) cardIndex.textContent = `#${(index + 1).toLocaleString()}`;
  const cardRow = $('#card-row');
  if (cardRow) cardRow.textContent = `Row ${prompt.original_row}`;

  const isDone = STATE.completed.has(index);
  const statusBadge = $('#card-status');
  if (statusBadge) {
    statusBadge.textContent = isDone ? 'Done' : 'Pending';
    statusBadge.className = isDone ? 'badge badge-status done' : 'badge badge-status';
  }

  const markPendingBtn = $('#btn-mark-pending');
  if (markPendingBtn) {
    if (isDone) markPendingBtn.classList.remove('hidden');
    else markPendingBtn.classList.add('hidden');
  }

  const cHigh = $('#crumb-high'); if (cHigh) cHigh.textContent = prompt.high_level || '—';
  const cMid = $('#crumb-mid'); if (cMid) cMid.textContent = prompt.middle_level || '—';
  const cLow = $('#crumb-low'); if (cLow) cLow.textContent = prompt.low_level || '—';
  const cName = $('#concept-name'); if (cName) cName.textContent = prompt.concept_name || '—';
  const cDef = $('#concept-definition'); if (cDef) cDef.textContent = prompt.concept_definition || '—';

  // Build prompt text
  const template = STATE.templates.find(t => t.id === STATE.activeTemplateId) || STATE.templates[0];
  if (template) {
    let text = template.content;
    text = text.replace(/\{\{concept_name\}\}/g, prompt.concept_name || '—');
    text = text.replace(/\{\{concept_definition\}\}/g, prompt.concept_definition || '—');
    text = text.replace(/\{\{high_level\}\}/g, prompt.high_level || '—');
    text = text.replace(/\{\{middle_level\}\}/g, prompt.middle_level || '—');
    text = text.replace(/\{\{low_level\}\}/g, prompt.low_level || '—');
    const promptTextEl = $('#prompt-text');
    if (promptTextEl) promptTextEl.textContent = text;
  }

  const saved = STATE.responses[index];
  const responseTextArea = $('#response-textarea');
  if (responseTextArea) responseTextArea.value = saved ? saved.response : '';

  const decisionSelect = $('#decision-select');
  const decisionReason = $('#decision-reason');
  const decisionIssues = $('#decision-issues');
  const decisionNewPathRow = $('#decision-newpath-row');
  const decisionNewPath = $('#decision-newpath');
  
  if (saved && saved.decision) {
    if (decisionSelect) {
      decisionSelect.value = saved.decision;
      decisionSelect.dataset.decision = saved.decision;
    }
    if (decisionReason) decisionReason.value = saved.reason || '';
    if (decisionIssues) decisionIssues.value = saved.issues || '';
    if (saved.decision === 'Move') {
      if (decisionNewPathRow) decisionNewPathRow.classList.remove('hidden');
      if (decisionNewPath) decisionNewPath.value = saved.newPath || '';
    } else {
      if (decisionNewPathRow) decisionNewPathRow.classList.add('hidden');
      if (decisionNewPath) decisionNewPath.value = '';
    }
  } else {
    if (decisionSelect) {
      decisionSelect.value = '';
      decisionSelect.dataset.decision = '';
    }
    if (decisionReason) decisionReason.value = '';
    if (decisionIssues) decisionIssues.value = '';
    if (decisionNewPathRow) decisionNewPathRow.classList.add('hidden');
    if (decisionNewPath) decisionNewPath.value = '';
  }
  
  const autofillBanner = $('#decision-autofill');
  if (autofillBanner) autofillBanner.classList.add('hidden');

  const copyBtn = $('#btn-copy');
  if (copyBtn) {
    copyBtn.classList.remove('copied');
    const lbl = copyBtn.querySelector('.btn-copy-label');
    if (lbl) lbl.textContent = 'Copy Prompt';
  }

  const wrapper = $('.prompt-card-wrapper');
  if (wrapper) wrapper.scrollTop = 0;
}

function getEffectiveList() {
  if (STATE.filteredIndices && STATE.filteredIndices.length > 0) return STATE.filteredIndices;
  return null;
}

export function jumpToPrompt(index) {
  const effectiveList = getEffectiveList();
  if (effectiveList) {
    const closest = effectiveList.reduce((prev, curr) =>
      Math.abs(curr - index) < Math.abs(prev - index) ? curr : prev
    );
    renderPrompt(closest);
  } else {
    if (index >= 0 && index < STATE.prompts.length) {
      renderPrompt(index);
    }
  }
  if (updateStatsCallback) updateStatsCallback();
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
    for (let i = 0; i <= STATE.currentIndex; i++) {
      if (!STATE.completed.has(i)) {
        renderPrompt(i);
        return;
      }
    }
    showToast('All prompts are complete! 🎉');
  }
}

export function saveResponse() {
  const index = STATE.currentIndex;
  const response = $('#response-textarea')?.value.trim() || '';
  const decision = $('#decision-select')?.value || '';
  const reason = $('#decision-reason')?.value.trim() || '';
  const issues = $('#decision-issues')?.value.trim() || '';
  const newPath = $('#decision-newpath')?.value.trim() || '';

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
  if (updateStatsCallback) updateStatsCallback();
  showToast(`Saved response for #${index + 1}`, 'success');
}

function markPending() {
  const index = STATE.currentIndex;
  delete STATE.responses[index];
  STATE.completed.delete(index);
  
  const textarea = $('#response-textarea');
  if (textarea) textarea.value = '';
  
  saveState();
  if (updateStatsCallback) updateStatsCallback();
  renderPrompt(index);
  showToast(`#${index + 1} reset to pending`, 'success');
}

function saveAndNext() {
  saveResponse();
  navigateNext();
}

async function copyPrompt() {
  const prompt = STATE.prompts[STATE.currentIndex];
  if (!prompt) return;

  const text = $('#prompt-text')?.textContent || '';

  try {
    await navigator.clipboard.writeText(text);
    const btn = $('#btn-copy');
    if (btn) {
      btn.classList.add('copied');
      const lbl = btn.querySelector('.btn-copy-label');
      if (lbl) lbl.textContent = 'Copied!';
      setTimeout(() => {
        btn.classList.remove('copied');
        const lbl2 = btn.querySelector('.btn-copy-label');
        if (lbl2) lbl2.textContent = 'Copy Prompt';
      }, 2000);
    }
    showToast('Prompt copied to clipboard ✓', 'success');
  } catch (err) {
    showToast('Failed to copy to clipboard', 'error');
  }
}

function bindEvents() {
  $('#btn-prev')?.addEventListener('click', navigatePrev);
  $('#btn-next')?.addEventListener('click', navigateNext);
  $('#btn-skip-to-next-pending')?.addEventListener('click', skipToNextPending);

  $('#nav-input')?.addEventListener('change', (e) => {
    const val = parseInt(e.target.value);
    if (val >= 1 && val <= STATE.prompts.length) {
      renderPrompt(val - 1);
    }
  });

  $('#btn-copy')?.addEventListener('click', copyPrompt);
  $('#btn-save-next')?.addEventListener('click', saveAndNext);
  $('#btn-mark-pending')?.addEventListener('click', markPending);

  $('#btn-paste')?.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      const textarea = $('#response-textarea');
      if (textarea) textarea.value = text;
    } catch (err) {
      showToast('Could not read clipboard. Please paste manually.');
    }
  });

  $('#btn-clear-response')?.addEventListener('click', () => {
    const textarea = $('#response-textarea');
    if (textarea) textarea.value = '';
  });

  // Filters
  $('#list-filter-status')?.addEventListener('change', (e) => {
    STATE.listFilters.status = e.target.value;
    STATE.listFilters.page = 1;
    renderListView();
  });

  $('#list-filter-decision')?.addEventListener('change', (e) => {
    STATE.listFilters.decision = e.target.value;
    STATE.listFilters.page = 1;
    renderListView();
  });

  $('#btn-page-prev')?.addEventListener('click', () => {
    STATE.listFilters.page--;
    renderListView();
  });

  $('#btn-page-next')?.addEventListener('click', () => {
    STATE.listFilters.page++;
    renderListView();
  });

  $('#decision-select')?.addEventListener('change', (e) => {
    const val = e.target.value;
    e.target.dataset.decision = val;
    const row = $('#decision-newpath-row');
    if (row) {
      if (val === 'Move') row.classList.remove('hidden');
      else row.classList.add('hidden');
    }
  });

  // Search
  const searchInput = $('#search-input');
  const searchClear = $('#search-clear');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      STATE.listFilters.search = e.target.value;
      STATE.listFilters.page = 1;
      if (e.target.value) {
        if (searchClear) searchClear.classList.remove('hidden');
        STATE.listFilters.tree = { high: null, middle: null, low: null };
        renderTree();
      } else {
        if (searchClear) searchClear.classList.add('hidden');
      }
      renderListView();
    });
  }
  if (searchClear) {
    searchClear.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      STATE.listFilters.search = '';
      STATE.listFilters.page = 1;
      searchClear.classList.add('hidden');
      renderListView();
    });
  }
}
