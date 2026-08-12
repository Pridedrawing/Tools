#!/usr/bin/env python3
"""Qwen TTS Web UI — paste text, pick a voice, generate and play audio."""

import io
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

VOICES_DIR = Path(r"C:\Users\olli_\Documents\GitHub\Tools\Qwen\voices")
MODEL_PATH = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
PORT = 8765

# ---------------------------------------------------------------------------
# Voice discovery
# ---------------------------------------------------------------------------

def scan_voices():
    groups = {}
    for folder in sorted(VOICES_DIR.iterdir()):
        if not folder.is_dir():
            continue
        if not (folder / "ref.wav").exists() or not (folder / "ref.txt").exists():
            continue
        if "_" not in folder.name:
            continue
        prefix, char = folder.name.split("_", 1)
        groups.setdefault(prefix, []).append(char)
    return groups

VOICES = scan_voices()

# ---------------------------------------------------------------------------
# Model (loaded once in background thread)
# ---------------------------------------------------------------------------

_model = None
_model_lock = threading.Lock()
_model_ready = threading.Event()
_model_error = None


def _load_model():
    global _model, _model_error
    try:
        import torch
        import soundfile as sf
        from qwen_tts import Qwen3TTSModel

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        print(f"[TTS] Loading model on {device} ({dtype}) …", flush=True)
        m = Qwen3TTSModel.from_pretrained(MODEL_PATH, device_map=device, dtype=dtype)
        _model = (m, device, sf, torch)
        print("[TTS] Model ready.", flush=True)
    except Exception as exc:
        _model_error = str(exc)
        print(f"[TTS] Model load failed: {exc}", flush=True)
    finally:
        _model_ready.set()


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _generate(text: str, game_prefix: str, character: str, language: str) -> bytes:
    _model_ready.wait()
    if _model_error:
        raise RuntimeError(f"Model unavailable: {_model_error}")

    voice_dir = VOICES_DIR / f"{game_prefix}_{character}"
    ref_wav = voice_dir / "ref.wav"
    ref_txt = voice_dir / "ref.txt"
    if not ref_wav.exists():
        raise ValueError(f"Voice not found: {game_prefix}_{character}")

    ref_transcript = ref_txt.read_text(encoding="utf-8").strip()
    m, device, sf, torch = _model

    max_tokens = min(max(int(len(text) * 12 * 1.5), 256), 4096)

    with _model_lock:
        with torch.inference_mode():
            wavs, sr = m.generate_voice_clone(
                text=text,
                language=language,
                ref_audio=str(ref_wav),
                ref_text=ref_transcript,
                x_vector_only_mode=True,
                max_new_tokens=max_tokens,
            )

    buf = io.BytesIO()
    sf.write(buf, wavs[0], sr, format="WAV")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# HTML UI (embedded)
# ---------------------------------------------------------------------------

def _build_voice_options():
    label_map = {"BEngel": "BEngel", "BtC": "Bound to College", "GOS": "Gay Office Sim"}
    parts = []
    for prefix, chars in VOICES.items():
        label = label_map.get(prefix, prefix)
        parts.append(f'<optgroup label="{label}">')
        for char in chars:
            parts.append(f'  <option value="{prefix}_{char}">{char}</option>')
        parts.append("</optgroup>")
    return "\n".join(parts)


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qwen TTS</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: system-ui, sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2rem 1rem;
  }
  h1 { font-size: 1.4rem; font-weight: 600; color: #a78bfa; margin-bottom: 1.5rem; letter-spacing: .04em; }
  .card {
    background: #16213e;
    border: 1px solid #2d2d5e;
    border-radius: 12px;
    padding: 1.5rem;
    width: 100%;
    max-width: 680px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  textarea {
    width: 100%;
    min-height: 200px;
    resize: vertical;
    background: #0f0f2a;
    color: #e0e0e0;
    border: 1px solid #3a3a6e;
    border-radius: 8px;
    padding: .75rem;
    font-size: .95rem;
    line-height: 1.6;
    font-family: inherit;
  }
  textarea:focus { outline: none; border-color: #7c3aed; }
  .row { display: flex; gap: .75rem; flex-wrap: wrap; }
  .field { display: flex; flex-direction: column; gap: .35rem; flex: 1; min-width: 160px; }
  label { font-size: .8rem; color: #9ca3af; text-transform: uppercase; letter-spacing: .06em; }
  select {
    background: #0f0f2a;
    color: #e0e0e0;
    border: 1px solid #3a3a6e;
    border-radius: 8px;
    padding: .55rem .75rem;
    font-size: .95rem;
    cursor: pointer;
  }
  select:focus { outline: none; border-color: #7c3aed; }
  button#generate {
    background: #7c3aed;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: .7rem 1.5rem;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: background .15s;
    align-self: flex-start;
  }
  button#generate:hover:not(:disabled) { background: #6d28d9; }
  button#generate:disabled { background: #4b3d72; cursor: not-allowed; }
  #status {
    font-size: .85rem;
    color: #9ca3af;
    min-height: 1.2em;
  }
  #status.error { color: #f87171; }
  #status.ok { color: #34d399; }
  #audio-wrap {
    display: none;
    flex-direction: column;
    gap: .5rem;
  }
  audio { width: 100%; border-radius: 8px; }
  #download {
    background: transparent;
    border: 1px solid #7c3aed;
    color: #a78bfa;
    border-radius: 8px;
    padding: .45rem 1rem;
    font-size: .85rem;
    cursor: pointer;
    align-self: flex-start;
    transition: background .15s;
  }
  #download:hover { background: #2d2d5e; }
</style>
</head>
<body>
<h1>Qwen TTS</h1>
<div class="card">
  <textarea id="text" placeholder="Paste your text here…"></textarea>

  <div class="row">
    <div class="field">
      <label for="voice">Voice</label>
      <select id="voice">
        {VOICE_OPTIONS}
      </select>
    </div>
    <div class="field">
      <label for="language">Language</label>
      <select id="language">
        <option value="english" selected>English</option>
        <option value="german">German</option>
        <option value="french">French</option>
        <option value="spanish">Spanish</option>
        <option value="italian">Italian</option>
        <option value="portuguese">Portuguese</option>
        <option value="auto">Auto-detect</option>
      </select>
    </div>
  </div>

  <button id="generate">Generate</button>
  <div id="status">Checking model…</div>

  <div id="audio-wrap">
    <audio id="player" controls></audio>
    <button id="download">Download WAV</button>
  </div>
</div>

<script>
const btn = document.getElementById('generate');
const status = document.getElementById('status');
const audioWrap = document.getElementById('audio-wrap');
const player = document.getElementById('player');
const dlBtn = document.getElementById('download');
let lastBlob = null;

function setStatus(msg, cls) {
  status.textContent = msg;
  status.className = cls || '';
}

async function checkModel() {
  try {
    const r = await fetch('/status');
    const d = await r.json();
    if (d.error) {
      setStatus('Model error: ' + d.error, 'error');
      btn.disabled = true;
    } else if (d.ready) {
      setStatus('Model ready.', 'ok');
      btn.disabled = false;
    } else {
      setStatus('Loading model…');
      btn.disabled = true;
      setTimeout(checkModel, 2000);
    }
  } catch {
    setStatus('Server not responding…', 'error');
    setTimeout(checkModel, 3000);
  }
}

btn.addEventListener('click', async () => {
  const text = document.getElementById('text').value.trim();
  const voice = document.getElementById('voice').value;
  const language = document.getElementById('language').value;
  if (!text) { setStatus('Please enter some text.', 'error'); return; }

  btn.disabled = true;
  audioWrap.style.display = 'none';
  setStatus('Generating… (this may take a minute)');

  try {
    const r = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice, language }),
    });

    if (!r.ok) {
      const err = await r.json().catch(() => ({ error: r.statusText }));
      setStatus('Error: ' + (err.error || r.statusText), 'error');
      return;
    }

    lastBlob = await r.blob();
    const url = URL.createObjectURL(lastBlob);
    player.src = url;
    audioWrap.style.display = 'flex';
    player.play();
    setStatus('Done.', 'ok');
  } catch (e) {
    setStatus('Request failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
});

dlBtn.addEventListener('click', () => {
  if (!lastBlob) return;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(lastBlob);
  const voice = document.getElementById('voice').value;
  a.download = voice + '_tts.wav';
  a.click();
});

checkModel();
</script>
</body>
</html>
"""

HTML = HTML_TEMPLATE.replace("{VOICE_OPTIONS}", _build_voice_options())


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress per-request noise

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/status":
            self._send_json({
                "ready": _model_ready.is_set(),
                "error": _model_error,
            })
        elif path == "/voices":
            self._send_json(VOICES)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/generate":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        text = body.get("text", "").strip()
        voice = body.get("voice", "")
        language = body.get("language", "english")

        if not text:
            self._send_json({"error": "No text provided"}, 400)
            return
        if "_" not in voice:
            self._send_json({"error": "Invalid voice selection"}, 400)
            return

        game_prefix, character = voice.split("_", 1)

        try:
            print(f"[TTS] Generating: voice={voice} lang={language} chars={len(text)}", flush=True)
            wav_bytes = _generate(text, game_prefix, character, language)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav_bytes)))
            self.end_headers()
            self.wfile.write(wav_bytes)
            print(f"[TTS] Done: {len(wav_bytes)//1024} KB", flush=True)
        except Exception as exc:
            print(f"[TTS] Error: {exc}", flush=True)
            self._send_json({"error": str(exc)}, 500)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    threading.Thread(target=_load_model, daemon=True).start()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"[TTS] Web UI: {url}", flush=True)
    print("[TTS] Model loading in background — page will enable Generate when ready.", flush=True)

    threading.Timer(1.5, webbrowser.open, args=[url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[TTS] Stopped.")
