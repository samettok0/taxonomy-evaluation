/**
 * AI4RSE Taxonomy — Batch Execution Dashboard View
 */

import { getEvalStatus, startBatchEvaluation, stopBatchEvaluation, fetchSystemPrompts, fetchEvaluationProgress } from '../api.js';
import { showToast } from '../components/modal.js';

const $ = (sel) => document.querySelector(sel);

let statusInterval = null;

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
    }
  } catch (e) {
    showToast('Failed to load prompts for batch run', 'error');
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
  
  if (!promptId) {
    showToast('Select a system prompt first', 'error');
    return;
  }
  
  try {
    await startBatchEvaluation(promptId, 'full', maxBatches);
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
  });
}
