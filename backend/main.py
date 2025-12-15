import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import time
import io
import asyncio
import base64
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- SDK IMPORTS ---
# Legacy SDK für einfache Text/JSON Generierung (WODs)
import google.generativeai as genai_legacy 
# Neues SDK für Live API (WebSocket / Native Audio)
from google import genai as google_genai 
from google.genai import types as genai_types
from gtts import gTTS

app = FastAPI()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# DB CONFIG
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gymhub")
DB_USER = os.getenv("DB_USER", "gymhub")
DB_PASSWORD = os.getenv("DB_PASSWORD", "gymhub")

# --- KONFIGURATION ---
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

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        print("Waiting for DB...")
        return
    
    try:
        with conn.cursor() as cur:
            # Create n8n DB/User if needed is handled by Postgres Env or manually, 
            # here we init GymHub tables.
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, 
                    name TEXT, 
                    role TEXT, 
                    color TEXT, 
                    stats TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workouts (
                    id TEXT PRIMARY KEY, 
                    date TEXT, 
                    json_data TEXT, 
                    created_at TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id SERIAL PRIMARY KEY, 
                    user_id TEXT, 
                    workout_id TEXT, 
                    exercise TEXT, 
                    result TEXT, 
                    feeling TEXT, 
                    notes TEXT, 
                    timestamp TEXT
                )
            """)
            
            # Seed Users
            users = [
                ('u_richard', 'Richard', 'admin', 'blue', '{"dob": "1987"}'),
                ('u_nina', 'Nina', 'user', 'pink', '{"dob": "1987-03-27"}'),
                ('u_ben', 'Ben', 'kid', 'green', '{"dob": "2016-07-12"}'),
                ('u_lio', 'Lio', 'kid', 'yellow', '{"dob": "2018-10-05"}'),
                ('u_jona', 'Jona', 'kid', 'purple', '{"dob": "2023-09-25"}'),
                ('u_imad', 'Imad', 'user', 'indigo', '{}'),
                ('u_robert', 'Robert', 'user', 'orange', '{}')
            ]
            
            # Upsert users
            for u in users:
                cur.execute("""
                    INSERT INTO users (id, name, role, color, stats) 
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE 
                    SET name = EXCLUDED.name, role = EXCLUDED.role, color = EXCLUDED.color, stats = EXCLUDED.stats
                """, u)
                
            conn.commit()
            print("DB Initialized.")
    except Exception as e:
        print(f"DB Init Error: {e}")
    finally:
        conn.close()

# Wait for DB to be ready in Docker
time.sleep(5)
init_db()

class LogEntry(BaseModel):
    user_id: str
    workout_id: str
    exercise: str
    result: str
    feeling: Optional[str] = None
    notes: Optional[str] = None

def get_recent_history():
    conn = get_db_connection()
    if not conn: return "DB Error"
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, exercise, result, timestamp FROM logs ORDER BY timestamp DESC LIMIT 20")
            logs = cur.fetchall()
            if not logs: return "Keine Historie."
            hist = "Vergangene Logs:\n"
            for l in logs:
                hist += f"- {l[3][:10]}: {l[0]} -> {l[1]}: {l[2]}\n"
            return hist
    finally:
        conn.close()

def get_system_context():
    return f"""
    INVENTAR: {GYM_INVENTORY}
    ATHLETEN: {ATHLETES_CONTEXT}
    HISTORIE: {get_recent_history()}
    """

# --- TEXT/JSON GENERIERUNG (WOD PLANUNG) ---
# NOTE: This is now largely handled by n8n, but we keep the helper for now or fallback.
def ask_coach_gem(participants: List[str], custom_prompt: Optional[str] = None):
    # ... Implementation kept but likely unused if n8n takes over ...
    # Simplified for brevity as logic moves to n8n
    return {"focus": "Use n8n", "parts": []}

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

# Load last workout on startup
try:
    conn = get_db_connection()
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT json_data FROM workouts ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                gym_state.workout = json.loads(row[0])
        conn.close()
except Exception as e:
    print(f"Error loading last workout: {e}")

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
                
                if action == 'TOGGLE_TIMER':
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
                
                elif action == 'SET_WORKOUT':
                    # Accept pre-generated workout plan from external orchestrator (e.g., n8n)
                    new_plan = data.get('payload', {}).get('workout')
                    if new_plan and isinstance(new_plan, dict):
                        gym_state.workout = new_plan
                        gym_state.active_part_index = 0

                        if "timer" in new_plan:
                            gym_state.timer_config = new_plan["timer"]
                        else:
                            gym_state.timer_config = {
                                "mode": "STOPWATCH",
                                "duration": 0,
                                "rounds": 0,
                                "work": 0,
                                "rest": 0
                            }

                        gym_state.timer_running = False
                        gym_state.timer_value = 0
                        gym_state.start_time = 0

                        # Persist workout to DB for history
                        try:
                            w_id = f"wod_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            conn = get_db_connection()
                            if conn:
                                with conn.cursor() as cur:
                                    cur.execute("INSERT INTO workouts (id, date, json_data, created_at) VALUES (%s, %s, %s, %s)", 
                                                (w_id, datetime.now().strftime('%Y-%m-%d'), json.dumps(new_plan), datetime.now().isoformat()))
                                    conn.commit()
                                conn.close()
                        except Exception as e:
                            print(f"ERROR persisting workout from SET_WORKOUT: {e}")

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
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users")
            res = cur.fetchall()
            return [dict(u) for u in res]
    finally:
        conn.close()

@app.get("/workout/current")
def get_current():
    conn = get_db_connection()
    if not conn: return {"parts": []}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT json_data FROM workouts ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            return json.loads(row[0]) if row else {"parts": []}
    finally:
        conn.close()

@app.get("/history")
def get_history():
    conn = get_db_connection()
    if not conn: return []
    
    try:
        # RealDictCursor is useful for mapped access
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, date, json_data, created_at FROM workouts ORDER BY created_at DESC LIMIT 20")
            workouts_rows = cur.fetchall()
            
            workouts = []
            for w in workouts_rows:
                w_data = dict(w)
                try:
                    w_data['plan'] = json.loads(w_data['json_data'])
                except:
                    w_data['plan'] = {}
                del w_data['json_data']
                
                # Get logs for this workout
                # We need a new cursor or execute on same? Same is fine.
                cur.execute("SELECT user_id, result, feeling, notes, timestamp FROM logs WHERE workout_id = %s", (w_data['id'],))
                logs = cur.fetchall()
                w_data['logs'] = [dict(l) for l in logs]
                workouts.append(w_data)
                
            return workouts
    finally:
        conn.close()

@app.post("/log")
async def log_res(log: LogEntry):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO logs (user_id, workout_id, exercise, result, feeling, notes, timestamp) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (log.user_id, log.workout_id, log.exercise, log.result, log.feeling, log.notes, datetime.now().isoformat()))
                conn.commit()
            await manager.broadcast({"type": "NEW_LOG", "payload": log.dict()})
        finally:
            conn.close()
    return {"status": "ok"}

# --- LIVE AUDIO ENDPOINT ---
# (Keeping this for now if you want to use the old path or if n8n doesn't support streaming well yet)
@app.websocket("/live/audio")
async def live_audio_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Placeholder: In new n8n architecture this should ideally move to n8n webhook (talk)
    # But for streaming low-latency voice, direct WebSocket to Google might still be better.
    # Leaving it here but it's deprecated in favor of n8n flow if strict requirements apply.
    await websocket.close(code=1000, reason="Use n8n webhook")

# --- Legacy Endpoints ---
# Disabled/Redirected to n8n in Frontend
