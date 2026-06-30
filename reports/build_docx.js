const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, Footer,
} = require("docx");

const OUT = path.join(__dirname, "model-selection-report.docx");
const CONTENT_W = 9360; // US Letter, 1" margins

// ---- helpers ----
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function runs(text) {
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

// ---- Title ----
children.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("AI4RSE Taxonomy Evaluation")] }));
children.push(new Paragraph({ children: [new TextRun({ text: "Methodology, Model Selection & Final Results", size: 28, bold: true, color: "555555" })], spacing: { after: 200 } }));
children.push(P("**Prepared by:** Samet Tok (intern)"));
children.push(P("**For:** Dr. Farshidi (supervisor), AI4RSE project"));
children.push(P("**Date:** 30 June 2026"));
children.push(P("**Project:** Automated validation of IEEE 2025 taxonomy alignment for 10,542 AI4RSE concepts"));

// ---- 1. Executive Summary ----
children.push(H1("1. Executive Summary"));
children.push(P("The task was to validate, for each of 10,542 research-software-engineering concepts, whether its automatically-assigned IEEE 2025 taxonomy path is correct, and if not, classify the problem (misclassified / ambiguous / overly generic / irrelevant) and suggest a better category."));
children.push(P("Over three weeks I moved from manual, one-by-one testing (Gemini web UI, Google AI Studio) to a reproducible API pipeline, benchmarked five LLMs on identical inputs, fixed two data/prompt quality problems, and produced a complete, single-judge, rule-validated dataset."));
children.push(P("**Conclusions:**", { spacing: { after: 40 } }));
children.push(bullet("The Gemini models are clearly the better judges; the OpenAI models (gpt-4o-mini, gpt-4.1-mini, gpt-5-mini, gpt-5) were cheaper or newer but produced lower-quality, internally inconsistent output."));
children.push(bullet("Final deliverable: all 10,542 concepts evaluated by Gemini 3.5 Flash on capitalisation-normalised data (Batch API + context caching), then cleaned with two deterministic fixes. It passes all nine automated rule-compliance checks with zero violations."));
children.push(P("Hard evidence — OpenAI vs Gemini reliability (measured directly from the results):", { spacing: { before: 80, after: 80 } }));
children.push(table(
  ["Reliability metric", "Gemini", "gpt-4.1-mini"],
  [
    ["Self-contradiction ¹", "1.5%", "19% (1,815)"],
    ["Invalid suggestion ²", "0.7%", "16% (1,485)"],
    ["Marked “correctly placed” (none)", "24%", "3%"],
  ],
  [4360, 2500, 2500]
));
children.push(P("¹ Flagged a concept “misclassified” but suggested the same category it is already in.", { spacing: { before: 80, after: 20 } }));
children.push(P("² Suggested a category name that does not exist in the IEEE taxonomy (an explicit rule violation)."));
children.push(P("**Total cost (this billing request):** ₺1,000 (Gemini, 2 prepayments) + US$6.00 (OpenAI, incl. VAT) — see §8 for invoice-level detail."));

// ---- 2. Objective ----
children.push(H1("2. Objective & Context"));
children.push(P("The broader AI4RSE systematic literature review extracts, per paper, fields such as Year, Authors, Domain, Application, Standards, GenAI model, Data-collection method, Dataset size, Evaluation approach, Research approach. This sub-task focuses on one column: validating the IEEE taxonomy path assigned to each extracted concept."));
children.push(bullet("Input per concept: concept_name, concept_definition, current low_level category (plus high/middle parents)."));
children.push(bullet("Reference: the official IEEE 2025 taxonomy (8,037 category names)."));
children.push(bullet("Required output: issue ∈ {none, misclassified, ambiguous, overly_generic, irrelevant}, phantom_category (bool), suggested_low_level (verbatim taxonomy name), confidence, reasoning."));
children.push(P("The taxonomy must not be redesigned — only the alignment is judged."));

// ---- 3. Methodology ----
children.push(H1("3. Methodology & Timeline"));
children.push(H2("Phase 1 — Orientation & taxonomy preparation (Days 1–6)"));
children.push(bullet("Studied the project and ontology vs. taxonomy concepts; read the assigned papers."));
children.push(bullet("Converted the IEEE taxonomy from its source PDF into a machine-readable, structured reference set (8,037 categories), so path existence no longer depends on the LLM’s memory."));
children.push(bullet("An initial elaborate plan (pre-check + local retrieval + cheap multiple-choice call) was scoped down after the Day-6 meeting to follow the assigned spec exactly."));
children.push(H2("Phase 2 — Manual prompt testing (Days 7–11)"));
children.push(bullet("Built an internal tool to organise concepts, manage prompt versions, and review model outputs."));
children.push(bullet("Designed a structured-output JSON schema; manually tested prompts in Google AI Studio and the Gemini web UI (incl. Pro models); iterated the prompt; funded an initial ₺500 Gemini budget."));
children.push(H2("Phase 3 — API pipeline & model benchmarking (Days 12–16)"));
children.push(bullet("Moved from manual testing to an automated pipeline with live testing and a background batch runner."));
children.push(bullet("Tested Gemini 1.5 / 2.5 / 3.5 Flash; selected 2.5 Flash initially on cost. Processed ~61% (6,450) with Gemini (≈90% 2.5 + ≈10% 3.5) on Standard pricing + caching."));
children.push(bullet("Budget exhausted → benchmarked OpenAI models; ran gpt-4.1-mini via Batch API to 90% (9,500) on US$5."));
children.push(H2("Phase 4 — Data/prompt fixes & full clean run (Days 17–20)"));
children.push(bullet("Normalised the capitalisation mismatch — fixed 2,628 concepts (25%) that were false phantoms."));
children.push(bullet("Confirmed Gemini Batch API + context caching works, and re-ran the entire 10,542-concept dataset on Gemini 3.5 Flash (normalised data) — a clean single-judge result."));
children.push(bullet("Found & fixed two prompt gaps via deterministic auditing (genericity 251, empty-category 10); ran a nine-check rule-compliance sweep — zero violations."));

// ---- 4. Models ----
children.push(H1("4. Models Evaluated"));
children.push(table(
  ["Model", "How tested", "Verdict"],
  [
    ["Gemini web UI (Pro)", "Manual", "Early exploration / prompt design"],
    ["Gemini 1.5 Flash", "API", "Weaker than 2.5; not selected"],
    ["Gemini 2.5 Flash", "API, 6,450", "Good quality; initial cost-driven choice"],
    ["Gemini 3.5 Flash", "API Batch, full 10,542", "✅ FINAL judge — best rule-fidelity, normalised data"],
    ["gpt-4o-mini", "API (test)", "Cheapest; weaker reasoning"],
    ["gpt-4.1-mini", "API Batch, 9,500", "Best OpenAI option, but worse than Gemini"],
    ["gpt-5-mini", "API (test)", "❌ Severe failure mode"],
    ["gpt-5", "API (test)", "❌ Same failure milder; 6× output cost"],
  ],
  [2600, 3000, 3760]
));
children.push(H2("4.1 Gemini 2.5 vs 3.5 Flash — cost, and how it was resolved"));
children.push(P("The choice between the two viable Gemini models was driven by price, not quality:", { spacing: { after: 80 } }));
children.push(table(
  ["Per 1M tokens (USD)", "2.5 Flash", "3.5 Flash", "3.5 multiplier"],
  [
    ["Input — Batch", "$0.15", "$0.75", "5×"],
    ["Output — Batch", "$1.25", "$4.50", "3.6×"],
  ],
  [3360, 2000, 2000, 2000]
));
children.push(P("2.5 Flash was rational for the partial run. For the final complete dataset, 3.5 Flash was used because (a) Batch API + context caching brought per-token cost into an acceptable range, and (b) on normalised data 3.5 Flash is the most rule-faithful judge. The result is one consistent, high-quality judge across all 10,542 concepts.", { spacing: { before: 80 } }));

// ---- 5. Quantitative ----
children.push(H1("5. Quantitative Comparison & Proofs"));
children.push(H2("5.1 Controlled head-to-head (same 20 concepts)"));
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
children.push(P("gpt-5-mini failure mode: flagged 16/20 phantom with an identical copy-pasted justification — a shallow string-capitalisation comparison instead of evaluating placement. gpt-5 showed the same pattern and emitted ~6× more output tokens, making it the most expensive option.", { spacing: { before: 80 } }));
children.push(H2("5.2 Full-run reliability"));
children.push(table(
  ["Metric", "Gemini 2.5-flash (6,450)", "gpt-4.1-mini (9,500)"],
  [
    ["none", "24%", "3%"],
    ["misclassified", "65%", "89%"],
    ["self-contradiction (same category)", "99 (1.5%)", "1,815 (19%)"],
    ["invalid suggestion (not in taxonomy)", "46 (0.7%)", "1,485 (16%)"],
  ],
  [3760, 2800, 2800]
));
children.push(P("gpt-4.1-mini violates the verbatim-category rule 16% of the time and contradicts itself 19% of the time; Gemini’s rates are an order of magnitude lower.", { spacing: { before: 80 } }));
children.push(H2("5.3 Manual audits (judged against the literal rules)"));
children.push(bullet("gpt-4.1-mini: only 2/10 random results fully correct (missed phantoms, self-contradictions, an invented category “Malware Analysis”)."));
children.push(bullet("Gemini 2.5 Flash: 12 random — suggestions all valid, domain-aware; only “errors” were lenient phantom calls on capitalisation (fixed in Phase 4)."));
children.push(bullet("Final Gemini 3.5 Flash on normalised data: 12 random — 0 false phantoms, 0 self-contradictions, 0 invalid suggestions; correct pipeline ordering."));
children.push(H2("5.4 Inter-model agreement"));
children.push(P("On the 6,450 concepts both Gemini and gpt-4.1-mini judged, they disagree on the issue label 35% of the time — confirming the model choice materially changes the dataset."));

// ---- 6. Data Quality & Prompt Improvements ----
children.push(H1("6. Data Quality & Prompt Improvements (key findings)"));
children.push(P("**6.1 Capitalisation mismatch (fixed).** Data was Title-Cased (“Neural Networks”) but the taxonomy is Sentence-cased (“Neural networks”). This made 2,628 concepts (25%) look like phantoms purely over casing. A normalisation step rewrites each low_level entry to the exact taxonomy casing where a case-insensitive match exists (genuine phantoms untouched; fully reversible). Verbatim matches rose 717 → 3,345."));
children.push(P("**6.2 Genericity blind spot (found & fixed — 251 concepts).** The genericity check only compared a concept’s name to its assigned category. Concepts whose name is itself an IEEE category (e.g. “genetic algorithms”, “formal languages”, “computer vision”) but assigned elsewhere slipped through and were marked misclassified → relocate into a same-named category (circular). Of 358 such concepts, 251 (2.4%) were mislabelled; re-evaluated with a corrected prompt (100% agreed overly_generic) and fixed."));
children.push(P("**6.3 Undefined empty-category case (found & fixed — 10 concepts).** The prompt never defined how to handle an empty current_low_level; the model improvised inconsistently. All 10 were finalised (empty → treated as phantom with a verbatim suggestion, unless caught earlier as irrelevant/generic)."));
children.push(P("**6.4 Automated rule-compliance sweep (zero violations).** A nine-check deterministic audit of the final dataset found 0 violations: no suggestion on a non-misclassified row, no missing suggestions, no invalid suggestions, no phantom on the wrong issue, no false phantoms, no missed phantoms, no “none” on a non-existent category, no self-contradictions, no out-of-range confidence."));

// ---- 7. Prompt evolution ----
children.push(H1("7. Prompt Evolution"));
children.push(bullet("v1: alignment ∈ {Correct, Partially Correct, Incorrect} + suggested_path + confidence (1–5) + reasoning."));
children.push(bullet("v2: explicit issue categories (Misclassified, Ambiguous, Overly Generic, Irrelevant)."));
children.push(bullet("v3: sequential pipeline — Relevance → Genericity → Ambiguity → Placement/Phantom — strict verbatim rule, ≤15-word reasoning."));
children.push(bullet("v4 (recommended): (a) flag overly_generic if the name matches ANY IEEE category, not only the assigned one; (b) treat an empty current_low_level as a phantom category."));

// ---- 8. Cost ----
children.push(H1("8. Cost & Billing Summary"));
children.push(P("This covers spend since the initial ₺500 budget approved at the Day-11 meeting (§3).", { spacing: { after: 80 } }));
children.push(table(
  ["Provider", "Invoice #", "Date", "Amount", "Notes"],
  [
    ["Google Cloud (Gemini API)", "5606976172", "Jun 22, 2026", "₺500.00", "Funded capitalisation-fix verification + early 3.5 Flash full-run attempts"],
    ["Google Cloud (Gemini API)", "5607450038", "Jun 29, 2026", "₺500.00", "Funded the completed 10,542-concept 3.5 Flash batch run"],
    ["Google subtotal", "", "", "₺1,000.00", "2 prepayments"],
    ["OpenAI", "31BC7BC9-0001", "Jun 25, 2026", "$6.00", "$5.00 usage credit + 20% VAT $1.00; funded gpt-4.1-mini (9,500) + gpt-5/gpt-5-mini tests"],
  ],
  [2400, 1800, 1700, 1260, 2200]
));
children.push(P("**Note on prepaid vs. usage:** the Google amounts above are prepayments (top-ups), not a metered usage statement — Google AI Studio requires prepaid credit.", { spacing: { before: 80 } }));

// ---- 9. Final deliverable ----
children.push(H1("9. Final Deliverable"));
children.push(P("The clean dataset is the Gemini 3.5 Flash run on normalised data, covering all 10,542 / 10,542 concepts (100%)."));
children.push(P("Issue distribution:", { spacing: { after: 80 } }));
children.push(table(
  ["Issue", "Count", "%"],
  [
    ["misclassified", "7,501", "71%"],
    ["none (correctly placed)", "1,757", "17%"],
    ["overly_generic", "793", "8%"],
    ["irrelevant", "455", "4%"],
    ["ambiguous", "36", "<1%"],
  ],
  [4360, 2500, 2500]
));
children.push(P("Provenance: Gemini 3.5 Flash batch 10,271; genericity-fix re-evaluation 251; manually finalised stragglers/edge-cases 21 (≈0.2%).", { spacing: { before: 80 } }));
children.push(P("Quality guarantees: capitalisation normalised (0 false phantoms), genericity gap closed (0 circular suggestions), 0 self-contradictions, 0 invalid suggestions, 0 rule violations across nine automated checks."));
children.push(P("Note for analysis: ~68% of concepts carry a low-level category that is not in the IEEE 2025 taxonomy (genuine phantoms, after normalisation) — a property of the source auto-categorisation, not of any model. It explains the high misclassified rate and is itself a useful SLR result."));

// ---- 10. Conclusions ----
children.push(H1("10. Conclusions & Recommendations"));
children.push(bullet("Use Gemini, not OpenAI, for this task — proven by an order-of-magnitude difference in self-contradiction and invalid-suggestion rates."));
children.push(bullet("The deliverable dataset is complete and validated (§9); no further evaluation spend is required."));
children.push(bullet("Adopt prompt v4 (§7) for any future taxonomy work — the two fixes generalise."));
children.push(bullet("Optional: phantom_category is now deterministic (a taxonomy lookup on normalised data) and could be recomputed independently of the model for a 100% guarantee."));

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
