"""Rasterize a read-only Word export using the packaged DOCX renderer."""

import importlib.util
import os
from pathlib import Path


TASK = Path(__file__).resolve().parent
RUNTIME = Path("C:/Users/86177/.cache/codex-runtimes/codex-primary-runtime")
SKILL = Path("C:/Users/86177/.codex/plugins/cache/openai-primary-runtime/documents/26.1017.22136/skills/documents")
RENDER = TASK / "qa_render_v2"
PDF = RENDER / "weekly_report.pdf"
assert PDF.is_file()
os.environ["PATH"] = str(RUNTIME / "dependencies/native/poppler/Library/bin") + os.pathsep + os.environ["PATH"]
spec = importlib.util.spec_from_file_location("packaged_docx_renderer", SKILL / "render_docx.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
# The conversion already ran in read-only Word. Keep the renderer's PNG path
# unchanged and do not fall back to an installed desktop LibreOffice.
renderer.convert_to_pdf = lambda *args, **kwargs: (str(PDF), "Read-only Microsoft Word export")
docx = TASK.parent.parent / "reports/Fe110_新模型训练与AQCat25微调周报_20261026-20261030.docx"
renderer.rasterize(str(docx), str(RENDER), dpi=150, verbose=False, emit_pdf=False)
print("Rendered pages:", len(list(RENDER.glob("page-*.png"))))
