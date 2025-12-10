#!/bin/bash

echo "🚀 Starte GymHub Setup..."

# 1. Ordnerstruktur erstellen
mkdir -p backend
mkdir -p frontend/src
mkdir -p data

# --- ROOT DATEIEN ---

echo "📄 Erstelle .gitignore..."
cat << 'EOF' > .gitignore
node_modules/
frontend/node_modules/
backend/venv/
backend/__pycache__/
*.pyc
.env
.DS_Store
frontend/dist/
frontend/build/
data/*.db
data/*.sqlite
.docker/
EOF

echo "📄 Erstelle docker-compose.yml..."
cat << 'EOF' > docker-compose.yml
version: '3.8'

services:
  api:
    build: ./backend
    container_name: gym_backend
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./backend:/app
      - ./data:/data
    ports:
      - "8000:8000"
    env_file: .env
    restart: unless-stopped

  web:
    build: ./frontend
    container_name: gym_frontend
    command: npm run dev -- --host
    volumes:
      - ./frontend:/app
      - /app/node_modules
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8000
    depends_on:
      - api
    restart: unless-stopped

volumes:
  data:
EOF

echo "📄 Erstelle README.md..."
cat << 'EOF' > README.md
# GymHub

Homegym AI Coach für Richard & Nina.

## Setup
1. \`.env\` erstellen: \`GOOGLE_API_KEY=xyz\`
2. Starten: \`docker-compose up --build\`
EOF

# --- BACKEND DATEIEN ---

echo "🐍 Erstelle Backend..."

cat << 'EOF' > backend/Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

cat << 'EOF' > backend/requirements.txt
fastapi
uvicorn[standard]
google-generativeai
pydantic
websockets
EOF

cat << 'EOF' > backend/main.py
import os
import json
import sqlite3
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai

app = FastAPI()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DB_PATH = "/data/gym.db"

GYM_INVENTORY = """
LOCATION A: KELLER (Haupt-Gym)
- Limitierung: Niedrige Decke! Keine Wall Balls, keine hohen Sprünge.
- Cardio: 1x Concept2 Rower (Engpass!), 1x Boxsack, Springseile.
- Rack: Atletica R7 Rider inkl. Latzug (125kg), Spotter Arms.
- Gewichte: 1x Langhantel (20kg), 150kg Bumper Plates.
- KH/KB: Hex Dumbbells, Kettlebells (8, 12, 16kg).
- Gymnastics: Ringe (tief), Plyo Box, Bank.

LOCATION B: 2. OBERGESCHOSS
- Equipment: Klimmzugstange.
- Skills: Strict Pull-ups, Kipping, Toes-to-Bar.
- Logistik: Treppenlauf zwischen Keller und OG ist Teil des Trainings.
"""

ATHLETES_CONTEXT = """
- Richard (Papa): Informatik-Lehrer, mag Struktur & Heavy Lifting.
- Nina (Mama): CrossFit erfahren, mag WODs. Skaliert moderat.
- Ben (9J): Kindertraining, Technik/Spaß.
- Lio (7J): Kindertraining, Spielerisch.
- Jona (2J): Spielt mit.
- Imad & Robert: Freunde/Gäste.
"""

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT, role TEXT, color TEXT, stats TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS workouts (id TEXT PRIMARY KEY, date TEXT, json_data TEXT, created_at TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, workout_id TEXT, exercise TEXT, result TEXT, timestamp TEXT)')
    
    users = [
        ('u_richard', 'Richard', 'admin', 'blue', '{"dob": "1987"}'),
        ('u_nina', 'Nina', 'user', 'pink', '{"dob": "1987-03-27"}'),
        ('u_ben', 'Ben', 'kid', 'green', '{"dob": "2016-07-12"}'),
        ('u_lio', 'Lio', 'kid', 'yellow', '{"dob": "2018-10-05"}'),
        ('u_jona', 'Jona', 'kid', 'purple', '{"dob": "2023-09-25"}'),
        ('u_imad', 'Imad', 'user', 'indigo', '{}'),
        ('u_robert', 'Robert', 'user', 'orange', '{}')
    ]
    conn.executemany('INSERT OR IGNORE INTO users VALUES (?,?,?,?,?)', users)
    conn.commit()
    conn.close()

init_db()

class LogEntry(BaseModel):
    user_id: str
    workout_id: str
    exercise: str
    result: str

def get_recent_history():
    conn = sqlite3.connect(DB_PATH)
    logs = conn.execute("SELECT user_id, exercise, result, timestamp FROM logs ORDER BY timestamp DESC LIMIT 20").fetchall()
    conn.close()
    if not logs: return "Keine Historie."
    hist = "Vergangene Logs:\n"
    for l in logs:
        hist += f"- {l[3][:10]}: {l[0]} -> {l[1]}: {l[2]}\n"
    return hist

def ask_coach_gem(participants: List[str]):
    if not GOOGLE_API_KEY: return {"focus": "API Key Missing", "parts": []}
    
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

    sys_prompt = f"""
    Du bist 'Gem', Elite Coach für Richard & Nina.
    Teilnehmer heute: {", ".join(participants)}
    
    INVENTAR: {GYM_INVENTORY}
    ATHLETEN: {ATHLETES_CONTEXT}
    HISTORIE: {get_recent_history()}
    
    AUFGABE: Erstelle Training für HEUTE.
    REGELN:
    - Partner Mode: Nur 1 Rower/Barbell! I-G-Y-G nutzen.
    - Solo: Treppenlauf nutzen.
    - Kids: Wenn dabei, Feld 'kids_version' füllen.
    
    JSON OUT ONLY:
    {{
      "focus": "...",
      "parts": [
        {{ "type": "Warmup", "content": [...] }},
        {{ "type": "Strength", "exercise": "...", "scheme": "...", "target_weight": "...", "notes": "..." }},
        {{ "type": "WOD", "name": "...", "format": "...", "exercises": [...], "scaling": "...", "kids_version": "..." }}
      ]
    }}
    """
    try:
        res = model.generate_content(sys_prompt)
        return json.loads(res.text.replace('```json','').replace('```','').strip())
    except Exception as e:
        print(e)
        return {"focus": "Error", "parts": []}

class ConnectionManager:
    def __init__(self): self.active_connections: List[WebSocket] = []
    async def connect(self, ws: WebSocket): await ws.accept(); self.active_connections.append(ws)
    def disconnect(self, ws: WebSocket): self.active_connections.remove(ws)
    async def broadcast(self, msg: dict):
        for c in self.active_connections: 
            try: await c.send_json(msg)
            except: pass
manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get('type') == 'ACTION' and data.get('payload', {}).get('action') == 'GENERATE_WOD':
                user = data.get('payload', {}).get('user', 'u_richard')
                parts = ["Richard", "Nina"] if "Nina" in user else ["Richard"]
                new_plan = ask_coach_gem(parts)
                
                w_id = f"wod_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                conn = sqlite3.connect(DB_PATH)
                conn.execute("INSERT INTO workouts VALUES (?, ?, ?, ?)", (w_id, datetime.now().strftime('%Y-%m-%d'), json.dumps(new_plan), datetime.now().isoformat()))
                conn.commit()
                conn.close()
                await manager.broadcast({"type": "STATE_UPDATE", "payload": {"workout": new_plan}})
            else:
                await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/users")
def get_users():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    res = conn.execute("SELECT * FROM users").fetchall(); conn.close()
    return [dict(u) for u in res]

@app.get("/workout/current")
def get_current():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT json_data FROM workouts ORDER BY created_at DESC LIMIT 1").fetchone(); conn.close()
    return json.loads(row[0]) if row else {"parts": []}

@app.post("/log")
async def log_res(log: LogEntry):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO logs (user_id, workout_id, exercise, result, timestamp) VALUES (?,?,?,?,?)",
                 (log.user_id, log.workout_id, log.exercise, log.result, datetime.now().isoformat()))
    conn.commit(); conn.close()
    await manager.broadcast({"type": "NEW_LOG", "payload": log.dict()})
    return {"status": "ok"}
EOF

# --- FRONTEND DATEIEN ---

echo "⚛️  Erstelle Frontend..."

cat << 'EOF' > frontend/Dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
CMD ["npm", "run", "dev", "--", "--host"]
EOF

cat << 'EOF' > frontend/package.json
{
  "name": "gymhub-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "lucide-react": "^0.292.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.37",
    "@types/react-dom": "^18.2.15",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.31",
    "tailwindcss": "^3.3.5",
    "vite": "^5.0.0"
  }
}
EOF

cat << 'EOF' > frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    watch: { usePolling: true },
    host: true,
    strictPort: true,
    port: 3000, 
  }
})
EOF

cat << 'EOF' > frontend/tailwind.config.js
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
EOF

cat << 'EOF' > frontend/postcss.config.js
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
}
EOF

cat << 'EOF' > frontend/index.html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>GymHub</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
EOF

cat << 'EOF' > frontend/src/main.jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>,
)
EOF

cat << 'EOF' > frontend/src/index.css
@tailwind base;
@tailwind components;
@tailwind utilities;
body { background-color: #020617; color: white; }
EOF

cat << 'EOF' > frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import { User, Play, Square, Plus, RotateCcw, Monitor, Smartphone, Dumbbell, History, Wifi, Baby } from 'lucide-react';

const HOST = window.location.hostname || 'localhost';
const API_URL = `http://${HOST}:8000`;
const WS_URL = `ws://${HOST}:8000/ws`;

const MOCK_USERS = [
  { id: 'u_richard', name: 'Richard', role: 'admin', color: 'blue', initials: 'RI' },
  { id: 'u_nina', name: 'Nina', role: 'user', color: 'pink', initials: 'NI' },
  { id: 'u_ben', name: 'Ben', role: 'kid', color: 'green', initials: 'BE' },
  { id: 'u_lio', name: 'Lio', role: 'kid', color: 'yellow', initials: 'LI' }
];

export default function App() {
  const [view, setView] = useState('home');
  const [user, setUser] = useState(null);
  
  useEffect(() => {
    if (window.location.pathname === '/tv') setView('tv');
    const saved = localStorage.getItem('gym_user');
    if (saved) setUser(JSON.parse(saved));
  }, []);

  const login = (u) => {
    setUser(u);
    localStorage.setItem('gym_user', JSON.stringify(u));
    setView('remote');
  };

  if (view === 'tv') return <TvMode />;
  if (view === 'remote' && user) return <RemoteMode user={user} onBack={() => setView('home')} />;
  return <HomeLogin onLogin={login} onEnterTv={() => setView('tv')} />;
}

function useGymSocket() {
  const [state, setState] = useState({ timerRunning: false, timerVal: 0, rounds: {} });
  const ws = useRef(null);

  useEffect(() => {
    const connect = () => {
        ws.current = new WebSocket(WS_URL);
        ws.current.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'STATE_UPDATE') setState(msg.payload);
            } catch (err) {}
        };
        ws.current.onclose = () => setTimeout(connect, 3000); // Auto Reconnect
    };
    connect();
    return () => ws.current?.close();
  }, []);

  const send = (type, payload) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type, payload }));
    }
  };
  return { state, send };
}

function HomeLogin({ onLogin, onEnterTv }) {
  const [users, setUsers] = useState([]);
  useEffect(() => {
    fetch(`${API_URL}/users`).then(res => res.json()).then(setUsers).catch(() => setUsers(MOCK_USERS));
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white p-6 flex flex-col items-center justify-center font-sans">
      <h1 className="text-4xl font-bold mb-8 flex items-center gap-3"><Dumbbell className="text-blue-500"/> GymHub</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8 w-full max-w-2xl">
        {users.map(u => (
          <button key={u.id} onClick={() => onLogin(u)} className={`p-6 rounded-2xl bg-slate-900 border-2 border-slate-800 hover:border-${u.color}-500 transition-all flex flex-col items-center gap-3`}>
            <div className={`w-16 h-16 rounded-full bg-${u.color}-600 flex items-center justify-center text-2xl font-bold shadow-lg`}>
              {u.name.substring(0,2)}
            </div>
            <span className="font-bold text-lg">{u.name}</span>
          </button>
        ))}
      </div>
      <button onClick={onEnterTv} className="flex items-center gap-2 text-slate-500 hover:text-white border border-slate-800 px-6 py-3 rounded-full">
        <Monitor size={18}/> Start TV Mode
      </button>
    </div>
  );
}

function TvMode() {
  const { state } = useGymSocket();
  const [workout, setWorkout] = useState(null);
  const [displayTime, setDisplayTime] = useState(0);

  useEffect(() => {
    fetch(`${API_URL}/workout/current`).then(r => r.json()).then(setWorkout).catch(() => {});
  }, []);

  useEffect(() => {
    let interval;
    if (state.timerRunning) interval = setInterval(() => setDisplayTime(t => t + 1), 1000);
    return () => clearInterval(interval);
  }, [state.timerRunning]);

  return (
    <div className="min-h-screen bg-black text-white p-8 grid grid-cols-12 gap-8 font-sans">
      <div className="col-span-8 space-y-6 overflow-y-auto max-h-screen pb-20">
        <h1 className="text-4xl font-black uppercase text-slate-400">Today's Mission</h1>
        {workout?.parts?.map((part, i) => (
            <div key={i} className="bg-slate-900 p-6 rounded-3xl border-l-8 border-blue-600 shadow-lg">
                <h2 className="text-3xl font-bold mb-4 flex items-center gap-3">
                  {part.type}
                  {part.format && <span className="bg-blue-600 text-sm px-3 py-1 rounded-full text-white">{part.format}</span>}
                </h2>
                <div className="text-xl space-y-3 text-slate-300">
                    {part.content?.map((line, k) => <div key={k}>• {line}</div>)}
                    {part.exercise && (
                      <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                        <div className="text-2xl font-bold text-white">{part.exercise}</div>
                        <div className="text-yellow-400 font-mono text-lg">{part.scheme} @ {part.target_weight}</div>
                        {part.notes && <div className="text-sm text-slate-500 italic mt-1">{part.notes}</div>}
                      </div>
                    )}
                    {part.exercises?.map((ex, k) => <div key={k} className="font-bold text-white flex items-center gap-2"><input type="checkbox" className="w-5 h-5 accent-blue-500"/> {ex}</div>)}
                </div>
                <div className="mt-6 flex flex-wrap gap-3">
                  {part.scaling && <div className="text-sm text-yellow-500 font-bold border border-yellow-500/30 p-2 rounded px-4">⚡ {part.scaling}</div>}
                  {part.kids_version && <div className="text-sm text-green-400 font-bold border border-green-500/30 p-2 rounded flex items-center gap-2 px-4"><Baby size={16}/> {part.kids_version}</div>}
                </div>
            </div>
        ))}
      </div>
      <div className="col-span-4 flex flex-col gap-6">
        <div className={`bg-slate-900 rounded-3xl p-8 text-center border-4 ${state.timerRunning ? 'border-green-500 shadow-[0_0_30px_rgba(34,197,94,0.2)]' : 'border-slate-800'}`}>
            <div className="text-slate-400 text-sm uppercase tracking-widest font-bold mb-2">Timer</div>
            <div className="text-[6rem] font-mono font-black leading-none">{Math.floor(displayTime/60).toString().padStart(2,'0')}:{(displayTime%60).toString().padStart(2,'0')}</div>
        </div>
        <div className="flex-grow bg-slate-900 rounded-3xl p-6 border border-slate-800">
            <h3 className="text-slate-500 font-bold uppercase mb-6 tracking-widest text-sm border-b border-slate-800 pb-2">Scoreboard</h3>
            {state.rounds && Object.entries(state.rounds).map(([name, count]) => (
                <div key={name} className="flex justify-between items-center mb-4 text-3xl font-bold">
                    <span className="text-slate-300">{name}</span>
                    <span className="text-blue-500 bg-blue-500/10 px-4 py-1 rounded-lg">{count}</span>
                </div>
            ))}
        </div>
      </div>
    </div>
  );
}

function RemoteMode({ user, onBack }) {
  const { state, send } = useGymSocket();
  return (
    <div className="min-h-screen bg-slate-950 text-white p-6 flex flex-col font-sans">
      <div className="flex justify-between items-center mb-8">
        <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-full bg-${user.color}-600 flex items-center justify-center font-bold text-xl`}>{user.name.substring(0,2)}</div>
            <div><h2 className="font-bold text-2xl">{user.name}</h2></div>
        </div>
        <button onClick={onBack} className="text-slate-500 hover:text-white px-3 py-2 rounded-lg hover:bg-slate-900">Exit</button>
      </div>
      <div className="flex-grow grid grid-rows-2 gap-6 pb-6">
         <button onClick={() => send('ACTION', { action: 'ADD_ROUND', user: user.name })} className={`bg-${user.color}-600 rounded-[2.5rem] flex flex-col items-center justify-center shadow-xl active:scale-95 transition-all`}>
            <Plus size={80} strokeWidth={2.5} /><span className="text-3xl font-black uppercase tracking-widest mt-2">Runde +1</span>
         </button>
         <div className="grid grid-cols-2 gap-6">
             <button onClick={() => send('ACTION', { action: 'TOGGLE_TIMER', user: user.name })} className={`rounded-3xl flex flex-col items-center justify-center font-bold uppercase transition-all active:scale-95 ${state.timerRunning ? 'bg-red-500/20 text-red-500 border-2 border-red-500' : 'bg-green-500/20 text-green-500 border-2 border-green-500'}`}>
                 {state.timerRunning ? <Square size={40} fill="currentColor"/> : <Play size={40} fill="currentColor"/>}
                 <span className="mt-3 tracking-widest">{state.timerRunning ? 'Stop' : 'Start'}</span>
             </button>
             <button onClick={() => send('ACTION', { action: 'GENERATE_WOD', user: user.name })} className="bg-slate-900 rounded-3xl flex flex-col items-center justify-center font-bold text-slate-400 border border-slate-800 active:scale-95 transition-all hover:bg-slate-800 hover:text-white">
                 <Wifi size={32} /><span className="mt-3 text-xs uppercase tracking-widest">New AI Plan</span>
             </button>
         </div>
      </div>
    </div>
  );
}
EOF

echo "✅ Setup abgeschlossen! Nächste Schritte:"
echo "1. Erstelle die Datei .env mit: nano .env (Inhalt: GOOGLE_API_KEY=...)"
echo "2. Starte mit: docker-compose up -d --build"
echo "3. Initialisiere Git: git init && git add . && git commit -m 'Initial Setup'"