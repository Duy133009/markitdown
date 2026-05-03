---
title: MarkItDown Converter
emoji: 📄
colorFrom: indigo
colorTo: purple
sdk: docker
pinned: false
---

# MarkItDown Web UI

Web app to convert files (PDF, Word, Excel, PowerPoint, images, audio, etc.) to Markdown for AI/LLM workflows.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Open: http://localhost:5000

## Supported formats

PDF, DOCX, XLSX, PPTX, HTML, CSV, JSON, XML, TXT, JPG/PNG, MP3/WAV, EPUB, ZIP

## Optional: PDF Translate Mode (RetainPDF)

You can enable `Translate PDF (RetainPDF)` mode from the sidebar. It calls an external RetainPDF service and stores translated Markdown preview in this app.

Set env vars:

```bash
RETAINPDF_API_BASE=http://127.0.0.1:40001
RETAINPDF_API_KEY=your_x_api_key
RETAINPDF_PROVIDER=paddle
RETAINPDF_PADDLE_TOKEN=...
RETAINPDF_MODEL_API_KEY=...
RETAINPDF_MODEL=deepseek-v4-flash
RETAINPDF_BASE_URL=https://api.deepseek.com/v1
```
