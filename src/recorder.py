import pyaudio
import wave
import os
import time

# PyAudio constants
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
MAX_RECORD_SECONDS = 1800  # 30 minute safety limit


def record_audio(output_path: str, duration: int = 5) -> str:
    p = pyaudio.PyAudio()

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

    print(f"Recording for {duration} seconds...")
    frames = []

    for _ in range(0, int(RATE / CHUNK * duration)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("Recording finished.")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(output_path, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

    return output_path


def record_audio_manual(output_path: str, stop_check=None) -> str:
    """Record audio until stop_check() returns True or 30 min safety limit.
    
    Args:
        output_path: Path to save the WAV file
        stop_check: Callable that returns True when recording should stop
    
    Returns:
        output_path
    """
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=CHUNK)

    print("Recording (manual stop)...")
    frames = []
    max_frames = int(RATE / CHUNK * MAX_RECORD_SECONDS)

    for i in range(max_frames):
        if stop_check and stop_check():
            print("Recording stopped by user.")
            break
        data = stream.read(CHUNK)
        frames.append(data)

    elapsed = len(frames) / (RATE / CHUNK)
    print(f"Recording finished. Captured {elapsed:.1f} seconds.")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(output_path, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

    return output_path
