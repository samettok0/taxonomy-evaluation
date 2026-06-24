/**
 * AI4RSE Taxonomy — Modal & Toast Helper
 */

const $ = (sel) => document.querySelector(sel);

let toastTimeout;

export function showToast(message, type = '') {
  const toast = $('#toast');
  if (!toast) return;
  
  const msgEl = $('#toast-message');
  if (msgEl) msgEl.textContent = message;
  
  toast.className = `toast ${type}`;
  toast.classList.remove('hidden');
  
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.classList.add('hidden');
  }, 3000);
}

export function bindModalEvents() {
  // Settings
  $('#btn-settings')?.addEventListener('click', () => $('#settings-dialog')?.showModal());
  $('#btn-close-settings')?.addEventListener('click', () => $('#settings-dialog')?.close());

  // Templates
  $('#btn-close-templates')?.addEventListener('click', () => $('#templates-dialog')?.close());

  // Batch Tools
  $('#btn-batch-tools')?.addEventListener('click', () => $('#batch-tools-dialog')?.showModal());
  $('#btn-close-batch-tools')?.addEventListener('click', () => $('#batch-tools-dialog')?.close());
}
