import os
import io
import sys
import uuid
import zipfile
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template_string
from markitdown import MarkItDown

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB

UPLOAD_FOLDER = Path("uploads_temp")
UPLOAD_FOLDER.mkdir(exist_ok=True)

SUPPORTED_EXTENSIONS = {
    "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
    "html", "htm", "csv", "json", "xml", "txt",
    "jpg", "jpeg", "png", "gif", "webp",
    "mp3", "wav", "epub", "zip"
}

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarkItDown Converter</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #22263a;
    --border: #2e3350;
    --accent: #6366f1;
    --accent2: #818cf8;
    --green: #22c55e;
    --red: #ef4444;
    --yellow: #f59e0b;
    --text: #e2e8f0;
    --muted: #64748b;
  }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', system-ui, sans-serif;
    min-height: 100vh;
    padding: 24px 16px;
  }
  .container { max-width: 860px; margin: 0 auto; }
  header { text-align: center; margin-bottom: 32px; }
  header h1 { font-size: 2rem; font-weight: 700; background: linear-gradient(135deg, #6366f1, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  header p { color: var(--muted); margin-top: 6px; font-size: 0.95rem; }

  /* Drop zone */
  .dropzone {
    border: 2px dashed var(--border);
    border-radius: 16px;
    padding: 48px 24px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    background: var(--surface);
    position: relative;
  }
  .dropzone:hover, .dropzone.dragover {
    border-color: var(--accent);
    background: rgba(99,102,241,0.07);
  }
  .dropzone input[type=file] {
    position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%;
  }
  .dropzone .icon { font-size: 3rem; margin-bottom: 12px; }
  .dropzone h3 { font-size: 1.1rem; margin-bottom: 6px; }
  .dropzone p { color: var(--muted); font-size: 0.85rem; }
  .badge-list { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 14px; }
  .badge {
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 3px 10px;
    border-radius: 99px;
    font-size: 0.75rem;
    color: var(--muted);
    font-family: monospace;
  }

  /* Options */
  .options-bar {
    display: flex; align-items: center; gap: 16px;
    background: var(--surface); border-radius: 12px;
    padding: 16px 20px; margin-top: 16px;
    border: 1px solid var(--border);
    flex-wrap: wrap;
  }
  .options-bar label { color: var(--muted); font-size: 0.85rem; white-space: nowrap; }
  .options-bar select {
    background: var(--surface2); color: var(--text);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 6px 12px; font-size: 0.9rem; cursor: pointer;
  }
  .btn {
    padding: 10px 24px; border: none; border-radius: 10px;
    font-size: 0.95rem; font-weight: 600; cursor: pointer;
    transition: all 0.2s; white-space: nowrap;
  }
  .btn-primary { background: var(--accent); color: white; }
  .btn-primary:hover { background: var(--accent2); transform: translateY(-1px); }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
  .btn-outline {
    background: transparent; color: var(--accent2);
    border: 1px solid var(--accent); font-size: 0.85rem;
  }
  .btn-outline:hover { background: rgba(99,102,241,0.1); }
  .spacer { flex: 1; }

  /* File queue */
  .file-queue { margin-top: 20px; display: flex; flex-direction: column; gap: 8px; }
  .file-item {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 12px 16px;
    display: flex; align-items: center; gap: 12px;
  }
  .file-icon { font-size: 1.4rem; flex-shrink: 0; }
  .file-info { flex: 1; min-width: 0; }
  .file-name { font-size: 0.9rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .file-size { color: var(--muted); font-size: 0.78rem; margin-top: 2px; }
  .file-status { flex-shrink: 0; font-size: 0.8rem; font-weight: 600; }
  .status-waiting { color: var(--muted); }
  .status-converting { color: var(--yellow); }
  .status-done { color: var(--green); cursor: pointer; }
  .status-done:hover { text-decoration: underline; }
  .status-error { color: var(--red); font-size: 0.75rem; max-width: 160px; text-align: right; }
  .remove-btn { background: none; border: none; color: var(--muted); cursor: pointer; font-size: 1rem; padding: 2px 6px; border-radius: 4px; }
  .remove-btn:hover { color: var(--red); background: rgba(239,68,68,0.1); }

  /* Progress */
  .progress-bar-wrap { background: var(--surface2); border-radius: 99px; height: 4px; margin-top: 6px; overflow: hidden; display: none; }
  .progress-bar { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); border-radius: 99px; transition: width 0.3s; }

  /* Summary */
  .summary {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px 20px; margin-top: 16px;
    display: none; align-items: center; gap: 16px; flex-wrap: wrap;
  }
  .summary-text { font-size: 0.9rem; color: var(--muted); }
  .summary-text strong { color: var(--text); }
  .stat { display: inline-flex; align-items: center; gap: 6px; }

  /* Empty state */
  .empty-hint { text-align: center; color: var(--muted); padding: 24px; font-size: 0.9rem; display: none; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(245,158,11,0.3); border-top-color: var(--yellow); border-radius: 50%; animation: spin 0.7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>📄 MarkItDown Converter</h1>
    <p>Chuyển đổi PDF, Word, Excel, PowerPoint, ảnh... sang Markdown dùng với AI</p>
  </header>

  <!-- Drop zone -->
  <div class="dropzone" id="dropzone">
    <input type="file" id="fileInput" multiple accept="*/*">
    <div class="icon">☁️</div>
    <h3>Kéo thả file vào đây hoặc click để chọn</h3>
    <p>Hỗ trợ nhiều file cùng lúc, tối đa 200MB/file</p>
    <div class="badge-list">
      <span class="badge">PDF</span><span class="badge">DOCX</span><span class="badge">XLSX</span>
      <span class="badge">PPTX</span><span class="badge">HTML</span><span class="badge">CSV</span>
      <span class="badge">JSON</span><span class="badge">XML</span><span class="badge">TXT</span>
      <span class="badge">JPG/PNG</span><span class="badge">MP3/WAV</span><span class="badge">EPUB</span>
      <span class="badge">ZIP</span>
    </div>
  </div>

  <!-- Options -->
  <div class="options-bar">
    <label>Format đầu ra:</label>
    <select id="outputFormat">
      <option value="md">Markdown (.md)</option>
      <option value="txt">Plain Text (.txt)</option>
    </select>
    <div class="spacer"></div>
    <button class="btn btn-outline" id="clearAllBtn" onclick="clearAll()">Xóa tất cả</button>
    <button class="btn btn-primary" id="convertBtn" onclick="convertAll()" disabled>
      ⚡ Convert tất cả
    </button>
  </div>

  <!-- File queue -->
  <div class="file-queue" id="fileQueue"></div>
  <div class="empty-hint" id="emptyHint">Chưa có file nào được thêm vào</div>

  <!-- Progress -->
  <div class="progress-bar-wrap" id="progressWrap">
    <div class="progress-bar" id="progressBar" style="width:0%"></div>
  </div>

  <!-- Summary -->
  <div class="summary" id="summary">
    <div class="summary-text" id="summaryText"></div>
    <div class="spacer"></div>
    <button class="btn btn-primary" id="downloadAllBtn" onclick="downloadAll()">
      ⬇️ Tải tất cả (.zip)
    </button>
  </div>
</div>

<script>
const fileMap = new Map(); // name -> { file, status, resultId }
let sessionId = Math.random().toString(36).slice(2);

const fileIcons = {
  pdf: '📕', docx: '📘', doc: '📘', xlsx: '📗', xls: '📗',
  pptx: '📙', ppt: '📙', html: '🌐', htm: '🌐', csv: '📊',
  json: '📋', xml: '📋', txt: '📝', jpg: '🖼️', jpeg: '🖼️',
  png: '🖼️', gif: '🖼️', webp: '🖼️', mp3: '🎵', wav: '🎵',
  epub: '📚', zip: '🗜️',
};

function getExt(name) { return name.split('.').pop().toLowerCase(); }
function getIcon(name) { return fileIcons[getExt(name)] || '📄'; }
function formatSize(b) {
  if (b < 1024) return b + ' B';
  if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB';
  return (b/1024/1024).toFixed(1) + ' MB';
}

function addFiles(files) {
  for (const f of files) {
    if (!fileMap.has(f.name)) {
      fileMap.set(f.name, { file: f, status: 'waiting', resultId: null });
    }
  }
  renderQueue();
  document.getElementById('convertBtn').disabled = fileMap.size === 0;
}

function renderQueue() {
  const queue = document.getElementById('fileQueue');
  const hint = document.getElementById('emptyHint');
  queue.innerHTML = '';

  if (fileMap.size === 0) {
    hint.style.display = 'block';
    return;
  }
  hint.style.display = 'none';

  for (const [name, info] of fileMap) {
    const div = document.createElement('div');
    div.className = 'file-item';
    div.id = 'item-' + CSS.escape(name);

    let statusHtml = '';
    if (info.status === 'waiting')
      statusHtml = `<span class="file-status status-waiting">Chờ...</span>`;
    else if (info.status === 'converting')
      statusHtml = `<span class="file-status status-converting"><span class="spinner"></span> Đang convert</span>`;
    else if (info.status === 'done')
      statusHtml = `<span class="file-status status-done" onclick="downloadOne('${name}')">✅ Tải xuống</span>`;
    else if (info.status === 'error')
      statusHtml = `<span class="file-status status-error">❌ ${info.error || 'Lỗi'}</span>`;

    div.innerHTML = `
      <div class="file-icon">${getIcon(name)}</div>
      <div class="file-info">
        <div class="file-name" title="${name}">${name}</div>
        <div class="file-size">${formatSize(info.file.size)}</div>
      </div>
      ${statusHtml}
      <button class="remove-btn" onclick="removeFile('${name}')" title="Xóa">✕</button>
    `;
    queue.appendChild(div);
  }
}

function removeFile(name) {
  fileMap.delete(name);
  renderQueue();
  document.getElementById('convertBtn').disabled = fileMap.size === 0;
  updateSummary();
}

function clearAll() {
  fileMap.clear();
  renderQueue();
  document.getElementById('convertBtn').disabled = true;
  document.getElementById('summary').style.display = 'none';
  document.getElementById('progressWrap').style.display = 'none';
}

async function convertAll() {
  const btn = document.getElementById('convertBtn');
  btn.disabled = true;
  const format = document.getElementById('outputFormat').value;

  const waiting = [...fileMap.entries()].filter(([, v]) => v.status === 'waiting' || v.status === 'error');
  if (waiting.length === 0) { btn.disabled = false; return; }

  document.getElementById('progressWrap').style.display = 'block';
  let done = 0;

  for (const [name, info] of waiting) {
    info.status = 'converting';
    renderQueue();

    const formData = new FormData();
    formData.append('file', info.file);
    formData.append('format', format);
    formData.append('session', sessionId);

    try {
      const res = await fetch('/convert', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.ok) {
        info.status = 'done';
        info.resultId = data.result_id;
        info.outputName = data.output_name;
      } else {
        info.status = 'error';
        info.error = data.error || 'Thất bại';
      }
    } catch (e) {
      info.status = 'error';
      info.error = 'Lỗi kết nối';
    }

    done++;
    document.getElementById('progressBar').style.width = (done / waiting.length * 100) + '%';
    renderQueue();
  }

  updateSummary();
  btn.disabled = false;
}

function updateSummary() {
  const total = fileMap.size;
  const doneCount = [...fileMap.values()].filter(v => v.status === 'done').length;
  const errCount = [...fileMap.values()].filter(v => v.status === 'error').length;
  const summary = document.getElementById('summary');

  if (total === 0) { summary.style.display = 'none'; return; }
  if (doneCount === 0 && errCount === 0) { summary.style.display = 'none'; return; }

  summary.style.display = 'flex';
  document.getElementById('summaryText').innerHTML =
    `<strong>${doneCount}</strong> file thành công` +
    (errCount > 0 ? `, <strong style="color:var(--red)">${errCount}</strong> lỗi` : '');

  document.getElementById('downloadAllBtn').style.display = doneCount > 1 ? '' : 'none';
}

async function downloadOne(name) {
  const info = fileMap.get(name);
  if (!info || info.status !== 'done') return;
  const a = document.createElement('a');
  a.href = `/download/${info.resultId}/${encodeURIComponent(info.outputName)}`;
  a.download = info.outputName;
  a.click();
}

async function downloadAll() {
  const ids = [...fileMap.values()].filter(v => v.status === 'done').map(v => v.resultId);
  if (ids.length === 0) return;
  const a = document.createElement('a');
  a.href = `/download-zip?session=${sessionId}`;
  a.download = 'converted.zip';
  a.click();
}

// Drag & drop
const dz = document.getElementById('dropzone');
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
dz.addEventListener('drop', e => {
  e.preventDefault();
  dz.classList.remove('dragover');
  addFiles(e.dataTransfer.files);
});
document.getElementById('fileInput').addEventListener('change', e => {
  addFiles(e.target.files);
  e.target.value = '';
});
</script>
</body>
</html>
"""

md_converter = MarkItDown()
results_store = {}  # result_id -> (content_bytes, output_name, session_id)


@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/convert", methods=["POST"])
def convert():
    file = request.files.get("file")
    fmt = request.form.get("format", "md")
    session = request.form.get("session", "default")

    if not file:
        return jsonify({"ok": False, "error": "Không có file"})

    ext = Path(file.filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        return jsonify({"ok": False, "error": f"Định dạng .{ext} chưa hỗ trợ"})

    tmp_path = UPLOAD_FOLDER / f"{uuid.uuid4()}{Path(file.filename).suffix}"
    try:
        file.save(str(tmp_path))
        result = md_converter.convert(str(tmp_path))
        content = result.text_content

        stem = Path(file.filename).stem
        output_name = f"{stem}.{fmt}"
        content_bytes = content.encode("utf-8")

        result_id = str(uuid.uuid4())
        results_store[result_id] = (content_bytes, output_name, session)

        return jsonify({"ok": True, "result_id": result_id, "output_name": output_name})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:120]})
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.route("/download/<result_id>/<filename>")
def download_one(result_id, filename):
    if result_id not in results_store:
        return "Not found", 404
    content_bytes, output_name, _ = results_store[result_id]
    return send_file(
        io.BytesIO(content_bytes),
        as_attachment=True,
        download_name=output_name,
        mimetype="text/markdown"
    )


@app.route("/download-zip")
def download_zip():
    session = request.args.get("session", "")
    items = [(rid, cb, on) for rid, (cb, on, sid) in results_store.items() if sid == session]
    if not items:
        return "No files", 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, content_bytes, output_name in items:
            zf.writestr(output_name, content_bytes)
    buf.seek(0)

    return send_file(buf, as_attachment=True, download_name="converted.zip", mimetype="application/zip")


if __name__ == "__main__":
    print("MarkItDown Web UI: http://localhost:5000")
    app.run(debug=False, port=5000)
