"""
Simple Web UI for Whisper Local

Minimal Flask app that provides:
- Upload audio file
- Record from microphone  
- View results
- Real-time progress tracking

Access: http://localhost:8080 by default. Set WHISPER_LOCAL_HOST=0.0.0.0
only when you intentionally want LAN access.
"""
import os
import json
import secrets
import shutil
import subprocess
import threading
import tempfile
import time

from whisper_local.paths import load_env_file


load_env_file()

from flask import Flask, render_template_string, request, jsonify, Response
from werkzeug.utils import secure_filename

from whisper_local.core.progress import cancel as cancel_progress
from whisper_local.core.progress import clear_cancel, complete, get as get_progress, is_cancelled, reset_progress, start

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('WHISPER_LOCAL_MAX_UPLOAD_MB', '250')) * 1024 * 1024

ALLOWED_AUDIO_EXTENSIONS = {'.aac', '.aif', '.aiff', '.flac', '.m4a', '.mp3', '.ogg', '.wav'}
MAX_AUDIO_DURATION_SECONDS = int(os.environ.get('WHISPER_LOCAL_MAX_AUDIO_DURATION_SECONDS', str(2 * 60 * 60)))
LAN_HOSTS = {'0.0.0.0', '::'}

stop_flag = False

# Single-operation lock — prevents concurrent processing
_processing_busy = threading.Lock()


def _safe_audio_upload_name(filename: str) -> tuple[str, str]:
    """Validate and sanitize an uploaded audio filename.

    Returns `(safe_filename, extension)` for use in cache display names and temp
    file suffixes.
    """

    safe_name = secure_filename(filename or "")
    if not safe_name or safe_name in {'.', '..'}:
        raise ValueError('Invalid audio filename')

    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))
        raise ValueError(f'Unsupported audio type. Allowed extensions: {allowed}')

    return safe_name, ext


def _validate_audio_content(path: str, ext: str) -> None:
    """Reject files that do not look like supported audio before processing."""

    if not shutil.which('ffprobe'):
        raise ValueError('ffprobe is required to validate uploaded audio. Install ffmpeg first.')

    result = subprocess.run(
        [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'a',
            '-show_entries', 'stream=codec_type,codec_name:format=duration',
            '-of', 'json',
            path,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise ValueError('Uploaded file could not be probed as audio')

    try:
        media_info = json.loads(result.stdout or '{}')
        audio_streams = [s for s in media_info.get('streams', []) if s.get('codec_type') == 'audio']
        duration = float(media_info.get('format', {}).get('duration', 0))
        if audio_streams and 0 < duration <= MAX_AUDIO_DURATION_SECONDS:
            return
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        raise ValueError('Uploaded file probe data was invalid') from e

    raise ValueError('Uploaded file must contain an audio stream within the configured duration limit')


def _lan_mode_enabled() -> bool:
    return app.config.get('WHISPER_LOCAL_HOST', os.environ.get('WHISPER_LOCAL_HOST', '127.0.0.1')) in LAN_HOSTS


def _auth_token() -> str:
    return os.environ.get('WHISPER_LOCAL_AUTH_TOKEN', '')


@app.before_request
def require_lan_auth():
    """Require a bearer-like local token when the app is intentionally LAN-bound."""

    if not _lan_mode_enabled():
        return None

    expected_token = _auth_token()
    if request.path in {'/', '/ip'}:
        return None

    provided_token = request.headers.get('X-Whisper-Auth')
    if expected_token and provided_token == expected_token:
        return None

    return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

def _start_processing() -> bool:
    """Try to acquire the processing lock. Returns True if acquired."""
    return _processing_busy.acquire(blocking=False)

def _end_processing():
    """Release the processing lock."""
    try:
        _processing_busy.release()
    except (RuntimeError, ValueError):
        pass

# Manual recording state
_is_recording = False
_recording_stop_flag = False
_recording_start_time = 0.0

def get_local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# Web templates - Clean progress tracking
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Whisper Local - Meeting Analyzer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#0d1117">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-page: #0d1117;
            --bg-panel: #161b22;
            --bg-card: #21262d;
            --text-primary: #e6edf3;
            --text-muted: #8b949e;
            --border: #30363d;
            --accent-blue: #0096FF;
            --danger: #f85149;
            --success: #3fb950;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html { background-color: #0d1117 !important; }
        body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #0d1117;
            background: linear-gradient(135deg, #0d1117 0%, #050608 100%) fixed;
            min-height: 100vh;
            color: var(--text-primary);
            line-height: 1.6;
        }
        
        button { cursor: pointer; border: none; border-radius: 6px; font-weight: 500; font-size: 14px; padding: 8px 16px; transition: opacity 0.2s ease; font-family: inherit; }
        button:hover:not(:disabled) { opacity: 0.85; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background-color: var(--accent-blue); color: #ffffff; }
        .btn-secondary { background-color: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); }
        .btn-success { background-color: var(--success); color: #ffffff; }
        .btn-danger { background-color: var(--danger); color: #ffffff; }

        .app-container { display: flex; flex-direction: column; min-height: 100vh; }
        header { padding: 16px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background-color: var(--bg-panel); }
        .banner { font-size: 20px; font-weight: 600; color: var(--text-primary); margin: 0; }
        .banner span { color: var(--accent-blue); }
        
        .app-main { display: flex; flex-direction: column; gap: 24px; padding: 24px; max-width: 1200px; margin: 0 auto; width: 100%; flex: 1; }
        @media (min-width: 768px) {
            .app-main { flex-direction: row; }
            .panel-left, .panel-right { flex: 1; min-width: 0; }
        }
        
        .panel { background-color: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; padding: 20px; display: flex; flex-direction: column; }
        .card { background-color: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; padding: 16px; position: relative; }
        
        .file-input-wrapper { margin-top: 16px; margin-bottom: 16px; }
        .file-label {
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            padding: 40px; border: 1px dashed var(--border); border-radius: 6px; cursor: pointer;
            transition: all 0.3s; background-color: var(--bg-page); color: var(--text-muted);
        }
        .file-label:hover { border-color: var(--accent-blue); }
        .file-selected { padding: 12px; background: rgba(0,150,255,0.1); border-radius: 6px; margin-top: 12px; text-align: center; color: var(--accent-blue); display: none; }
        
        .processing { text-align: center; padding: 20px; }
        .spinner { border: 3px solid rgba(255, 255, 255, 0.1); width: 32px; height: 32px; border-radius: 50%; border-left-color: var(--accent-blue); animation: spin 1s linear infinite; margin: 0 auto 16px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        .progress-container { margin: 24px 0; }
        .progress-header { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }
        .progress-bar { width: 100%; height: 8px; background: var(--bg-page); border-radius: 4px; overflow: hidden; border: 1px solid var(--border); }
        .progress-fill { height: 100%; background-color: var(--accent-blue); width: 0%; transition: width 0.3s ease; }
        
        .timeline { background: var(--bg-page); border-radius: 6px; padding: 16px; margin-top: 20px; text-align: left; font-size: 13px; border: 1px solid var(--border); max-height: 150px; overflow-y: auto; }
        .timeline-title { opacity: 0.6; margin-bottom: 12px; text-transform: uppercase; font-size: 11px; }
        .timeline-item { display: flex; margin-bottom: 8px; }
        .timeline-item:last-child { margin-bottom: 0; }
        .timeline-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); margin-right: 12px; margin-top: 5px; }
        .timeline-item.done .timeline-dot { background: var(--success); }
        .timeline-item.current .timeline-dot { background: var(--accent-blue); }
        
        .result-content { background: var(--bg-page); border: 1px solid var(--border); border-radius: 6px; padding: 16px; white-space: pre-wrap; max-height: 250px; overflow-y: auto; font-size: 14px; margin-bottom: 16px; color: var(--text-primary); }
        
        .note { font-size: 12px; color: var(--text-muted); margin-top: 12px; }
        input[type="number"] { width: 80px; padding: 8px; background: var(--bg-page); border: 1px solid var(--border); color: var(--text-primary); border-radius: 4px; }
        input[type="file"] { display: none; }
        
        .footer { text-align: center; padding: 20px; color: var(--text-muted); font-size: 12px; border-top: 1px solid var(--border); margin-top: auto; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-page); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
    </style>
</head>
<body>
    <div class="app-container">
        <header>
            <h1 class="banner"><span>NuecAI</span> Whisper Local</h1>
            <div></div>
        </header>
        
        <main class="app-main">
            <div class="panel-left" style="display: flex; flex-direction: column; gap: 24px;">
                <!-- ===== PANEL 1: Upload Audio ===== -->
                <div class="panel" id="upload-panel">
                    <h2 style="margin: 0 0 16px 0; font-size: 18px;">Upload Audio</h2>

                    <div class="file-input-wrapper">
                        <label for="audioFile" class="file-label" id="fileLabel">
                            <span style="margin-bottom: 8px;">Upload an audio file</span>
                            <span class="btn-secondary" style="padding: 6px 12px; border-radius: 4px; font-size: 12px;">Choose File</span>
                            <span style="font-size: 11px; opacity: 0.5; margin-top: 8px;">(WAV, MP3, M4A, AAC)</span>
                        </label>
                        <input type="file" id="audioFile" accept=".wav,.mp3,.m4a,.aac,.ogg">
                        <div class="file-selected" id="fileSelected"></div>
                    </div>

                    <div style="margin: 12px 0; padding: 12px; background: var(--bg-page); border-radius: 6px; border: 1px solid var(--border);">
                        <label style="font-size: 13px; color: var(--text-muted); display: block; margin-bottom: 8px;">Mode:</label>
                        <div style="display: flex; gap: 12px;">
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                                <input type="radio" name="uploadMode" value="full" checked>
                                Transcribe + Summarize
                            </label>
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                                <input type="radio" name="uploadMode" value="transcribe_only">
                                Transcribe Only
                            </label>
                        </div>
                    </div>

                    <div style="margin: 12px 0; padding: 12px; background: var(--bg-page); border-radius: 6px; border: 1px solid var(--border);">
                        <label style="font-size: 13px; color: var(--text-muted); display: block; margin-bottom: 8px;">Transcript Format:</label>
                        <div style="display: flex; gap: 12px;">
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                                <input type="radio" name="transcriptFormat" value="raw" checked>
                                Raw (Plain Text)
                            </label>
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                                <input type="radio" name="transcriptFormat" value="formatted">
                                Formatted (Speaker Labels)
                            </label>
                        </div>
                    </div>

                    <button class="btn-primary" style="width: 100%;" id="uploadBtn" disabled>Upload and Process</button>
                </div>

                <!-- ===== PANEL 2: Record Audio ===== -->
                <div class="panel" id="record-panel">
                    <h2 style="margin: 0 0 16px 0; font-size: 18px;">Record Audio</h2>

                    <div style="margin: 12px 0; padding: 12px; background: var(--bg-page); border-radius: 6px; border: 1px solid var(--border);">
                        <label style="font-size: 13px; color: var(--text-muted); display: block; margin-bottom: 8px;">Mode:</label>
                        <div style="display: flex; gap: 12px;">
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                                <input type="radio" name="recordMode" value="full" checked>
                                Transcribe + Summarize
                            </label>
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                                <input type="radio" name="recordMode" value="transcribe_only">
                                Transcribe Only
                            </label>
                        </div>
                    </div>

                    <div style="margin: 12px 0; padding: 12px; background: var(--bg-page); border-radius: 6px; border: 1px solid var(--border);">
                        <label style="font-size: 13px; color: var(--text-muted); display: block; margin-bottom: 8px;">Transcript Format:</label>
                        <div style="display: flex; gap: 12px;">
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                                <input type="radio" name="recordFormat" value="raw" checked>
                                Raw (Plain Text)
                            </label>
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                                <input type="radio" name="recordFormat" value="formatted">
                                Formatted (Speaker Labels)
                            </label>
                        </div>
                    </div>

                    <button class="btn-danger" style="width: 100%;" id="recordBtn">Start Recording</button>
                    <p class="note">Click "Start Recording" to begin. Click "Stop Recording" to end.</p>
                </div>

                <!-- ===== PANEL 3: Analyze Transcript ===== -->
                <div class="panel" id="text-panel">
                    <h2 style="margin: 0 0 16px 0; font-size: 18px;">Analyze Transcript</h2>

                    <div class="file-input-wrapper" style="margin-bottom: 12px;">
                        <label for="textFile" class="file-label" id="textFileLabel" style="padding: 20px;">
                            <span style="margin-bottom: 6px; font-size: 13px;">Upload a .txt file</span>
                            <span class="btn-secondary" style="padding: 4px 10px; border-radius: 4px; font-size: 11px;">Choose File</span>
                        </label>
                        <input type="file" id="textFile" accept=".txt">
                        <div class="file-selected" id="textFileSelected" style="display:none; font-size: 12px;"></div>
                    </div>

                    <div style="margin-bottom: 12px;">
                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Paste transcript text:</label>
                        <textarea id="textInput" style="width: 100%; min-height: 80px; max-height: 200px; padding: 8px; background: var(--bg-page); border: 1px solid var(--border); color: var(--text-primary); border-radius: 4px; font-family: inherit; font-size: 13px; resize: vertical; box-sizing: border-box;" placeholder="Paste your transcript here..."></textarea>
                    </div>

                    <button class="btn-primary" style="width: 100%;" id="analyzeTextBtn">Analyze Text</button>
                </div>

                <div class="panel" id="processing-card" style="display:none;">
                    <div class="processing">
                        <div class="spinner" id="processing-spinner"></div>
                        <div style="color: var(--accent-blue); font-weight: 500;" id="phase-name">Processing...</div>
                        
                        <div class="progress-container">
                            <div class="progress-header">
                                <span>Progress</span>
                                <span id="progress-percent">0%</span>
                            </div>
                            <div class="progress-bar">
                                <div class="progress-fill" id="progress-fill"></div>
                            </div>
                        </div>
                        
                        <button class="btn-danger" style="width: 100%; margin: 16px 0;" id="stopBtn">■ Stop</button>
                        
                        <div class="timeline" id="timeline">
                            <div class="timeline-title">Status</div>
                        </div>
                    </div>
                </div>

                <div class="panel" id="error-card" style="display:none; border-color: var(--danger);">
                    <h3 style="color: var(--danger); margin-bottom: 12px;">Error</h3>
                    <p id="error-msg" style="color: var(--text-muted); margin-bottom: 16px; font-size: 14px;"></p>
                    <button class="btn-secondary" onclick="location.reload()">Try Again</button>
                </div>
            </div>
            
            <div class="panel-right" style="display: flex; flex-direction: column;">
                <div class="panel" style="flex: 1;">
                    <h2 style="margin: 0 0 16px 0; font-size: 18px;">Analysis Results</h2>
                    
                    <div id="no-result" style="flex: 1; display:flex; align-items:center; justify-content:center; color: var(--text-muted); text-align:center; min-height: 200px;">
                        No audio processed yet. Upload or record to see results.
                    </div>
                    
                    <div id="result-card" style="display:none;">
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <h4 style="margin: 0; font-size: 14px; color: var(--text-muted);">Summary</h4>
                                <div style="display: flex; gap: 8px;">
                                    <button class="btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="downloadPDF()">PDF</button>
                                    <button class="btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="downloadFile('summary')">Download</button>
                                </div>
                            </div>
                            <div id="summary-content" class="result-content"></div>
                        </div>
                        
                        <div style="margin-top: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <h4 style="margin: 0; font-size: 14px; color: var(--text-muted);">Transcript</h4>
                                <button class="btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="downloadFile('transcript')">Download</button>
                            </div>
                            <div id="transcript-content" class="result-content"></div>
                        </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>
        
        <div class="footer">
            <div>100% Local - Your data never leaves this device</div>
            <div id="server-ip" style="margin-top: 4px;"></div>
        </div>
    </div>

    <script>
        var currentSummary = '';
        var currentTranscript = '';
        var pollInterval = null;

        var authToken = window.localStorage.getItem('whisperLocalAuthToken') || '';

        function authFetch(url, options) {
            options = options || {};
            options.headers = options.headers || {};
            if(authToken) {
                options.headers['X-Whisper-Auth'] = authToken;
            }
            return fetch(url, options);
        }
        
        authFetch('/ip').then(r=>r.json()).then(d=>{
            if(d.lan_enabled && !authToken) {
                authToken = window.prompt('Enter WHISPER_LOCAL_AUTH_TOKEN for LAN mode:') || '';
                if(authToken) {
                    window.localStorage.setItem('whisperLocalAuthToken', authToken);
                }
            }
            if(d.lan_enabled && d.ip && d.ip !== '127.0.0.1'){
                document.getElementById('server-ip').textContent = 'Access from other devices: http://' + d.ip + ':8080';
            }
        });

        // ===== File Upload =====
        document.getElementById('audioFile').onchange = function() {
            var file = this.files[0];
            var selected = document.getElementById('fileSelected');
            var label = document.getElementById('fileLabel');
            var btn = document.getElementById('uploadBtn');
            
            if(file) {
                selected.style.display = 'block';
                selected.textContent = 'Selected: ' + file.name + ' (' + (file.size/1024/1024).toFixed(1) + ' MB)';
                label.style.display = 'none';
                btn.disabled = false;
            }
        };
        
        document.getElementById('uploadBtn').onclick = function() {
            var file = document.getElementById('audioFile').files[0];
            if(!file) return;

            showProcessing();

            var format = document.querySelector('input[name="transcriptFormat"]:checked').value;
            var mode = document.querySelector('input[name="uploadMode"]:checked').value;

            var formData = new FormData();
            formData.append('audio', file);
            formData.append('format', format);
            formData.append('mode', mode);

            authFetch('/upload', { method: 'POST', body: formData }).then(r=>r.json()).then(handleResponse);
        };

        // ===== Recording (Manual Start/Stop) =====
        document.getElementById('recordBtn').onclick = function() {
            var format = document.querySelector('input[name="recordFormat"]:checked').value;
            var mode = document.querySelector('input[name="recordMode"]:checked').value;

            showRecording();

            authFetch('/record', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({format: format, mode: mode})
            }).then(r=>r.json()).then(handleRecordResponse);
        };

        // ===== Stop / Cancel Button (works for all operations) =====
        document.getElementById('stopBtn').onclick = function() {
            var btn = document.getElementById('stopBtn');
            var phaseEl = document.getElementById('phase-name');
            var progressEl = document.getElementById('progress-percent');
            btn.disabled = true;
            btn.innerText = '■ Stopping...';
            phaseEl.innerText = 'Stopping...';
            progressEl.innerText = '--';
            // Send both stop signals — /stop kills all subprocesses
            authFetch('/stop', { method: 'POST' });
            authFetch('/stop-recording', { method: 'POST' });
            // Force-reset the UI after 3 seconds if server doesn't respond
            setTimeout(function() {
                if (document.getElementById('processing-card').style.display !== 'none') {
                    authFetch('/status').then(function(r) { return r.json(); }).then(function(d) {
                        if (d.status === 'idle' || d.status === 'stopped' || !d.status) {
                            showInputPanels();
                            document.getElementById('processing-card').style.display = 'none';
                        }
                    });
                }
            }, 3000);
        };

        // ===== Text Analysis =====
        document.getElementById('textFile').onchange = function() {
            var file = this.files[0];
            var selected = document.getElementById('textFileSelected');
            var label = document.getElementById('textFileLabel');
            
            if(file) {
                selected.style.display = 'block';
                selected.textContent = 'Selected: ' + file.name + ' (' + (file.size/1024).toFixed(1) + ' KB)';
                label.style.display = 'none';
            }
        };

        document.getElementById('analyzeTextBtn').onclick = function() {
            var text = document.getElementById('textInput').value.trim();
            var textFile = document.getElementById('textFile').files[0];
            
            if(textFile) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    sendTextForAnalysis(e.target.result);
                };
                reader.readAsText(textFile);
            } else if(text) {
                sendTextForAnalysis(text);
            } else {
                alert('Please upload a .txt file or paste text.');
            }
        };

        function sendTextForAnalysis(text) {
            showProcessing();
            authFetch('/analyze-text', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: text})
            }).then(r=>r.json()).then(handleResponse);
        }

        // ===== Response Handlers =====
        function handleResponse(d) {
            if(d.status === 'started') { startPolling(); }
            else if(d.status === 'recording') { startPolling(); }
            else { alert(d.message || 'Error'); location.reload(); }
        }

        function handleRecordResponse(d) {
            if(d.status === 'recording') { startPolling(); }
            else { alert(d.message || 'Error'); location.reload(); }
        }

        function hideInputPanels() {
            document.getElementById('upload-panel').style.display = 'none';
            document.getElementById('record-panel').style.display = 'none';
            document.getElementById('text-panel').style.display = 'none';
        }

        function showInputPanels() {
            document.getElementById('upload-panel').style.display = 'flex';
            document.getElementById('record-panel').style.display = 'flex';
            document.getElementById('text-panel').style.display = 'flex';
        }

        // ===== UI State Functions =====
        function showProcessing() {
            hideInputPanels();
            document.getElementById('processing-card').style.display = 'flex';
            document.getElementById('error-card').style.display = 'none';
            document.getElementById('result-card').style.display = 'none';
            document.getElementById('no-result').style.display = 'flex';
            
            document.getElementById('stopBtn').style.display = 'block';
            document.getElementById('stopBtn').disabled = false;
            document.getElementById('stopBtn').innerText = '■ Stop';
            document.getElementById('progress-fill').style.width = '1%';
            document.getElementById('progress-percent').innerText = '1%';
            document.getElementById('phase-name').innerText = 'Starting...';
            renderTimelineMessage('Starting up...');
        }

        function showRecording() {
            hideInputPanels();
            document.getElementById('processing-card').style.display = 'flex';
            document.getElementById('error-card').style.display = 'none';
            document.getElementById('result-card').style.display = 'none';
            document.getElementById('no-result').style.display = 'flex';
            
            document.getElementById('stopBtn').style.display = 'block';
            document.getElementById('stopBtn').disabled = false;
            document.getElementById('stopBtn').innerText = '■ Stop Recording';
            document.getElementById('progress-fill').style.width = '5%';
            document.getElementById('progress-percent').innerText = 'Recording...';
            document.getElementById('phase-name').innerText = 'Recording...';
            renderTimelineMessage('Recording audio... Click Stop when done.');
        }

        function renderTimelineMessage(message) {
            var timeline = document.getElementById('timeline');
            timeline.textContent = '';

            var title = document.createElement('div');
            title.className = 'timeline-title';
            title.textContent = 'Status';
            timeline.appendChild(title);

            var item = document.createElement('div');
            item.className = 'timeline-item current';
            var dot = document.createElement('div');
            dot.className = 'timeline-dot';
            var text = document.createElement('div');
            text.textContent = message;
            item.appendChild(dot);
            item.appendChild(text);
            timeline.appendChild(item);
        }

        function startPolling() {
            if(pollInterval) {
                clearInterval(pollInterval);
            }
            pollInterval = setInterval(pollStatus, 1200);
        }
        
        function pollStatus() {
            authFetch('/status').then(r=>r.json()).then(d=>{
                if(d.status === 'idle') {
                    clearInterval(pollInterval);
                    showInputPanels();
                    document.getElementById('processing-card').style.display = 'none';
                } else if(d.status === 'recording') {
                    document.getElementById('progress-fill').style.width = '5%';
                    document.getElementById('progress-percent').innerText = Math.floor(d.elapsed) + 's';
                    document.getElementById('phase-name').innerText = 'Recording... (' + Math.floor(d.elapsed) + 's)';
                } else if(d.status === 'processing') {
                    updateProgress(d);
                } else if(d.status === 'done') {
                    clearInterval(pollInterval);
                    document.getElementById('processing-card').style.display = 'none';
                    showResult(d.summary, d.transcript);
                } else if(d.status === 'error') {
                    clearInterval(pollInterval);
                    showError(d.message);
                }
            });
        }
        
        function updateProgress(d) {
            var progress = d.progress || 0;
            var phase = d.phase_name || 'Processing';
            
            document.getElementById('progress-fill').style.width = progress + '%';
            document.getElementById('progress-percent').innerText = progress + '%';
            document.getElementById('phase-name').innerText = phase;
            
            if(d.steps && d.steps.length > 0) {
                var timeline = document.getElementById('timeline');
                timeline.textContent = '';

                var title = document.createElement('div');
                title.className = 'timeline-title';
                title.textContent = 'Status';
                timeline.appendChild(title);
                
                d.steps.forEach(function(step, idx) {
                    var isLast = idx === d.steps.length - 1;
                    var statusClass = isLast ? 'current' : (progress >= step.p ? 'done' : '');
                    var item = document.createElement('div');
                    item.className = 'timeline-item ' + statusClass;

                    var dot = document.createElement('div');
                    dot.className = 'timeline-dot';

                    var body = document.createElement('div');
                    body.style.flex = '1';

                    var time = document.createElement('div');
                    time.style.fontSize = '11px';
                    time.style.opacity = '0.5';
                    time.textContent = step.t || '';

                    var message = document.createElement('div');
                    message.textContent = step.m || '';

                    body.appendChild(time);
                    body.appendChild(message);
                    item.appendChild(dot);
                    item.appendChild(body);
                    timeline.appendChild(item);
                });
                timeline.scrollTop = timeline.scrollHeight;
            }
        }
        
        function showResult(summary, transcript) {
            currentSummary = summary;
            currentTranscript = transcript;
            
            document.getElementById('no-result').style.display = 'none';
            document.getElementById('result-card').style.display = 'block';
            
            document.getElementById('summary-content').innerText = summary || 'No summary available (transcribe-only mode)';
            document.getElementById('transcript-content').innerText = transcript || 'No transcript available';

            // Reset input panels for next operation
            showInputPanels();
            document.getElementById('audioFile').value = '';
            document.getElementById('fileSelected').style.display = 'none';
            document.getElementById('fileLabel').style.display = 'flex';
            document.getElementById('uploadBtn').disabled = true;
        }
        
        function showError(msg) {
            document.getElementById('processing-card').style.display = 'none';
            document.getElementById('error-card').style.display = 'flex';
            document.getElementById('error-msg').innerText = msg;
        }
        
        function downloadFile(type) {
            var content = type === 'summary' ? currentSummary : currentTranscript;
            var extension = type === 'summary' ? '.md' : '.txt';
            var blob = new Blob([content], {type: 'text/plain'});
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = type + '_' + Date.now() + extension;
            a.click();
            URL.revokeObjectURL(url);
        }
        
        function downloadPDF() {
            if (!currentSummary) {
                alert('No summary available');
                return;
            }
            authFetch('/pdf', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content: currentSummary})
            }).then(r => {
                if (!r.ok) throw new Error('PDF generation failed');
                return r.blob();
            }).then(blob => {
                var url = URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = url;
                a.download = 'summary_' + Date.now() + '.pdf';
                a.click();
                URL.revokeObjectURL(url);
            }).catch(err => {
                alert('Error generating PDF: ' + err.message);
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    reset_progress()  # Reset on page load
    return render_template_string(HTML_TEMPLATE)

@app.route('/ip')
def get_ip():
    return jsonify({'ip': get_local_ip(), 'lan_enabled': _lan_mode_enabled()})

@app.route('/status')
def status():
    global stop_flag, _last_result, _last_error, _is_recording, _recording_start_time
    
    # Check for cancel first
    if is_cancelled():
        stop_flag = False
        reset_progress()
        _last_result = {'summary': '', 'transcript': ''}
        _last_error = None
        return jsonify({'status': 'idle'})
    
    if stop_flag:
        stop_flag = False
        reset_progress()
        _last_result = {'summary': '', 'transcript': ''}
        _last_error = None
        return jsonify({'status': 'idle'})
    
    # Check recording state first
    if _is_recording:
        elapsed = time.time() - _recording_start_time
        return jsonify({
            'status': 'recording',
            'elapsed': round(elapsed, 1),
            'progress': 5,
            'phase_name': 'Recording...'
        })
    
    # Check for error first
    if _last_error:
        error = _last_error
        _last_error = None
        return jsonify({'status': 'error', 'message': error})
    
    # Check for completed result
    if _last_result.get('summary') or _last_result.get('transcript'):
        result = _last_result.copy()
        _last_result = {'summary': '', 'transcript': ''}
        reset_progress()
        return jsonify({
            'status': 'done',
            'summary': result.get('summary', ''),
            'transcript': result.get('transcript', ''),
            'progress': 100,
            'message': 'Complete!'
        })
    
    # Get progress from the progress module
    prog = get_progress()
    
    if prog['active']:
        return jsonify({
            'status': 'processing',
            'progress': prog['progress'],
            'message': prog['message'],
            'phase_name': prog['phase_name'],
            'current_chunk': prog['current_chunk'],
            'total_chunks': prog['total_chunks'],
            'steps': prog['steps']
        })
    
    return jsonify({'status': 'idle'})

@app.route('/stop', methods=['POST'])
def stop():
    """Forcefully stop ALL operations — kills subprocesses, cancels everything."""
    global stop_flag, _is_recording, _recording_stop_flag
    stop_flag = True
    _recording_stop_flag = True
    _is_recording = False
    # Cancel progress + kill all tracked subprocesses
    cancel_progress()
    reset_progress()
    _end_processing()
    return jsonify({'status': 'stopped'})

@app.route('/upload', methods=['POST'])
def upload():
    global stop_flag
    
    if not _start_processing():
        return jsonify({'status': 'error', 'message': 'Already processing an operation. Please wait for it to complete.'})

    stop_flag = False
    clear_cancel()

    try:
        if 'audio' not in request.files:
            _end_processing()
            return jsonify({'status': 'error', 'message': 'No file uploaded'})

        audio = request.files['audio']
        if not audio or audio.filename == '':
            _end_processing()
            return jsonify({'status': 'error', 'message': 'No file selected'})

        try:
            original_filename, ext = _safe_audio_upload_name(audio.filename)
        except ValueError as e:
            _end_processing()
            return jsonify({'status': 'error', 'message': str(e)}), 400

        # Get options
        transcript_format = request.form.get('format', 'raw')
        mode = request.form.get('mode', 'full')

        # Save temp file
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_audio:
            temp_path = temp_audio.name
        audio.save(temp_path)

        try:
            _validate_audio_content(temp_path, ext)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            _end_processing()
            return jsonify({'status': 'error', 'message': str(e)}), 400

        # Start progress tracking
        start(1, 'upload')

        def process():
            from whisper_local.processing.pipeline import run_pipeline
            global stop_flag

            try:
                if stop_flag:
                    return
                result = run_pipeline(temp_path, transcript_format=transcript_format, original_filename=original_filename, mode=mode)

                if not stop_flag:
                    summary = result.get('summary', '') if mode != 'transcribe_only' else ''
                    transcript = result.get('transcript', 'No transcript')

                    global _last_result
                    _last_result = {'summary': summary, 'transcript': transcript}
            except Exception as e:
                global _last_error
                _last_error = str(e)
            finally:
                _end_processing()
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                except:
                    pass
        
        threading.Thread(target=process).start()
        return jsonify({'status': 'started'})
        
    except Exception as e:
        _end_processing()
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/record', methods=['POST'])
def record():
    global stop_flag, _is_recording, _recording_stop_flag, _recording_start_time
    
    if not _start_processing():
        return jsonify({'status': 'error', 'message': 'Already processing an operation. Please wait for it to complete.'})

    stop_flag = False
    _recording_stop_flag = False
    clear_cancel()

    try:
        transcript_format = request.json.get('format', 'raw')
        mode = request.json.get('mode', 'full')
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
            temp_path = temp_audio.name

        def record_and_process():
            from whisper_local.audio.recorder import record_audio_manual
            from whisper_local.processing.pipeline import run_pipeline
            global stop_flag, _is_recording, _recording_stop_flag

            try:
                # Manual recording phase
                _is_recording = True
                record_audio_manual(temp_path, stop_check=lambda: _recording_stop_flag)
                _is_recording = False

                if stop_flag:
                    return

                result = run_pipeline(temp_path, transcript_format=transcript_format, 
                                      original_filename="recording.wav", mode=mode)

                if not stop_flag:
                    global _last_result
                    _last_result = {
                        'summary': result.get('summary', '') if mode != 'transcribe_only' else '',
                        'transcript': result.get('transcript', '')
                    }
            except Exception as e:
                global _last_error
                _last_error = str(e)
            finally:
                _end_processing()
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                except:
                    pass
        
        _recording_start_time = time.time()
        threading.Thread(target=record_and_process).start()
        return jsonify({'status': 'recording'})
        
    except Exception as e:
        _is_recording = False
        _end_processing()
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop-recording', methods=['POST'])
def stop_recording():
    """Stop the active recording."""
    global _recording_stop_flag, _is_recording
    
    if not _is_recording:
        return jsonify({'status': 'error', 'message': 'No active recording to stop.'})
    
    _recording_stop_flag = True
    return jsonify({'status': 'stopping', 'message': 'Recording stopping...'})


@app.route('/analyze-text', methods=['POST'])
def analyze_text():
    """Accept text content and run it through the LLM analysis pipeline."""
    if not _start_processing():
        return jsonify({'status': 'error', 'message': 'Already processing an operation. Please wait for it to complete.'})

    clear_cancel()
    
    try:
        text = ''

        # Check for file upload first
        if 'file' in request.files:
            uploaded_file = request.files['file']
            if uploaded_file and uploaded_file.filename:
                text = uploaded_file.read().decode('utf-8', errors='replace')
        elif request.is_json:
            data = request.get_json()
            text = data.get('text', '')
        elif request.form:
            text = request.form.get('text', '')

        if not text or not text.strip():
            _end_processing()
            return jsonify({'status': 'error', 'message': 'No text provided. Upload a .txt file or paste text.'})

        # Limit text size
        if len(text) > 500000:
            text = text[:500000]
            print("[Analyze-Text] Truncated input to 500K chars")

        start(1, 'text')

        def process():
            from whisper_local.processing.pipeline import process_text
            global stop_flag

            try:
                if stop_flag:
                    return
                result = process_text(text)

                if not stop_flag:
                    global _last_result
                    _last_result = {
                        'summary': result.get('summary', ''),
                        'transcript': result.get('transcript', '')
                    }
            except Exception as e:
                global _last_error
                _last_error = str(e)
            finally:
                _end_processing()

        threading.Thread(target=process).start()
        return jsonify({'status': 'started'})

    except Exception as e:
        _end_processing()
        return jsonify({'status': 'error', 'message': str(e)})


# Global to store last result (simple approach)
_last_result = {'summary': '', 'transcript': ''}
_last_error = None

@app.route('/result')
def get_result():
    """Get the last processing result"""
    global _last_result, _last_error
    
    if _last_error:
        return jsonify({'status': 'error', 'message': _last_error})
    
    return jsonify({'status': 'done', 'summary': _last_result.get('summary', ''), 'transcript': _last_result.get('transcript', '')})


@app.route('/pdf', methods=['POST'])
def generate_pdf():
    """Generate PDF from markdown content"""
    import tempfile
    from whisper_local.export.pdf import convert
    
    try:
        data = request.get_json()
        md_content = data.get('content', '')
        
        if not md_content:
            return jsonify({'error': 'No content provided'}), 400
        
        # Create a temp markdown file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write(md_content)
            md_path = f.name
        
        try:
            # Generate PDF
            pdf_path = md_path.replace('.md', '.pdf')
            convert(md_content, pdf_path)
            
            # Read PDF and return
            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()
            
            # Cleanup
            os.remove(md_path)
            os.remove(pdf_path)
            
            return Response(
                pdf_data,
                mimetype='application/pdf',
                headers={'Content-Disposition': 'attachment; filename=summary.pdf'}
            )
            
        except Exception as e:
            # Cleanup on error
            if os.path.exists(md_path):
                os.remove(md_path)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            raise
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def run_server(host=None, port=8080):
    host = host or os.environ.get('WHISPER_LOCAL_HOST', '127.0.0.1')
    app.config['WHISPER_LOCAL_HOST'] = host
    if host in LAN_HOSTS and not _auth_token():
        raise RuntimeError('LAN mode requires WHISPER_LOCAL_AUTH_TOKEN. Set a strong local token before binding to the network.')

    local_ip = get_local_ip()
    print(f"\n{'='*60}")
    print(f"Whisper Local Web UI")
    print(f"{'='*60}")
    print(f"Open in browser:")
    print(f"   http://localhost:{port}")
    if host in LAN_HOSTS:
        print(f"   http://{local_ip}:{port}")
        print("   Enter WHISPER_LOCAL_AUTH_TOKEN in the browser prompt.")
    else:
        print("   LAN access disabled by default. Set WHISPER_LOCAL_HOST=0.0.0.0 to opt in.")
    print(f"{'='*60}\n")
    
    app.run(host=host, port=port, debug=False, threaded=True)

if __name__ == '__main__':
    run_server()
