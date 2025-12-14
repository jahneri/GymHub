import os
import json
import sqlite3
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
DB_PATH = os.getenv("DB_PATH", "/data/gym.db")

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

def get_system_context():
    return f"""
    INVENTAR: {GYM_INVENTORY}
    ATHLETEN: {ATHLETES_CONTEXT}
    HISTORIE: {get_recent_history()}
    """

# --- TEXT/JSON GENERIERUNG (WOD PLANUNG) ---
def ask_coach_gem(participants: List[str], custom_prompt: Optional[str] = None):
    if not GOOGLE_API_KEY: return {"focus": "API Key Missing", "parts": []}
    
    # Nutzung des Legacy Clients für JSON Task (stabiler für Text)
    genai_legacy.configure(api_key=GOOGLE_API_KEY)
    
    # WICHTIG: Hier nutzen wir das normale Flash Modell, NICHT das Audio-Modell!
    # Das Audio-Modell ist oft schlecht in JSON-Formatting.
    model = genai_legacy.GenerativeModel('gemini-2.5-flash') 

    additional_instructions = f"\nZUSATZWUNSCH DER ATHLETEN: {custom_prompt}" if custom_prompt else ""

    sys_prompt = f"""
    Du bist 'Pablo', Elite Coach für Richard & Nina. Du hast einen leichten spanischen Akzent (nutze ab und zu "Amigos", "Vamos", "Claro" etc., aber bleib verständlich auf Deutsch).
    Teilnehmer heute: {", ".join(participants)}
    
    {get_system_context()}
    
    AUFGABE: Erstelle Training für HEUTE. {additional_instructions}
    REGELN:
    - SPRACHE: Alle Beschreibungen und Anweisungen auf DEUTSCH schreiben! Fachbegriffe (Back Squat, Deadlift, Box Jumps, Wall Balls, Burpees, etc.) dürfen auf Englisch bleiben.
    - Persönlichkeit: Sei feurig, motivierend, aber streng. Nutze spanische Füllwörter.
    - Partner Mode: Nur 1 Rower/Barbell! I-G-Y-G nutzen.
    - Solo: Treppenlauf nutzen.
    - Kids: Wenn dabei, Feld 'kids_version' füllen.
    - TIMER: Definiere den passenden Timer für das WOD (z.B. EMOM, For Time -> Stopwatch, Time Cap -> Countdown).
    - ZEIT: Jeder Teil (Warmup, Strength, WOD) MUSS eine 'duration_min' (geschätzte Dauer in Minuten) haben.
    
    JSON OUT ONLY:
    {{
      "focus": "...",
      "reasoning": "Explain WHY you chose this workout (based on history, inventory, athletes). Max 2 sentences.",
      "timer": {{ "mode": "STOPWATCH|COUNTDOWN|EMOM|TABATA", "duration": 600, "rounds": 10, "work": 40, "rest": 20 }},
      "parts": [
        {{ 
          "type": "Warmup", 
          "duration_min": 10, 
          "content": [...],
          "tv_script": "Short text for the TV to speak explaining this part and giving 1-2 key tips. Direct speech to athletes."
        }},
        {{ 
          "type": "Strength", 
          "duration_min": 15, 
          "exercise": "...", 
          "scheme": "...", 
          "target_weight": "...", 
          "notes": "...",
          "tv_script": "..."
        }},
        {{ 
          "type": "WOD", 
          "duration_min": 20, 
          "name": "...", 
          "format": "...", 
          "exercises": [...], 
          "scaling": "...", 
          "kids_version": "...",
          "tv_script": "..."
        }}
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
        genai_legacy.configure(api_key=GOOGLE_API_KEY)
        print("DEBUG: Checking available Gemini models...")
        for m in genai_legacy.list_models():
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

@app.get("/history")
def get_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Get last 20 workouts
    workouts_rows = conn.execute("SELECT id, date, json_data, created_at FROM workouts ORDER BY created_at DESC LIMIT 20").fetchall()
    workouts = []
    
    for w in workouts_rows:
        w_data = dict(w)
        try:
            w_data['plan'] = json.loads(w_data['json_data'])
        except:
            w_data['plan'] = {}
        del w_data['json_data']
        
        # Get logs for this workout
        logs = conn.execute("SELECT user_id, result, feeling, notes, timestamp FROM logs WHERE workout_id = ?", (w_data['id'],)).fetchall()
        w_data['logs'] = [dict(l) for l in logs]
        workouts.append(w_data)
        
    conn.close()
    return workouts

@app.post("/log")
async def log_res(log: LogEntry):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO logs (user_id, workout_id, exercise, result, feeling, notes, timestamp) VALUES (?,?,?,?,?,?,?)",
                 (log.user_id, log.workout_id, log.exercise, log.result, log.feeling, log.notes, datetime.now().isoformat()))
    conn.commit(); conn.close()
    await manager.broadcast({"type": "NEW_LOG", "payload": log.dict()})
    return {"status": "ok"}

# --- LIVE AUDIO ENDPOINT ---
@app.websocket("/live/audio")
async def live_audio_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("INFO: Live Audio WebSocket connected", flush=True)

    if not GOOGLE_API_KEY:
        print("ERROR: No API Key!", flush=True)
        await websocket.close(code=1008, reason="API Key Missing")
        return

    try:
        # Use the new SDK Client for Live API
        print("DEBUG: Creating Gemini client...", flush=True)
        client = google_genai.Client(api_key=GOOGLE_API_KEY, http_options={'api_version': 'v1alpha'})
        
        # FIX: Das korrekte Preview Model für Native Audio
        model_id = "gemini-2.5-flash-native-audio-preview-09-2025"
        
        # System Prompt
        system_instruction = f"""
        Du bist 'Pablo', der feurige spanische Fitness-Coach. 
        CONTEXT: {get_system_context()}
        Antworte hilfreich, motivierend und mit spanischem Akzent/Flair ("Vamos!", "Amigos!").
        Bleib kurz und knackig.
        """
        
        config = genai_types.LiveConnectConfig(
            response_modalities=["AUDIO"], # Nur Audio zurück
            system_instruction=genai_types.Content(parts=[genai_types.Part(text=system_instruction)]),
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Puck"))
            ),
        )

        print(f"DEBUG: Connecting to Gemini Live API with model {model_id}...", flush=True)
        
        async with client.aio.live.connect(model=model_id, config=config) as session:
            print("DEBUG: Connected to Gemini Live API!", flush=True)
            
            # Tasks tracking
            receive_task = None
            send_task = None
            
            async def receive_from_client():
                try:
                    while True:
                        try:
                            message = await websocket.receive()
                        except RuntimeError:
                            break # Client disconnected
                        
                        if "bytes" in message:
                            # Audio Chunk - send continuously, VAD will handle turn detection
                            try:
                                # Use send_realtime_input for continuous audio streaming
                                # The API's VAD (Voice Activity Detection) will automatically detect when user stops speaking
                                await session.send_realtime_input(
                                    audio=genai_types.Blob(
                                        data=message["bytes"],
                                        mime_type="audio/pcm;rate=16000"
                                    )
                                )
                                print(".", end="", flush=True)
                            except Exception as e:
                                print(f"ERROR sending audio to Gemini: {e}", flush=True)
                        
                        elif message.get("type") == "websocket.disconnect":
                            break

                except WebSocketDisconnect:
                    print("INFO: WebSocket disconnected by client.", flush=True)
                except Exception as e:
                    print(f"ERROR in receive_from_client: {e}", flush=True)

            async def send_to_client():
                print("DEBUG: Starting send_to_client loop...", flush=True)
                try:
                    async for response in session.receive():
                        # Logging what we get back (for debug)
                        if response.server_content:
                            # Debug log only once or when content changes to avoid spam
                            pass 
                        
                        # Extract Audio from Server Content
                        if response.server_content and response.server_content.model_turn:
                            for part in response.server_content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    try:
                                        await websocket.send_bytes(part.inline_data.data)
                                    except Exception:
                                        return # Client gone
                        
                        # Handle Turn Complete (optional logic)
                        if response.server_content and response.server_content.turn_complete:
                             pass 

                except Exception as e:
                    print(f"ERROR in send_to_client: {e}", flush=True)

            # Start loops
            receive_task = asyncio.create_task(receive_from_client())
            send_task = asyncio.create_task(send_to_client())
            
            await asyncio.gather(receive_task, send_task)
            
    except Exception as e:
        print(f"ERROR in live_audio_endpoint: {e}", flush=True)

# --- Legacy Endpoints ---

class TTSRequest(BaseModel):
    text: str

@app.post("/tts")
async def tts_endpoint(req: TTSRequest):
    try:
        tts = gTTS(text=req.text, lang='de')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return StreamingResponse(fp, media_type="audio/mp3")
    except Exception as e:
        print(f"ERROR generating TTS: {e}")
        return {"error": "TTS Failed"}