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

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MarkItDown Converter</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0;}
  ::-webkit-scrollbar{width:5px;height:5px;}
  ::-webkit-scrollbar-track{background:#0a0b0f;}
  ::-webkit-scrollbar-thumb{background:#1e2133;border-radius:4px;}
  ::-webkit-scrollbar-thumb:hover{background:#2e3350;}
  body{background:#0a0b0f;font-family:'Segoe UI',system-ui,sans-serif;color:#e2e8f0;}

  @keyframes spin{to{transform:rotate(360deg);}}
  @keyframes bounce-up{0%,100%{transform:translateY(0);}50%{transform:translateY(-8px);}}
  @keyframes fade-up{from{opacity:0;transform:translateY(14px);}to{opacity:1;transform:translateY(0);}}
  @keyframes slide-right{from{opacity:0;transform:translateX(20px);}to{opacity:1;transform:translateX(0);}}
  @keyframes shimmer{0%{background-position:-200% 0;}100%{background-position:200% 0;}}
  @keyframes card-in{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);}}

  .spin{animation:spin .7s linear infinite;}
  .bounce{animation:bounce-up 2s ease-in-out infinite;}
  .fade-up{animation:fade-up .22s ease forwards;}
  .slide-right{animation:slide-right .22s ease forwards;}
  .card-in{animation:card-in .2s ease forwards;}

  .shimmer-btn{
    background:linear-gradient(90deg,#6366f1 0%,#818cf8 25%,#6366f1 50%,#818cf8 75%,#6366f1 100%);
    background-size:200% auto;
  }
  .shimmer-btn:hover:not(:disabled){animation:shimmer 1.4s linear infinite;}
  .shimmer-skel{
    background:linear-gradient(90deg,#1a1d2e 25%,#22263a 50%,#1a1d2e 75%);
    background-size:200% auto;
    animation:shimmer 1.5s linear infinite;
  }

  .dz-active{
    border-color:#6366f1!important;
    background:rgba(99,102,241,.06)!important;
    box-shadow:0 0 0 4px rgba(99,102,241,.14),inset 0 0 40px rgba(99,102,241,.04);
  }

  .card-progress{
    position:absolute;bottom:0;left:0;right:0;height:3px;border-radius:0 0 12px 12px;
    background:linear-gradient(90deg,#6366f1,#818cf8);background-size:200% auto;
    animation:shimmer 1.2s linear infinite;
  }

  .prose-dark{color:#e2e8f0;line-height:1.8;font-size:.93rem;}
  .prose-dark h1,.prose-dark h2,.prose-dark h3,.prose-dark h4{color:#f1f5f9;font-weight:700;margin:1.4em 0 .5em;}
  .prose-dark h1{font-size:1.55em;border-bottom:1px solid #1e2133;padding-bottom:.4em;}
  .prose-dark h2{font-size:1.3em;border-bottom:1px solid #1e2133;padding-bottom:.3em;}
  .prose-dark h3{font-size:1.1em;}
  .prose-dark p{margin:.75em 0;}
  .prose-dark ul,.prose-dark ol{padding-left:1.6em;margin:.75em 0;}
  .prose-dark li{margin:.25em 0;}
  .prose-dark code:not(pre code){background:#1e2133;color:#a78bfa;padding:2px 6px;border-radius:4px;font-size:.85em;font-family:'Cascadia Code','Fira Code',monospace;}
  .prose-dark pre{background:#0d0f17!important;border:1px solid #1e2133;border-radius:8px;overflow-x:auto;margin:.9em 0;}
  .prose-dark pre code{font-size:.83em;}
  .prose-dark table{width:100%;border-collapse:collapse;margin:.9em 0;font-size:.88em;}
  .prose-dark th{background:#1a1d2e;color:#a78bfa;padding:8px 12px;text-align:left;border:1px solid #1e2133;}
  .prose-dark td{padding:8px 12px;border:1px solid #1e2133;}
  .prose-dark tr:nth-child(even){background:rgba(30,33,51,.4);}
  .prose-dark a{color:#818cf8;text-decoration:underline;}
  .prose-dark blockquote{border-left:3px solid #6366f1;padding-left:1em;color:#94a3b8;margin:.9em 0;}
  .prose-dark hr{border:none;border-top:1px solid #1e2133;margin:1.4em 0;}
  .prose-dark img{max-width:100%;border-radius:8px;}

  .tab-on{color:#818cf8;border-bottom:2px solid #6366f1;}
  .tab-off{color:#64748b;border-bottom:2px solid transparent;}
  .tab-off:hover{color:#94a3b8;}

  .two-col{display:grid;grid-template-columns:1fr 1fr;gap:20px;transition:grid-template-columns .3s ease;}
  .one-col{display:grid;grid-template-columns:1fr;gap:20px;}

  @media(max-width:768px){.two-col{grid-template-columns:1fr!important;}}

  .modal-bg{position:fixed;inset:0;background:rgba(0,0,0,.75);backdrop-filter:blur(4px);z-index:40;}
  .modal-box{position:fixed;inset:0;z-index:41;display:flex;flex-direction:column;background:#12141c;}

  .pill{background:rgba(99,102,241,.12);border:1px solid rgba(99,102,241,.25);color:#818cf8;}

  .icon-btn{
    width:32px;height:32px;display:flex;align-items:center;justify-content:center;
    border-radius:8px;border:1px solid #1e2133;background:#1a1d2e;
    color:#94a3b8;cursor:pointer;font-size:.95rem;transition:all .15s;
  }
  .icon-btn:hover{border-color:#6366f1;color:#818cf8;}
</style>
</head>
<body class="min-h-screen">
<div class="max-w-screen-xl mx-auto px-4 py-8">

  <!-- HEADER -->
  <header class="text-center mb-10 relative">
    <div class="absolute top-0 right-0">
      <span class="pill text-xs px-3 py-1 rounded-full font-medium">✨ Powered by AI</span>
    </div>
    <h1 class="text-4xl font-bold mb-2"
      style="background:linear-gradient(135deg,#6366f1,#a78bfa,#c4b5fd);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">
      📄 MarkItDown Converter
    </h1>
    <p class="text-sm" style="color:#64748b;">Chuyen doi PDF, Word, Excel, PowerPoint, anh... sang Markdown de dung voi LLM</p>
  </header>

  <!-- DROP ZONE -->
  <div id="dropzone"
    class="relative rounded-2xl border-2 border-dashed text-center cursor-pointer transition-all duration-200 mb-4"
    style="border-color:#1e2133;background:#12141c;padding:52px 24px;">
    <input type="file" id="fileInput" multiple accept="*/*"
      class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10">
    <div class="bounce text-5xl mb-4">&#9729;&#65039;</div>
    <h3 class="text-lg font-semibold mb-1">Keo tha file vao day hoac click de chon</h3>
    <p class="text-sm mb-5" style="color:#64748b;">Ho tro nhieu file cung luc &middot; Toi da 200MB/file</p>
    <div class="flex flex-wrap gap-2 justify-center">
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">PDF</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">DOCX</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">XLSX</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">PPTX</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">HTML</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">CSV</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">JSON</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">XML</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">TXT</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">JPG/PNG</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">MP3/WAV</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">EPUB</span>
      <span class="pill text-xs px-2.5 py-1 rounded-full font-mono">ZIP</span>
    </div>
  </div>

  <!-- OPTIONS BAR -->
  <div class="flex items-center gap-3 rounded-xl border px-5 py-3.5 mb-5 flex-wrap"
    style="background:#12141c;border-color:#1e2133;">
    <span class="text-sm" style="color:#64748b;">Format dau ra:</span>
    <select id="outputFormat" class="text-sm rounded-lg px-3 py-1.5 outline-none cursor-pointer"
      style="background:#1a1d2e;border:1px solid #1e2133;color:#e2e8f0;">
      <option value="md">Markdown (.md)</option>
      <option value="txt">Plain Text (.txt)</option>
    </select>
    <div class="flex-1"></div>
    <button onclick="clearAll()" id="clearBtn"
      class="text-sm px-4 py-2 rounded-lg font-medium border transition-all"
      style="color:#ef4444;border-color:rgba(239,68,68,.35);background:transparent;"
      onmouseover="this.style.background='rgba(239,68,68,.08)'"
      onmouseout="this.style.background='transparent'">Xoa tat ca</button>
    <button id="convertBtn" onclick="convertAll()" disabled
      class="shimmer-btn text-sm px-5 py-2 rounded-lg font-semibold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed">
      &#9889; Convert tat ca
    </button>
  </div>

  <!-- MAIN LAYOUT -->
  <div class="one-col" id="mainLayout">

    <!-- LEFT col -->
    <div id="leftCol">
      <div id="fileQueue" class="flex flex-col gap-2.5"></div>
      <div id="emptyHint" class="text-center py-12 text-sm" style="color:#475569;display:none;">
        Chua co file nao duoc them vao
      </div>

      <!-- global progress -->
      <div id="progressWrap" class="mt-3 rounded-full overflow-hidden"
        style="height:4px;background:#1a1d2e;display:none;">
        <div id="progressBar" class="h-full rounded-full transition-all duration-300"
          style="width:0%;background:linear-gradient(90deg,#6366f1,#818cf8);"></div>
      </div>

      <!-- summary -->
      <div id="summary" class="flex items-center gap-4 rounded-xl border px-5 py-3.5 mt-4 flex-wrap"
        style="background:#12141c;border-color:#1e2133;display:none;">
        <div id="summaryText" class="text-sm" style="color:#94a3b8;"></div>
        <div class="flex-1"></div>
        <button id="downloadAllBtn" onclick="downloadAll()"
          class="shimmer-btn text-sm px-4 py-2 rounded-lg font-semibold text-white">
          &#11015;&#65039; Tai tat ca (.zip)
        </button>
      </div>
    </div>

    <!-- RIGHT col: preview panel (desktop) -->
    <div id="previewPanel" style="display:none;">
      <div class="rounded-2xl border flex flex-col slide-right"
        style="background:#12141c;border-color:#1e2133;position:sticky;top:20px;height:calc(100vh - 200px);min-height:420px;">

        <!-- panel header -->
        <div class="flex items-center gap-2 px-4 py-3 border-b" style="border-color:#1e2133;flex-shrink:0;">
          <span id="previewFileName" class="text-sm font-medium truncate flex-1" style="color:#e2e8f0;"></span>
          <button onclick="copyContent()" id="copyBtn"
            class="text-xs px-3 py-1.5 rounded-lg font-medium border transition-all"
            style="background:#1a1d2e;border-color:#1e2133;color:#94a3b8;"
            onmouseover="this.style.borderColor='#6366f1';this.style.color='#818cf8'"
            onmouseout="this.style.borderColor='#1e2133';this.style.color='#94a3b8'">
            &#128203; Copy
          </button>
          <button id="dlOneBtn"
            class="text-xs px-3 py-1.5 rounded-lg font-medium border transition-all"
            style="background:#1a1d2e;border-color:#1e2133;color:#94a3b8;"
            onmouseover="this.style.borderColor='#6366f1';this.style.color='#818cf8'"
            onmouseout="this.style.borderColor='#1e2133';this.style.color='#94a3b8'">
            &#11015; Tai xuong
          </button>
          <button onclick="closePreview()"
            class="icon-btn" style="border:none;background:#1a1d2e;"
            onmouseover="this.style.color='#ef4444'" onmouseout="this.style.color='#94a3b8'">&#10005;</button>
        </div>

        <!-- tabs -->
        <div class="flex border-b px-4" style="border-color:#1e2133;flex-shrink:0;">
          <button onclick="switchTab('rendered')" id="tabR"
            class="tab-on text-sm px-4 py-2.5 font-medium transition-all mr-1">Rendered</button>
          <button onclick="switchTab('raw')" id="tabRaw"
            class="tab-off text-sm px-4 py-2.5 font-medium transition-all">Raw Markdown</button>
        </div>

        <!-- content -->
        <div class="flex-1 overflow-hidden relative">
          <div id="skelWrap" class="p-5 space-y-3" style="display:none;">
            <div class="shimmer-skel h-6 rounded" style="width:60%;"></div>
            <div class="shimmer-skel h-4 rounded w-full"></div>
            <div class="shimmer-skel h-4 rounded" style="width:80%;"></div>
            <div class="shimmer-skel h-4 rounded w-full"></div>
            <div class="shimmer-skel h-4 rounded" style="width:70%;"></div>
            <div class="shimmer-skel h-24 rounded w-full mt-3"></div>
            <div class="shimmer-skel h-4 rounded w-full"></div>
            <div class="shimmer-skel h-4 rounded" style="width:85%;"></div>
          </div>
          <div id="pRendered" class="prose-dark p-5 overflow-y-auto h-full"
            style="scrollbar-width:thin;"></div>
          <textarea id="pRaw" readonly
            class="w-full h-full p-4 resize-none outline-none text-xs font-mono"
            style="background:#0a0b0f;color:#94a3b8;border:none;display:none;scrollbar-width:thin;"></textarea>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- MOBILE MODAL -->
<div id="mobileModal" style="display:none;">
  <div class="modal-bg" onclick="closePreview()"></div>
  <div class="modal-box">
    <div class="flex items-center gap-2 px-4 py-3 border-b" style="border-color:#1e2133;flex-shrink:0;">
      <span id="mPreviewName" class="text-sm font-medium truncate flex-1" style="color:#e2e8f0;"></span>
      <button onclick="copyContent()" class="icon-btn text-xs" style="width:auto;padding:0 10px;font-size:.75rem;">&#128203;</button>
      <button onclick="closePreview()" class="icon-btn"
        onmouseover="this.style.color='#ef4444'" onmouseout="this.style.color='#94a3b8'">&#10005;</button>
    </div>
    <div class="flex border-b px-4" style="border-color:#1e2133;flex-shrink:0;">
      <button onclick="switchTab('rendered')" id="mTabR"
        class="tab-on text-sm px-4 py-2.5 font-medium transition-all mr-1">Rendered</button>
      <button onclick="switchTab('raw')" id="mTabRaw"
        class="tab-off text-sm px-4 py-2.5 font-medium transition-all">Raw</button>
    </div>
    <div class="flex-1 overflow-hidden">
      <div id="mRendered" class="prose-dark p-4 overflow-y-auto h-full" style="scrollbar-width:thin;"></div>
      <textarea id="mRaw" readonly class="w-full h-full p-4 resize-none outline-none text-xs font-mono"
        style="background:#0a0b0f;color:#94a3b8;border:none;display:none;scrollbar-width:thin;"></textarea>
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
  const q    = document.getElementById('fileQueue');
  const hint = document.getElementById('emptyHint');
  q.innerHTML = '';
  if(fileMap.size===0){ hint.style.display='block'; return; }
  hint.style.display='none';

  for(const [name,info] of fileMap){
    const sel = name===curPreview;
    const card = document.createElement('div');
    card.className = 'card-in';
    card.style.cssText =
      'position:relative;overflow:hidden;border-radius:12px;border:1px solid '+(sel?'#6366f1':'#1e2133')+
      ';background:'+(sel?'rgba(99,102,241,.07)':'#12141c')+
      ';padding:12px 14px;display:flex;align-items:center;gap:12px;'+
      'transition:border-color .15s,background .15s;'+
      (info.status==='done'?'cursor:pointer;':'');

    if(info.status==='done'){
      card.addEventListener('click', e=>{ if(!e.target.closest('button')) previewFile(name); });
      card.addEventListener('mouseover',()=>{ if(name!==curPreview) card.style.borderColor='#2e3350'; });
      card.addEventListener('mouseout', ()=>{ if(name!==curPreview) card.style.borderColor='#1e2133'; });
    }

    // status badge
    let badge='';
    if(info.status==='waiting')
      badge=`<span style="font-size:.72rem;padding:3px 10px;border-radius:99px;background:rgba(100,116,139,.12);color:#64748b;font-weight:600;">Cho...</span>`;
    else if(info.status==='converting')
      badge=`<span style="font-size:.72rem;padding:3px 10px;border-radius:99px;background:rgba(245,158,11,.12);color:#f59e0b;font-weight:600;display:inline-flex;align-items:center;gap:6px;">
               <span class="spin" style="display:inline-block;width:11px;height:11px;border-radius:50%;border:2px solid rgba(245,158,11,.3);border-top-color:#f59e0b;"></span>Xu ly
             </span>`;
    else if(info.status==='done')
      badge=`<span style="font-size:.72rem;padding:3px 10px;border-radius:99px;background:rgba(34,197,94,.12);color:#22c55e;font-weight:600;">&#10003; Xong</span>`;
    else
      badge=`<span title="${info.error||'Loi'}" style="font-size:.72rem;padding:3px 10px;border-radius:99px;background:rgba(239,68,68,.12);color:#ef4444;font-weight:600;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;">&#10006; ${(info.error||'Loi').slice(0,20)}</span>`;

    // action buttons
    let actions='';
    if(info.status==='done'){
      const n=esc(name);
      actions=`
        <button onclick="previewFile('${n}')" class="icon-btn" title="Preview">&#128065;</button>
        <button onclick="downloadOne('${n}')" class="icon-btn" title="Tai xuong">&#11015;</button>`;
    }

    card.innerHTML=`
      <div style="font-size:1.5rem;flex-shrink:0;">${icon(name)}</div>
      <div style="flex:1;min-width:0;">
        <div style="font-size:.875rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${name}">${name}</div>
        <div style="font-size:.75rem;color:#64748b;margin-top:2px;">${fmtSz(info.file.size)}</div>
      </div>
      <div style="display:flex;align-items:center;gap:7px;flex-shrink:0;">
        ${badge}${actions}
        <button onclick="removeFile('${esc(name)}')" class="icon-btn" style="border:none;background:transparent;color:#475569;"
          onmouseover="this.style.color='#ef4444';this.style.background='rgba(239,68,68,.1)'"
          onmouseout="this.style.color='#475569';this.style.background='transparent'"
          title="Xoa">&#10005;</button>
      </div>
      ${info.status==='converting'?'<div class="card-progress"></div>':''}
    `;
    q.appendChild(card);
  }
}

// ── Convert ────────────────────────────────────────────────────────────────
async function convertAll(){
  const btn=document.getElementById('convertBtn');
  btn.disabled=true; btn.textContent='Dang xu ly...';
  const fmt=document.getElementById('outputFormat').value;
  const todo=[...fileMap.entries()].filter(([,v])=>v.status==='waiting'||v.status==='error');
  if(!todo.length){ btn.disabled=false; btn.textContent='⚡ Convert tat ca'; return; }

  document.getElementById('progressWrap').style.display='block';
  let done=0;
  for(const [name,info] of todo){
    info.status='converting'; render();
    const fd=new FormData();
    fd.append('file',info.file); fd.append('format',fmt); fd.append('session',sessionId);
    try{
      const r=await fetch('/convert',{method:'POST',body:fd});
      const d=await r.json();
      if(d.ok){ info.status='done'; info.resultId=d.result_id; info.outputName=d.output_name; }
      else    { info.status='error'; info.error=d.error||'That bai'; }
    }catch{ info.status='error'; info.error='Loi ket noi'; }
    done++;
    document.getElementById('progressBar').style.width=(done/todo.length*100)+'%';
    render();
    if(info.status==='done'&&!curPreview) previewFile(name);
  }
  updateSummary();
  btn.disabled=false; btn.textContent='⚡ Convert tat ca';
}

// ── Summary ────────────────────────────────────────────────────────────────
function updateSummary(){
  const ok  = [...fileMap.values()].filter(v=>v.status==='done').length;
  const err = [...fileMap.values()].filter(v=>v.status==='error').length;
  const el  = document.getElementById('summary');
  if(!ok&&!err){ el.style.display='none'; return; }
  el.style.display='flex';
  document.getElementById('summaryText').innerHTML=
    `<strong style="color:#e2e8f0">${ok}</strong> file thanh cong`+
    (err?`, <strong style="color:#ef4444">${err}</strong> loi`:'');
  document.getElementById('downloadAllBtn').style.display=ok>1?'':'none';
}

// ── Download ───────────────────────────────────────────────────────────────
function downloadOne(name){
  const i=fileMap.get(name);
  if(!i||i.status!=='done') return;
  Object.assign(document.createElement('a'),{
    href:`/download/${i.resultId}/${encodeURIComponent(i.outputName)}`,
    download:i.outputName
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
    showSkel(true); showSkelM(true);
    const c=await getContent(info.resultId);
    showSkelM(false); renderContent(c,true);
  } else {
    document.getElementById('previewPanel').style.display='block';
    document.getElementById('mainLayout').className='two-col';
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
  return '> Khong the tai noi dung.';
}

function renderContent(txt,mobile){
  const html=marked.parse(txt||'');
  if(mobile){
    document.getElementById('mRendered').innerHTML=html;
    document.getElementById('mRaw').value=txt||'';
    document.getElementById('mRendered').querySelectorAll('pre code').forEach(el=>hljs.highlightElement(el));
  } else {
    document.getElementById('pRendered').innerHTML=html;
    document.getElementById('pRaw').value=txt||'';
    document.getElementById('pRendered').querySelectorAll('pre code').forEach(el=>hljs.highlightElement(el));
  }
  applyTab();
}

function showSkel(on){
  document.getElementById('skelWrap').style.display   =on?'block':'none';
  document.getElementById('pRendered').style.display  =on?'none':'block';
  document.getElementById('pRaw').style.display       ='none';
}
function showSkelM(on){
  if(on){
    document.getElementById('mRendered').innerHTML=
      '<div class="space-y-3">'+
      '<div class="shimmer-skel h-6 rounded" style="width:60%"></div>'+
      '<div class="shimmer-skel h-4 rounded w-full"></div>'+
      '<div class="shimmer-skel h-4 rounded" style="width:80%"></div>'+
      '<div class="shimmer-skel h-20 rounded w-full mt-3"></div>'+
      '</div>';
  }
}

function closePreview(){
  curPreview=null;
  document.getElementById('previewPanel').style.display='none';
  document.getElementById('mainLayout').className='one-col';
  document.getElementById('mobileModal').style.display='none';
  render();
}

function switchTab(tab){
  curTab=tab; applyTab();
}
function applyTab(){
  const on ='tab-on text-sm px-4 py-2.5 font-medium transition-all mr-1';
  const off='tab-off text-sm px-4 py-2.5 font-medium transition-all';
  const onNoMr='tab-on text-sm px-4 py-2.5 font-medium transition-all';
  const isR=curTab==='rendered';

  // desktop
  const pR=document.getElementById('pRendered');
  const pRaw=document.getElementById('pRaw');
  if(pR) pR.style.display=isR?'block':'none';
  if(pRaw) pRaw.style.display=isR?'none':'block';
  const tR=document.getElementById('tabR');
  const tRaw=document.getElementById('tabRaw');
  if(tR) tR.className=isR?on:off.replace('mr-1','');
  if(tRaw) tRaw.className=isR?off.replace('mr-1',''):onNoMr;

  // mobile
  const mR=document.getElementById('mRendered');
  const mRaw=document.getElementById('mRaw');
  if(mR) mR.style.display=isR?'block':'none';
  if(mRaw) mRaw.style.display=isR?'none':'block';
  const mtR=document.getElementById('mTabR');
  const mtRaw=document.getElementById('mTabRaw');
  if(mtR) mtR.className=isR?on:off.replace('mr-1','');
  if(mtRaw) mtRaw.className=isR?off.replace('mr-1',''):onNoMr;
}

async function copyContent(){
  const txt=document.getElementById('pRaw').value||document.getElementById('mRaw').value;
  if(!txt) return;
  await navigator.clipboard.writeText(txt);
  const btn=document.getElementById('copyBtn');
  const old=btn.innerHTML; btn.innerHTML='&#10003; Da copy!';
  setTimeout(()=>btn.innerHTML=old,1800);
}

// ── Drag & drop ────────────────────────────────────────────────────────────
const dz=document.getElementById('dropzone');
dz.addEventListener('dragover', e=>{ e.preventDefault(); dz.classList.add('dz-active'); });
dz.addEventListener('dragleave',  ()=>dz.classList.remove('dz-active'));
dz.addEventListener('drop', e=>{
  e.preventDefault(); dz.classList.remove('dz-active');
  addFiles(e.dataTransfer.files);
});
document.getElementById('fileInput').addEventListener('change',e=>{
  addFiles(e.target.files); e.target.value='';
});

marked.setOptions({breaks:true,gfm:true});
</script>
</body>
</html>"""

md_converter  = MarkItDown()
results_store = {}


@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/convert", methods=["POST"])
def convert():
    file    = request.files.get("file")
    fmt     = request.form.get("format", "md")
    session = request.form.get("session", "default")

    if not file:
        return jsonify({"ok": False, "error": "No file"})

    file_ext = Path(file.filename).suffix.lower().lstrip(".")
    if file_ext not in SUPPORTED_EXTENSIONS:
        return jsonify({"ok": False, "error": f"Dinh dang .{file_ext} chua ho tro"})

    tmp_path = UPLOAD_FOLDER / f"{uuid.uuid4()}{Path(file.filename).suffix}"
    try:
        file.save(str(tmp_path))
        result        = md_converter.convert(str(tmp_path))
        content_bytes = result.text_content.encode("utf-8")
        output_name   = f"{Path(file.filename).stem}.{fmt}"
        result_id     = str(uuid.uuid4())
        results_store[result_id] = (content_bytes, output_name, session)
        return jsonify({"ok": True, "result_id": result_id, "output_name": output_name})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:120]})
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.route("/preview/<result_id>")
def preview(result_id):
    if result_id not in results_store:
        return jsonify({"ok": False, "error": "Not found"}), 404
    content_bytes, output_name, _ = results_store[result_id]
    return jsonify({"ok": True, "content": content_bytes.decode("utf-8"), "output_name": output_name})


@app.route("/download/<result_id>/<filename>")
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
