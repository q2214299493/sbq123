"""Retrieve identified publisher SI; cache bytes, print bounded relevant text."""
import hashlib
from pathlib import Path

import requests
from pypdf import PdfReader
from scripts.artifact_io import write_json

root = Path(__file__).resolve().parent
target = root / "jp8b10310_si_001.pdf"
url = "https://ndownloader.figshare.com/files/13778723"
if not target.exists():
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    assert response.content.startswith(b"%PDF"), "Expected publisher PDF"
    target.write_bytes(response.content)
reader = PdfReader(target)
selected = []
for i, page in enumerate(reader.pages):
    text = page.extract_text()
    if i < 2 or "CHCO" in text or "CCH2" in text or "CCH " in text:
        selected.append({"page": i + 1, "text": text})
        print("page", i + 1, text[:1700])
write_json(root / "si_excerpts.json", {"source_url": url,
           "resource_doi": "10.1021/acs.jpcc.8b10310",
           "si_doi": "10.1021/acs.jpcc.8b10310.s001",
           "license": "CC BY-NC 4.0 per publisher Figshare metadata",
           "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
           "pages": len(reader.pages), "selected_pages": selected,
           "acceptance": "SOURCE_INSPECTION_ONLY_NO_MOTIF_TRANSFER_REVIEW"})
