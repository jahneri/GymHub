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
- Rack: Atletica R7 Rider inkl. Latzug (90kg), Spotter Arms.
- Gewichte: 1x Langhantel (20kg), 90kg Bumper Plates.
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
    conn.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, workout_id TEXT, exercise TEXT, result TEXT, feeling TEXT, notes TEXT, timestamp TEXT)')
    
    try:
        conn.execute("ALTER TABLE logs ADD COLUMN feeling TEXT")
        conn.execute("ALTER TABLE logs ADD COLUMN notes TEXT")
    except:
        pass
    
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
    feeling: Optional[str] = None
    notes: Optional[str] = None

def get_recent_history():
    conn = sqlite3.connect(DB_PATH)
    logs = conn.execute("SELECT user_id, exercise, result, timestamp FROM logs ORDER BY timestamp DESC LIMIT 20").fetchall()
    conn.close()
    if not logs: return "Keine Historie."
    hist = "Vergangene Logs:\n"
    for l in logs:
        hist += f"- {l[3][:10]}: {l[0]} -> {l[1]}: {l[2]}\n"
    return hist

def ask_coach_gem(participants: List[str], custom_prompt: Optional[str] = None):
    if not GOOGLE_API_KEY: return {"focus": "API Key Missing", "parts": []}
    
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

    additional_instructions = f"\nZUSATZWUNSCH DER ATHLETEN: {custom_prompt}" if custom_prompt else ""

    sys_prompt = f"""
    Du bist 'Gem', Elite Coach für Richard & Nina.
    Teilnehmer heute: {", ".join(participants)}
    
    INVENTAR: {GYM_INVENTORY}
    ATHLETEN: {ATHLETES_CONTEXT}
    HISTORIE: {get_recent_history()}
    
    AUFGABE: Erstelle Training für HEUTE. {additional_instructions}
    REGELN:
    - SPRACHE: Alle Beschreibungen und Anweisungen auf DEUTSCH schreiben! Fachbegriffe (Back Squat, Deadlift, Box Jumps, Wall Balls, Burpees, etc.) dürfen auf Englisch bleiben.
    - Partner Mode: Nur 1 Rower/Barbell! I-G-Y-G nutzen.
    - Solo: Treppenlauf nutzen.
    - Kids: Wenn dabei, Feld 'kids_version' füllen.
    - TIMER: Definiere den passenden Timer für das WOD (z.B. EMOM, For Time -> Stopwatch, Time Cap -> Countdown).
    - ZEIT: Jeder Teil (Warmup, Strength, WOD) MUSS eine 'duration_min' (geschätzte Dauer in Minuten) haben.
    
    JSON OUT ONLY:
    {{
      "focus": "...",
      "timer": {{ "mode": "STOPWATCH|COUNTDOWN|EMOM|TABATA", "duration": 600, "rounds": 10, "work": 40, "rest": 20 }},
      "parts": [
        {{ "type": "Warmup", "duration_min": 10, "content": [...] }},
        {{ "type": "Strength", "duration_min": 15, "exercise": "...", "scheme": "...", "target_weight": "...", "notes": "..." }},
        {{ "type": "WOD", "duration_min": 20, "name": "...", "format": "...", "exercises": [...], "scaling": "...", "kids_version": "..." }}
      ]
    }}
    """
    try:
        print(f"DEBUG: Asking Gemini with participants={participants}, prompt={custom_prompt}")
        res = model.generate_content(sys_prompt)
        print(f"DEBUG: Gemini Response Raw: {res.text}")
        
        # Robust JSON extraction
        text = res.text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1:
            json_str = text[start:end]
            return json.loads(json_str)
        else:
            print("ERROR: No JSON found in response")
            return {"focus": "Error parsing", "parts": []}
            
    except Exception as e:
        print(f"ERROR calling Gemini: {e}")
        return {"focus": "Error", "parts": []}

# List available models on startup
try:
    if GOOGLE_API_KEY:
        genai.configure(api_key=GOOGLE_API_KEY)
        print("DEBUG: Checking available Gemini models...")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f" - {m.name}")
except Exception as e:
    print(f"WARNING: Could not list models: {e}")

# Global State
class GymState:
    def __init__(self):
        self.timer_running = False
        self.timer_value = 0.0
        self.start_time = 0.0
        self.rounds = {}
        self.workout = {"parts": []}
        self.active_part_index = 0
        self.timer_config = {
            "mode": "STOPWATCH",
            "duration": 0,
            "rounds": 0,
            "work": 0,
            "rest": 0
        }

    def to_dict(self):
        current_time = self.timer_value
        if self.timer_running:
            current_time += (time.time() - self.start_time)

        return {
            "timerRunning": self.timer_running,
            "timerVal": int(current_time),
            "timerConfig": self.timer_config,
            "activePartIndex": self.active_part_index,
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
            except Exception: pass
manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Send initial state
    try:
        await websocket.send_json({"type": "STATE_UPDATE", "payload": gym_state.to_dict()})
    except Exception:
        manager.disconnect(websocket)
        return

    try:
        while True:
            data = await websocket.receive_json()

            if data.get('type') == 'ACTION':
                action = data.get('payload', {}).get('action')
                user = data.get('payload', {}).get('user')
                
                if action == 'GENERATE_WOD':
                    print("DEBUG: GENERATE_WOD action received")
                    parts = ["Richard", "Nina"] if "Nina" in (user or "") else ["Richard"]
                    custom_prompt = data.get('payload', {}).get('custom_prompt')
                    new_plan = ask_coach_gem(parts, custom_prompt)
                    print(f"DEBUG: New Plan Generated: {new_plan.keys() if isinstance(new_plan, dict) else 'INVALID'}")

                    # Validate Plan Structure
                    if not isinstance(new_plan, dict) or "parts" not in new_plan:
                        print("ERROR: AI response missing 'parts'")
                        new_plan = {
                            "focus": "AI Error", 
                            "parts": [{"type": "Error", "content": ["AI delivered invalid format.", "Please try again."]}]
                        }

                    w_id = f"wod_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("INSERT INTO workouts VALUES (?, ?, ?, ?)", (w_id, datetime.now().strftime('%Y-%m-%d'), json.dumps(new_plan), datetime.now().isoformat()))
                    conn.commit()
                    conn.close()

                    gym_state.workout = new_plan
                    print("DEBUG: Workout saved to GymState")
                    
                    if "timer" in new_plan:
                        print(f"DEBUG: Setting Timer Config: {new_plan['timer']}")
                        gym_state.timer_config = new_plan["timer"]
                        gym_state.timer_running = False
                        gym_state.timer_value = 0
                        gym_state.start_time = 0
                    
                    gym_state.active_part_index = 0

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

                elif action == 'CONFIGURE_TIMER':
                    config = data.get('payload', {}).get('config')
                    if config:
                        gym_state.timer_config = config
                        # Reset timer when config changes
                        gym_state.timer_running = False
                        gym_state.timer_value = 0
                        gym_state.start_time = 0

                elif action == 'SET_ACTIVE_PART':
                    idx = data.get('payload', {}).get('index')
                    if idx is not None and isinstance(idx, int):
                        gym_state.active_part_index = idx
                        
                        # Auto-configure Timer based on part duration
                        if gym_state.workout and "parts" in gym_state.workout:
                            try:
                                part = gym_state.workout["parts"][idx]
                                duration = part.get("duration_min")
                                if duration and isinstance(duration, (int, float)):
                                    gym_state.timer_config = {
                                        "mode": "COUNTDOWN",
                                        "duration": int(duration) * 60,
                                        "rounds": 0, "work": 0, "rest": 0
                                    }
                                    gym_state.timer_running = False
                                    gym_state.timer_value = 0
                                    gym_state.start_time = 0
                            except:
                                pass

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
    conn.execute("INSERT INTO logs (user_id, workout_id, exercise, result, feeling, notes, timestamp) VALUES (?,?,?,?,?,?,?)",
                 (log.user_id, log.workout_id, log.exercise, log.result, log.feeling, log.notes, datetime.now().isoformat()))
    conn.commit(); conn.close()
    await manager.broadcast({"type": "NEW_LOG", "payload": log.dict()})
    return {"status": "ok"}
