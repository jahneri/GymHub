import os
import json
import sqlite3
import time
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai

app = FastAPI()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DB_PATH = os.getenv("DB_PATH", "/data/gym.db")

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

# Global State
class GymState:
    def __init__(self):
        self.timer_running = False
        self.timer_value = 0.0
        self.start_time = 0.0
        self.rounds = {}
        self.workout = {"parts": []}

    def to_dict(self):
        current_time = self.timer_value
        if self.timer_running:
            current_time += (time.time() - self.start_time)

        return {
            "timerRunning": self.timer_running,
            "timerVal": int(current_time),
            "rounds": self.rounds,
            "workout": self.workout
        }

gym_state = GymState()
try:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT json_data FROM workouts ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        gym_state.workout = json.loads(row[0])
except:
    pass

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
    # Send initial state
    await websocket.send_json({"type": "STATE_UPDATE", "payload": gym_state.to_dict()})

    try:
        while True:
            data = await websocket.receive_json()

            if data.get('type') == 'ACTION':
                action = data.get('payload', {}).get('action')
                user = data.get('payload', {}).get('user')
                
                if action == 'GENERATE_WOD':
                    parts = ["Richard", "Nina"] if "Nina" in (user or "") else ["Richard"]
                    new_plan = ask_coach_gem(parts)

                    w_id = f"wod_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("INSERT INTO workouts VALUES (?, ?, ?, ?)", (w_id, datetime.now().strftime('%Y-%m-%d'), json.dumps(new_plan), datetime.now().isoformat()))
                    conn.commit()
                    conn.close()

                    gym_state.workout = new_plan
                    # Broadcast State Update happens at the end

                elif action == 'TOGGLE_TIMER':
                    if gym_state.timer_running:
                        # Stop
                        gym_state.timer_value += (time.time() - gym_state.start_time)
                        gym_state.timer_running = False
                    else:
                        # Start
                        gym_state.start_time = time.time()
                        gym_state.timer_running = True

                elif action == 'ADD_ROUND':
                    if user:
                        gym_state.rounds[user] = gym_state.rounds.get(user, 0) + 1

                elif action == 'RESET_TIMER':
                    gym_state.timer_running = False
                    gym_state.timer_value = 0

                elif action == 'RESET_ROUNDS':
                    gym_state.rounds = {}

                # Broadcast new state
                await manager.broadcast({"type": "STATE_UPDATE", "payload": gym_state.to_dict()})

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
