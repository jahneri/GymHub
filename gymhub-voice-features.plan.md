# Feature Implementation Plan: Voice Chat & TV Coach

## Goal
1.  **Mobile Voice Chat:** Allow users to talk to the AI Coach via audio and receive audio responses.
2.  **TV Coach Explanations:** Automatically explain the current workout part and give tips on the TV when the workout moves to that part.

## Architecture

### Backend (`backend/main.py`)
-   **Dependencies:** Add `python-multipart` (for audio upload) and `gTTS` (Google Text-to-Speech) and `ffmpeg-python` (if needed for audio conversion, though gTTS outputs mp3).
-   **AI Integration:**
    -   Use `google-generativeai` with Gemini 2.5 Flash.
    -   Use Gemini's native audio understanding (Multimodal) for the Voice Chat.
-   **Endpoints:**
    -   `POST /chat/audio`: Accepts `UploadFile` (audio/webm or wav). Uploads to Gemini (or sends inline). Gets text response. Converts to Audio via gTTS. Returns Audio.
    -   `POST /tts`: Accepts text. Returns Audio (via gTTS).
-   **Workout Generation:**
    -   Update `ask_coach_gem` prompt to include a `tv_script` field in the JSON for each workout part, containing a short explanation and tips (max 2 sentences).

### Frontend (`frontend/src/App.jsx`)
-   **RemoteMode (Mobile):**
    -   Add a Microphone Button (Hold to Record).
    -   Use `MediaRecorder` API to capture audio.
    -   Send `Blob` to `/chat/audio`.
    -   Play returned Audio.
-   **TvMode (TV):**
    -   Monitor `state.activePartIndex`.
    -   When it changes (and is not the initial load), fetch TTS audio for `workout.parts[index].tv_script`.
    -   Play Audio.
    -   Show visual indicator ("Coach is speaking...").

## Steps
1.  **Install Dependencies:** Update `requirements.txt` and install.
2.  **Backend - Prompt Update:** Modify `sys_prompt` in `ask_coach_gem` to request `tv_script`.
3.  **Backend - Voice Logic:** Implement `/chat/audio` and `/tts`.
4.  **Frontend - Voice Chat:** Implement `VoiceRecorder` component and integrate into `RemoteMode`.
5.  **Frontend - TV Logic:** Implement logic to trigger TTS on part change.

