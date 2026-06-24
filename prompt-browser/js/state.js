/**
 * AI4RSE Taxonomy — Centralized State
 */

export const STORAGE_KEY = 'ai4rse-prompt-browser';

export const STATE = {
  prompts: [],
  categoryIndex: [],
  metadata: null,
  currentIndex: 0,
  responses: {},        // { globalIndex: { response: string, timestamp: string } }
  completed: new Set(),
  filteredIndices: null, // null = show all
  listFilters: { search: '', status: 'all', decision: 'all', page: 1, limit: 100, tree: { high: null, middle: null, low: null } },
  currentView: 'list',
  templates: [],
  activeTemplateId: 't1',
  lastBatchedIndex: 1,
};

export const DEFAULT_TEMPLATES = [
  {
    id: 't1',
    name: 'Default IEEE Alignment',
    content: `You are an expert in Artificial Intelligence, Software Engineering, Ontology Engineering, Knowledge Organization, and Taxonomy Engineering.

Context:
We are evaluating a taxonomy for Artificial Intelligence for Research Software Engineering (AI4RSE). The current taxonomy is aligned with the IEEE Taxonomy (2025 edition). The categorization below was generated automatically and now requires validation.

Your task is not to redesign the IEEE taxonomy. Instead, evaluate whether the concept is appropriately aligned with the current taxonomy path.

Concept:
{{concept_name}}

Definition:
{{concept_definition}}

Current Taxonomy Path:
{{high_level}} > {{middle_level}} > {{low_level}}

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
}`
  },
  {
    id: 't2',
    name: 'Advanced Issue Detection',
    content: `You are an expert in Artificial Intelligence, Software Engineering, Ontology Engineering, Knowledge Organization, and Taxonomy Engineering.

Context:
We are evaluating a taxonomy for Artificial Intelligence for Research Software Engineering (AI4RSE). The current taxonomy is aligned with the IEEE Taxonomy (2025 edition). The categorization below was generated automatically and now requires validation.

Your task is not to redesign the IEEE taxonomy. Instead, evaluate the concept and determine if it has any of the following issues:
- Misclassified Concept: Assigned to an inappropriate category path.
- Ambiguous Concept: Unclear meaning or fits multiple categories equally well.
- Overly Generic Concept: Too broad to be useful as a specific taxonomy node.
- AI4RSE Relevance Issue: Valid AI concept, but does not contribute meaningfully to the AI4RSE domain.

Concept:
{{concept_name}}

Definition:
{{concept_definition}}

Current Taxonomy Path:
{{high_level}} > {{middle_level}} > {{low_level}}

Please answer the following questions mentally before outputting your JSON:
1. Does the concept suffer from ambiguity, being overly generic, or lacking relevance to the AI4RSE domain?
2. If it is relevant and clear, does it belong to the assigned category path? Is it consistent with the IEEE Taxonomy?
3. Based on your evaluation, what is the primary issue? (If multiple exist, pick the most critical one. If none, pick "None").
4. If the concept is misclassified but otherwise valid, suggest a more appropriate category path.
5. Explain your reasoning in one short sentence.

Return your final answer in EXACTLY this JSON format (and nothing else):
{
  "alignment": "Correct | Partially Correct | Incorrect",
  "issue": "None | Misclassified Concept | Ambiguous Concept | Overly Generic Concept | AI4RSE Relevance Issue",
  "suggested_path": "High-Level > Middle-Level > Low-Level (or N/A)",
  "confidence": 1-5,
  "reasoning": "Your one short sentence explanation here."
}`
  }
];

let _saveTimeout = null;

/**
 * Debounce saves — wait 500ms of inactivity before writing to disk
 */
export function saveState() {
  clearTimeout(_saveTimeout);
  _saveTimeout = setTimeout(() => _doSave(), 500);
}

async function _doSave() {
  const data = {
    currentIndex: STATE.currentIndex,
    responses: STATE.responses,
    completed: [...STATE.completed],
    templates: STATE.templates,
    activeTemplateId: STATE.activeTemplateId,
    lastBatchedIndex: STATE.lastBatchedIndex,
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

export async function loadSavedState() {
  try {
    const res = await fetch('/api/load');
    if (res.ok) {
      const data = await res.json();
      STATE.currentIndex = data.currentIndex || 0;
      STATE.responses = data.responses || {};
      STATE.completed = new Set(data.completed || []);
      STATE.templates = data.templates && data.templates.length > 0 ? data.templates : [...DEFAULT_TEMPLATES];
      STATE.activeTemplateId = data.activeTemplateId || 't1';
      STATE.lastBatchedIndex = data.lastBatchedIndex || 1;
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
    STATE.templates = data.templates && data.templates.length > 0 ? data.templates : [...DEFAULT_TEMPLATES];
    STATE.activeTemplateId = data.activeTemplateId || 't1';
    STATE.lastBatchedIndex = data.lastBatchedIndex || 1;
  } catch (e) {
    console.warn('Could not load saved state:', e);
  }
}
