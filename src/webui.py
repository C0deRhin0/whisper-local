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

# Fix path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.progress import get as get_progress, start, complete, reset as reset_progress

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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html { background: #1a1a2e; }
        body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e2e8f0;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 640px; margin: 0 auto; }
        
        .header { text-align: center; padding: 30px 0 40px; }
        .header h1 {
            font-size: 2.5rem;
            font-weight: 600;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }
        .header p { opacity: 0.7; font-size: 0.95rem; }
        
        .card {
            background: rgba(255,255,255,0.08);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 28px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            transition: all 0.3s;
        }
        .card:hover { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(0,0,0,0.4); }
        .card h3 { font-size: 1.1rem; font-weight: 500; margin-bottom: 16px; color: #fff; }
        
        .file-input-wrapper { position: relative; margin: 16px 0; }
        .file-input { display: none; }
        .file-label {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px;
            border: 2px dashed rgba(255,255,255,0.25);
            border-radius: 14px;
            cursor: pointer;
            transition: all 0.3s;
            background: rgba(255,255,255,0.03);
        }
        .file-label:hover { border-color: #667eea; background: rgba(102,126,234,0.1); }
        .file-label svg { width: 48px; height: 48px; margin-bottom: 12px; opacity: 0.6; }
        .file-label span { opacity: 0.7; font-size: 0.9rem; }
        .file-selected {
            display: none;
            padding: 16px;
            background: rgba(102,126,234,0.15);
            border-radius: 10px;
            margin-top: 12px;
            text-align: center;
            font-size: 0.9rem;
            color: #667eea;
        }
        
        .btn {
            width: 100%;
            padding: 14px 24px;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s;
            font-family: inherit;
        }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover:not(:disabled) { transform: scale(1.02); box-shadow: 0 8px 24px rgba(102,126,234,0.4); }
        .btn-record {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }
        .btn-record:hover { transform: scale(1.02); box-shadow: 0 8px 24px rgba(245,87,108,0.4); }
        .btn-download {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: #e2e8f0;
            padding: 10px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
        }
        .btn-download:hover { background: rgba(255,255,255,0.2); }
        
        input[type="number"] {
            width: 100px;
            padding: 12px 16px;
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(255,255,255,0.08);
            color: #fff;
            font-size: 1rem;
        }
        input[type="number"]:focus { outline: none; border-color: #667eea; }
        
        .processing { text-align: center; }
        .spinner {
            width: 56px;
            height: 56px;
            border: 4px solid rgba(255,255,255,0.1);
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        
        /* Clean Progress Bar */
        .progress-container { margin: 24px 0; }
        .progress-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .progress-phase {
            font-size: 1.1rem;
            font-weight: 500;
            color: #fff;
        }
        .progress-percent {
            font-size: 1.5rem;
            font-weight: 600;
            color: #667eea;
        }
        .progress-bar {
            width: 100%;
            height: 12px;
            background: rgba(255,255,255,0.1);
            border-radius: 6px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 6px;
            transition: width 0.5s ease;
            width: 0%;
        }
        
        /* Steps Timeline */
        .timeline {
            background: #0d1117;
            border-radius: 12px;
            padding: 16px;
            margin-top: 20px;
            text-align: left;
            font-size: 0.85rem;
        }
        .timeline-title {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            opacity: 0.5;
            margin-bottom: 12px;
        }
        .timeline-item {
            display: flex;
            align-items: flex-start;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .timeline-item:last-child { border-bottom: none; }
        .timeline-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #667eea;
            margin-right: 12px;
            margin-top: 5px;
            flex-shrink: 0;
        }
        .timeline-item.done .timeline-dot { background: #10b981; }
        .timeline-item.current .timeline-dot { 
            background: #667eea;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(102,126,234,0.4); }
            50% { box-shadow: 0 0 0 8px rgba(102,126,234,0); }
        }
        .timeline-content { flex: 1; }
        .timeline-time { 
            font-size: 0.7rem; 
            opacity: 0.5; 
            margin-bottom: 4px; 
        }
        .timeline-text { color: #e2e8f0; }
        
        .result-section { margin-bottom: 20px; }
        .result-section h4 {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            opacity: 0.6;
            margin-bottom: 12px;
        }
        .result-content {
            background: rgba(0,0,0,0.3);
            border-radius: 12px;
            padding: 20px;
            white-space: pre-wrap;
            max-height: 300px;
            overflow-y: auto;
            font-size: 0.95rem;
            line-height: 1.7;
        }
        .download-bar { display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
        
        .footer { text-align: center; opacity: 0.5; font-size: 0.8rem; margin-top: 30px; padding-bottom: 20px; }
        
        .note {
            font-size: 0.75rem;
            opacity: 0.5;
            margin-top: 12px;
            padding: 10px;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
        }
        
        .fade-out { animation: fadeOut 0.5s forwards; }
        @keyframes fadeOut {
            from { opacity: 1; }
            to { opacity: 0; transform: translateY(-10px); }
        }
        
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Whisper Local</h1>
            <p>Meeting Audio Analyzer</p>
        </div>
        
        <!-- Processing State -->
        <div id="processing-card" class="card" style="display:none;">
            <div class="processing">
                <div class="spinner"></div>
                
                <div class="progress-container">
                    <div class="progress-header">
                        <span class="progress-phase" id="phase-name">Preparing...</span>
                        <span class="progress-percent" id="progress-percent">0%</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="progress-fill"></div>
                    </div>
                </div>
                
                <div class="timeline" id="timeline">
                    <div class="timeline-title">Progress</div>
                </div>
            </div>
        </div>
        
        <!-- Error State -->
        <div id="error-card" class="card" style="display:none;">
            <div style="text-align:center;padding:20px;">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#f85149" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <h3 style="color:#f85149;margin:16px 0;">Error</h3>
                <p id="error-msg" style="opacity:0.8;margin-bottom:20px;"></p>
                <button class="btn btn-primary" onclick="location.reload()">Try Again</button>
            </div>
        </div>
        
        <!-- Result State -->
        <div id="result-card" class="card" style="display:none;">
            <h3>Analysis Complete</h3>
            
            <div class="result-section">
                <h4>Summary</h4>
                <div id="summary-content" class="result-content"></div>
                <div class="download-bar">
                    <button class="btn-download" onclick="downloadFile('summary')">Download Summary</button>
                </div>
            </div>
            
            <div class="result-section">
                <h4>Transcript</h4>
                <div id="transcript-content" class="result-content"></div>
                <div class="download-bar">
                    <button class="btn-download" onclick="downloadFile('transcript')">Download Transcript</button>
                </div>
            </div>
            
            <button class="btn btn-primary" onclick="location.reload()">Analyze Another Meeting</button>
        </div>
        
        <!-- Upload Form -->
        <div id="upload-card" class="card">
            <h3>Upload Audio File</h3>
            <div class="file-input-wrapper">
                <input type="file" id="audioFile" class="file-input" accept=".wav,.mp3,.m4a,.aac,.ogg">
                <label for="audioFile" class="file-label" id="fileLabel">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <path d="M12 2a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                        <line x1="12" y1="19" x2="12" y2="23"/>
                        <line x1="8" y1="23" x2="16" y2="23"/>
                    </svg>
                    <span>Click to select audio file<br>(WAV, MP3, M4A, AAC)</span>
                </label>
                <div class="file-selected" id="fileSelected"></div>
            </div>
            <button class="btn btn-primary" id="uploadBtn" disabled>Upload and Process</button>
        </div>
        
        <!-- Recording Form -->
        <div id="record-card" class="card">
            <h3>Record Now</h3>
            <p style="opacity:0.6;margin-bottom:16px;">Record meeting directly</p>
            <div style="margin-bottom:16px;">
                <label style="display:block;margin-bottom:8px;opacity:0.7;">Duration (seconds):</label>
                <input type="number" id="duration" value="60" min="5" max="600">
            </div>
            <button class="btn btn-record" id="recordBtn">Start Recording</button>
            <p class="note">Note: Recording uses the host computer's microphone</p>
        </div>
        
        <div class="footer">
            100% Local - Your data never leaves this device<br>
            <span id="server-ip"></span>
        </div>
    </div>
    
    <script>
        var currentSummary = '';
        var currentTranscript = '';
        var pollInterval = null;
        var lastProgress = 0;
        
        // Show server IP
        fetch('/ip').then(r=>r.json()).then(d=>{
            if(d.ip && d.ip !== '127.0.0.1'){
                document.getElementById('server-ip').innerHTML = 'Access from other devices: http://' + d.ip + ':8080';
            }
        });
        
        // File selection
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
        
        // Upload
        document.getElementById('uploadBtn').onclick = function() {
            var file = document.getElementById('audioFile').files[0];
            if(!file) return;
            
            showProcessing();
            
            var formData = new FormData();
            formData.append('audio', file);
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            }).then(r=>r.json()).then(handleResponse);
        };
        
        // Record
        document.getElementById('recordBtn').onclick = function() {
            var duration = parseInt(document.getElementById('duration').value);
            if (duration < 5) {
                alert('Minimum recording duration is 5 seconds');
                return;
            }
            if (duration > 600) {
                alert('Maximum recording duration is 600 seconds (10 minutes)');
                return;
            }
            showProcessing();
            
            fetch('/record', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({duration: duration})
            }).then(r=>r.json()).then(handleResponse);
        };
        
        function handleResponse(d) {
            if(d.status === 'started') {
                startPolling();
            } else {
                alert(d.message || 'Error');
                location.reload();
            }
        }
        
        function showProcessing() {
            document.getElementById('processing-card').style.display = 'block';
            document.getElementById('upload-card').style.display = 'none';
            document.getElementById('record-card').style.display = 'none';
            document.getElementById('progress-fill').style.width = '1%';
            document.getElementById('progress-percent').innerText = '1%';
            document.getElementById('phase-name').innerText = 'Starting...';
            document.getElementById('timeline').innerHTML = '<div class="timeline-title">Progress</div>';
        }
        
        function startPolling() {
            pollInterval = setInterval(pollStatus, 1200);
        }
        
        function pollStatus() {
            fetch('/status').then(r=>r.json()).then(d=>{
                if(d.status === 'processing') {
                    updateProgress(d);
                } else if(d.status === 'done') {
                    clearInterval(pollInterval);
                    var card = document.getElementById('processing-card');
                    card.classList.add('fade-out');
                    setTimeout(function() {
                        card.style.display = 'none';
                        card.classList.remove('fade-out');
                        showResult(d.summary, d.transcript);
                    }, 500);
                } else if(d.status === 'error') {
                    clearInterval(pollInterval);
                    showError(d.message);
                }
            });
        }
        
        function updateProgress(d) {
            var progress = d.progress || 0;
            var message = d.message || 'Processing...';
            var phase = d.phase_name || 'Processing';
            
            // Update progress bar
            var fill = document.getElementById('progress-fill');
            var percent = document.getElementById('progress-percent');
            var phaseName = document.getElementById('phase-name');
            
            fill.style.width = progress + '%';
            percent.innerText = progress + '%';
            phaseName.innerText = phase;
            
            // Update timeline only if new progress
            if(d.steps && d.steps.length > 0) {
                var timeline = document.getElementById('timeline');
                var html = '<div class="timeline-title">Progress</div>';
                
                d.steps.forEach(function(step, idx) {
                    var isLast = idx === d.steps.length - 1;
                    var statusClass = isLast ? 'current' : (progress >= step.p ? 'done' : '');
                    html += '<div class="timeline-item ' + statusClass + '">';
                    html += '<div class="timeline-dot"></div>';
                    html += '<div class="timeline-content">';
                    html += '<div class="timeline-time">' + step.t + '</div>';
                    html += '<div class="timeline-text">' + step.m + '</div>';
                    html += '</div></div>';
                });
                
                timeline.innerHTML = html;
            }
        }
        
        function showResult(summary, transcript) {
            currentSummary = summary;
            currentTranscript = transcript;
            
            document.getElementById('result-card').style.display = 'block';
            document.getElementById('upload-card').style.display = 'none';
            document.getElementById('record-card').style.display = 'none';
            
            document.getElementById('summary-content').innerText = summary || 'No summary available';
            document.getElementById('transcript-content').innerText = transcript || 'No transcript available';
        }
        
        function showError(msg) {
            document.getElementById('error-card').style.display = 'block';
            document.getElementById('processing-card').style.display = 'none';
            document.getElementById('upload-card').style.display = 'none';
            document.getElementById('record-card').style.display = 'none';
            document.getElementById('error-msg').innerText = msg;
        }
        
        function downloadFile(type) {
            var content = type === 'summary' ? currentSummary : currentTranscript;
            var blob = new Blob([content], {type: 'text/plain'});
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = type + '_' + Date.now() + '.txt';
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
            from src.pipeline import run_pipeline
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
            from src.recorder import record_audio
            from src.pipeline import run_pipeline
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