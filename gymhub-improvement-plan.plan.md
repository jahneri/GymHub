<!-- a4ded53e-1a6c-4aea-8cda-e429cb230102 167ba706-fb64-4a48-a762-97122e631509 -->
# GymHub Improvement Plan

This plan outlines the steps to upgrade the GymHub app with advanced features, starting with the Timer enhancements.

## Phase 1: Advanced Timer Modes (Priority 1) [COMPLETED]

**Goal:** Support Stopwatch, Countdown, EMOM, and Tabata modes synchronized across devices.

### Backend (`backend/main.py`)

- [x] Update `GymState` to include `timer_config` (mode, duration, rounds, work/rest intervals).
- [x] Add `CONFIGURE_TIMER` action to WebSocket handler.
- [x] Ensure `timer_value` continues to track total elapsed time, which frontends will interpret based on mode.

### Frontend (`frontend/src/App.jsx`)

- **Remote Mode:**
    - [x] Add "Timer Settings" button/modal.
    - [x] Create UI to select mode (Stopwatch, Countdown, EMOM, Tabata) and parameters.
    - [x] Send `CONFIGURE_TIMER` action on save.
- **TV Mode:**
    - [x] Update Timer display logic to handle different modes:
        - **Countdown:** `duration - elapsed`
        - **EMOM:** Show current round and countdown for current minute.
        - **Tabata:** Show "Work" or "Rest" phase, current round, and interval countdown.
    - [x] Add visual indicators for rounds/phases.

## Phase 2: Sound Feedback (Priority 1) [COMPLETED]

**Goal:** Audio cues for timer events (Start, Stop, Round End, Countdown).

- [x] Add audio assets (beep, gong) or use synthesized sound.
- [x] Integrate sound triggers in `TvMode` based on timer state changes.

## Phase 3: Quick Log UI (Priority 1) [COMPLETED]

**Goal:** Allow users to log workout results immediately after finishing.

- [x] Create `LogModal` component in Frontend.
- [x] Trigger manually or auto-suggest after timer/workout end.
- [x] Use existing `POST /log` endpoint.

## Phase 4: Remote Mode Enhancements (Priority 2) [COMPLETED]

**Goal:** Show more context on the remote (current movement, next exercise).

- [x] Update `RemoteMode` to display current part of the workout.
- [x] Remove Settings button to keep UI clean.
- [x] Show exercise list directly on remote.

## Phase 5: Admin & Settings Dashboard (Priority 2) [COMPLETED]

**Goal:** Central place for coach interactions and settings, keeping the remote clean.

- [x] Create `AdminMode` view.
- [x] Move "Generate WOD" logic to Admin.
- [x] Add input for custom AI instructions (e.g. "Leg Day").
- [x] Allow manual timer configuration from Admin.
- [x] Remove AI/Settings buttons from Remote Mode.

## Phase 6: Kids Mode (Priority 3) [COMPLETED]

**Goal:** Simplified, colorful UI for users with role 'kid'.

- [x] Create dedicated `KidsMode` component.
- [x] Implement role-based routing in `App.jsx`.
- [x] Show simplified "Kids Version" of workout.
- [x] Large, fun buttons for Timer and Rounds.

## Phase 7: AI Coach Debugging & Optimization (Current)

---

## Implementation Steps for Phase 1 (Timer)

1.  **Modify Backend State (`backend/main.py`)**

    -   Add `timer_config` to `GymState`.
    -   Handle `CONFIGURE_TIMER` in `websocket_endpoint`.

2.  **Update Frontend State (`frontend/src/App.jsx`)**

    -   Update `useGymSocket` to handle new state fields if necessary (mostly automatic).

3.  **Create Timer Config UI (`frontend/src/App.jsx`)**

    -   Add `TimerConfig` component/modal.
    -   Add button in `RemoteMode` to open config.

4.  **Update TV Display (`frontend/src/App.jsx`)**

    -   Refactor Timer display in `TvMode` to support all modes.
    -   Implement logic:
        -   `Stopwatch`: Default behavior.
        -   `Countdown`: `Math.max(0, config.duration - timerVal)`.
        -   `EMOM`: Calculate `currentRound` and `timeLeftInInterval`.
        -   `Tabata`: Calculate phase (Work/Rest) and time remaining.