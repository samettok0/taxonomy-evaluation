/**
 * AI4RSE Taxonomy — Batch Execution Dashboard View
 */

import { getEvalStatus, startBatchEvaluation, stopBatchEvaluation, fetchSystemPrompts, fetchEvaluationProgress, fetchEvalResults } from '../api.js';
import { showToast } from '../components/modal.js';

const $ = (sel) => document.querySelector(sel);

let statusInterval = null;
let resultsCache = [];          // last fetched results for the selected prompt
const RESULTS_RENDER_CAP = 500; // cap DOM rows for performance; filter to narrow

const ISSUE_COLORS = {
  none: 'var(--success)',
  misclassified: 'var(--danger)',
  ambiguous: '#e0a030',
  overly_generic: 'var(--accent)',
  irrelevant: 'var(--text-tertiary)',
};

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function initBatchView() {
  bindEvents();
}

export async function onShowBatch() {
  await loadPromptsDropdown();
  startPolling();
}

export function onHideBatch() {
  stopPolling();
}

async function loadPromptsDropdown() {
  try {
    const data = await fetchSystemPrompts();
    const list = $('#batch-prompt-list');
    if (!list) return;
    
    list.innerHTML = '';
    const prompts = data.prompts || [];
    prompts.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.is_active ? '★ ' : ''}${p.name}`;
      list.appendChild(opt);
    });
    
    const active = prompts.find(p => p.is_active);
    if (active) list.value = active.id;

    if (list.value) {
      await updateOverallProgress(list.value);
      await loadResults(list.value);
    }
  } catch (e) {
    showToast('Failed to load prompts for batch run', 'error');
  }
}

async function loadResults(promptId) {
  const body = $('#results-table-body');
  const note = $('#results-count-note');
  const summary = $('#results-summary');
  if (!promptId) return;
  if (body) body.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-tertiary);padding:20px;">Loading…</td></tr>`;
  try {
    const data = await fetchEvalResults(promptId);
    resultsCache = data.results || [];

    // Summary chips: issue breakdown + phantom count.
    if (summary) {
      const chips = [];
      chips.push(`<span style="padding:3px 8px;border-radius:10px;background:var(--bg-secondary);border:1px solid var(--border-color);">Total: <b>${data.total || 0}</b></span>`);
      Object.entries(data.issues || {}).sort((a, b) => b[1] - a[1]).forEach(([k, v]) => {
        const color = ISSUE_COLORS[k] || 'var(--text-secondary)';
        chips.push(`<span style="padding:3px 8px;border-radius:10px;background:var(--bg-secondary);border:1px solid ${color};color:${color};">${escapeHtml(k)}: <b>${v}</b></span>`);
      });
      if (data.phantoms) chips.push(`<span style="padding:3px 8px;border-radius:10px;background:var(--bg-secondary);border:1px solid #c060c0;color:#c060c0;">phantom: <b>${data.phantoms}</b></span>`);
      summary.innerHTML = chips.join('');
    }
    renderResults();
  } catch (e) {
    if (body) body.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--danger);padding:20px;">Failed to load results.</td></tr>`;
    if (note) note.textContent = '';
  }
}

function renderResults() {
  const body = $('#results-table-body');
  const note = $('#results-count-note');
  if (!body) return;

  const issueFilter = $('#results-filter-issue')?.value || 'all';
  const search = ($('#results-search')?.value || '').trim().toLowerCase();

  let rows = resultsCache;
  if (issueFilter === 'phantom') rows = rows.filter(r => r.phantom_category);
  else if (issueFilter !== 'all') rows = rows.filter(r => r.issue === issueFilter);
  if (search) rows = rows.filter(r => (r.concept_name || '').toLowerCase().includes(search));

  const total = rows.length;
  const shown = rows.slice(0, RESULTS_RENDER_CAP);

  if (total === 0) {
    body.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-tertiary);padding:20px;">No results match.</td></tr>`;
    if (note) note.textContent = resultsCache.length ? 'No rows match the current filter.' : 'No results yet for this prompt.';
    return;
  }

  body.innerHTML = shown.map(r => {
    const color = ISSUE_COLORS[r.issue] || 'var(--text-secondary)';
    const conf = (r.confidence != null) ? Number(r.confidence).toFixed(2) : '';
    return `<tr>
      <td style="font-family:monospace;color:var(--text-tertiary);">${r.global_index ?? ''}</td>
      <td>${escapeHtml(r.concept_name)}</td>
      <td><span style="color:${color};font-weight:600;">${escapeHtml(r.issue)}</span></td>
      <td style="text-align:center;">${r.phantom_category ? '⚠️' : ''}</td>
      <td style="color:var(--text-secondary);">${escapeHtml(r.suggested_low_level)}</td>
      <td style="text-align:center;font-family:monospace;">${conf}</td>
      <td style="color:var(--text-tertiary);font-size:0.8rem;max-width:340px;">${escapeHtml(r.reasoning)}</td>
    </tr>`;
  }).join('');

  if (note) {
    note.textContent = total > RESULTS_RENDER_CAP
      ? `Showing first ${RESULTS_RENDER_CAP} of ${total} — use the filter or search to narrow.`
      : `Showing ${total} result${total === 1 ? '' : 's'}.`;
  }
}

async function updateOverallProgress(promptId) {
  try {
    const data = await fetchEvaluationProgress(promptId);
    const pct = data.total_concepts > 0 ? (data.evaluated_concepts / data.total_concepts) * 100 : 0;
    
    const textEl = $('#overall-progress-text');
    const barEl = $('#overall-progress-bar-fill');
    
    if (textEl) {
      textEl.textContent = `Concepts Evaluated: ${data.evaluated_concepts.toLocaleString()} / ${data.total_concepts.toLocaleString()} (${Math.round(pct)}%)`;
    }
    if (barEl) {
      barEl.style.width = `${pct}%`;
    }
  } catch (e) {
    console.error('Failed to fetch overall progress', e);
  }
}

async function handleStartBatch() {
  const promptId = $('#batch-prompt-list')?.value;
  const maxBatchesRaw = $('#batch-max-limit')?.value;
  const maxBatches = maxBatchesRaw ? parseInt(maxBatchesRaw) : null;
  const batchSizeRaw = $('#batch-size')?.value;
  const batchSize = batchSizeRaw ? parseInt(batchSizeRaw) : 20;
  
  if (!promptId) {
    showToast('Select a system prompt first', 'error');
    return;
  }
  
  try {
    await startBatchEvaluation(promptId, 'full', maxBatches, batchSize);
    showToast('Batch evaluation started!', 'success');
    updateStatusUI(); // immediate refresh
  } catch (e) {
    showToast(e.message || 'Error starting evaluation', 'error');
  }
}

async function handleStopBatch() {
  try {
    await stopBatchEvaluation();
    showToast('Stop signal sent (will stop after current batch)', 'info');
  } catch (e) {
    showToast('Error stopping evaluation', 'error');
  }
}

function startPolling() {
  if (statusInterval) clearInterval(statusInterval);
  updateStatusUI();
  statusInterval = setInterval(updateStatusUI, 2000);
}

function stopPolling() {
  if (statusInterval) clearInterval(statusInterval);
  statusInterval = null;
}

async function updateStatusUI() {
  try {
    const status = await getEvalStatus();
    
    const isRunning = status.running;
    const btnStart = $('#btn-batch-start');
    const btnStop = $('#btn-batch-stop');
    
    if (btnStart) btnStart.disabled = isRunning;
    if (btnStop) btnStop.disabled = !isRunning;
    
    // Status text
    const statusTextEl = $('#batch-status-text');
    if (statusTextEl) {
      if (isRunning) {
        if (status.should_stop) statusTextEl.textContent = 'Stopping after current batch...';
        else statusTextEl.textContent = 'Running';
      } else {
        statusTextEl.textContent = 'Idle';
      }
    }
    
    // Progress
    const progressText = $('#batch-progress-text');
    const progressBar = $('#batch-progress-bar-fill');
    
    if (progressText) {
      progressText.textContent = `Batch ${status.current_batch} / ${status.total_batches}`;
    }
    if (progressBar) {
      const pct = status.total_batches > 0 ? (status.current_batch / status.total_batches) * 100 : 0;
      progressBar.style.width = `${pct}%`;
    }
    
    // Stats
    const succEl = $('#batch-stat-success');
    const errEl = $('#batch-stat-error');
    if (succEl) succEl.textContent = status.success_count || 0;
    if (errEl) errEl.textContent = status.error_count || 0;
    
    // Logs
    const logsEl = $('#batch-logs');
    if (logsEl && status.logs) {
      const currentScroll = logsEl.scrollTop;
      const isAtBottom = (logsEl.scrollHeight - currentScroll - logsEl.clientHeight) < 20;
      
      logsEl.innerHTML = status.logs.join('\n');
      
      if (isAtBottom) {
        logsEl.scrollTop = logsEl.scrollHeight;
      }
    }
    
    // Always fetch overall progress from DB for active dropdown
    const currentPromptId = $('#batch-prompt-list')?.value;
    if (currentPromptId) {
      updateOverallProgress(currentPromptId);
    }
    
  } catch (e) {
    // silently fail polling if server restart etc
  }
}

function bindEvents() {
  $('#btn-batch-start')?.addEventListener('click', handleStartBatch);
  $('#btn-batch-stop')?.addEventListener('click', handleStopBatch);
  $('#batch-prompt-list')?.addEventListener('change', (e) => {
    updateOverallProgress(e.target.value);
    loadResults(e.target.value);
  });
  $('#btn-load-results')?.addEventListener('click', () => {
    const promptId = $('#batch-prompt-list')?.value;
    if (promptId) loadResults(promptId);
  });
  $('#results-filter-issue')?.addEventListener('change', renderResults);
  $('#results-search')?.addEventListener('input', renderResults);
}
