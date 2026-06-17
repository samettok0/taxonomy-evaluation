Internship Task 1: Evaluation and Refinement of the AI4RSE Taxonomy
1. Introduction
Artificial Intelligence for Research Software Engineering (AI4RSE) is an emerging research area that investigates how Artificial Intelligence techniques can support the development, maintenance, testing, documentation, operation, and evolution of research software.
As the number of publications in this area continues to grow, it becomes increasingly difficult to organize, understand, and navigate the knowledge produced by the research community. To address this challenge, we have developed an AI4RSE taxonomy that captures concepts extracted from a large collection of scientific publications.
The taxonomy was generated using automated extraction techniques, Large Language Models (LLMs), and the IEEE Taxonomy (2025 edition) as a reference structure. The resulting taxonomy contains approximately 11,000 concepts organized into a hierarchical structure consisting of:
High-Level Categories
Middle-Level Categories
Low-Level Categories
Concepts
For example:
Artificial Intelligence
→ Computational Intelligence
→ Agent Systems
→ Autonomous Agents
The initial categorization has already been completed. Every concept has been assigned to a category path within the taxonomy.
However, because the taxonomy was generated automatically, we cannot assume that all concept-category assignments are correct. Some concepts may have been assigned to inappropriate categories, some concepts may appear multiple times, and some concepts may not be relevant to the AI4RSE domain.
Before the taxonomy can be transformed into an ontology, we must first evaluate and refine the current categorization.
2. What is a Taxonomy?
A taxonomy is a structured classification system that organizes concepts into categories and subcategories.
The primary purpose of a taxonomy is to organize knowledge and group related concepts together. A taxonomy helps us understand how concepts are organized within a domain and provides a common vocabulary for discussing that domain.
A taxonomy focuses on classification and hierarchy. It answers questions such as:
Which concepts belong together?
Which category best represents a concept?
How are concepts organized within a domain?
Which concepts belong to a particular research area?
Unlike an ontology, a taxonomy primarily represents hierarchical relationships and classification structures. It does not explicitly represent richer semantic relationships, such as:
supports
improves
depends on
uses
generates
automates
In this project, the taxonomy serves as the foundation for ontology construction. Consequently, the quality of the ontology will depend heavily on the quality of the taxonomy.
3. Why Do We Need to Evaluate the Taxonomy?
Although the taxonomy has already been constructed, its quality has not yet been systematically evaluated.
Several types of issues may exist.
A concept may have been assigned to the wrong category.
For example, a concept related to Software Testing may have been assigned to Software Maintenance.
A concept may appear multiple times under different categories.
A concept may be overly generic and provide little value within the taxonomy.
A concept may be ambiguous or poorly defined.
Some concepts may be valid Artificial Intelligence concepts, but may not be relevant to the AI4RSE domain.
If such issues remain in the taxonomy, they will also propagate into the ontology that we build in the next stage of the project. As a result, errors introduced during taxonomy construction may affect ontology quality, ontology evaluation, and any downstream applications that rely on the ontology.
For this reason, taxonomy evaluation is a critical first step before ontology construction.
4. Objective of This Task
The objective of this task is to evaluate the alignment between concepts and categories within the AI4RSE taxonomy and improve the quality of the current categorization.

We are not creating a new taxonomy.
We are not redesigning the IEEE Taxonomy.
We are not restructuring the overall hierarchy.

Instead, we are evaluating whether the existing concepts have been assigned to appropriate categories and identifying concepts that require modification.
The outcome of this task should be a refined taxonomy that more accurately represents the AI4RSE domain and can serve as the foundation for ontology construction.
5. Taxonomy Evaluation Process
The taxonomy contains approximately 11,000 concepts. Reviewing every concept manually would be time-consuming and difficult to perform consistently.
Therefore, we will use Generative AI as an assistant during the evaluation process.
For each concept, we will provide:
Concept name
Concept definition
Current taxonomy path
The taxonomy path consists of:
High-Level Category → Middle-Level Category → Low-Level Category
For example:
Artificial Intelligence → Computational Intelligence → Agent Systems
Generative AI will evaluate whether the concept belongs to the assigned category and whether a more appropriate taxonomy path exists.
The purpose of using AI is not to automate decision-making completely.
Instead, AI is used to:
identify potentially problematic concepts
suggest alternative taxonomy paths
identify duplicate concepts
identify ambiguous concepts
provide an independent assessment of the current categorization
The final decision should always be based on our own judgment.
The goal is to identify concepts that require changes and record those changes in a structured format.
6. Types of Taxonomy Issues
During the evaluation process, we should pay particular attention to the following types of issues.
Misclassified Concepts
A concept may have been assigned to an inappropriate category.
For example, a concept related to software testing may have been placed under software maintenance.
Duplicate Concepts
The same concept may appear multiple times under different categories or under slightly different names.
Ambiguous Concepts
Some concepts may have unclear meanings or may fit multiple categories equally well.
Overly Generic Concepts
Some concepts may be too broad to be useful and may require further specialization.
AI4RSE Relevance Issues
Some concepts may be valid Artificial Intelligence concepts, but may not contribute meaningfully to the AI4RSE domain.
Identifying these concepts will help improve the focus and usefulness of the taxonomy.
7. Using Generative AI for Taxonomy Alignment
Generative AI should be used to provide an independent assessment of concept-category alignment.
A suggested prompt is:
You are an expert in Artificial Intelligence, Software Engineering, Ontology Engineering, Knowledge Organization, and Taxonomy Engineering.
Context:
We are evaluating a taxonomy for Artificial Intelligence for Research Software Engineering (AI4RSE).
The current taxonomy is aligned with the IEEE Taxonomy (2025 edition). The categorization below was generated automatically and now requires validation.
Your task is not to redesign the IEEE taxonomy. Instead, evaluate whether the concept is appropriately aligned with the current taxonomy path.
Concept:
[Concept Name]
Definition:
[Concept Definition]
Current Taxonomy Path:
[High-Level Category → Middle-Level Category → Low-Level Category]
Please answer the following questions:
Does the concept belong to the assigned category path?
Is the categorization consistent with the IEEE Taxonomy?
If not, suggest a more appropriate category path.
Explain your reasoning in one short sentence.
Rate your confidence from 1 (very low) to 5 (very high).
Return your answer in JSON format:
{
"alignment": "Correct | Partially Correct | Incorrect",
"suggested_path": "...",
"confidence": 1-5,
"reasoning": "..."
}

The generated response should be treated as a recommendation rather than a final decision.
8. Recording Decisions in the Google Sheet
The Google Sheet will be the primary artifact produced during this task.
The purpose of the Google Sheet is to record all taxonomy-review decisions in a structured format that can later be processed automatically.
To keep the review process simple and scalable, we should only record three fields for concepts that require attention.
Decision
Possible values are:
Keep: Keep means the concept is correctly aligned and should remain unchanged.
Move: Move means the concept should be reassigned to another taxonomy path.
Merge: Merge means the concept is duplicated and should be merged with another concept.
Remove: Remove means the concept should be excluded from the taxonomy.
Discuss: Discuss means the concept requires additional review and cannot be resolved immediately.
Reason
The reason should be short and concise.
Examples include: 
Fits current category.
Better fits software testing.
Duplicate concept.
Too generic.
Not relevant to AI4RSE.
Requires expert review.
The purpose of this field is to provide traceability while keeping the review process efficient.
New Taxonomy Path
This field should only be completed when the decision is Move.
Example: Artificial Intelligence → Machine Learning → Supervised Learning
For all other decisions, this field can remain empty.
9. Analysis
After the evaluation process is completed, we should analyze the collected data.
The analysis should answer questions such as:
How many concepts were reviewed?
How many concepts were flagged?
How many concepts were moved?
How many duplicates were identified?
How many concepts were removed?
Which categories contained the largest number of issues?
Which issue types occurred most frequently?
The analysis should also discuss the usefulness and limitations of Generative AI for taxonomy alignment.
10. Deliverables
At the end of this task, we expect to produce:
A refined version of the AI4RSE taxonomy.
A Google Sheet containing all taxonomy-review decisions.
A summary of identified taxonomy issues.
Statistics describing the review process.
A specification for the automated taxonomy-refinement pipeline.
Recommendations for ontology construction in Task 2.
11. Expected Outcome
At the completion of this task, we expect to have a validated and refined AI4RSE taxonomy with improved concept-category alignment and reduced inconsistencies.
The resulting taxonomy will provide a more accurate representation of the AI4RSE domain and will serve as the primary input for Task 2, where the taxonomy will be transformed into an ontology by introducing semantic relationships, properties, constraints, and formal knowledge structures.
Estimated duration: 2 weeks.
