/**
 * AI4RSE Taxonomy — Simple View Router
 */
import { STATE, saveState } from './state.js';

const $ = (sel) => document.querySelector(sel);

// Registry of views and their lifecycle callbacks
const views = {};

export function registerView(viewId, onShow, onHide) {
  views[viewId] = { onShow, onHide };
}

export function toggleView(viewName) {
  // Hide current view if different
  if (STATE.currentView && STATE.currentView !== viewName) {
    const oldViewEl = $(`#view-${STATE.currentView}`);
    if (oldViewEl) oldViewEl.classList.add('hidden');
    
    // De-activate nav link
    const oldNav = $(`#nav-${STATE.currentView}`);
    if (oldNav) oldNav.classList.remove('active');

    if (views[STATE.currentView] && views[STATE.currentView].onHide) {
      views[STATE.currentView].onHide();
    }
  }

  STATE.currentView = viewName;
  saveState();

  // Show new view
  const newViewEl = $(`#view-${viewName}`);
  if (newViewEl) newViewEl.classList.remove('hidden');

  // Activate nav link
  const newNav = $(`#nav-${viewName}`);
  if (newNav) newNav.classList.add('active');

  if (views[viewName] && views[viewName].onShow) {
    views[viewName].onShow();
  }
}
