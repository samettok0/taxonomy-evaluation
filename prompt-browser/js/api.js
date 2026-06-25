/**
 * AI4RSE Taxonomy — API Fetch Wrappers
 */

export async function fetchPrompts() {
  const response = await fetch('/api/prompts');
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
}

export async function fetchSystemPrompts() {
  const response = await fetch('/api/system-prompts');
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
}

export async function createSystemPrompt(name, content) {
  const res = await fetch('/api/system-prompts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content })
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function setActiveSystemPrompt(id) {
  const res = await fetch('/api/system-prompts/active', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function deleteSystemPrompt(id) {
  const res = await fetch('/api/system-prompts/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function evaluateSingle(conceptIndex, systemPromptId, count = 1) {
  const res = await fetch('/api/evaluate-single', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ concept_index: conceptIndex, system_prompt_id: systemPromptId, count })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function getEvalStatus() {
  const res = await fetch('/api/evaluation/status');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function startBatchEvaluation(systemPromptId, runMode = 'full', maxBatches = null, batchSize = 20) {
  const res = await fetch('/api/evaluation/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      system_prompt_id: systemPromptId,
      run_mode: runMode,
      max_batches: maxBatches,
      batch_size: batchSize
    })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return await res.json();
}

export async function stopBatchEvaluation() {
  const res = await fetch('/api/evaluation/stop', { method: 'POST' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function fetchEvalResults(systemPromptId) {
  const res = await fetch(`/api/evaluation/results?system_prompt_id=${systemPromptId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function fetchEvaluationProgress(systemPromptId) {
  const res = await fetch(`/api/evaluation/progress?system_prompt_id=${systemPromptId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

export async function fetchPlaygroundHistory() {
  const response = await fetch('/api/playground-history');
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
}

export async function clearPlaygroundHistory() {
  const res = await fetch('/api/playground-history/clear', { method: 'POST' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}
