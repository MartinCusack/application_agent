# Feature Plans

Implementation plans for all proposed improvements to the Job Agent pipeline.

## From README Roadmap

| # | Plan | Priority | Key dependency |
|---|------|----------|----------------|
| 01 | [URL Input for Job Descriptions](01_url_input.md) | High | None |
| 02 | [Streaming Terminal Output](02_streaming_output.md) | Medium | None |
| 03 | [Dry Run Mode](03_dry_run_mode.md) | Medium | None |
| 04 | [LinkedIn / Job Board Integration](04_linkedin_integration.md) | Low | Plan 01 |
| 05 | [Salary Benchmarking Agent (Agent 0)](05_salary_benchmarking_agent.md) | Low | None |
| 06 | [Company Research Agent](06_company_research_agent.md) | Low | None |
| 07 | [Skills Gap Learning Plan](07_skills_gap_learning_plan.md) | Low | Tracker (shipped) |
| 08 | [DOCX / PDF Export](08_docx_pdf_export.md) | Low | None |

## Additional Functional Improvements

| # | Plan | Complexity | Key dependency |
|---|------|-----------|----------------|
| 09 | [Per-Agent Model Configuration](09_per_agent_model_config.md) | Low | None |
| 10 | [Interview Prep Agent](10_interview_prep_agent.md) | Medium | Agent 1a + Agent 3b |
| 11 | [Application Deduplication Check](11_application_deduplication.md) | Low | Vault (shipped) |
| 12 | [Prompt Version Tracking](12_prompt_version_tracking.md) | Low | None |
| 13 | [Threshold Auto-Tuning Suggestion](13_threshold_auto_tuning.md) | Low | Tracker (shipped) |
| 14 | [JD Deduplication via Content Hash](14_jd_deduplication.md) | Low | None |
| 15 | [Soft Gap Coverage Report](15_soft_gap_coverage_report.md) | Low | Agent 1a + Agent 3b |
| 16 | [Configurable Agent Pipeline](16_configurable_agent_pipeline.md) | Low | None |

## Suggested implementation order

For maximum value with minimum risk, implement in this order:

1. **Plan 12** — Prompt version tracking (5 min, zero risk, immediate audit trail)
2. **Plan 14** — JD deduplication (30 min, protects against token waste)
3. **Plan 11** — Application deduplication (30 min, same)
4. **Plan 15** — Soft gap coverage report (30 min, immediate feedback improvement)
5. **Plan 09** — Per-agent model config (1 hr, reduces cost or improves quality)
6. **Plan 16** — Configurable pipeline (1 hr, speeds up iteration)
7. **Plan 03** — Dry run mode (2 hrs, development quality-of-life)
8. **Plan 02** — Streaming output (2 hrs, UX improvement)
9. **Plan 01** — URL input (3 hrs, removes manual step)
10. **Plan 10** — Interview prep agent (3 hrs, high-value new feature)
11. **Plan 13** — Threshold auto-tuning (2 hrs, requires run history)
12. **Plan 07** — Skills gap learning plan (4 hrs, requires run history)
13. **Plan 08** — DOCX/PDF export (4 hrs, platform-dependent complexity)
14. **Plan 06** — Company research agent (4 hrs, requires search API)
15. **Plan 05** — Salary benchmarking agent (4 hrs, requires search API)
16. **Plan 04** — LinkedIn integration (6 hrs, depends on Plan 01 + board-specific complexity)
