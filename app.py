import io
import os
import sys
import uuid
import zipfile
import hashlib
import secrets
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, send_file, render_template_string, session, redirect, url_for
from markitdown import MarkItDown

# ── Auth config ────────────────────────────────────────────────────────────
APP_PASSWORD  = os.environ.get("APP_PASSWORD", "markitdown2026")
SECRET_KEY    = os.environ.get("SECRET_KEY", secrets.token_hex(32))

def hash_password(pw: str) -> str:
    salt = b"markitdown_salt_v1"
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 260000).hex()

def get_current_password_hash() -> str:
    """Read password hash from Supabase kv_store. Falls back to env var."""
    try:
        sb = get_supabase()
        if sb:
            row = sb.table("kv_store_2281cd7c").select("value").eq("key", "app_password_hash").execute()
            if row.data:
                return row.data[0]["value"]["hash"]
    except Exception:
        pass
    return hash_password(APP_PASSWORD)

def set_password(new_pw: str):
    """Persist new password hash to Supabase."""
    sb = get_supabase()
    if not sb:
        return False
    h = hash_password(new_pw)
    existing = sb.table("kv_store_2281cd7c").select("key").eq("key", "app_password_hash").execute()
    if existing.data:
        sb.table("kv_store_2281cd7c").update({"value": {"hash": h}}).eq("key", "app_password_hash").execute()
    else:
        sb.table("kv_store_2281cd7c").insert({"key": "app_password_hash", "value": {"hash": h}}).execute()
    return True

# Supabase
SUPABASE_URL = "https://hiojtrjfatfxbffrihnx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhpb2p0cmpmYXRmeGJmZnJpaG54Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI1Njk1NjEsImV4cCI6MjA3ODE0NTU2MX0.HuCpZ2HaNrPXrh6mGR9aH6VGQXEQyDFHzP3_ep9f8Eg"

def get_supabase():
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None

def save_conversion(file_name, file_size, file_ext, engine, output_name, content):
    try:
        sb = get_supabase()
        if sb:
            sb.table("conversions").insert({
                "file_name":   file_name,
                "file_size":   file_size,
                "file_ext":    file_ext,
                "engine":      engine,
                "output_name": output_name,
                "content":     content[:500000],  # cap 500k chars
            }).execute()
    except Exception as e:
        print(f"[Supabase] save failed: {e}")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB
app.secret_key = SECRET_KEY

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

UPLOAD_FOLDER = Path("uploads_temp")
UPLOAD_FOLDER.mkdir(exist_ok=True)

SUPPORTED_EXTENSIONS = {
    "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
    "html", "htm", "csv", "json", "xml", "txt",
    "jpg", "jpeg", "png", "gif", "webp",
    "mp3", "wav", "epub", "zip"
}

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarkItDown Converter</title>
<link id="hl-theme" rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<style>
:root{
  --bg:#080808;--surface:#141416;--surface2:#1e1e22;
  --border:rgba(255,255,255,.12);--border-hover:rgba(255,255,255,.25);
  --text:#ffffff;--text-2:rgba(255,255,255,.82);--text-3:rgba(255,255,255,.52);
  --btn-bg:#ffffff;--btn-text:#000000;
  --success:#22c55e;--error:#ef4444;--warning:#f59e0b;
}
body.light{
  --bg:#ffffff;--surface:#f7f7f8;--surface2:#ebebed;
  --border:rgba(0,0,0,.12);--border-hover:rgba(0,0,0,.25);
  --text:#0a0a0a;--text-2:rgba(0,0,0,.75);--text-3:rgba(0,0,0,.50);
  --btn-bg:#000000;--btn-text:#ffffff;
  --success:#16a34a;--error:#dc2626;--warning:#d97706;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,'Segoe UI',system-ui,sans-serif;font-size:14px;height:100vh;overflow:hidden;}
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--surface2);border-radius:2px;}
::-webkit-scrollbar-thumb:hover{background:var(--border-hover);}

@keyframes spin{to{transform:rotate(360deg);}}
@keyframes slideIn{from{opacity:0;transform:translateY(5px);}to{opacity:1;transform:translateY(0);}}
@keyframes shimmer{0%,100%{opacity:.4;}50%{opacity:.75;}}

/* THREE-PANE LAYOUT */
.app{display:grid;grid-template-columns:260px 320px 1fr;height:100vh;overflow:hidden;}

/* ── SIDEBAR ── */
.sidebar{background:var(--bg);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;}
.sidebar-header{padding:18px 16px 12px;display:flex;align-items:flex-start;justify-content:space-between;border-bottom:1px solid var(--border);flex-shrink:0;}
.logo{display:flex;flex-direction:column;gap:3px;}
.logo-name{font-size:14px;font-weight:600;letter-spacing:-.02em;display:flex;align-items:center;gap:6px;}
.logo-dot{width:6px;height:6px;background:var(--text);border-radius:50%;display:inline-block;}
.logo-sub{font-size:11px;color:var(--text-3);letter-spacing:.01em;}
.theme-btn{width:28px;height:28px;background:var(--surface);border:1px solid var(--border);border-radius:6px;color:var(--text-2);font-size:13px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s,border-color .15s;}
.theme-btn:hover{background:var(--surface2);border-color:var(--border-hover);}
.sidebar-body{flex:1;padding:12px;overflow:hidden;display:flex;flex-direction:column;}
.dropzone{border:1px dashed var(--border);border-radius:8px;padding:22px 12px;text-align:center;cursor:pointer;transition:all .15s;background:transparent;position:relative;flex-shrink:0;}
.dropzone input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%;}
.dropzone:hover,.dropzone.dz-active{border-color:var(--border-hover);background:var(--surface);}
.dropzone-icon{font-size:26px;margin-bottom:8px;}
.dropzone-title{font-size:12px;font-weight:500;color:var(--text-2);margin-bottom:4px;}
.dropzone-sub{font-size:11px;color:var(--text-3);margin-bottom:10px;}
.badge-list{display:flex;flex-wrap:wrap;gap:4px;justify-content:center;}
.badge{font-size:10px;padding:2px 6px;border-radius:4px;background:var(--surface2);color:var(--text-3);border:1px solid var(--border);font-family:monospace;}
.sidebar-controls{padding:12px;border-top:1px solid var(--border);flex-shrink:0;display:flex;flex-direction:column;gap:8px;}
.label-sm{font-size:10px;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:.07em;margin-bottom:4px;}
.select-format{width:100%;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px 10px;font-size:12px;outline:none;cursor:pointer;transition:border-color .15s;font-family:inherit;}
.select-format:hover{border-color:var(--border-hover);}
.btn-primary{width:100%;background:var(--btn-bg);color:var(--btn-text);border:none;border-radius:6px;padding:10px;font-size:12px;font-weight:600;cursor:pointer;transition:opacity .15s,transform .15s;letter-spacing:-.01em;display:flex;align-items:center;justify-content:center;gap:6px;font-family:inherit;}
.btn-primary:hover:not(:disabled){opacity:.85;transform:translateY(-1px);}
.btn-primary:disabled{opacity:.3;cursor:not-allowed;transform:none;}
.btn-secondary{width:100%;background:transparent;color:var(--text-3);border:1px solid var(--border);border-radius:6px;padding:8px;font-size:12px;cursor:pointer;transition:all .15s;font-family:inherit;}
.btn-secondary:hover{color:var(--text-2);border-color:var(--border-hover);background:var(--surface);}
.spinner{width:12px;height:12px;border:1.5px solid rgba(0,0,0,.2);border-top-color:var(--btn-text);border-radius:50%;animation:spin .7s linear infinite;display:inline-block;}

/* ── FILE PANE ── */
.file-pane{background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;}
.file-pane-header{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-shrink:0;}
.file-pane-title{font-size:12px;font-weight:600;letter-spacing:-.01em;}
.count-badge{background:var(--surface2);color:var(--text-3);font-size:10px;padding:1px 6px;border-radius:99px;border:1px solid var(--border);}
.file-list{overflow-y:auto;flex:1;}
.file-item{padding:10px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;transition:background .1s;position:relative;animation:slideIn .2s ease;}
.file-item:hover{background:rgba(128,128,128,.05);}
.file-item.selected{background:var(--surface2);}
.file-item.selected::before{content:'';position:absolute;left:0;top:0;bottom:0;width:2px;background:var(--text);border-radius:0 1px 1px 0;}
.file-item.clickable{cursor:pointer;}
.file-icon{font-size:18px;flex-shrink:0;width:22px;text-align:center;}
.file-info{flex:1;min-width:0;}
.file-name{font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px;}
.file-size{font-size:11px;color:var(--text-3);margin-top:2px;}
.file-status{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:500;padding:2px 7px;border-radius:4px;margin-top:4px;}
.status-waiting{background:rgba(128,128,128,.1);color:var(--text-3);}
.status-converting{background:rgba(245,158,11,.1);color:var(--warning);}
.status-done{background:rgba(34,197,94,.1);color:var(--success);}
.status-error{background:rgba(239,68,68,.1);color:var(--error);}
.file-actions{display:flex;gap:4px;flex-shrink:0;opacity:0;transition:opacity .15s;}
.file-item:hover .file-actions{opacity:1;}
.icon-btn{width:24px;height:24px;background:transparent;border:1px solid var(--border);border-radius:4px;color:var(--text-3);cursor:pointer;font-size:11px;display:flex;align-items:center;justify-content:center;transition:all .1s;}
.icon-btn:hover{background:var(--surface2);color:var(--text);border-color:var(--border-hover);}
.icon-btn.danger:hover{color:var(--error);border-color:var(--error);}
.file-progress{position:absolute;bottom:0;left:0;height:1px;background:var(--text);opacity:.2;width:100%;animation:shimmer 1.5s ease-in-out infinite;}
.file-empty{flex-direction:column;align-items:center;justify-content:center;gap:8px;color:var(--text-3);padding:40px 16px;text-align:center;}
.file-empty-icon{font-size:28px;opacity:.25;}
.file-empty-text{font-size:12px;}
.progress-wrap{padding:8px 16px;flex-shrink:0;}
.progress-track{background:var(--surface2);border-radius:99px;height:2px;overflow:hidden;}
.progress-fill{height:100%;background:var(--text);border-radius:99px;transition:width .3s;width:0%;}
.summary-bar{padding:10px 16px;border-top:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-shrink:0;}
.summary-text{font-size:11px;color:var(--text-3);flex:1;}
.btn-zip{background:transparent;border:1px solid var(--border);color:var(--text-2);font-size:11px;padding:5px 10px;border-radius:5px;cursor:pointer;transition:all .15s;white-space:nowrap;font-family:inherit;}
.btn-zip:hover{background:var(--surface2);border-color:var(--border-hover);color:var(--text);}

/* ── PREVIEW PANE ── */
.preview-pane{background:var(--bg);display:flex;flex-direction:column;overflow:hidden;}
.preview-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;}
.preview-empty-icon{font-size:36px;opacity:.1;}
.preview-empty-text{font-size:13px;color:var(--text-3);}
.preview-empty-sub{font-size:11px;color:var(--text-3);opacity:.6;}
#previewPanel{display:none;flex-direction:column;height:100%;}
#previewPanel.visible{display:flex;}
.preview-header{padding:10px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-shrink:0;}
.preview-filename{font-size:12px;font-weight:500;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.tab-toggle{display:inline-flex;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:3px;gap:2px;}
.tab-btn{font-size:11px;padding:4px 12px;border-radius:4px;cursor:pointer;color:var(--text-3);border:none;background:transparent;transition:all .1s;font-family:inherit;}
.tab-btn.active{background:var(--btn-bg);color:var(--btn-text);font-weight:500;}
.preview-actions{display:flex;gap:6px;}
.action-btn{height:26px;padding:0 10px;background:transparent;border:1px solid var(--border);border-radius:5px;color:var(--text-3);font-size:11px;cursor:pointer;display:flex;align-items:center;gap:4px;transition:all .1s;white-space:nowrap;font-family:inherit;}
.action-btn:hover{background:var(--surface);color:var(--text);border-color:var(--border-hover);}
.action-btn.close-btn{width:26px;padding:0;justify-content:center;}
#skelWrap{padding:28px 36px;flex-shrink:0;}
.skeleton-line{background:var(--surface2);border-radius:4px;height:14px;margin-bottom:12px;animation:shimmer 1.5s ease-in-out infinite;}
.preview-content{flex:1;overflow-y:auto;padding:28px 36px;}
.prose{max-width:680px;margin:0 auto;font-size:14px;line-height:1.75;color:var(--text-2);}
.prose h1{font-size:1.5rem;font-weight:700;color:var(--text);margin:1.5em 0 .4em;letter-spacing:-.02em;}
.prose h2{font-size:1.2rem;font-weight:600;color:var(--text);margin:1.4em 0 .4em;letter-spacing:-.01em;}
.prose h3{font-size:1rem;font-weight:600;color:var(--text);margin:1.2em 0 .3em;}
.prose h4,.prose h5,.prose h6{font-weight:600;color:var(--text);margin:1em 0 .3em;}
.prose p{margin:0 0 1em;}
.prose a{color:var(--text-2);text-decoration:underline;text-decoration-color:var(--border-hover);}
.prose a:hover{color:var(--text);}
.prose code{background:var(--surface2);color:var(--text-2);padding:1px 6px;border-radius:4px;font-size:12px;font-family:'SF Mono','Fira Code','Consolas',monospace;border:1px solid var(--border);}
.prose pre{background:var(--surface)!important;border:1px solid var(--border);border-radius:8px;padding:16px;overflow-x:auto;margin:1em 0;}
.prose pre code{background:none;border:none;padding:0;font-size:12px;line-height:1.6;}
.prose blockquote{border-left:2px solid var(--border-hover);padding-left:16px;color:var(--text-3);margin:1em 0;}
.prose table{width:100%;border-collapse:collapse;margin:1em 0;font-size:13px;}
.prose th{background:var(--surface2);color:var(--text);font-weight:500;text-align:left;padding:8px 12px;border:1px solid var(--border);font-size:11px;text-transform:uppercase;letter-spacing:.04em;}
.prose td{padding:8px 12px;border:1px solid var(--border);color:var(--text-2);}
.prose ul,.prose ol{padding-left:1.5em;margin:.5em 0;}
.prose li{margin:.25em 0;}
.prose hr{border:none;border-top:1px solid var(--border);margin:1.5em 0;}
.prose img{max-width:100%;border-radius:6px;border:1px solid var(--border);}
.prose strong{color:var(--text);font-weight:600;}
.raw-area{flex:1;background:var(--surface);color:var(--text-2);font-family:'SF Mono','Fira Code','Consolas',monospace;font-size:12px;line-height:1.6;border:none;outline:none;resize:none;padding:28px 36px;border-top:1px solid var(--border);}

/* Mobile modal */
.modal-bg{position:fixed;inset:0;background:rgba(0,0,0,.75);backdrop-filter:blur(4px);z-index:40;}
.modal-box{position:fixed;inset:0;z-index:41;display:flex;flex-direction:column;background:var(--surface);}

/* Settings modal */
.settings-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:blur(3px);z-index:50;display:none;align-items:center;justify-content:center;}
.settings-overlay.open{display:flex;}
.settings-modal{background:var(--surface);border:1px solid var(--border);border-radius:14px;width:100%;max-width:360px;overflow:hidden;}
.settings-header{padding:18px 20px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.settings-title{font-size:13px;font-weight:600;letter-spacing:-.01em;}
.settings-body{padding:20px;}
.settings-section-label{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:var(--text-3);margin-bottom:12px;}
.settings-field{margin-bottom:12px;}
.settings-field label{font-size:11px;color:var(--text-3);display:block;margin-bottom:5px;}
.settings-input{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:9px 12px;font-size:12px;outline:none;transition:border-color .15s;font-family:inherit;}
.settings-input:focus{border-color:var(--border-hover);}
.settings-save{width:100%;background:var(--btn-bg);color:var(--btn-text);border:none;border-radius:7px;padding:10px;font-size:12px;font-weight:600;cursor:pointer;margin-top:4px;transition:opacity .15s;font-family:inherit;}
.settings-save:hover{opacity:.82;}
.settings-msg{font-size:11px;margin-top:8px;min-height:16px;}
.settings-msg.ok{color:var(--success);}
.settings-msg.err{color:var(--error);}

.engine-badge{display:inline-block;font-size:9px;padding:1px 5px;border-radius:3px;font-weight:700;letter-spacing:.02em;vertical-align:middle;margin-left:4px;}
.badge-pymupdf{background:rgba(168,85,247,.15);color:#c084fc;border:1px solid rgba(168,85,247,.3);}
.badge-docling{background:rgba(234,179,8,.15);color:#facc15;border:1px solid rgba(234,179,8,.3);}
.badge-local{background:rgba(255,255,255,.08);color:var(--text-3);border:1px solid var(--border);}
</style>
</head>
<body>
<div class="app">

  <!-- ── PANE 1: SIDEBAR ── -->
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo">
        <div class="logo-name"><span class="logo-dot"></span>MarkItDown</div>
        <div class="logo-sub">File to Markdown converter</div>
      </div>
      <div style="display:flex;gap:6px;">
        <button class="theme-btn" id="themeBtn" onclick="toggleTheme()">&#9728;</button>
        <button class="theme-btn" onclick="openSettings()" title="Settings">&#9881;</button>
        <a href="/logout" class="theme-btn" title="Sign out" style="text-decoration:none;font-size:12px;display:flex;align-items:center;justify-content:center;">&#10562;</a>
      </div>
    </div>
    <div class="sidebar-body">
      <div class="dropzone" id="dropzone">
        <input type="file" id="fileInput" multiple accept="*/*">
        <div class="dropzone-icon">&#9729;&#65039;</div>
        <div class="dropzone-title">Drag & drop or click to select</div>
        <div class="dropzone-sub">Up to 200MB per file</div>
        <div class="badge-list">
          <span class="badge">PDF</span><span class="badge">DOCX</span><span class="badge">XLSX</span>
          <span class="badge">PPTX</span><span class="badge">HTML</span><span class="badge">CSV</span>
          <span class="badge">JSON</span><span class="badge">XML</span><span class="badge">TXT</span>
          <span class="badge">JPG</span><span class="badge">PNG</span><span class="badge">MP3</span>
          <span class="badge">WAV</span><span class="badge">EPUB</span><span class="badge">ZIP</span>
        </div>
      </div>
    </div>
    <div class="sidebar-controls">
      <div>
        <div class="label-sm">Conversion engine</div>
        <select id="engineSelect" class="select-format" onchange="saveEngineChoice()">
          <option value="markitdown">MarkItDown (default)</option>
          <option value="pymupdf">PyMuPDF (fast)</option>
          <option value="docling">Docling — IBM (best quality)</option>
        </select>
      </div>
      <div>
        <div class="label-sm">Output format</div>
        <select id="outputFormat" class="select-format">
          <option value="md">Markdown (.md)</option>
          <option value="txt">Plain Text (.txt)</option>
        </select>
      </div>

      <button id="convertBtn" onclick="convertAll()" disabled class="btn-primary">Convert all</button>
      <button onclick="clearAll()" class="btn-secondary">Clear all</button>
    </div>
  </aside>

  <!-- ── PANE 2: FILE LIST ── -->
  <div class="file-pane">
    <div class="file-pane-header">
      <span class="file-pane-title">Files</span>
      <span class="count-badge" id="countBadge">0</span>
      <div style="flex:1;"></div>
      <button onclick="toggleHistory()" id="historyBtn"
        style="font-size:10px;padding:2px 8px;border-radius:4px;background:transparent;border:1px solid var(--border);color:var(--text-3);cursor:pointer;transition:all .15s;font-family:inherit;"
        onmouseover="this.style.borderColor='var(--border-hover)';this.style.color='var(--text-2)'"
        onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--text-3)'">
        &#128336; History
      </button>
    </div>
    <!-- History panel -->
    <div id="historyPanel" style="display:none;flex-direction:column;flex:1;overflow:hidden;">
      <div style="padding:8px 16px;border-bottom:1px solid var(--border);font-size:11px;color:var(--text-3);display:flex;align-items:center;gap:8px;flex-shrink:0;">
        Recent conversions
        <button onclick="loadHistory()" style="margin-left:auto;background:transparent;border:none;color:var(--text-3);cursor:pointer;font-size:11px;">&#8635; Refresh</button>
      </div>
      <div id="historyList" style="overflow-y:auto;flex:1;"></div>
    </div>
    <div class="file-list" id="fileQueue"></div>
    <div class="file-empty" id="emptyHint" style="display:flex;">
      <div class="file-empty-icon">&#128196;</div>
      <div class="file-empty-text">No files yet</div>
    </div>
    <div class="progress-wrap" id="progressWrap" style="display:none;">
      <div class="progress-track"><div class="progress-fill" id="progressBar"></div></div>
    </div>
    <div class="summary-bar" id="summary" style="display:none;">
      <span class="summary-text" id="summaryText"></span>
      <button class="btn-zip" id="downloadAllBtn" onclick="downloadAll()">&#11015; Download all .zip</button>
    </div>
  </div>

  <!-- ── PANE 3: PREVIEW ── -->
  <div class="preview-pane">
    <div class="preview-empty" id="previewEmpty">
      <div class="preview-empty-icon">&#128196;</div>
      <div class="preview-empty-text">Select a file to preview</div>
      <div class="preview-empty-sub">Convert files first, then click to view content</div>
    </div>
    <div id="previewPanel">
      <div class="preview-header">
        <span class="preview-filename" id="previewFileName"></span>
        <div class="tab-toggle">
          <button class="tab-btn active" id="tabR" onclick="switchTab('rendered')">Rendered</button>
          <button class="tab-btn" id="tabRaw" onclick="switchTab('raw')">Raw</button>
        </div>
        <div class="preview-actions">
          <button class="action-btn" id="copyBtn" onclick="copyContent()">&#128203; Copy</button>
          <button class="action-btn" id="dlOneBtn">&#11015; Download</button>
          <button class="action-btn close-btn" onclick="closePreview()">&#10005;</button>
        </div>
      </div>
      <div id="skelWrap" style="display:none;">
        <div class="skeleton-line" style="width:55%;height:18px;"></div>
        <div class="skeleton-line" style="width:100%;"></div>
        <div class="skeleton-line" style="width:80%;"></div>
        <div class="skeleton-line" style="width:100%;"></div>
        <div class="skeleton-line" style="width:65%;"></div>
        <div class="skeleton-line" style="height:70px;width:100%;margin-top:8px;"></div>
        <div class="skeleton-line" style="width:90%;"></div>
      </div>
      <div class="preview-content" id="pRendered">
        <div class="prose" id="proseContent"></div>
      </div>
      <textarea class="raw-area" id="pRaw" readonly style="display:none;"></textarea>
    </div>
  </div>
</div>

<!-- hidden: JS toggles mainLayout class (no visual effect in 3-pane) -->
<div id="mainLayout" style="display:none;"></div>

<!-- Settings modal -->
<div class="settings-overlay" id="settingsOverlay" onclick="closeSettingsOutside(event)">
  <div class="settings-modal">
    <div class="settings-header">
      <span class="settings-title">&#9881; Settings</span>
      <button onclick="closeSettings()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:16px;padding:2px 6px;">&#10005;</button>
    </div>
    <div class="settings-body">
      <div class="settings-section-label">Change Password</div>
      <div class="settings-field">
        <label>Current password</label>
        <input type="password" id="setCurrent" class="settings-input" placeholder="••••••••">
      </div>
      <div class="settings-field">
        <label>New password</label>
        <input type="password" id="setNew" class="settings-input" placeholder="Min. 6 characters">
      </div>
      <div class="settings-field">
        <label>Confirm new password</label>
        <input type="password" id="setConfirm" class="settings-input" placeholder="Re-enter new password">
      </div>
      <button class="settings-save" onclick="savePassword()">Save password</button>
      <div class="settings-msg" id="setMsg"></div>
    </div>
  </div>
</div>

<!-- MOBILE MODAL -->
<div id="mobileModal" style="display:none;">
  <div class="modal-bg" onclick="closePreview()"></div>
  <div class="modal-box">
    <div style="padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0;display:flex;align-items:center;gap:8px;">
      <span id="mPreviewName" style="font-size:12px;font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></span>
      <button onclick="copyContent()" class="action-btn">&#128203;</button>
      <button onclick="closePreview()" class="action-btn close-btn">&#10005;</button>
    </div>
    <div style="display:flex;border-bottom:1px solid var(--border);padding:0 4px;flex-shrink:0;">
      <button onclick="switchTab('rendered')" id="mTabR" class="tab-btn active" style="padding:10px 14px;">Rendered</button>
      <button onclick="switchTab('raw')" id="mTabRaw" class="tab-btn" style="padding:10px 14px;">Raw</button>
    </div>
    <div style="flex:1;overflow:hidden;display:flex;flex-direction:column;">
      <div id="mRendered" class="preview-content" style="flex:1;overflow-y:auto;"><div class="prose"></div></div>
      <textarea id="mRaw" readonly class="raw-area" style="display:none;flex:1;"></textarea>
    </div>
  </div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
const fileMap = new Map();
let sessionId  = Math.random().toString(36).slice(2);
let curPreview = null;
let curTab     = 'rendered';
const cache    = {};

const ICONS = {
  pdf:'📕',docx:'📘',doc:'📘',xlsx:'📗',xls:'📗',
  pptx:'📙',ppt:'📙',html:'🌐',htm:'🌐',csv:'📊',
  json:'📋',xml:'📋',txt:'📝',jpg:'🖼️',jpeg:'🖼️',
  png:'🖼️',gif:'🖼️',webp:'🖼️',mp3:'🎵',wav:'🎵',
  epub:'📚',zip:'🗜️'
};
const ext  = n => n.split('.').pop().toLowerCase();
const icon = n => ICONS[ext(n)] || '📄';
const fmtSz = b => b < 1024 ? b+' B' : b < 1048576 ? (b/1024).toFixed(1)+' KB' : (b/1048576).toFixed(1)+' MB';
const esc  = s => s.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
const mob  = () => window.innerWidth < 768;

// ── File management ────────────────────────────────────────────────────────
function addFiles(files){
  for(const f of files)
    if(!fileMap.has(f.name))
      fileMap.set(f.name,{file:f,status:'waiting',resultId:null,outputName:null,error:null});
  render();
  document.getElementById('convertBtn').disabled = fileMap.size===0;
}

function removeFile(name){
  fileMap.delete(name);
  if(curPreview===name) closePreview();
  render(); updateSummary();
  document.getElementById('convertBtn').disabled = fileMap.size===0;
}

function clearAll(){
  fileMap.clear(); Object.keys(cache).forEach(k=>delete cache[k]);
  closePreview(); render();
  document.getElementById('convertBtn').disabled=true;
  document.getElementById('summary').style.display='none';
  document.getElementById('progressWrap').style.display='none';
}

// ── Render queue ───────────────────────────────────────────────────────────
function render(){
  const q=document.getElementById('fileQueue');
  const hint=document.getElementById('emptyHint');
  q.innerHTML='';
  document.getElementById('countBadge').textContent=fileMap.size;
  if(fileMap.size===0){ hint.style.display='flex'; return; }
  hint.style.display='none';

  for(const [name,info] of fileMap){
    const sel=name===curPreview, done=info.status==='done';
    const item=document.createElement('div');
    item.className='file-item'+(sel?' selected':'')+(done?' clickable':'');
    if(done) item.addEventListener('click',e=>{ if(!e.target.closest('button')) previewFile(name); });

    let badge='';
    if(info.status==='waiting')
      badge=`<span class="file-status status-waiting">Pending</span>`;
    else if(info.status==='converting')
      badge=`<span class="file-status status-converting"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;border:1.5px solid rgba(245,158,11,.3);border-top-color:var(--warning);animation:spin .7s linear infinite;"></span> Converting...</span>`;
    else if(info.status==='done'){
      const eMap={
        'azure-di':      ['Azure DI','badge-azure'],
        'pymupdf':       ['PyMuPDF','badge-pymupdf'],
        'docling':       ['Docling','badge-docling'],
        'markitdown':    ['local','badge-local'],
        'markitdown-fallback': ['fallback','badge-local'],
      };
      const [engLabel,engClass]=eMap[info.engine]||['local','badge-local'];
      badge=`<span class="file-status status-done">&#10003; Done <span class="engine-badge ${engClass}">${engLabel}</span></span>`;
    }
    else
      badge=`<span class="file-status status-error" title="${info.error||''}">&#10006; Error</span>`;

    let actions='';
    if(done){
      const n=esc(name);
      actions=`<button onclick="previewFile('${n}')" class="icon-btn" title="Preview">&#128065;</button>
               <button onclick="downloadOne('${n}')" class="icon-btn" title="Download">&#11015;</button>`;
    }
    item.innerHTML=`
      <div class="file-icon">${icon(name)}</div>
      <div class="file-info">
        <div class="file-name" title="${name}">${name}</div>
        <div class="file-size">${fmtSz(info.file.size)}</div>
        ${badge}
      </div>
      <div class="file-actions">
        ${actions}
        <button onclick="removeFile('${esc(name)}')" class="icon-btn danger" title="Remove">&#10005;</button>
      </div>
      ${info.status==='converting'?'<div class="file-progress"></div>':''}
    `;
    q.appendChild(item);
  }
}

// ── Convert ────────────────────────────────────────────────────────────────
async function convertAll(){
  const btn=document.getElementById('convertBtn');
  btn.disabled=true;
  btn.innerHTML='<span class="spinner"></span> Processing...';
  const fmt=document.getElementById('outputFormat').value;
  const todo=[...fileMap.entries()].filter(([,v])=>v.status==='waiting'||v.status==='error');
  if(!todo.length){ btn.disabled=false; btn.textContent='Convert all'; return; }

  document.getElementById('progressWrap').style.display='block';
  let done=0;
  for(const [name,info] of todo){
    info.status='converting'; render();
    const fd=new FormData();
    const engineChoice=document.getElementById('engineSelect').value;
    fd.append('file',info.file); fd.append('format',fmt); fd.append('session',sessionId);
    fd.append('engine', engineChoice);
    try{
      const r=await fetch('/convert',{method:'POST',body:fd});
      const d=await r.json();
      if(d.ok){ info.status='done'; info.resultId=d.result_id; info.outputName=d.output_name; info.engine=d.engine||'markitdown'; }
      else    { info.status='error'; info.error=d.error||'Failed'; }
    }catch{ info.status='error'; info.error='Loi ket noi'; }
    done++;
    document.getElementById('progressBar').style.width=(done/todo.length*100)+'%';
    render();
    if(info.status==='done'&&!curPreview) previewFile(name);
  }
  updateSummary();
  btn.disabled=false; btn.textContent='Convert all';
}

// ── Summary ────────────────────────────────────────────────────────────────
function updateSummary(){
  const ok=[...fileMap.values()].filter(v=>v.status==='done').length;
  const err=[...fileMap.values()].filter(v=>v.status==='error').length;
  const el=document.getElementById('summary');
  if(!ok&&!err){ el.style.display='none'; return; }
  el.style.display='flex';
  document.getElementById('summaryText').innerHTML=
    `<strong>${ok}</strong> file${ok>1?'s':''} converted`+
    (err?`, <strong style="color:var(--error)">${err}</strong> failed`:'');
  document.getElementById('downloadAllBtn').style.display=ok>1?'':'none';
}

// ── Download ───────────────────────────────────────────────────────────────
function downloadOne(name){
  const i=fileMap.get(name);
  if(!i||i.status!=='done') return;
  Object.assign(document.createElement('a'),{
    href:`/download/${i.resultId}/${encodeURIComponent(i.outputName)}`,download:i.outputName
  }).click();
}
function downloadAll(){
  Object.assign(document.createElement('a'),{
    href:`/download-zip?session=${sessionId}`,download:'converted.zip'
  }).click();
}

// ── Preview ────────────────────────────────────────────────────────────────
async function previewFile(name){
  const info=fileMap.get(name);
  if(!info||info.status!=='done') return;
  curPreview=name; render();
  if(mob()){
    document.getElementById('mobileModal').style.display='block';
    document.getElementById('mPreviewName').textContent=info.outputName||name;
    showSkelM(true);
    const c=await getContent(info.resultId);
    showSkelM(false); renderContent(c,true);
  } else {
    document.getElementById('previewEmpty').style.display='none';
    document.getElementById('previewPanel').classList.add('visible');
    document.getElementById('previewFileName').textContent=info.outputName||name;
    document.getElementById('dlOneBtn').onclick=()=>downloadOne(name);
    showSkel(true);
    const c=await getContent(info.resultId);
    showSkel(false); renderContent(c,false);
  }
}

async function getContent(id){
  if(cache[id]) return cache[id];
  try{
    const r=await fetch('/preview/'+id);
    const d=await r.json();
    if(d.ok){ cache[id]=d.content; return d.content; }
  }catch{}
  return '> Failed to load content.';
}

function renderMath(el){
  if(typeof renderMathInElement !== 'undefined'){
    renderMathInElement(el,{
      delimiters:[
        {left:'$$',right:'$$',display:true},
        {left:'$',right:'$',display:false},
        {left:'\\(',right:'\\)',display:false},
        {left:'\\[',right:'\\]',display:true},
      ],
      throwOnError:false,
    });
  }
}

function renderContent(txt,mobile){
  const html=marked.parse(txt||'');
  if(mobile){
    const mR=document.getElementById('mRendered');
    mR.innerHTML='<div class="prose">'+html+'</div>';
    document.getElementById('mRaw').value=txt||'';
    mR.querySelectorAll('pre code').forEach(el=>hljs.highlightElement(el));
    renderMath(mR);
  } else {
    document.getElementById('proseContent').innerHTML=html;
    document.getElementById('pRaw').value=txt||'';
    document.getElementById('proseContent').querySelectorAll('pre code').forEach(el=>hljs.highlightElement(el));
    renderMath(document.getElementById('proseContent'));
  }
  applyTab();
}

function showSkel(on){
  document.getElementById('skelWrap').style.display =on?'block':'none';
  document.getElementById('pRendered').style.display=on?'none':'block';
  document.getElementById('pRaw').style.display     ='none';
}
function showSkelM(on){
  const mR=document.getElementById('mRendered');
  if(on) mR.innerHTML='<div style="padding:20px 28px">'+
    '<div class="skeleton-line" style="width:55%;height:18px;"></div>'+
    '<div class="skeleton-line" style="width:100%;"></div>'+
    '<div class="skeleton-line" style="width:75%;"></div>'+
    '<div class="skeleton-line" style="height:60px;width:100%;margin-top:10px;"></div>'+
    '</div>';
}

function closePreview(){
  curPreview=null;
  document.getElementById('previewPanel').classList.remove('visible');
  document.getElementById('previewEmpty').style.display='flex';
  document.getElementById('mobileModal').style.display='none';
  document.getElementById('mainLayout').className='one-col';
  render();
}

function switchTab(tab){ curTab=tab; applyTab(); }
function applyTab(){
  const isR=curTab==='rendered';
  const pR=document.getElementById('pRendered');
  const pRaw=document.getElementById('pRaw');
  if(pR)   pR.style.display  =isR?'block':'none';
  if(pRaw) pRaw.style.display=isR?'none':'block';
  const tR=document.getElementById('tabR');
  const tRaw=document.getElementById('tabRaw');
  if(tR)   tR.className  =isR?'tab-btn active':'tab-btn';
  if(tRaw) tRaw.className=isR?'tab-btn':'tab-btn active';
  const mR=document.getElementById('mRendered');
  const mRaw=document.getElementById('mRaw');
  if(mR)   mR.style.display  =isR?'block':'none';
  if(mRaw) mRaw.style.display=isR?'none':'block';
  const mtR=document.getElementById('mTabR');
  const mtRaw=document.getElementById('mTabRaw');
  if(mtR)   mtR.className  =isR?'tab-btn active':'tab-btn';
  if(mtRaw) mtRaw.className=isR?'tab-btn':'tab-btn active';
}

async function copyContent(){
  const txt=document.getElementById('pRaw').value||document.getElementById('mRaw').value;
  if(!txt) return;
  await navigator.clipboard.writeText(txt);
  const btn=document.getElementById('copyBtn');
  const old=btn.innerHTML; btn.innerHTML='&#10003; Copied!';
  setTimeout(()=>btn.innerHTML=old,1800);
}

// ── Drag & drop ────────────────────────────────────────────────────────────
const dz=document.getElementById('dropzone');
dz.addEventListener('dragover', e=>{ e.preventDefault(); dz.classList.add('dz-active'); });
dz.addEventListener('dragleave',  ()=>dz.classList.remove('dz-active'));
dz.addEventListener('drop', e=>{
  e.preventDefault(); dz.classList.remove('dz-active'); addFiles(e.dataTransfer.files);
});
document.getElementById('fileInput').addEventListener('change',e=>{ addFiles(e.target.files); e.target.value=''; });
marked.setOptions({breaks:true,gfm:true});

// ── History ────────────────────────────────────────────────────────────────
let historyOpen=false;
function toggleHistory(){
  historyOpen=!historyOpen;
  document.getElementById('historyPanel').style.display=historyOpen?'flex':'none';
  document.getElementById('fileQueue').style.display=historyOpen?'none':'block';
  document.getElementById('emptyHint').style.display=historyOpen?'none':(fileMap.size===0?'flex':'none');
  document.getElementById('historyBtn').style.color=historyOpen?'var(--text)':'var(--text-3)';
  if(historyOpen) loadHistory();
}
async function loadHistory(){
  const list=document.getElementById('historyList');
  list.innerHTML='<div style="padding:16px;font-size:11px;color:var(--text-3);">Loading...</div>';
  try{
    const r=await fetch('/history');
    const d=await r.json();
    if(!d.ok||!d.rows.length){ list.innerHTML='<div style="padding:16px;font-size:11px;color:var(--text-3);">No history yet.</div>'; return; }
    list.innerHTML=d.rows.map(row=>{
      const date=new Date(row.created_at).toLocaleDateString('en',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
      const eng=row.engine==='azure-di'?'<span class="engine-badge badge-azure">Azure DI</span>':'<span class="engine-badge badge-local">local</span>';
      const chars=row.char_count?`${(row.char_count/1000).toFixed(1)}k chars`:'';
      return `<div onclick="loadHistoryItem('${row.id}','${row.output_name||row.file_name}')"
        style="padding:10px 16px;border-bottom:1px solid var(--border);cursor:pointer;transition:background .1s;"
        onmouseover="this.style.background='rgba(128,128,128,.05)'" onmouseout="this.style.background='transparent'">
        <div style="font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${row.file_name}</div>
        <div style="font-size:10px;color:var(--text-3);margin-top:3px;display:flex;gap:6px;align-items:center;">
          <span>${date}</span>${eng}<span>${chars}</span>
        </div>
      </div>`;
    }).join('');
  }catch{ list.innerHTML='<div style="padding:16px;font-size:11px;color:var(--error);">Failed to load.</div>'; }
}
async function loadHistoryItem(id,name){
  document.getElementById('previewEmpty').style.display='none';
  document.getElementById('previewPanel').classList.add('visible');
  document.getElementById('previewFileName').textContent=name;
  document.getElementById('dlOneBtn').onclick=()=>{};
  showSkel(true);
  try{
    const r=await fetch('/history/'+id+'/content');
    const d=await r.json();
    showSkel(false);
    if(d.ok){ renderContent(d.content,false); }
    else { document.getElementById('proseContent').innerHTML='<p style="color:var(--error)">Failed to load.</p>'; }
  }catch{ showSkel(false); }
}

// ── Engine selection ────────────────────────────────────────────────────────
function saveEngineChoice(){
  const v=document.getElementById('engineSelect').value;
  localStorage.setItem('engineChoice',v);
  document.getElementById('azureSection').style.display=v==='azure-di'?'block':'none';
}
function loadEngineChoice(){
  const v=localStorage.getItem('engineChoice')||'markitdown';
  document.getElementById('engineSelect').value=v;
  document.getElementById('azureSection').style.display=v==='azure-di'?'block':'none';
}
loadEngineChoice();


// ── Settings ───────────────────────────────────────────────────────────────
function openSettings(){
  document.getElementById('settingsOverlay').classList.add('open');
  document.getElementById('setCurrent').focus();
  document.getElementById('setMsg').textContent='';
  document.getElementById('setCurrent').value='';
  document.getElementById('setNew').value='';
  document.getElementById('setConfirm').value='';
}
function closeSettings(){ document.getElementById('settingsOverlay').classList.remove('open'); }
function closeSettingsOutside(e){ if(e.target===document.getElementById('settingsOverlay')) closeSettings(); }
async function savePassword(){
  const cur=document.getElementById('setCurrent').value;
  const nw=document.getElementById('setNew').value;
  const cf=document.getElementById('setConfirm').value;
  const msg=document.getElementById('setMsg');
  if(!cur||!nw||!cf){ msg.className='settings-msg err'; msg.textContent='All fields are required.'; return; }
  if(nw!==cf){ msg.className='settings-msg err'; msg.textContent='New passwords do not match.'; return; }
  msg.className='settings-msg'; msg.textContent='Saving...';
  try{
    const r=await fetch('/settings/password',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({current:cur,new_pw:nw})
    });
    const d=await r.json();
    if(d.ok){
      msg.className='settings-msg ok'; msg.textContent='Password updated! Redirecting to login...';
      setTimeout(()=>window.location.href='/logout',1500);
    } else {
      msg.className='settings-msg err'; msg.textContent=d.error;
    }
  }catch{ msg.className='settings-msg err'; msg.textContent='Network error.'; }
}

// ── Theme toggle ───────────────────────────────────────────────────────────
const hlTheme=document.getElementById('hl-theme');
function applyTheme(isLight){
  if(isLight){
    document.body.classList.add('light');
    hlTheme.href='https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
    document.getElementById('themeBtn').textContent='🌙';
  } else {
    document.body.classList.remove('light');
    hlTheme.href='https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css';
    document.getElementById('themeBtn').textContent='☀️';
  }
}
function toggleTheme(){
  const isLight=!document.body.classList.contains('light');
  localStorage.setItem('theme',isLight?'light':'dark');
  applyTheme(isLight);
}
applyTheme(localStorage.getItem('theme')==='light');
</script>
</body>
</html>"""

md_converter  = MarkItDown()
results_store = {}


def convert_with_pymupdf(file_path: str) -> str:
    """Fast local conversion using pymupdf4llm."""
    import pymupdf4llm
    return pymupdf4llm.to_markdown(file_path)


def convert_with_docling(file_path: str) -> str:
    """High-quality local conversion using docling (IBM)."""
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()
    result = converter.convert(file_path)
    return result.document.export_to_markdown()


def convert_with_azure_di(file_path: str, endpoint: str, api_key: str) -> str:
    """Convert file using Azure Document Intelligence — returns native Markdown."""
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    client = DocumentIntelligenceClient(
        endpoint=endpoint.rstrip("/"),
        credential=AzureKeyCredential(api_key),
    )
    with open(file_path, "rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=f,
            content_type="application/octet-stream",
            output_content_format="markdown",
        )
    result = poller.result()
    return result.content or ""


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarkItDown — Login</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#080808;color:#fff;font-family:-apple-system,'Segoe UI',system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;}
.card{background:#111113;border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:40px 36px;width:100%;max-width:360px;}
.logo{font-size:15px;font-weight:700;letter-spacing:-.02em;margin-bottom:28px;display:flex;align-items:center;gap:8px;color:#fff;}
.dot{width:7px;height:7px;background:#fff;border-radius:50%;}
h2{font-size:1.2rem;font-weight:600;margin-bottom:6px;letter-spacing:-.02em;}
p{font-size:13px;color:rgba(255,255,255,.45);margin-bottom:24px;}
label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:rgba(255,255,255,.4);display:block;margin-bottom:6px;}
input[type=password]{width:100%;background:#1a1a1d;color:#fff;border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:11px 14px;font-size:14px;outline:none;transition:border-color .15s;font-family:inherit;}
input[type=password]:focus{border-color:rgba(255,255,255,.3);}
button{width:100%;background:#fff;color:#000;border:none;border-radius:8px;padding:12px;font-size:13px;font-weight:600;cursor:pointer;margin-top:16px;transition:opacity .15s;font-family:inherit;}
button:hover{opacity:.85;}
.err{color:#ef4444;font-size:12px;margin-top:10px;}
</style>
</head>
<body>
<div class="card">
  <div class="logo"><span class="dot"></span>MarkItDown</div>
  <h2>Welcome back</h2>
  <p>Enter your password to continue</p>
  <form method="POST" action="/login">
    <label>Password</label>
    <input type="password" name="password" autofocus placeholder="••••••••••">
    <button type="submit">Sign in</button>
    {% if error %}<div class="err">{{ error }}</div>{% endif %}
  </form>
</div>
</body>
</html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        if hash_password(pw) == get_current_password_hash():
            session["authenticated"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error = "Incorrect password."
    return render_template_string(LOGIN_PAGE, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/settings/password", methods=["POST"])
@login_required
def change_password():
    data        = request.get_json(silent=True) or {}
    current     = data.get("current", "")
    new_pw      = data.get("new_pw", "")
    if hash_password(current) != get_current_password_hash():
        return jsonify({"ok": False, "error": "Current password is incorrect."})
    if len(new_pw) < 6:
        return jsonify({"ok": False, "error": "Password must be at least 6 characters."})
    ok = set_password(new_pw)
    if ok:
        session.clear()  # force re-login with new password
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Failed to save. Check Supabase connection."})


@app.route("/")
@login_required
def index():
    return render_template_string(HTML_PAGE)


@app.route("/test-azure", methods=["POST"])
@login_required
def test_azure():
    data     = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint", "").strip()
    api_key  = data.get("key", "").strip()
    if not endpoint or not api_key:
        return jsonify({"ok": False, "error": "Missing endpoint or API key"})
    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential
        from azure.core.rest import HttpRequest
        client = DocumentIntelligenceClient(
            endpoint=endpoint.rstrip("/"),
            credential=AzureKeyCredential(api_key),
        )
        req = HttpRequest(
            "GET",
            f"{endpoint.rstrip('/')}/documentintelligence/documentModels?api-version=2024-11-30"
        )
        resp = client.send_request(req)
        if resp.status_code == 200:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": f"HTTP {resp.status_code}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:160]})


@app.route("/convert", methods=["POST"])
@login_required
def convert():
    file              = request.files.get("file")
    fmt               = request.form.get("format", "md")
    session           = request.form.get("session", "default")
    engine_choice     = request.form.get("engine", "markitdown")  # markitdown|pymupdf|docling|azure-di
    docintel_endpoint = request.form.get("docintel_endpoint", "").strip()
    docintel_key      = request.form.get("docintel_key", "").strip()

    if not file:
        return jsonify({"ok": False, "error": "No file"})

    file_ext = Path(file.filename).suffix.lower().lstrip(".")
    if file_ext not in SUPPORTED_EXTENSIONS:
        return jsonify({"ok": False, "error": f"Format .{file_ext} not supported"})

    tmp_path = UPLOAD_FOLDER / f"{uuid.uuid4()}{Path(file.filename).suffix}"
    try:
        file.save(str(tmp_path))
        engine = engine_choice

        if engine_choice == "pymupdf":
            try:
                content = convert_with_pymupdf(str(tmp_path))
            except Exception as e:
                print(f"[pymupdf] failed: {e}, fallback to markitdown")
                content = md_converter.convert(str(tmp_path)).text_content
                engine  = "markitdown-fallback"

        elif engine_choice == "docling":
            try:
                content = convert_with_docling(str(tmp_path))
            except Exception as e:
                print(f"[docling] failed: {e}, fallback to markitdown")
                content = md_converter.convert(str(tmp_path)).text_content
                engine  = "markitdown-fallback"

        elif engine_choice == "azure-di" and docintel_endpoint and docintel_key:
            try:
                content = convert_with_azure_di(str(tmp_path), docintel_endpoint, docintel_key)
                engine  = "azure-di"
            except Exception as az_err:
                import traceback
                print(f"[Azure DI] FAILED: {type(az_err).__name__}: {az_err}")
                traceback.print_exc()
                content = md_converter.convert(str(tmp_path)).text_content
                engine  = "markitdown-fallback"
        else:
            content = md_converter.convert(str(tmp_path)).text_content
            engine  = "markitdown"

        content_bytes = content.encode("utf-8")
        output_name   = f"{Path(file.filename).stem}.{fmt}"
        result_id     = str(uuid.uuid4())
        results_store[result_id] = (content_bytes, output_name, session)

        # Persist to Supabase (non-blocking best-effort)
        save_conversion(
            file_name=file.filename, file_size=file.content_length or len(content_bytes),
            file_ext=file_ext, engine=engine, output_name=output_name, content=content,
        )
        return jsonify({"ok": True, "result_id": result_id, "output_name": output_name, "engine": engine})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:160]})
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.route("/history")
@login_required
def history():
    try:
        sb = get_supabase()
        if not sb:
            return jsonify({"ok": False, "error": "Supabase not available"})
        rows = sb.table("conversions").select(
            "id,created_at,file_name,file_size,file_ext,engine,output_name,char_count"
        ).order("created_at", desc=True).limit(50).execute()
        return jsonify({"ok": True, "rows": rows.data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:160]})


@app.route("/history/<record_id>/content")
@login_required
def history_content(record_id):
    try:
        sb = get_supabase()
        row = sb.table("conversions").select("content,output_name").eq("id", record_id).single().execute()
        return jsonify({"ok": True, "content": row.data["content"], "output_name": row.data["output_name"]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:160]})


@app.route("/preview/<result_id>")
@login_required
def preview(result_id):
    if result_id not in results_store:
        return jsonify({"ok": False, "error": "Not found"}), 404
    content_bytes, output_name, _ = results_store[result_id]
    return jsonify({"ok": True, "content": content_bytes.decode("utf-8"), "output_name": output_name})


@app.route("/download/<result_id>/<filename>")
@login_required
def download_one(result_id, filename):
    if result_id not in results_store:
        return "Not found", 404
    content_bytes, output_name, _ = results_store[result_id]
    return send_file(
        io.BytesIO(content_bytes),
        as_attachment=True,
        download_name=output_name,
        mimetype="text/markdown",
    )


@app.route("/download-zip")
@login_required
def download_zip():
    session = request.args.get("session", "")
    items   = [(cb, on) for cb, on, sid in results_store.values() if sid == session]
    if not items:
        return "No files", 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for content_bytes, output_name in items:
            zf.writestr(output_name, content_bytes)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="converted.zip", mimetype="application/zip")


if __name__ == "__main__":
    print("MarkItDown Web UI: http://localhost:5000")
    app.run(debug=False, port=5000)
