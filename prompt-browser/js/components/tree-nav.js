/**
 * AI4RSE Taxonomy — Tree Navigation Component
 */
import { STATE } from '../state.js';

const $ = (sel) => document.querySelector(sel);

let onTreeFilterChange = null;

export function initTreeNav(onChangeCallback) {
  onTreeFilterChange = onChangeCallback;
}

export function renderTree() {
  const highList = $('#tree-high-list');
  const midList = $('#tree-mid-list');
  const lowList = $('#tree-low-list');
  
  if (!highList || !midList || !lowList) return;

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
        const searchInput = $('#search-input');
        const searchClear = $('#search-clear');
        if (searchInput) searchInput.value = '';
        if (searchClear) searchClear.classList.add('hidden');
      }
      
      renderTree();
      if (onTreeFilterChange) onTreeFilterChange();
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
        if (onTreeFilterChange) onTreeFilterChange();
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
        if (onTreeFilterChange) onTreeFilterChange();
      });
      lowList.appendChild(item);
    });
  }
}
