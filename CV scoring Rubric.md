## The Rubric

Use this rubric consistently across every round. Scores are out of 5.

| # | Criterion | Score 5 | Score 3 | Score 1 |
|---|-----------|---------|---------|---------|
| 1 | **Impact & Quantification** | Every bullet has a measurable outcome; numbers are specific and credible | Mix of quantified and vague bullets; some outcomes missing | Mostly activity descriptions with no results |
| 2 | **Structure & Scannability** | Clean hierarchy, consistent formatting, survives a 10-second skim | Some inconsistencies; structure mostly works but has friction | Hard to navigate; inconsistent headings, walls of text |
| 3 | **Summary / Profile** | One tight paragraph: seniority, differentiator, proof points, forward hook | Too long, too vague, or missing one of the four elements | Generic; could belong to anyone |
| 4 | **Skills Section** | Categorised, ATS-friendly, credible, no hedging | Present but poorly organised or with credibility issues | Missing, dumped as a list, or full of irrelevant entries |
| 5 | **Career Narrative** | Clear arc of growth; each role builds on the last; reader understands trajectory | Progression visible but not articulated; some gaps | Roles feel disconnected; no sense of growth |
| 6 | **Completeness & Detail** | All sections present; authorship clear; contact info complete; no unexplained gaps | Minor gaps; some sections thin | Missing sections; unexplained time gaps; no contact info |
| 7 | **Language & Professionalism** | Tight, active, consistent tense; no artefacts; every sentence earns its place | A few loose sentences; minor inconsistencies | First-person throughout; grammatical errors; unfinished prose |

---

## Scoring Output Format

Ask Claude to present scores in this format each round:

| # | Criterion | Score | vs Last |
|---|-----------|-------|---------|
| 1 | Impact & Quantification | X / 5 | arrow + delta |
| 2 | Structure & Scannability | X / 5 | arrow + delta |
| 3 | Summary / Profile | X / 5 | arrow + delta |
| 4 | Skills Section | X / 5 | arrow + delta |
| 5 | Career Narrative | X / 5 | arrow + delta |
| 6 | Completeness & Detail | X / 5 | arrow + delta |
| 7 | Language & Professionalism | X / 5 | arrow + delta |
| | **Overall** | **X / 5** | arrow + delta |

---

## Improvement Plan Format

When any criterion is below 4.5, ask for an improvement plan structured as:

- **Fix title** — which criteria it affects
- **Current text** (the exact problem passage)
- **Rewritten version** (the exact replacement)
- **Why** this matters and what it changes
- **Priority** — high / medium / low based on score impact

---

## Key Principles Learned from This Process

These are the rules that produced the most improvement across iterations:

**On quantification:**
- Every bullet should answer: what did you do, at what scale, with what result
- "Improved X" is not enough — "improved X by Y%" or "reducing X from A to B" is
- If you have no hard number, use scope: number of customers, users, sites, countries, releases, team members
- Never insert a number without its unit ("reduced by 3" is worse than no number at all)

**On the summary:**
- Four elements only: seniority, differentiator, proof points, forward hook
- One paragraph, maximum 6 lines
- Let proof points demonstrate differentiation rather than claiming it directly
- Tailor the final sentence per application

**On language:**
- No first-person pronouns anywhere in the CV
- No en-dashes (perceived as AI writing)
- Consistent bullet marker throughout (all `-` or all `*`, never mixed)
- Consistent tense within each role
- Every sentence should earn its place — if it explains rather than demonstrates, cut it

**On skills:**
- Use a table format: category column + skills column
- No hedging ("if applicable", "awareness of")
- Separate capabilities from tools (e.g. "Distributed computing · Spark" not "distributed computing (Spark)")
- ATS-friendly: spell out acronyms at least once

**On career narrative:**
- One company for many years is a strength, not a weakness — frame the progression explicitly
- Acquisitions, pivots, and promotions are context worth including as bullets
- Research placements and internships should connect forward to later work, not stand alone
- Early-career experience should be formatted as bullets, not prose paragraphs

**On completeness:**
- LinkedIn URL in the contact strip is expected
- A public portfolio link (GitHub, personal site, or portfolio) adds credibility if relevant to the role
- Publication or patent authorship position should be explicit if listed
- No unexplained gaps between roles

---

## Ceiling Expectations

| Situation | Realistic ceiling |
|-----------|------------------|
| Strong quantification, public portfolio | 4.8-5.0 |
| Strong quantification, no public portfolio | 4.5-4.7 |
| Good experience, weak quantification | 3.5-4.0 |
| New graduate or career changer | 3.0-3.8 |

A score of 4.5+ is genuinely excellent and competitive for senior roles. Chasing 5.0 beyond that point has diminishing returns — spend the time on tailoring per application instead.

---

## Per-Application Tailoring Checklist

Before submitting to any specific role, check:

- [ ] Does the summary's final sentence match this role's framing?
- [ ] Are the top 3 bullets in each role the most relevant ones for this job description?
- [ ] Does the skills section include keywords from the job description?
- [ ] Is the seniority framing (individual contributor vs leadership) appropriate for this role?
- [ ] Have you removed any sections irrelevant to this role to save space?
- [ ] Does the contact strip include a portfolio or profile link relevant to this industry?
