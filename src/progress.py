"""
Progress callback system for pipeline.

Allows the pipeline to report real-time progress to the web UI.
Uses a simple, accurate progress calculation.

Also provides cross-module cancel/shutdown signaling so any
module can check if the user requested a stop and abort.
"""
import threading
import time
import signal as _signal
import os as _os

# Global progress state
_state = {
    'lock': threading.Lock(),
    'active': False,
    'progress': 0,
    'phase_num': 0,   # 1=prepare, 2=split, 3=transcribe, 4=summarize, 5=save, 6=done
    'phase_done': 0,   # completed items in current phase
    'phase_total': 0,  # total items in current phase
    'total_chunks': 0,
    'message': '',
    'initial_message': '',
    'steps': [],
    # Track separate counters for each phase type
    'transcribe_done': 0,
    'analyze_done': 0,
    'cancelled': False,        # user requested stop
    'active_pids': set(),      # subprocess PIDs to kill on cancel
    'active_pids_lock': threading.Lock(),
}

PHASE_NAMES = {
    0: 'Ready',
    1: 'Preparing...',
    2: 'Preparing audio...',
    3: 'Transcribing...',
    4: 'Analyzing...',
    5: 'Saving...',
    6: 'Complete!',
}

# Progress ranges for each phase (start, end)
PHASE_PROGRESS = {
    1: (1, 5),
    2: (5, 15),
    3: (15, 55),
    4: (55, 90),
    5: (90, 98),
    6: (98, 100),
}

OPERATION_DISPLAY = {
    'upload': 'Uploading file...',
    'record': 'Recording audio...',
    'text': 'Processing text...',
    'transcribe_only': 'Transcribing audio...',
}

def reset_progress():
    """Reset progress state"""
    with _state['lock']:
        _state['active'] = False
        _state['progress'] = 0
        _state['phase_num'] = 0
        _state['phase_done'] = 0
        _state['phase_total'] = 0
        _state['total_chunks'] = 0
        _state['message'] = ''
        _state['initial_message'] = ''
        _state['steps'] = []
        _state['transcribe_done'] = 0
        _state['analyze_done'] = 0
        _state['cancelled'] = False

def start(total_chunks: int = 1, operation: str = 'upload'):
    """Start processing"""
    with _state['lock']:
        _state['active'] = True
        _state['cancelled'] = False
        _state['total_chunks'] = max(1, total_chunks)
        _state['phase_num'] = 1
        _state['phase_done'] = 0
        _state['phase_total'] = total_chunks
        _state['initial_message'] = OPERATION_DISPLAY.get(operation, 'Preparing...')
        _state['message'] = _state['initial_message']
        _state['progress'] = 1
        _state['steps'] = [{'p': 1, 'm': _state['initial_message'], 't': time.strftime("%H:%M:%S")}]

def set_phase(phase: int, total: int = 0):
    """Set current phase with accurate progress calculation"""
    with _state['lock']:
        if phase not in PHASE_NAMES:
            return
        
        _state['phase_num'] = phase
        _state['phase_done'] = 0
        
        if total > 0:
            _state['phase_total'] = total
            _state['total_chunks'] = total
        
        # Get progress range for this phase
        phase_range = PHASE_PROGRESS.get(phase, (0, 100))
        start_pct, end_pct = phase_range
        
        # If single chunk or just starting, use phase start
        _state['progress'] = start_pct
        
        # Calculate message
        if phase == 1:
            _state['message'] = _state.get('initial_message', PHASE_NAMES[phase])
        else:
            _state['message'] = PHASE_NAMES[phase]
        
        # Log step only if phase changed or first time
        _state['steps'].append({
            'p': _state['progress'],
            'm': _state['message'],
            't': time.strftime("%H:%M:%S"),
            'phase': phase
        })

def update_chunk():
    """Mark one chunk as done - separate tracking for transcribe vs analyze"""
    with _state['lock']:
        phase = _state['phase_num']
        total = _state.get('total_chunks', 1)
        
        if phase == 3:
            _state['transcribe_done'] += 1
            current = _state['transcribe_done']
            start_pct, end_pct = PHASE_PROGRESS[3]
            msg_prefix = "Transcribed chunk"
        elif phase == 4:
            _state['analyze_done'] += 1
            current = _state['analyze_done']
            start_pct, end_pct = PHASE_PROGRESS[4]
            msg_prefix = "Analyzed chunk"
        else:
            _state['phase_done'] += 1
            current = _state['phase_done']
            start_pct, end_pct = PHASE_PROGRESS.get(phase, (15, 55))
            msg_prefix = PHASE_NAMES.get(phase, 'Processing...')
        
        if total > 1:
            per_chunk = (end_pct - start_pct) / total
            _state['progress'] = start_pct + int(current * per_chunk)
        else:
            _state['progress'] = end_pct
        
        display_current = min(current, total)
        if total > 1:
            _state['message'] = f"{msg_prefix} {display_current}/{total}"
        else:
            _state['message'] = msg_prefix
        
        _state['steps'].append({
            'p': _state['progress'],
            'm': _state['message'],
            't': time.strftime("%H:%M:%S")
        })

def complete():
    """Mark complete - ensure 100%"""
    with _state['lock']:
        _state['progress'] = 100
        _state['phase_num'] = 6
        _state['message'] = 'Complete!'
        _state['active'] = False
        _state['steps'].append({'p': 100, 'm': 'Complete!', 't': time.strftime("%H:%M:%S")})

def log_message(msg: str):
    """Add a reactive log message to the UI timeline"""
    with _state['lock']:
        _state['steps'].append({
            'p': _state['progress'],
            'm': msg,
            't': time.strftime("%H:%M:%S")
        })

def get():
    """Get current progress"""
    with _state['lock']:
        return {
            'active': _state['active'],
            'progress': _state['progress'],
            'phase': _state['phase_num'],
            'phase_name': PHASE_NAMES.get(_state['phase_num'], 'Ready'),
            'message': _state['message'],
            'current_chunk': _state['transcribe_done'],
            'total_chunks': _state['total_chunks'],
            'steps': list(_state['steps'])
        }

def is_active():
    """Check if in progress"""
    with _state['lock']:
        return _state['active']

# ── Cross-module Cancel / Shutdown API ──────────────────────

def cancel():
    """Signal cancel — used by webui.py /stop endpoint."""
    with _state['lock']:
        _state['cancelled'] = True
        _state['active'] = False
    _kill_subprocesses()

def is_cancelled() -> bool:
    """Check whether a cancel was requested."""
    with _state['lock']:
        return _state['cancelled']

def clear_cancel():
    """Clear the cancel flag (e.g. at start of a new operation)."""
    with _state['lock']:
        _state['cancelled'] = False

def register_pid(pid: int):
    """Register a subprocess PID so it gets killed on cancel."""
    with _state['active_pids_lock']:
        _state['active_pids'].add(pid)

def unregister_pid(pid: int):
    """Remove a subprocess PID from the kill-list."""
    with _state['active_pids_lock']:
        _state['active_pids'].discard(pid)

def _kill_subprocesses():
    """Kill all tracked subprocesses (called on cancel)."""
    with _state['active_pids_lock']:
        pids = list(_state['active_pids'])
        _state['active_pids'].clear()
    for pid in pids:
        try:
            _os.kill(pid, _signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            _os.kill(pid, _signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
