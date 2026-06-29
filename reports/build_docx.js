const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, Header, Footer, ExternalHyperlink, PageBreak,
} = require("docx");

const OUT = path.join(__dirname, "model-selection-report.docx");
const CONTENT_W = 9360; // US Letter, 1" margins

// ---- helpers ----
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function runs(text) {
  // supports **bold** inline
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map(p => p.startsWith("**") && p.endsWith("**")
    ? new TextRun({ text: p.slice(2, -2), bold: true })
    : new TextRun(p));
}
const P = (text, opts = {}) => new Paragraph({ children: runs(text), spacing: { after: 120 }, ...opts });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const bullet = (t) => new Paragraph({ numbering: { reference: "bul", level: 0 }, children: runs(t), spacing: { after: 60 } });

function table(headerRow, dataRows, widths) {
  const w = widths || headerRow.map(() => Math.floor(CONTENT_W / headerRow.length));
  const mkCell = (txt, i, head) => new TableCell({
    borders, width: { size: w[i], type: WidthType.DXA }, margins: cellMargins,
    shading: head ? { fill: "D5E8F0", type: ShadingType.CLEAR } : undefined,
    children: [new Paragraph({ children: [new TextRun({ text: String(txt), bold: !!head, size: 20 })] })],
  });
  const rows = [new TableRow({ tableHeader: true, children: headerRow.map((c, i) => mkCell(c, i, true)) })];
  for (const r of dataRows) rows.push(new TableRow({ children: r.map((c, i) => mkCell(c, i, false)) }));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: w, rows });
}

const children = [];

// ---- Title block ----
children.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("AI4RSE Taxonomy Evaluation")] }));
children.push(new Paragraph({ children: [new TextRun({ text: "Methodology & Model-Selection Report", size: 28, bold: true, color: "555555" })], spacing: { after: 200 } }));
children.push(P("**Prepared by:** Samet Tok (intern)"));
children.push(P("**For:** Dr. Farshidi (supervisor), AI4RSE project"));
children.push(P("**Date:** 26 June 2026"));
children.push(P("**Project:** Automated validation of IEEE 2025 taxonomy alignment for ~10,542 AI4RSE concepts"));
children.push(P("**Repository:** taxonomy-evaluation (all code, prompts, and data referenced below are committed)"));

// ---- 1. Executive Summary ----
children.push(H1("1. Executive Summary"));
children.push(P("The task was to validate, for each of 10,542 research-software-engineering concepts, whether its automatically-assigned IEEE 2025 taxonomy path is correct, and if not, to classify the problem (misclassified / ambiguous / overly generic / irrelevant) and suggest a better category."));
children.push(P("Over three weeks I moved from manual, one-by-one testing (Gemini web UI, Google AI Studio) to a reproducible API pipeline with a custom web tool for prompt management and result review. I tested five LLMs and benchmarked them on identical inputs."));
children.push(P("Main conclusion: Gemini 2.5 Flash is the best judge for this task. The OpenAI models (gpt-4o-mini, gpt-4.1-mini, gpt-5-mini, gpt-5) were cheaper or newer but produced substantially lower-quality, internally inconsistent output on this specific task."));
children.push(P("Hard evidence (full runs, measured directly from the database):", { spacing: { after: 80 } }));
children.push(table(
  ["Reliability metric", "Gemini 2.5 Flash", "gpt-4.1-mini"],
  [
    ["Concepts evaluated", "6,450", "9,500"],
    ["Self-contradiction ¹", "1.5% (99)", "19% (1,815)"],
    ["Invalid suggestion ²", "0.7% (46)", "16% (1,485)"],
    ["Marked “correctly placed” (none)", "24%", "3%"],
  ],
  [4360, 2500, 2500]
));
children.push(P("¹ Flagged a concept as “misclassified” but suggested the same category it is already in.", { spacing: { before: 80, after: 20 } }));
children.push(P("² Suggested a category name that does not exist in the IEEE taxonomy (an explicit rule violation)."));
children.push(P("A funding request follows in §7 to finish the remaining concepts on the chosen model."));

// ---- 2. Objective ----
children.push(H1("2. Objective & Context"));
children.push(P("The broader AI4RSE systematic literature review extracts, per paper, fields such as Year, Authors, Domain, Application, Standards, GenAI model, Data-collection method, Dataset size, Evaluation approach, Research approach. This sub-task focuses on one column: validating the IEEE taxonomy path assigned to each extracted concept."));
children.push(bullet("Input per concept: concept_name, concept_definition, current low_level category (plus its high/middle parents)."));
children.push(bullet("Reference: the official IEEE 2025 taxonomy (8,037 category names)."));
children.push(bullet("Required output: issue ∈ {none, misclassified, ambiguous, overly_generic, irrelevant}, phantom_category (bool), suggested_low_level (verbatim taxonomy name), confidence, reasoning."));
children.push(P("The taxonomy must not be redesigned — only the alignment is judged."));

// ---- 3. Methodology ----
children.push(H1("3. Methodology & Timeline"));
children.push(H2("Phase 1 — Orientation & taxonomy preparation (Days 1–6)"));
children.push(bullet("Studied the project and ontology vs. taxonomy concepts (“taxonomy is the skeleton; ontology gives the muscle connections; semantics is meaning, not just structure”), and read the assigned papers."));
children.push(bullet("Converted the IEEE taxonomy from PDF to a machine-readable JSON tree via clean_taxonomy.py (noise removal) and parse_taxonomy.py (indentation parsing). The script now knows the exact set of valid categories, so path existence no longer depends on the LLM’s memory."));
children.push(bullet("An initial elaborate plan (Python pre-check + local RAG retrieval + cheap multiple-choice API call) was scoped down after the Day-6 supervisor meeting, in favour of following the assigned task specification exactly."));
children.push(H2("Phase 2 — Manual prompt testing (Days 7–11)"));
children.push(bullet("Built a local web tool (“Prompt Browser”) to organize concepts, manage prompt versions, and review outputs (FastAPI + static front-end)."));
children.push(bullet("Designed a structured-output JSON schema for deterministic parsing (issue, suggested path, confidence, reasoning)."));
children.push(bullet("Manually tested prompts in Google AI Studio and the Gemini web UI (including Pro models), running 20-concept batches by hand and inspecting quality. Iterated the prompt across versions; identified that early prompts under-detected the overly-generic case and refined the rules."));
children.push(bullet("Presented the workflow at the Day-11 meeting; received positive feedback. Funded an initial ₺500 Gemini API budget."));
children.push(H2("Phase 3 — API pipeline & model benchmarking (Days 12–16)"));
children.push(bullet("Migrated the tool to FastAPI, added a SQLite database, live single-concept testing, and a background batch runner."));
children.push(bullet("Tested Gemini 1.5 Flash, 2.5 Flash, and 3.5 Flash. Gemini 2.5 Flash was selected on a cost/quality basis: sufficient quality at a fraction of the price. Gemini 3.5 Flash is ~5× the input price and ~3.6× the output price of 2.5 Flash (see §5.1); the quality difference for this task did not justify that cost."));
children.push(bullet("Processed ~61% of the dataset (6,450 concepts) with Gemini using context caching. This run was a mix of ~90% Gemini 2.5 Flash and ~10% Gemini 3.5 Flash, on Standard (non-batch) pricing — see §9. (“The Gemini run” / prompt 3 throughout this report refers to this 2.5/3.5 mix.)"));
children.push(bullet("When the Gemini budget was exhausted (its prepaid top-up had a ₺500 minimum), switched to OpenAI. Benchmarked gpt-4o-mini, gpt-4.1-mini, gpt-5-mini, and gpt-5; selected gpt-4.1-mini as the best OpenAI option and ran it via the Batch API, reaching 90% (9,500 concepts) on a US$5 budget."));
children.push(bullet("Day-16 meeting with Dr. Farshidi: presented the pipeline and the Gemini-vs-GPT evaluation."));

// ---- 4. Tooling ----
children.push(H1("4. Tooling Built (deliverables)"));
children.push(table(
  ["Component", "Path", "Purpose"],
  [
    ["Taxonomy parser", "clean_taxonomy.py, parse_taxonomy.py, taxonomy/ieee_taxonomy.json", "PDF → validated JSON tree (8,037 categories)"],
    ["Prompt Browser (web)", "prompt-browser/", "Manage prompts; run live/batch evals; review results in-browser"],
    ["Gemini batch runner", "prompt-browser/backend/batch_runner.py", "Background batch eval with context caching"],
    ["OpenAI batch pipeline", "prompt-browser/batch_submit_openai.py", "Auto-chunked OpenAI Batch API runs"],
    ["Sheets export", "prompt-browser/export_for_sheets.py", "Model comparison + supervisor-sheet paste format"],
    ["Results store", "taxonomy.db (SQLite)", "All concepts + per-model evaluation results"],
  ],
  [2200, 3760, 3400]
));
children.push(P("All results are stored under separate “system prompt” rows, so each model’s run is independent and preserved (Gemini and OpenAI results coexist for side-by-side comparison)."));

// ---- 5. Models ----
children.push(H1("5. Models Evaluated"));
children.push(table(
  ["Model", "How tested", "Verdict"],
  [
    ["Gemini web UI (Pro)", "Manual, web UI", "Early exploration / prompt design"],
    ["Gemini 1.5 Flash", "API", "Weaker than 2.5; not selected"],
    ["Gemini 2.5 Flash", "API, 6,450 concepts", "✅ SELECTED — best quality/cost balance"],
    ["Gemini 3.5 Flash", "AI Studio + API", "Comparable quality, ~5× input/3.6× output cost"],
    ["gpt-4o-mini", "API (test)", "Cheapest; weaker reasoning"],
    ["gpt-4.1-mini", "API Batch, 9,500", "Best OpenAI option, but worse than Gemini"],
    ["gpt-5-mini", "API (40-concept test)", "❌ Severe failure mode"],
    ["gpt-5", "API (40-concept test)", "❌ Same failure milder; 6× output cost"],
  ],
  [2600, 3300, 3460]
));

children.push(H2("5.1 Why Gemini 2.5 Flash over 3.5 Flash (cost)"));
children.push(P("The selection between the two viable Gemini models was driven by price, not quality — both produced acceptable validation output, but 3.5 Flash costs several times more.", { spacing: { after: 80 } }));
children.push(table(
  ["Per 1M tokens (USD)", "Gemini 2.5 Flash", "Gemini 3.5 Flash", "3.5 multiplier"],
  [
    ["Input — Standard", "$0.30", "$1.50", "5×"],
    ["Output — Standard", "$2.50", "$9.00", "3.6×"],
    ["Input — Batch", "$0.15", "$0.75", "5×"],
    ["Output — Batch", "$1.25", "$4.50", "3.6×"],
    ["Context-cache (Batch)", "$0.03", "$0.075", "2.5×"],
  ],
  [3060, 2300, 2300, 1700]
));
children.push(P("For a ~10,500-concept run dominated by a re-sent ~46.5k-token system prompt, the 3.5 Flash premium would have multiplied the bill several-fold with no material accuracy gain on this task. 2.5 Flash was the rational choice. Note: the completed Gemini runs used Standard pricing; moving the remaining run to the Batch tier would roughly halve token costs (see §9).", { spacing: { before: 80 } }));

// ---- 6. Quantitative ----
children.push(H1("6. Quantitative Comparison & Proofs"));
children.push(H2("6.1 Controlled head-to-head (same 20 concepts, indices 20–39)"));
children.push(P("All models judged the identical “Evolutionary Computation” concept block. Counts of how each labelled the 20:", { spacing: { after: 80 } }));
children.push(table(
  ["Label", "Gemini 2.5", "gpt-4.1-mini", "gpt-5-mini", "gpt-5"],
  [
    ["none (correct)", "6", "0", "0", "0"],
    ["misclassified", "10", "14", "16", "16"],
    ["overly_generic", "3", "3", "3", "3"],
    ["irrelevant", "1", "3", "1", "1"],
    ["phantom flags", "0", "2", "16", "12"],
    ["reasoning quality", "specific", "specific", "copy-paste", "mixed"],
  ],
  [2360, 1750, 1750, 1750, 1750]
));
children.push(P("gpt-5-mini failure mode: flagged 16/20 as phantom with an identical, copy-pasted justification — it performed a shallow string-capitalisation comparison instead of evaluating placement. gpt-5 showed the same pattern (12/20) and emitted ~6× more output tokens (hidden reasoning), making it the most expensive option.", { spacing: { before: 80 } }));
children.push(H2("6.2 Full-run reliability (entire datasets)"));
children.push(table(
  ["Metric", "Gemini 2.5-flash (6,450)", "gpt-4.1-mini (9,500)"],
  [
    ["none", "24%", "3%"],
    ["misclassified", "65%", "89%"],
    ["overly_generic", "8%", "3%"],
    ["irrelevant", "0.5%", "3%"],
    ["self-contradiction (same category)", "99 (1.5%)", "1,815 (19%)"],
    ["invalid suggestion (not in taxonomy)", "46 (0.7%)", "1,485 (16%)"],
  ],
  [3760, 2800, 2800]
));
children.push(P("gpt-4.1-mini violates the explicit “use a verbatim taxonomy category” rule 16% of the time and contradicts itself 19% of the time. Gemini’s equivalent error rates are an order of magnitude lower.", { spacing: { before: 80 } }));
children.push(H2("6.3 Manual audit (10 random gpt-4.1-mini results vs. the literal rules)"));
children.push(P("Only 2/10 were fully correct. Errors: missed phantom detection; “misclassified → same category” self-contradiction (e.g. adam optimiser → Optimization, already in Optimization); and a suggestion (Malware Analysis) that does not exist in the taxonomy."));
children.push(H2("6.4 Inter-model agreement"));
children.push(P("On the 6,450 concepts both models judged, they disagree on the issue label 35% of the time — confirming the model choice materially changes the dataset."));

// ---- 7. Findings ----
children.push(H1("7. Key Technical Findings (independent of model choice)"));
children.push(P("**1. Capitalisation mismatch between data and taxonomy (important).** The input data is Title-Cased (“Neural Networks”, “Active Learning”) while the IEEE taxonomy is Sentence-cased (“Neural networks”, “Active learning”). Verified against the 8,037-name taxonomy. Under a strict verbatim-match rule, almost every concept is technically a “phantom category”, which is why phantom rates are erratic across models. Recommended fix (free): normalise the data’s capitalisation to match the taxonomy, or make the existence check case-insensitive. This improves reliability for any chosen model."));
children.push(P("**2. Context caching works but does not eliminate cost.** The system prompt (full taxonomy) is ~46,500 tokens and is re-sent per request. Gemini context caching was confirmed working (cached ≈46.5k tokens per request). The large Gemini bill came mainly from 503/429 retry churn under Tier-1 rate limits, not a caching failure."));
children.push(P("**3. OpenAI Batch API constraints.** Tier-1 has a 2,000,000 enqueued-token limit (org-wide, per model). The full run had to be split into sequential chunks of ≤25 requests, with output reservation capped, to stay under the limit."));

// ---- 8. Prompt evolution ----
children.push(H1("8. Prompt Evolution (summary)"));
children.push(bullet("v1: alignment ∈ {Correct, Partially Correct, Incorrect} + suggested_path + confidence (1–5) + reasoning."));
children.push(bullet("v2: introduced explicit issue categories (Misclassified, Ambiguous, Overly Generic, Irrelevant) after manual testing showed the generic case was under-detected."));
children.push(bullet("v3 (current): sequential checks — Relevance → Genericity → Ambiguity → Placement/Phantom — with a strict “suggested category must appear verbatim in the IEEE 2025 taxonomy” rule and a ≤15-word reasoning constraint."));

// ---- 9. Cost ----
children.push(H1("9. Cost & Billing Summary"));
children.push(P("Billing exports to be attached by Samet from the Google AI Studio and OpenAI billing dashboards.", { spacing: { after: 80 } }));
children.push(table(
  ["Provider", "Model", "Concepts done", "Spend", "Notes"],
  [
    ["Google (Gemini)", "~90% 2.5 + ~10% 3.5 Flash", "6,450 (61%)", "≈ ₺550 (attach invoice)", "Standard (non-batch) pricing + context caching; high 503 retry overhead"],
    ["OpenAI", "gpt-4.1-mini + tests", "9,500 (90%)", "US$5.00 (attach invoice)", "Batch API; gpt-5/gpt-5-mini tests included"],
    ["Total", "", "", "≈ ₺550 + US$5", ""],
  ],
  [1700, 1900, 1700, 2000, 2060]
));
children.push(P("Cost-reduction opportunity: the Gemini runs were billed at Standard rates. Running the remaining ~4,092 concepts on the Batch tier would cut Gemini token prices ~50% (input $0.30 → $0.15, output $2.50 → $1.25), on top of eliminating the 503/429 retry overhead that inflated the Standard run.", { spacing: { before: 100 } }));
children.push(P("Attachments to include:", { spacing: { before: 120, after: 60 } }));
children.push(bullet("Google AI Studio billing export (period covering the Gemini runs)"));
children.push(bullet("OpenAI usage/billing export (period covering the OpenAI runs)"));
children.push(bullet("Screenshots: token-usage dashboards (input / cached / output)"));

// ---- 10. Recommendation ----
children.push(H1("10. Recommendation & Decision Required"));
children.push(P("**Recommendation:** Continue and complete the dataset with Gemini 2.5 Flash, the demonstrably more reliable judge for this task. Before the final run, apply the capitalisation normalisation (§7.1) so the phantom_category field becomes trustworthy."));
children.push(P("What is needed from supervisors:", { spacing: { after: 60 } }));
children.push(bullet("Approve continued funding for Gemini 2.5 Flash to evaluate the remaining ~4,092 concepts."));
children.push(bullet("Decide: keep the existing Gemini partial run + finish on Gemini (recommended), or re-run the full set on a single judge for consistency."));
children.push(bullet("Confirm whether the capitalisation fix should be applied to the source data (recommended) or handled in-prompt."));
children.push(P("Comparison artifact for the decision: prompt-browser/compare_gemini_vs_gpt.tsv — every concept with both models’ verdicts side by side and an Agree? flag — ready to paste into the shared Google Sheet."));

// ---- 11. Reproducibility ----
children.push(H1("11. Reproducibility (appendix)"));
children.push(bullet("Taxonomy build: python clean_taxonomy.py && python parse_taxonomy.py"));
children.push(bullet("Web tool: prompt-browser/start.sh → http://localhost:8080"));
children.push(bullet("OpenAI batch run: OPENAI_MODEL=gpt-4.1-mini python batch_submit_openai.py submit --all"));
children.push(bullet("Export for sheets: python prompt-browser/export_for_sheets.py compare"));
children.push(bullet("All results queryable in taxonomy.db (evaluation_results joined to concepts); each model is a separate system_prompts row."));
children.push(new Paragraph({ spacing: { before: 120 }, children: [
  new TextRun("Reference paper: "),
  new ExternalHyperlink({ children: [new TextRun({ text: "https://link.springer.com/article/10.1007/s10515-026-00621-0", style: "Hyperlink" })], link: "https://link.springer.com/article/10.1007/s10515-026-00621-0" }),
] }));

// ---- Document ----
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 40, bold: true, font: "Arial", color: "1F3864" }, paragraph: { spacing: { after: 80 } } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "1F3864" }, paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "2E5496" }, paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun("AI4RSE Model-Selection Report — Page "), new TextRun({ children: [PageNumber.CURRENT] }),
    ] })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("Wrote", OUT); });
