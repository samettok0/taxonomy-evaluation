/**
 * AI4RSE Taxonomy — System Prompts & Live Testing View
 */

import { fetchSystemPrompts, createSystemPrompt, setActiveSystemPrompt, deleteSystemPrompt, evaluateSingle, fetchPlaygroundHistory, clearPlaygroundHistory } from '../api.js';
import { STATE, saveState } from '../state.js';
import { showToast } from '../components/modal.js';

const $ = (sel) => document.querySelector(sel);
let systemPrompts = [];
let playgroundHistory = [];

export function initTestingView() {
  bindEvents();
}

export async function onShowTesting() {
  await loadSystemPrompts();
  updateSelectedConceptUI();
  await loadPlaygroundHistory();
}

function updateSelectedConceptUI() {
  const index = STATE.currentIndex;
  const concept = STATE.prompts[index];
  
  const input = $('#test-concept-input');
  if (input) input.value = index + 1;

  const totalDisplay = $('#test-concept-total-display');
  if (totalDisplay) totalDisplay.textContent = STATE.prompts.length.toLocaleString();

  const name = $('#test-concept-name');
  if (name) name.textContent = concept ? concept.concept_name : '—';

  const path = $('#test-concept-path');
  if (path) path.textContent = concept ? concept.category_path : '—';
}

async function loadSystemPrompts() {
  try {
    const data = await fetchSystemPrompts();
    systemPrompts = data.prompts || [];
    renderPromptList();
  } catch (e) {
    showToast('Failed to load system prompts', 'error');
  }
}

function renderPromptList() {
  const list = $('#testing-prompt-list');
  if (!list) return;

  list.innerHTML = '';
  systemPrompts.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    // Show active marker
    opt.textContent = `${p.is_active ? '★ ' : ''}${p.name} (Used ${p.result_count} times)`;
    list.appendChild(opt);
  });

  const active = systemPrompts.find(p => p.is_active);
  if (active) {
    list.value = active.id;
    loadPromptIntoEditor(active.id);
  } else if (systemPrompts.length > 0) {
    list.value = systemPrompts[0].id;
    loadPromptIntoEditor(systemPrompts[0].id);
  }
}

function loadPromptIntoEditor(id) {
  const p = systemPrompts.find(p => p.id == id);
  if (!p) return;
  
  const nameEl = $('#testing-prompt-name');
  const contentEl = $('#testing-prompt-content');
  if (nameEl) nameEl.value = p.name;
  if (contentEl) contentEl.value = p.content;

  const btnActivate = $('#btn-activate-prompt');
  if (btnActivate) {
    if (p.is_active) {
      btnActivate.disabled = true;
      btnActivate.textContent = 'Active Prompt';
    } else {
      btnActivate.disabled = false;
      btnActivate.textContent = 'Set as Active';
    }
  }
}

async function handleSaveNewPrompt() {
  const name = $('#testing-prompt-name')?.value.trim() || 'Untitled Prompt';
  const content = $('#testing-prompt-content')?.value || '';
  
  try {
    await createSystemPrompt(name, content);
    showToast('New prompt created', 'success');
    await loadSystemPrompts();
  } catch (e) {
    showToast('Error saving prompt', 'error');
  }
}

async function handleActivatePrompt() {
  const id = $('#testing-prompt-list')?.value;
  if (!id) return;
  try {
    await setActiveSystemPrompt(id);
    showToast('Prompt activated', 'success');
    await loadSystemPrompts();
  } catch (e) {
    showToast('Error activating prompt', 'error');
  }
}

async function handleDeletePrompt() {
  const id = $('#testing-prompt-list')?.value;
  if (!id) return;
  
  if (!confirm('Are you sure you want to delete this prompt AND all its associated evaluations?')) return;
  
  try {
    await deleteSystemPrompt(id);
    showToast('Prompt deleted', 'success');
    await loadSystemPrompts();
  } catch (e) {
    showToast('Cannot delete prompt. You must have at least one.', 'error');
  }
}

async function handleRunTest() {
  const systemPromptId = $('#testing-prompt-list')?.value;
  const conceptIndex = STATE.currentIndex; // Use current concept from Browser view
  
  if (!systemPromptId) {
    showToast('Select a system prompt first', 'error');
    return;
  }
  
  const concept = STATE.prompts[conceptIndex];
  if (!concept) {
    showToast('No concept selected (try navigating in Browser first)', 'error');
    return;
  }

  const btn = $('#btn-run-test');
  const resultArea = $('#testing-result-area');
  const tokensArea = $('#testing-tokens');
  const countInput = $('#test-concept-count');
  const count = countInput ? parseInt(countInput.value) || 20 : 20;
  
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Running...';
  }
  if (resultArea) resultArea.textContent = 'Waiting for API...';
  if (tokensArea) tokensArea.textContent = '';
  
  try {
    const data = await evaluateSingle(conceptIndex, systemPromptId, count);
    if (resultArea) resultArea.textContent = JSON.stringify(data.result, null, 2);
    if (tokensArea) {
      tokensArea.textContent = `Tokens: ${data.tokens.prompt} prompt | ${data.tokens.output} output`;
    }
    showToast('Test complete', 'success');
    await loadPlaygroundHistory();
  } catch (e) {
    if (resultArea) resultArea.textContent = `Error: ${e.message}`;
    showToast('Test failed', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Run Playground Test';
    }
  }
}

function bindEvents() {
  $('#testing-prompt-list')?.addEventListener('change', (e) => loadPromptIntoEditor(e.target.value));
  $('#btn-save-new-prompt')?.addEventListener('click', handleSaveNewPrompt);
  $('#btn-activate-prompt')?.addEventListener('click', handleActivatePrompt);
  $('#btn-delete-prompt')?.addEventListener('click', handleDeletePrompt);
  $('#btn-run-test')?.addEventListener('click', handleRunTest);

  // Concept Selector events
  $('#btn-test-prev')?.addEventListener('click', () => {
    if (STATE.currentIndex > 0) {
      STATE.currentIndex--;
      saveState();
      updateSelectedConceptUI();
    }
  });

  $('#btn-test-next')?.addEventListener('click', () => {
    if (STATE.currentIndex < STATE.prompts.length - 1) {
      STATE.currentIndex++;
      saveState();
      updateSelectedConceptUI();
    }
  });

  $('#test-concept-input')?.addEventListener('change', (e) => {
    const val = parseInt(e.target.value);
    if (val >= 1 && val <= STATE.prompts.length) {
      STATE.currentIndex = val - 1;
      saveState();
      updateSelectedConceptUI();
    } else {
      updateSelectedConceptUI(); // reset invalid input
    }
  });

  $('#btn-clear-history')?.addEventListener('click', handleClearHistory);
}

async function loadPlaygroundHistory() {
  try {
    const data = await fetchPlaygroundHistory();
    playgroundHistory = data.history || [];
    renderPlaygroundHistory();
  } catch (e) {
    showToast('Failed to load history', 'error');
  }
}

function renderPlaygroundHistory() {
  const list = $('#testing-history-list');
  if (!list) return;

  list.innerHTML = '';
  if (playgroundHistory.length === 0) {
    list.innerHTML = '<div style="color: var(--text-tertiary); font-size: 0.85rem; padding: 10px;">No history yet.</div>';
    return;
  }

  playgroundHistory.forEach(h => {
    const d = new Date(h.timestamp);
    const timeStr = d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    const el = document.createElement('div');
    el.className = 'history-item';
    el.style.cssText = `
      background: var(--bg-primary); 
      border: 1px solid var(--border-color); 
      border-radius: 6px; 
      padding: 10px; 
      cursor: pointer;
      transition: border-color 0.2s;
    `;
    el.innerHTML = `
      <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">${h.prompt_name}</div>
      <div style="font-size: 0.75rem; color: var(--text-tertiary); display: flex; justify-content: space-between;">
        <span>Index: ${h.concept_index} (${h.count} batch)</span>
        <span>${timeStr}</span>
      </div>
    `;
    
    el.addEventListener('mouseover', () => el.style.borderColor = 'var(--accent)');
    el.addEventListener('mouseout', () => el.style.borderColor = 'var(--border-color)');
    
    el.addEventListener('click', () => {
      const resultArea = $('#testing-result-area');
      if (resultArea) {
        resultArea.textContent = JSON.stringify(h.result_json, null, 2);
      }
      showToast('Loaded history item', 'success');
    });

    list.appendChild(el);
  });
}

async function handleClearHistory() {
  if (!confirm('Are you sure you want to clear all playground run history?')) return;
  try {
    await clearPlaygroundHistory();
    showToast('History cleared', 'success');
    await loadPlaygroundHistory();
  } catch (e) {
    showToast('Failed to clear history', 'error');
  }
}
