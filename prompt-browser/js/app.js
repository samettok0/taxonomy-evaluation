/**
 * AI4RSE Taxonomy — Prompt Browser Entry Point
 */

import { fetchPrompts } from './api.js';
import { STATE, loadSavedState } from './state.js';
import { registerView, toggleView } from './router.js';
import { initTreeNav, renderTree } from './components/tree-nav.js';
import { bindModalEvents } from './components/modal.js';

import { initBrowserView, onShowBrowser, renderListView, renderPrompt, jumpToPrompt } from './views/browser-view.js';
import { initTestingView, onShowTesting } from './views/testing-view.js';
import { initBatchView, onShowBatch, onHideBatch } from './views/batch-view.js';

const $ = (sel) => document.querySelector(sel);

document.addEventListener('DOMContentLoaded', async () => {
  try {
    // 1. Initial State Load
    await loadSavedState();
    
    // 2. Fetch all concepts from the server (which gets it from DB/JSON)
    const data = await fetchPrompts();
    STATE.metadata = data.metadata;
    STATE.categoryIndex = data.category_index;
    STATE.prompts = data.prompts;

    Object.keys(STATE.responses).forEach(k => STATE.completed.add(Number(k)));

    // 3. Register Views with Router
    registerView('browser', onShowBrowser, null);
    registerView('testing', onShowTesting, null);
    registerView('batch', onShowBatch, onHideBatch);

    // 4. Initialize Modules
    bindModalEvents();
    initBrowserView(() => {
      // Callback when stats need updating (from browser actions)
      updateStatsUI();
    });
    initTestingView();
    initBatchView();
    initTreeNav(() => {
      renderListView();
    });

    // 5. Setup Global Nav Event Listeners
    $('#nav-browser')?.addEventListener('click', (e) => { e.preventDefault(); toggleView('browser'); });
    $('#nav-testing')?.addEventListener('click', (e) => { e.preventDefault(); toggleView('testing'); });
    $('#nav-batch')?.addEventListener('click', (e) => { e.preventDefault(); toggleView('batch'); });

    // 6. Build initial UI
    $('#total-badge').textContent = `${STATE.prompts.length.toLocaleString()} prompts`;
    $('#nav-total-display').textContent = STATE.prompts.length.toLocaleString();
    $('#nav-input').max = STATE.prompts.length;

    renderTree();
    renderPrompt(STATE.currentIndex);
    updateStatsUI();

    // 7. Hide loading screen and show App
    $('#loading-screen')?.classList.add('fade-out');
    setTimeout(() => {
      $('#loading-screen')?.classList.add('hidden');
      $('#app')?.classList.remove('hidden');
      toggleView('browser'); // Default view
    }, 300);

  } catch (err) {
    const loadingStatus = $('#loading-status');
    const loadingBar = $('#loading-bar');
    if (loadingStatus) loadingStatus.textContent = `Error: ${err.message}. Ensure backend server is running.`;
    if (loadingBar) loadingBar.style.background = 'var(--danger)';
    console.error('Initialization failed:', err);
  }
});

function updateStatsUI() {
  const total = STATE.prompts.length;
  const done = STATE.completed.size;
  const remaining = total - done;
  const pct = total > 0 ? ((done / total) * 100) : 0;

  const statDone = $('#stat-done .stat-value');
  const statRem = $('#stat-remaining .stat-value');
  if (statDone) statDone.textContent = done.toLocaleString();
  if (statRem) statRem.textContent = remaining.toLocaleString();

  const progressFill = $('#progress-ring-fill');
  const progressText = $('#progress-ring-text');
  
  if (progressFill && progressText) {
    const circumference = 2 * Math.PI * 18;
    const offset = circumference - (pct / 100) * circumference;
    progressFill.style.strokeDashoffset = offset;
    progressText.textContent = `${Math.round(pct)}%`;
  }
}
