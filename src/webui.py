"""
Simple Web UI for Whisper Local

Minimal Flask app that provides:
- Upload audio file
- Record from microphone  
- View results
- Real-time progress tracking

Access: http://localhost:8080 (or your IP:8080)
"""
import os
import sys
import threading
import tempfile
import time
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify

# Fix path to allow local imports
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from progress import get as get_progress, start, complete, reset_progress

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whisper-local-secret'

stop_flag = False

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
        
        .timeline { background: var(--bg-page); border-radius: 6px; padding: 16px; margin-top: 20px; text-align: left; font-size: 13px; border: 1px solid var(--border); }
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
                <div class="panel" id="input-panel">
                    <h2 style="margin: 0 0 16px 0; font-size: 18px;">Input Audio</h2>
                    
                    <div id="upload-card">
                        <div class="file-input-wrapper">
                            <label for="audioFile" class="file-label" id="fileLabel">
                                <span style="margin-bottom: 8px;">Upload an audio file</span>
                                <span class="btn-secondary" style="padding: 6px 12px; border-radius: 4px; font-size: 12px;">Choose File</span>
                                <span style="font-size: 11px; opacity: 0.5; margin-top: 8px;">(WAV, MP3, M4A, AAC)</span>
                            </label>
                            <input type="file" id="audioFile" accept=".wav,.mp3,.m4a,.aac,.ogg">
                            <div class="file-selected" id="fileSelected"></div>
                        </div>
                        <button class="btn-primary" style="width: 100%; margin-bottom: 16px;" id="uploadBtn" disabled>Upload and Process</button>
                    </div>
                    
                    <div style="border-top: 1px solid var(--border); margin: 16px 0;"></div>
                    
                    <div id="record-card">
                        <p style="color: var(--text-muted); margin-bottom: 12px; font-size: 14px;">Or record directly from microphone</p>
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                            <label style="color: var(--text-muted); font-size: 14px;">Duration (sec):</label>
                            <input type="number" id="duration" value="60" min="5" max="600">
                        </div>
                        <button class="btn-danger" style="width: 100%;" id="recordBtn">Start Recording</button>
                        <p class="note">Note: Uses host computer's microphone</p>
                    </div>
                </div>

                <div class="panel" id="processing-card" style="display:none;">
                    <div class="processing">
                        <div class="spinner"></div>
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
                                <button class="btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="downloadFile('summary')">Download</button>
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
        
        fetch('/ip').then(r=>r.json()).then(d=>{
            if(d.ip && d.ip !== '127.0.0.1'){
                document.getElementById('server-ip').innerHTML = 'Access from other devices: http://' + d.ip + ':8080';
            }
        });
        
        document.getElementById('audioFile').onchange = function() {
            var file = this.files[0];
            var selected = document.getElementById('fileSelected');
            var label = document.getElementById('fileLabel');
            var btn = document.getElementById('uploadBtn');
            
            if(file) {
                selected.style.display = 'block';
                selected.innerHTML = 'Selected: ' + file.name + ' (' + (file.size/1024/1024).toFixed(1) + ' MB)';
                label.style.display = 'none';
                btn.disabled = false;
            }
        };
        
        document.getElementById('uploadBtn').onclick = function() {
            var file = document.getElementById('audioFile').files[0];
            if(!file) return;
            
            showProcessing();
            
            var formData = new FormData();
            formData.append('audio', file);
            
            fetch('/upload', { method: 'POST', body: formData }).then(r=>r.json()).then(handleResponse);
        };
        
        document.getElementById('recordBtn').onclick = function() {
            var duration = parseInt(document.getElementById('duration').value);
            if (duration < 5) { alert('Min duration is 5s'); return; }
            if (duration > 600) { alert('Max duration is 600s'); return; }
            showProcessing();
            
            fetch('/record', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({duration: duration})
            }).then(r=>r.json()).then(handleResponse);
        };
        
        function handleResponse(d) {
            if(d.status === 'started') { startPolling(); } 
            else { alert(d.message || 'Error'); location.reload(); }
        }
        
        function showProcessing() {
            document.getElementById('input-panel').style.display = 'none';
            document.getElementById('processing-card').style.display = 'flex';
            document.getElementById('error-card').style.display = 'none';
            document.getElementById('result-card').style.display = 'none';
            document.getElementById('no-result').style.display = 'flex';
            
            document.getElementById('progress-fill').style.width = '1%';
            document.getElementById('progress-percent').innerText = '1%';
            document.getElementById('phase-name').innerText = 'Starting...';
            document.getElementById('timeline').innerHTML = '<div class="timeline-title">Status</div>';
        }
        
        function startPolling() { pollInterval = setInterval(pollStatus, 1200); }
        
        function pollStatus() {
            fetch('/status').then(r=>r.json()).then(d=>{
                if(d.status === 'processing') { updateProgress(d); } 
                else if(d.status === 'done') {
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
                var html = '<div class="timeline-title">Status</div>';
                
                d.steps.forEach(function(step, idx) {
                    var isLast = idx === d.steps.length - 1;
                    var statusClass = isLast ? 'current' : (progress >= step.p ? 'done' : '');
                    html += '<div class="timeline-item ' + statusClass + '">';
                    html += '<div class="timeline-dot"></div>';
                    html += '<div style="flex:1;">';
                    html += '<div style="font-size:11px;opacity:0.5;">' + step.t + '</div>';
                    html += '<div>' + step.m + '</div>';
                    html += '</div></div>';
                });
                timeline.innerHTML = html;
            }
        }
        
        function showResult(summary, transcript) {
            currentSummary = summary;
            currentTranscript = transcript;
            
            document.getElementById('no-result').style.display = 'none';
            document.getElementById('result-card').style.display = 'block';
            
            document.getElementById('summary-content').innerText = summary || 'No summary available';
            document.getElementById('transcript-content').innerText = transcript || 'No transcript available';

            // Show input panel again for new upload
            document.getElementById('input-panel').style.display = 'block';
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
    return jsonify({'ip': get_local_ip()})

@app.route('/status')
def status():
    global stop_flag, _last_result, _last_error
    
    if stop_flag:
        stop_flag = False
        reset_progress()
        _last_result = {'summary': '', 'transcript': ''}
        _last_error = None
        return jsonify({'status': 'idle'})
    
    # Check for error first
    if _last_error:
        error = _last_error
        _last_error = None
        return jsonify({'status': 'error', 'message': error})
    
    # Check for completed result
    if _last_result.get('summary') or _last_result.get('transcript'):
        result = _last_result.copy()
        _last_result = {'summary': '', 'transcript': ''}
        # Reset progress after returning result
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
    global stop_flag
    stop_flag = True
    reset_progress()
    return jsonify({'status': 'stopped'})

@app.route('/upload', methods=['POST'])
def upload():
    global stop_flag
    stop_flag = False
    
    try:
        if 'audio' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file uploaded'})
        
        audio = request.files['audio']
        if not audio or audio.filename == '':
            return jsonify({'status': 'error', 'message': 'No file selected'})
        
        # Save temp file
        ext = '.' + audio.filename.split('.')[-1].lower()
        temp_path = tempfile.mktemp(suffix=ext)
        audio.save(temp_path)
        
        # Start progress tracking
        start(1, 'upload')
        
        def process():
            from pipeline import run_pipeline
            global stop_flag
            
            try:
                if stop_flag:
                    return
                result = run_pipeline(temp_path)
                
                if not stop_flag:
                    # Get the transcript/summary from result
                    summary = result.get('summary', 'No summary')
                    transcript = result.get('transcript', 'No transcript')
                    
                    # Store result in a global for retrieval (simplified)
                    global _last_result
                    _last_result = {'summary': summary, 'transcript': transcript}
            except Exception as e:
                global _last_error
                _last_error = str(e)
            finally:
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                except:
                    pass
        
        threading.Thread(target=process).start()
        return jsonify({'status': 'started'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/record', methods=['POST'])
def record():
    global stop_flag
    stop_flag = False
    
    try:
        duration = request.json.get('duration', 60)
        temp_path = tempfile.mktemp(suffix='.wav')
        
        # Start progress tracking
        start(1, 'record')
        
        def record_and_process():
            from recorder import record_audio
            from pipeline import run_pipeline
            global stop_flag
            
            try:
                if stop_flag:
                    return
                
                # Recording phase
                record_audio(temp_path, duration=duration)
                
                if stop_flag:
                    return
                
                result = run_pipeline(temp_path)
                
                if not stop_flag:
                    global _last_result
                    _last_result = {'summary': result.get('summary', ''), 'transcript': result.get('transcript', '')}
            except Exception as e:
                global _last_error
                _last_error = str(e)
            finally:
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                except:
                    pass
        
        threading.Thread(target=record_and_process).start()
        return jsonify({'status': 'started'})
        
    except Exception as e:
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

def run_server(host='0.0.0.0', port=8080):
    local_ip = get_local_ip()
    print(f"\n{'='*60}")
    print(f"Whisper Local Web UI")
    print(f"{'='*60}")
    print(f"Open in browser:")
    print(f"   http://localhost:{port}")
    print(f"   http://{local_ip}:{port}")
    print(f"{'='*60}\n")
    
    app.run(host=host, port=port, debug=False, threaded=True)

if __name__ == '__main__':
    run_server()