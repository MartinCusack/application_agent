# Plan: DOCX / PDF Export

## Overview

Export the tailored CV from `cv_tailored.md` to a DOCX or PDF with consistent formatting. Triggered by a `--export` flag on the `apply` command, or as a standalone `job-agent export` command that works on any existing vault run.

---

## Feature Dependency Diagram

```
[Depends on]
  └── cv_tailored.md written by Agent 2 (already in pipeline)

  vault/cv_tailored.md
      │
  ExportService (new: job_agent/exporter.py)
      │
      ├── DOCX path: python-docx
      │       │
      │       └── Markdown → python-docx Document object
      │
      └── PDF path: md → HTML (markdown lib) → PDF (weasyprint)
              │
              └── Reads CSS template from data/cv_style.css
      │
      ▼
  vault/cv_tailored.docx | cv_tailored.pdf

  CLI: --export docx|pdf flag on apply
       job-agent export --run-id <id> --format docx|pdf (standalone)
```

---

## Technical Plan

### 1. New dependencies (`pyproject.toml`)

```toml
python-docx = ">=1.1"
markdown = ">=3.5"
weasyprint = ">=62.0"   # optional; only needed for PDF
```

`weasyprint` has a heavy dependency tree (Cairo, Pango). Make it an optional dependency group:

```toml
[project.optional-dependencies]
pdf = ["weasyprint>=62.0"]
```

Install with `uv sync --extra pdf` when PDF support is needed.

### 2. New module: `job_agent/exporter.py`

```python
def export_cv(markdown_text: str, output_path: Path, format: str) -> Path:
    """Export a markdown CV to DOCX or PDF. Returns the output file path."""
    if format == "docx":
        return _export_docx(markdown_text, output_path)
    if format == "pdf":
        return _export_pdf(markdown_text, output_path)
    raise ValueError(f"Unknown format: {format}")
```

#### DOCX export (`_export_docx`)

Walk the markdown AST using the `markdown` library with `python-docx`:

1. Parse markdown headings → `Document.add_heading(text, level)`
2. Paragraphs → `Document.add_paragraph(text)`
3. Bold/italic inline → `run.bold = True` / `run.italic = True`
4. Bullet lists → `Document.add_paragraph(text, style="List Bullet")`

This is a manual walk — a full markdown-to-docx converter. A simpler alternative is `pypandoc` (wraps Pandoc) which handles the full conversion reliably but requires Pandoc binary to be installed. `pypandoc` is the pragmatic choice; `python-docx` manual walk is the zero-binary-dependency choice.

**Recommendation:** use `pypandoc` as primary path with a `python-docx` fallback for environments without Pandoc. Check `pypandoc.get_pandoc_version()` at import time.

#### PDF export (`_export_pdf`)

1. Convert markdown to HTML via `markdown.markdown(text, extensions=["tables", "fenced_code"])`
2. Wrap in HTML template with linked CSS (`data/cv_style.css`)
3. Pass to `weasyprint.HTML(string=html_with_css).write_pdf(output_path)`

Provide a minimal `data/cv_style.css` with:
- `font-family: Georgia, serif`
- Page margins: `@page { margin: 2cm }`
- `h1`/`h2` sizing and border-bottom
- Clean list styling

### 3. CLI integration

**Inline flag on `apply`:**

```python
export: Optional[str] = typer.Option(None, "--export", help="Export CV to 'docx' or 'pdf' after pipeline completes")
```

After vault write of `cv_tailored.md`, call `export_cv(...)` if flag is set. Print `📄 Exported: {path}`.

**Standalone command:**

```python
@app.command()
def export(
    run_path: Path = typer.Argument(..., help="Path to vault run folder"),
    format: str = typer.Option("docx", "--format", "-f", help="Export format: docx or pdf"),
) -> None:
    """Export cv_tailored.md from an existing vault run to DOCX or PDF."""
```

Reads `cv_tailored.md` from the given folder and exports.

### 4. Formatting constraints

The CV markdown uses standard headings and bullet lists — no tables, no code blocks. This makes conversion straightforward. The main risk is that `## Summary` heading styles differ between DOCX styles. Provide a `data/cv_template.docx` with pre-configured heading styles that `python-docx` applies via `document = Document("data/cv_template.docx")`.

### 5. Tests

| Test | Approach |
|------|----------|
| DOCX export produces valid file | Run `_export_docx` on fixture markdown; assert `.docx` exists and `Document` opens without error |
| PDF export produces non-empty file | Run `_export_pdf` on fixture; assert `.pdf` exists and size > 1kb |
| Export with pypandoc missing falls back | Mock `pypandoc` import error; assert fallback runs without error |
| `--export` flag triggers export | Mock `export_cv`; assert called with correct format string |
| Standalone `export` command | End-to-end with fixture vault folder |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| WeasyPrint install fails (Cairo/GTK not available on macOS/Windows) | Medium | PDF export is an optional dependency group. Document install instructions per platform. DOCX is the default. |
| Pandoc not installed when using pypandoc | Medium | Check at runtime and print a clear install instruction: `brew install pandoc`. Fall back to `python-docx` manual walk. |
| DOCX heading styles don't match user's CV template | Medium | Ship `data/cv_template.docx` with pre-configured styles. Allow `CV_DOCX_TEMPLATE_PATH` config override. |
| Markdown extensions used in cv.md not handled by parser | Low | CV uses standard headings and bullets — no exotic extensions. Validate with fixture test on actual `cv.md` format. |
| Export appended to wrong section if cv_tailored.md has custom structure | Low | Export is a dumb markdown-to-format conversion; structure preserved as-is. User is responsible for cv.md formatting. |
