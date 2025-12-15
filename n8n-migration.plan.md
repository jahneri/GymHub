<!-- n8n Migration Plan - keep it minimal -->
# GymHub → n8n: Requirements & Plan

## Ziele
- Frontend bleibt unverändert im Verhalten (Timer/WS/UI identisch).
- Backend-Komplexität stark reduzieren: AI/Voice/WOD/TT S in n8n, nur das Nötigste in FastAPI belassen.
- Keine zusätzlichen Proxies, kein TLS/ZT. Nur LAN (`http://raspberrypi.local:5678`).
- Primär Google-Services (STT/LLM/TTS). Whisper lokal nur als Option, falls Google ausfällt/kostenoptimiert werden soll.
- Weniger ist mehr: unnötige Endpoints/Abhängigkeiten entfernen, klare Trennung Orchestration (n8n) vs. State (WS/Timer).

## Zielarchitektur (einfach)
- **n8n @ Raspberry Pi (Docker)**  
  - Webhooks:  
    - `POST /webhook-test/talk` (Voice-In → STT → LLM → TTS → Audio Out)  
    - `POST /webhook-test/wod` (WOD-Plan erstellen)  
    - `POST /webhook-test/tts` (Text → Speech, kompatibel zum TV/Remote)  
  - Nodes: Google Speech-to-Text, Gemini (LLM), Google TTS. Optional Whisper node als Fallback.
  - SQLite-Zugriff via n8n SQLite Node auf bestehende `data/gym.db`.
- **FastAPI (bestehend) schlank halten**  
  - Behält `/ws` Timer/State/Scoreboard (kein KI-Teil mehr).  
  - Optional: `/users`, `/history`, `/log` direkt auf SQLite (kann bleiben).  
  - AI-Endpunkte (`/chat/audio`, `/tts`, WOD-Gen) werden nicht mehr genutzt oder einfach auf n8n-Webhook umgebogen.
- **Frontend (React/Vite)**  
  - Endpoints umstellen auf n8n-Webhooks (kein Proxy):  
    - Voice Chat: auf `/webhook-test/talk`  
    - TTS: auf `/webhook-test/tts`  
    - WOD-Generate: Admin-Aktion callt `/webhook-test/wod`  
  - WebSocket bleibt gegen FastAPI (`/ws`) für Timer/State.

## Minimal-Requirements
- Raspberry Pi Docker mit n8n + (optionales) Postgres für n8n-Config/Executions.
- Zugriff auf `data/gym.db` (rw) für n8n-Workflows.
- Google API Key mit Speech-to-Text, Gemini, TTS aktiv (Pro Account).  
- (Optional) Whisper local: ffmpeg + whisper model, falls wir es nutzen.

## Ablauf / Tasks
1) **Setup n8n auf Pi**  
   - Docker Compose: n8n + Postgres (oder SQLite-intern, falls ganz minimal).  
   - Expose Port 5678 ohne TLS.
2) **Workflows bauen** (als JSON export ins Repo):  
   - `talk`: Webhook → STT (Google) → Kontext (SQLite queries für users/logs) → LLM (Gemini) → TTS (Google) → Audio Response (audio/mpeg).  
   - `wod`: Webhook → LLM (Gemini Flash) → Plan-JSON (kompatibel zu heutigem Schema) → SQLite insert (`workouts`) → Response JSON.  
   - `tts`: Webhook → Google TTS → audio/mpeg.  
   - Optional: Fallback Whisper-Pfad in `talk` (branch bei Google-Fehler).
3) **Frontend Anpassungen (klein, klar)**  
   - API_URL für Voice/TTS/WOD auf `http://raspberrypi.local:5678/webhook-test/...` ändern.  
   - Payloads/Responses kompatibel halten (gleiche Schemas).
4) **FastAPI Entrümpeln**  
   - AI-Endpunkte entfernen/ignorieren (oder lassen, aber Front nutzt sie nicht mehr).  
   - WS/Timer/Scoreboard unverändert lassen.  
   - Evtl. `.env`/requirements aufräumen (gTTS/Gemini nur noch gebraucht, falls wir minimal fallback wollen).
5) **Testen im LAN**  
   - Voice E2E: Handy → talk → Audio zurück.  
   - WOD Generate → Plan in UI + Timer Config.  
   - TV TTS → ruft neuen `/tts` Webhook ab.
6) **Docs & Exporte**  
   - n8n Workflow Exporte (`/n8n/exports/*.json`) ins Repo.  
   - Kurz-Doku im README Abschnitt “n8n”.

## Entscheidungen (bestätigt)
- STT/LLM/TTS: Google-only (Pro Account). Whisper nur optional als Fallback-Pfad.  
- n8n DB: Postgres (für n8n-Config/Executions).  
- Frontend-Calls direkt auf `http://raspberrypi.local:5678` (LAN only, kein TLS).

## Nächste Schritte (umsetzen)
1) Compose für n8n + Postgres aufsetzen.  
2) Drei Webhook-Workflows bauen + exportieren (`/n8n/exports/*.json`):  
   - `talk` (Webhook → Google STT → Kontext/SQLite → Gemini → Google TTS → audio/mpeg).  
   - `wod` (Webhook → Gemini Flash → Plan-JSON → SQLite insert → Response).  
   - `tts` (Webhook → Google TTS → audio/mpeg).  
   - Whisper-Fallback als optionaler Branch in `talk` (nur wenn gewünscht).  
3) Frontend-Endpoints umstellen auf die n8n-Webhooks (Voice/TTS/WOD). WS bleibt FastAPI.  
4) FastAPI entrümpeln: KI-Endpunkte deaktivieren/ignorieren, WS/Timer/Scoreboard belassen.  
5) Tests im LAN (Voice, WOD, TV-TTS).  
6) README-Abschnitt “n8n” ergänzen.

