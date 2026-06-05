import eventlet
eventlet.monkey_patch()

import os
import sys
import threading
import json
import time
import psutil
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Ensure jarvis context
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import run_agent
from config import BASE_DIR, LOG_FILE

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'gui_templates'))
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# ── Routes ────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

# ── API ───────────────────────────────────────────────────

@socketio.on('user_command')
def handle_command(data):
    task = data.get('command')
    emit('agent_status', {'msg': 'Director thinking...', 'type': 'brain'})
    
    def _status_callback(msg):
        socketio.emit('agent_status', {'msg': msg, 'type': 'tool'})
    
    # Run in a separate thread but since we monkey patched, we use eventlet's spawn
    def run():
        res = run_agent(task, status_callback=_status_callback)
        socketio.emit('agent_result', {'result': res})
        
    eventlet.spawn(run)

def system_stats_pusher():
    while True:
        stats = {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "tasks": 0
        }
        socketio.emit('sys_stats', stats)
        time.sleep(3)

# ── Launch ───────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), 'gui_templates'), exist_ok=True)
    
    # Start stats in background
    eventlet.spawn(system_stats_pusher)
    
    print("[GUI] Server starting on http://127.0.0.1:5000")
    socketio.run(app, host='127.0.0.1', port=5000, debug=False)
