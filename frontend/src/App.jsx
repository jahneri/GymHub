import React, { useState, useEffect, useRef } from 'react';
import { User, Play, Square, Plus, RotateCcw, Monitor, Smartphone, Dumbbell, History, Wifi, Baby, Settings, X, Check, ChevronLeft, ChevronRight, Mic, Volume2 } from 'lucide-react';

const HOST = window.location.hostname || 'localhost';
const API_URL = `http://${HOST}:8000`;
const WS_URL = `ws://${HOST}:8000/ws`;
const N8N_BASE = 'http://raspberrypi.local:5678/webhook-test';

const MOCK_USERS = [
  { id: 'u_richard', name: 'Richard', role: 'admin', color: 'blue', initials: 'RI' },
  { id: 'u_nina', name: 'Nina', role: 'user', color: 'pink', initials: 'NI' },
  { id: 'u_ben', name: 'Ben', role: 'kid', color: 'green', initials: 'BE' },
  { id: 'u_lio', name: 'Lio', role: 'kid', color: 'yellow', initials: 'LI' }
];

const playSound = (type) => {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    
    osc.connect(gain);
    gain.connect(ctx.destination);
    
    const now = ctx.currentTime;
    
    if (type === 'beep') {
        osc.frequency.setValueAtTime(800, now);
        gain.gain.setValueAtTime(0.1, now);
        osc.start(now);
        osc.stop(now + 0.1);
    } else if (type === 'gong') {
        osc.frequency.setValueAtTime(300, now);
        osc.frequency.exponentialRampToValueAtTime(100, now + 1.5);
        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 1.5);
        osc.start(now);
        osc.stop(now + 1.5);
    } else if (type === 'warn') {
        osc.frequency.setValueAtTime(600, now);
        gain.gain.setValueAtTime(0.1, now);
        osc.start(now);
        osc.stop(now + 0.05);
    }
};

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
  if (view === 'admin') return <AdminMode onBack={() => setView('home')} onHistory={() => setView('history')} />;
  if (view === 'history') return <HistoryMode onBack={() => setView('admin')} />;
  if (view === 'remote' && user) {
      if (user.role === 'kid') return <KidsMode user={user} onBack={() => setView('home')} />;
      return <RemoteMode user={user} onBack={() => setView('home')} />;
  }
  return <HomeLogin onLogin={login} onEnterTv={() => setView('tv')} onEnterAdmin={() => setView('admin')} />;
}

function useGymSocket() {
  const [state, setState] = useState({ timerRunning: false, timerVal: 0, rounds: {}, activePartIndex: 0, timerConfig: { mode: 'STOPWATCH', duration: 0, rounds: 0, work: 0, rest: 0 } });
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

function HomeLogin({ onLogin, onEnterTv, onEnterAdmin }) {
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
      <div className="flex gap-4">
        <button onClick={onEnterTv} className="flex items-center gap-2 text-slate-500 hover:text-white border border-slate-800 px-6 py-3 rounded-full">
            <Monitor size={18}/> TV Mode
        </button>
        <button onClick={onEnterAdmin} className="flex items-center gap-2 text-slate-500 hover:text-white border border-slate-800 px-6 py-3 rounded-full">
            <Settings size={18}/> Admin
        </button>
      </div>
    </div>
  );
}

function TvMode() {
  const { state } = useGymSocket();
  const [workout, setWorkout] = useState(null);
  const [displayTime, setDisplayTime] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const lastTimeRef = useRef(0);
  const runningRef = useRef(false);
  const partRefs = useRef([]);
  const activePartIndex = state.activePartIndex || 0;
  const lastExplainedIndexRef = useRef(-1);

  useEffect(() => {
    fetch(`${API_URL}/workout/current`).then(r => r.json()).then(setWorkout).catch(() => {});
  }, []);

  useEffect(() => {
    if (state.workout && Array.isArray(state.workout.parts) && state.workout.parts.length > 0) {
        setWorkout(state.workout);
    }
  }, [state.workout]);

  // Coach Explanation Logic
  useEffect(() => {
      if (!workout || !workout.parts) return;
      if (activePartIndex === lastExplainedIndexRef.current) return;
      
      const part = workout.parts[activePartIndex];
      if (part && part.tv_script) {
          lastExplainedIndexRef.current = activePartIndex;
          setSpeaking(true);
          
          fetch(`${N8N_BASE}/tts`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ text: part.tv_script })
          })
          .then(res => res.blob())
          .then(blob => {
              const url = URL.createObjectURL(blob);
              const audio = new Audio(url);
              audio.onended = () => setSpeaking(false);
              audio.play().catch(e => {
                  console.error("Auto-play failed", e);
                  setSpeaking(false);
              });
          })
          .catch(() => setSpeaking(false));
      }
  }, [activePartIndex, workout]);

  useEffect(() => {
      if (state.timerVal !== undefined) {
          setDisplayTime(state.timerVal);
      }
  }, [state.timerVal]);

  useEffect(() => {
      if (partRefs.current[activePartIndex]) {
          partRefs.current[activePartIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
  }, [activePartIndex, workout]);

  // Sound Logic
  useEffect(() => {
      if (state.timerRunning && !runningRef.current) playSound('beep'); // Start
      if (!state.timerRunning && runningRef.current) playSound('beep'); // Stop
      runningRef.current = state.timerRunning;
  }, [state.timerRunning]);

  useEffect(() => {
    let interval;
    if (state.timerRunning) {
        interval = setInterval(() => {
            setDisplayTime(t => {
                const newTime = t + 1;
                // Check for sound triggers based on mode and time
                const mode = state.timerConfig?.mode || 'STOPWATCH';
                
                if (mode === 'COUNTDOWN') {
                    const remaining = (state.timerConfig.duration || 0) - newTime;
                    if (remaining <= 3 && remaining > 0) playSound('warn');
                    if (remaining === 0) playSound('gong');
                }
                else if (mode === 'EMOM') {
                    const interval = state.timerConfig.work || 60;
                    const timeInRound = newTime % interval;
                    const remainingInRound = interval - timeInRound;
                    if (remainingInRound <= 3 && remainingInRound > 0) playSound('warn');
                    if (remainingInRound === interval || timeInRound === 0) playSound('gong'); // New round
                }
                else if (mode === 'TABATA') {
                    const work = state.timerConfig.work || 20;
                    const rest = state.timerConfig.rest || 10;
                    const cycleTime = work + rest;
                    const timeInCycle = newTime % cycleTime;
                    // Transitions: Work ends or Rest ends
                    if (timeInCycle === work) playSound('gong'); // Rest starts
                    if (timeInCycle === 0) playSound('gong'); // Work starts
                    if (timeInCycle === work - 3 || timeInCycle === work - 2 || timeInCycle === work - 1) playSound('warn');
                    if (timeInCycle === cycleTime - 3 || timeInCycle === cycleTime - 2 || timeInCycle === cycleTime - 1) playSound('warn');
                }

                return newTime;
            });
        }, 1000);
    }
    return () => clearInterval(interval);
  }, [state.timerRunning, state.timerConfig]);

  const formatTime = (seconds) => {
    const mins = Math.floor(Math.abs(seconds) / 60);
    const secs = Math.abs(seconds) % 60;
    return `${mins.toString().padStart(2,'0')}:${secs.toString().padStart(2,'0')}`;
  };

  const getTimerDisplay = () => {
      const mode = state.timerConfig?.mode || 'STOPWATCH';
      
      if (mode === 'STOPWATCH') return { main: formatTime(displayTime), sub: null };
      
      if (mode === 'COUNTDOWN') {
          const remaining = Math.max(0, (state.timerConfig.duration || 0) - displayTime);
          return { main: formatTime(remaining), sub: null };
      }

      if (mode === 'EMOM') {
          const interval = state.timerConfig.work || 60;
          const currentRound = Math.floor(displayTime / interval) + 1;
          const totalRounds = state.timerConfig.rounds || 10;
          const timeInRound = displayTime % interval;
          const remainingInRound = interval - timeInRound;
          
          if (currentRound > totalRounds) return { main: "DONE", sub: "Finished" };
          
          return { 
              main: formatTime(remainingInRound), 
              sub: `Round ${currentRound}/${totalRounds}`
          };
      }

      if (mode === 'TABATA') {
          const work = state.timerConfig.work || 20;
          const rest = state.timerConfig.rest || 10;
          const cycleTime = work + rest;
          const totalRounds = state.timerConfig.rounds || 8;
          
          const currentRound = Math.floor(displayTime / cycleTime) + 1;
          const timeInCycle = displayTime % cycleTime;
          const isWork = timeInCycle < work;
          const remaining = isWork ? (work - timeInCycle) : (cycleTime - timeInCycle);

          if (currentRound > totalRounds) return { main: "DONE", sub: "Finished" };

          return { 
              main: formatTime(remaining), 
              sub: `${isWork ? 'WORK' : 'REST'} - ${currentRound}/${totalRounds}`,
              color: isWork ? 'text-green-500' : 'text-red-500'
          };
      }
      
      return { main: formatTime(displayTime), sub: null };
  };

  const timerInfo = getTimerDisplay();

  return (
    <div className="h-screen bg-black text-white p-8 grid grid-cols-1 lg:grid-cols-[1fr_350px] gap-8 font-sans overflow-hidden">
      <div className="space-y-6 overflow-y-auto pr-4">
        <h1 className="text-4xl font-black uppercase text-slate-400 flex items-center gap-4">
            Today's Mission
            {speaking && <span className="text-blue-500 animate-pulse flex items-center gap-2 text-lg normal-case font-bold"><Volume2/> Listen to Coach</span>}
        </h1>
        {workout?.parts && workout.parts.length > 0 ? workout.parts.map((part, i) => (
            <div key={i} ref={el => partRefs.current[i] = el} className={`bg-slate-900 p-6 rounded-3xl border-l-8 border-blue-600 shadow-lg transition-all duration-500 ${i === activePartIndex ? 'opacity-100 scale-100 ring-4 ring-blue-500/50' : 'opacity-30 scale-95 grayscale'}`}>
                <h2 className="text-3xl font-bold mb-4 flex items-center gap-3">
                  {part.type || 'Part'}
                  {part.format && <span className="bg-blue-600 text-sm px-3 py-1 rounded-full text-white">{part.format}</span>}
                  {part.duration_min && <span className="bg-yellow-600/20 text-yellow-500 text-sm px-3 py-1 rounded-full font-mono">{part.duration_min} min</span>}
                </h2>
                <div className="text-xl space-y-3 text-slate-300">
                    {Array.isArray(part.content) && part.content.map((line, k) => <div key={k}>• {line}</div>)}
                    {part.exercise && (
                      <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                        <div className="text-2xl font-bold text-white">{part.exercise}</div>
                        <div className="text-yellow-400 font-mono text-lg">{part.scheme} @ {part.target_weight}</div>
                        {part.notes && <div className="text-sm text-slate-500 italic mt-1">{part.notes}</div>}
                      </div>
                    )}
                    {Array.isArray(part.exercises) && part.exercises.map((ex, k) => <div key={k} className="font-bold text-white flex items-center gap-2"><input type="checkbox" className="w-5 h-5 accent-blue-500"/> {ex}</div>)}
                </div>
                <div className="mt-6 flex flex-wrap gap-3">
                  {part.scaling && <div className="text-sm text-yellow-500 font-bold border border-yellow-500/30 p-2 rounded px-4">⚡ {part.scaling}</div>}
                  {part.kids_version && <div className="text-sm text-green-400 font-bold border border-green-500/30 p-2 rounded flex items-center gap-2 px-4"><Baby size={16}/> {part.kids_version}</div>}
                </div>
            </div>
        )) : (
            <div className="text-slate-500 text-2xl font-bold mt-10">Waiting for Coach...</div>
        )}
        <div className="h-20"></div>
      </div>
      <div className="flex flex-col gap-6 overflow-y-auto">
        <div className={`bg-slate-900 rounded-3xl p-8 text-center border-4 ${state.timerRunning ? 'border-green-500 shadow-[0_0_30px_rgba(34,197,94,0.2)]' : 'border-slate-800'}`}>
            <div className="text-slate-400 text-sm uppercase tracking-widest font-bold mb-2">
                {state.timerConfig?.mode || 'TIMER'}
            </div>
            <div className={`text-[6rem] font-mono font-black leading-none ${timerInfo.color || ''}`}>
                {timerInfo.main}
            </div>
            {timerInfo.sub && <div className="text-2xl font-bold text-slate-400 mt-4 uppercase tracking-widest">{timerInfo.sub}</div>}
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

function AdminMode({ onBack, onHistory }) {
  const { state, send } = useGymSocket();
  const [prompt, setPrompt] = useState('');
  const [showConfig, setShowConfig] = useState(false);
  const [generating, setGenerating] = useState(false);
  
  // Chat State
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks = [];
      
      recorder.ondataavailable = e => chunks.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');
        formData.append('user', 'admin'); // Assuming admin role in this view
        
        // Visual feedback that we are waiting
        setGenerating(true); // Re-use generating state or create new one for 'thinking'

        try {
            const res = await fetch(`${N8N_BASE}/talk`, { method: 'POST', body: formData });
            if (res.ok) {
                const audioBlob = await res.blob();
                const url = URL.createObjectURL(audioBlob);
                new Audio(url).play();
            } else {
                console.error("Coach talk failed");
            }
        } catch(e) { console.error(e); }
        finally { setGenerating(false); }
      };
      
      recorder.start();
      setMediaRecorder(recorder);
      setRecording(true);
    } catch(e) { console.error("Mic error", e); }
  };

  const stopRecording = () => {
    mediaRecorder?.stop();
    setRecording(false);
  };

  const toggleRecording = (e) => {
      e.preventDefault();
      if (recording) stopRecording();
      else startRecording();
  };

  const handleGenerate = async () => {
      setGenerating(true);
      try {
          const res = await fetch(`${N8N_BASE}/wod`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  participants: ['Richard', 'Nina'],
                  custom_prompt: prompt || ''
              })
          });
          const plan = await res.json();
          // Push plan into backend state via WS for TV/Remote
          send('ACTION', { action: 'SET_WORKOUT', workout: plan });
          setPrompt('');
      } catch (e) {
          console.error('WOD generation via n8n failed', e);
      } finally {
          setGenerating(false);
      }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white p-6 flex flex-col font-sans">
      {showConfig && <TimerConfig onClose={() => setShowConfig(false)} onSave={(cfg) => send('ACTION', { action: 'CONFIGURE_TIMER', config: cfg })} />}
      
      <div className="flex justify-between items-center mb-8">
        <h2 className="font-bold text-2xl flex items-center gap-2"><Settings/> Admin Tools</h2>
        <div className="flex gap-2">
            <button onClick={onHistory} className="bg-slate-800 text-slate-300 hover:text-white px-4 py-2 rounded-lg hover:bg-slate-700 font-bold flex items-center gap-2"><History size={18}/> History</button>
            <button onClick={onBack} className="text-slate-500 hover:text-white px-3 py-2 rounded-lg hover:bg-slate-900">Exit</button>
        </div>
      </div>

      <div className="space-y-8 max-w-2xl mx-auto w-full">
          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800">
              <h3 className="text-xl font-bold mb-4 flex items-center gap-2"><Wifi className="text-blue-500"/> AI Coach</h3>
              
              {/* Voice Chat Button */}
              <div className="mb-6">
                <button 
                    onClick={toggleRecording}
                    className={`w-full py-6 rounded-2xl font-bold uppercase transition-all active:scale-95 shadow-lg flex items-center justify-center gap-3 ${
                        recording ? 'bg-red-600 text-white animate-pulse' : 
                        'bg-indigo-600 text-white hover:bg-indigo-500'
                    }`}
                >
                    <Mic size={24} />
                    <span className="text-lg tracking-widest">
                        {recording ? 'End Conversation' : 'Start Conversation with Pablo'}
                    </span>
                </button>
                <div className="text-center text-slate-500 text-xs mt-2 uppercase tracking-widest">
                    {recording ? 'Click again to send. Pablo will respond.' : 'Click to start talking. Click again to send.'}
                </div>
              </div>

              <div className="border-t border-slate-800 my-6"></div>

              <div className="mb-4">
                  <label className="block text-slate-400 text-sm mb-2">Instructions for new Workout (optional)</label>
                  <textarea value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="e.g. 'Leg focused', 'Only 20 mins', 'Partner WOD'" className="w-full bg-slate-800 rounded-xl p-4 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 h-24 resize-none"/>
              </div>
              <button onClick={handleGenerate} disabled={generating} className={`w-full py-3 rounded-xl font-bold flex items-center justify-center gap-2 transition-all active:scale-95 ${generating ? 'bg-slate-700 text-slate-400' : 'bg-blue-600 hover:bg-blue-500 text-white'}`}>
                  {generating ? 'Contacting Coach...' : 'Generate New Workout'}
              </button>
          </div>

          <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800">
              <h3 className="text-xl font-bold mb-4 flex items-center gap-2"><Square className="text-green-500"/> Timer Control</h3>
              <div className="grid grid-cols-2 gap-4">
                  <button onClick={() => setShowConfig(true)} className="bg-slate-800 p-4 rounded-xl font-bold text-slate-300 hover:text-white border border-slate-700 transition-all active:scale-95">
                      Configure Timer
                  </button>
                  <button onClick={() => send('ACTION', { action: 'RESET_TIMER' })} className="bg-red-500/10 border border-red-500/50 p-4 rounded-xl font-bold text-red-500 hover:bg-red-500/20 transition-all active:scale-95">
                      Reset Timer
                  </button>
              </div>
          </div>
      </div>
    </div>
  );
}

function KidsMode({ user, onBack }) {
  const { state, send } = useGymSocket();
  const currentPart = state.workout?.parts?.find(p => p.type === 'WOD') || state.workout?.parts?.[0];
  
  return (
    <div className="min-h-screen bg-indigo-950 text-white p-6 flex flex-col font-sans">
       <div className="flex justify-between items-center mb-8">
        <div className="flex items-center gap-4">
            <div className={`w-16 h-16 rounded-full bg-${user.color}-500 flex items-center justify-center font-bold text-3xl border-4 border-white shadow-lg`}>
                {user.name.substring(0,1)}
            </div>
            <div><h2 className="font-black text-3xl uppercase tracking-widest">{user.name}</h2></div>
        </div>
        <button onClick={onBack} className="bg-indigo-900/50 p-4 rounded-2xl hover:bg-indigo-800 text-white font-bold">X</button>
      </div>

      <div className="bg-white/10 rounded-[2rem] p-6 mb-6 flex-grow border-4 border-white/20">
          <h3 className="text-indigo-300 font-black uppercase text-xl mb-4">Dein Training:</h3>
          <div className="text-2xl font-bold text-white leading-relaxed">
              {currentPart?.kids_version || "Mach einfach mit Papa mit! 💪"}
          </div>
      </div>

      <div className="grid grid-cols-2 gap-4 h-40">
          <button onClick={() => send('ACTION', { action: 'TOGGLE_TIMER' })} className={`rounded-[2rem] flex flex-col items-center justify-center font-black uppercase shadow-xl active:scale-95 transition-all border-b-8 ${state.timerRunning ? 'bg-red-500 border-red-700' : 'bg-green-500 border-green-700'}`}>
              <Play size={48} fill="currentColor"/>
              <span className="text-xl mt-2">{state.timerRunning ? 'STOP' : 'LOS!'}</span>
          </button>
          <button onClick={() => send('ACTION', { action: 'ADD_ROUND', user: user.name })} className="bg-yellow-400 border-yellow-600 border-b-8 rounded-[2rem] flex flex-col items-center justify-center font-black uppercase text-yellow-900 shadow-xl active:scale-95 transition-all">
              <Plus size={48} strokeWidth={4}/>
              <span className="text-xl mt-2">PUNKT +1</span>
          </button>
      </div>
    </div>
  );
}

function RemoteMode({ user, onBack }) {
  const { state, send } = useGymSocket();
  const [showLog, setShowLog] = useState(false);
  
  // Chat State
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState(null);
  const [thinking, setThinking] = useState(false);

  const activeIndex = state.activePartIndex || 0;
  const parts = state.workout?.parts || [];
  const currentPart = parts[activeIndex];
  const totalParts = parts.length;

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks = [];
      
      recorder.ondataavailable = e => chunks.push(e.data);
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');
        formData.append('user', user.name);
        
        setThinking(true);
        try {
            const res = await fetch(`${N8N_BASE}/talk`, { method: 'POST', body: formData });
            if (res.ok) {
                const audioBlob = await res.blob();
                const url = URL.createObjectURL(audioBlob);
                new Audio(url).play();
            } else {
                console.error("Coach talk failed");
            }
        } catch(e) { console.error(e); }
        finally { setThinking(false); }
      };
      
      recorder.start();
      setMediaRecorder(recorder);
      setRecording(true);
    } catch(e) { console.error("Mic error", e); }
  };

  const stopRecording = () => {
    mediaRecorder?.stop();
    setRecording(false);
  };

  const toggleRecording = (e) => {
      e.preventDefault();
      if (recording) stopRecording();
      else startRecording();
  };

  const handleLog = (data) => {
      const exerciseName = currentPart?.exercise || currentPart?.type || 'WOD';
      fetch(`${API_URL}/log`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
              user_id: user.name,
              workout_id: 'current',
              exercise: exerciseName,
              result: data.result,
              feeling: data.feeling,
              notes: data.notes
          })
      }).catch(err => console.error(err));
  };

  const changePart = (delta) => {
      const newIndex = Math.max(0, Math.min(totalParts - 1, activeIndex + delta));
      if (newIndex !== activeIndex) {
          send('ACTION', { action: 'SET_ACTIVE_PART', index: newIndex });
      }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white p-6 flex flex-col font-sans">
      {showLog && <LogModal onClose={() => setShowLog(false)} onSave={handleLog} part={currentPart} />}
      
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-full bg-${user.color}-600 flex items-center justify-center font-bold text-xl`}>{user.name.substring(0,2)}</div>
            <div><h2 className="font-bold text-2xl">{user.name}</h2></div>
        </div>
        <button onClick={onBack} className="text-slate-500 hover:text-white px-3 py-2 rounded-lg hover:bg-slate-900">Exit</button>
      </div>

      <div className="flex flex-col gap-4 flex-grow">
         <div className="grid grid-cols-2 gap-4 h-32">
            <button onClick={() => send('ACTION', { action: 'ADD_ROUND', user: user.name })} className={`bg-${user.color}-600 rounded-3xl flex flex-col items-center justify-center shadow-xl active:scale-95 transition-all`}>
                <Plus size={40} strokeWidth={3} /><span className="text-lg font-black uppercase tracking-widest mt-1">Round +1</span>
            </button>
            <button onClick={() => setShowLog(true)} className="bg-slate-800 rounded-3xl flex flex-col items-center justify-center shadow-lg active:scale-95 transition-all text-slate-300 hover:text-white hover:bg-slate-700">
                <History size={40} strokeWidth={2} /><span className="text-lg font-bold uppercase tracking-widest mt-1">Log</span>
            </button>
         </div>
         
         <div className="grid grid-cols-2 gap-4 h-24">
             <button onClick={() => send('ACTION', { action: 'TOGGLE_TIMER', user: user.name })} className={`col-span-2 rounded-3xl flex flex-col items-center justify-center font-bold uppercase transition-all active:scale-95 ${state.timerRunning ? 'bg-red-500/20 text-red-500 border-2 border-red-500' : 'bg-green-500/20 text-green-500 border-2 border-green-500'}`}>
                 {state.timerRunning ? <Square size={28} fill="currentColor"/> : <Play size={28} fill="currentColor"/>}
                 <span className="mt-1 tracking-widest text-xs">{state.timerRunning ? 'Stop' : 'Start'}</span>
             </button>
         </div>

         <button 
            onClick={toggleRecording}
            disabled={thinking}
            className={`w-full h-20 rounded-3xl flex items-center justify-center gap-4 font-bold uppercase transition-all active:scale-95 shadow-lg select-none ${
                recording ? 'bg-red-600 text-white animate-pulse' : 
                thinking ? 'bg-slate-700 text-slate-400' :
                'bg-indigo-600 text-white hover:bg-indigo-500'
            }`}
         >
             <Mic size={32} />
             <span className="text-xl tracking-widest">
                 {recording ? 'End Conversation' : thinking ? 'Coach is thinking...' : 'Start Conversation with Pablo'}
             </span>
         </button>
         <div className="text-center text-slate-500 text-xs uppercase tracking-widest">
             {recording ? 'Click again to send.' : thinking ? 'Wait...' : 'Tap to start recording. Tap again to stop & send.'}
         </div>

         <div className="bg-slate-900 rounded-3xl p-5 border border-slate-800 flex-grow overflow-y-auto shadow-inner flex flex-col">
            <div className="flex justify-between items-center mb-3 border-b border-slate-800 pb-2 gap-2">
                <button onClick={() => changePart(-1)} disabled={activeIndex === 0} className="flex-1 bg-slate-800/50 h-14 rounded-xl flex items-center justify-center active:bg-slate-700 disabled:opacity-20 transition-all">
                    <ChevronLeft size={32}/>
                </button>
                <div className="px-2 text-center min-w-[80px]">
                    <h3 className="text-slate-500 font-bold uppercase text-[10px] tracking-widest">MISSION</h3>
                    <div className="text-xl font-black">{activeIndex + 1} <span className="text-slate-500 text-sm">/ {totalParts}</span></div>
                </div>
                <button onClick={() => changePart(1)} disabled={activeIndex === totalParts - 1} className="flex-1 bg-slate-800/50 h-14 rounded-xl flex items-center justify-center active:bg-slate-700 disabled:opacity-20 transition-all">
                    <ChevronRight size={32}/>
                </button>
            </div>
            
            <div className="text-white space-y-2 flex-grow overflow-y-auto">
                {currentPart ? (
                    <>
                        <div className="text-blue-400 font-bold text-lg flex justify-between items-center">
                            <span>{currentPart.type} {currentPart.format && <span className="text-slate-400 text-sm font-normal">({currentPart.format})</span>}</span>
                            {currentPart.duration_min && <span className="text-yellow-500 text-sm bg-yellow-500/10 px-2 py-1 rounded">{currentPart.duration_min} min</span>}
                        </div>
                        {currentPart.exercises?.map((ex, i) => (
                            <div key={i} className="flex gap-2 items-start"><span className="text-blue-500 mt-1">•</span> <span className="font-medium">{ex}</span></div>
                        ))}
                        {currentPart.exercise && <div className="font-bold text-xl">{currentPart.exercise} <span className="text-yellow-500">{currentPart.scheme}</span></div>}
                        {currentPart.notes && <div className="text-sm text-slate-500 italic mt-2">{currentPart.notes}</div>}
                    </>
                ) : <span className="text-slate-600 italic">No active workout. Tap "New AI Plan" in Admin.</span>}
            </div>
         </div>
      </div>
    </div>
  );
}

function TimerConfig({ onClose, onSave }) {
  const [mode, setMode] = useState('STOPWATCH');
  const [duration, setDuration] = useState(600); // 10 mins default
  const [rounds, setRounds] = useState(10);
  const [work, setWork] = useState(40);
  const [rest, setRest] = useState(20);

  const handleSave = () => {
    onSave({ mode, duration, rounds, work, rest });
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 rounded-3xl p-6 w-full max-w-md border border-slate-700">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-xl font-bold">Timer Setup</h3>
          <button onClick={onClose}><X size={24}/></button>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-6">
          {['STOPWATCH', 'COUNTDOWN', 'EMOM', 'TABATA'].map(m => (
            <button key={m} onClick={() => setMode(m)} 
              className={`p-3 rounded-xl font-bold text-sm transition-all ${mode === m ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400'}`}>
              {m}
            </button>
          ))}
        </div>

        <div className="space-y-4 mb-8">
          {mode === 'COUNTDOWN' && (
             <div>
               <label className="block text-slate-400 text-sm mb-2">Duration (minutes)</label>
               <input type="number" value={duration / 60} onChange={e => setDuration(e.target.value * 60)} className="w-full bg-slate-800 rounded-xl p-4 text-white font-mono text-xl focus:outline-none focus:ring-2 focus:ring-blue-500"/>
             </div>
          )}
          {(mode === 'EMOM' || mode === 'TABATA') && (
             <div className="grid grid-cols-2 gap-4">
                <div>
                   <label className="block text-slate-400 text-sm mb-2">Rounds</label>
                   <input type="number" value={rounds} onChange={e => setRounds(parseInt(e.target.value))} className="w-full bg-slate-800 rounded-xl p-4 text-white font-mono text-xl focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                </div>
                {mode === 'TABATA' && (
                  <>
                    <div>
                       <label className="block text-slate-400 text-sm mb-2">Work (sec)</label>
                       <input type="number" value={work} onChange={e => setWork(parseInt(e.target.value))} className="w-full bg-slate-800 rounded-xl p-4 text-white font-mono text-xl focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                    </div>
                    <div>
                       <label className="block text-slate-400 text-sm mb-2">Rest (sec)</label>
                       <input type="number" value={rest} onChange={e => setRest(parseInt(e.target.value))} className="w-full bg-slate-800 rounded-xl p-4 text-white font-mono text-xl focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                    </div>
                  </>
                )}
                {mode === 'EMOM' && (
                    <div>
                       <label className="block text-slate-400 text-sm mb-2">Interval (sec)</label>
                       <input type="number" value={work} onChange={e => setWork(parseInt(e.target.value))} className="w-full bg-slate-800 rounded-xl p-4 text-white font-mono text-xl focus:outline-none focus:ring-2 focus:ring-blue-500"/>
                    </div>
                )}
             </div>
          )}
        </div>

        <button onClick={handleSave} className="w-full bg-green-600 py-4 rounded-xl font-bold text-lg flex items-center justify-center gap-2 hover:bg-green-500 transition-all">
          <Check size={24}/> Set Timer
        </button>
      </div>
    </div>
  );
}

function LogModal({ onClose, onSave, initialResult, timerMode, part }) {
  const [result, setResult] = useState('');
  const [feeling, setFeeling] = useState('Good');
  const [notes, setNotes] = useState('');

  const exerciseName = part?.exercise || part?.type || 'Workout';

  useEffect(() => {
      if (initialResult !== undefined && (timerMode === 'STOPWATCH' || timerMode === 'COUNTDOWN')) {
          const mins = Math.floor(initialResult / 60);
          const secs = initialResult % 60;
          const timeStr = `${mins.toString().padStart(2,'0')}:${secs.toString().padStart(2,'0')}`;
          setResult(timeStr);
      }
  }, []); // Run once on mount

  const handleSave = () => {
    onSave({ result, feeling, notes });
    onClose();
  };

  const feelings = [
    { label: 'Easy', emoji: '😎', color: 'green' },
    { label: 'Good', emoji: '💪', color: 'blue' },
    { label: 'Hard', emoji: '🥵', color: 'orange' },
    { label: 'Dead', emoji: '💀', color: 'red' }
  ];

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 rounded-3xl p-6 w-full max-w-md border border-slate-700">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-xl font-bold">Log Result</h3>
          <button onClick={onClose}><X size={24}/></button>
        </div>

        <div className="mb-4 bg-slate-800 p-3 rounded-xl border border-slate-700">
            <div className="text-slate-400 text-xs font-bold uppercase tracking-widest">Exercise</div>
            <div className="text-white font-bold text-lg">{exerciseName}</div>
            {part?.scheme && <div className="text-yellow-500 text-sm">{part.scheme}</div>}
        </div>

        <div className="mb-6">
           <label className="block text-slate-400 text-sm mb-2">How did it feel?</label>
           <div className="grid grid-cols-4 gap-2">
             {feelings.map(f => (
               <button key={f.label} onClick={() => setFeeling(f.label)}
                 className={`p-3 rounded-xl flex flex-col items-center gap-1 transition-all border-2 ${feeling === f.label ? `bg-${f.color}-500/20 border-${f.color}-500 text-white` : 'bg-slate-800 border-transparent text-slate-400'}`}>
                 <span className="text-2xl">{f.emoji}</span>
                 <span className="text-xs font-bold">{f.label}</span>
               </button>
             ))}
           </div>
        </div>

        <div className="mb-6">
           <label className="block text-slate-400 text-sm mb-2">Result (Time, Reps, Weight)</label>
           <input type="text" value={result} onChange={e => setResult(e.target.value)} placeholder="e.g. 12:45 or 5 rounds" className="w-full bg-slate-800 rounded-xl p-4 text-white text-lg focus:outline-none focus:ring-2 focus:ring-blue-500"/>
        </div>

        <div className="mb-8">
           <label className="block text-slate-400 text-sm mb-2">Notes</label>
           <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Any pain? Scaling used?" className="w-full bg-slate-800 rounded-xl p-4 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 h-24 resize-none"/>
        </div>

        <button onClick={handleSave} className="w-full bg-blue-600 py-4 rounded-xl font-bold text-lg flex items-center justify-center gap-2 hover:bg-blue-500 transition-all">
          <Check size={24}/> Save Log
        </button>
      </div>
    </div>
  );
}

function HistoryMode({ onBack }) {
  const [workouts, setWorkouts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/history`)
      .then(res => res.json())
      .then(data => {
        setWorkouts(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white p-6 flex flex-col font-sans">
      <div className="flex justify-between items-center mb-8">
        <h2 className="font-bold text-2xl flex items-center gap-2"><History/> Workout History</h2>
        <button onClick={onBack} className="text-slate-500 hover:text-white px-3 py-2 rounded-lg hover:bg-slate-900">Back</button>
      </div>

      {loading ? (
          <div className="text-center text-slate-500 mt-20">Loading history...</div>
      ) : (
        <div className="space-y-6 max-w-3xl mx-auto w-full">
            {workouts.map(w => (
                <div key={w.id} className="bg-slate-900 rounded-3xl p-6 border border-slate-800">
                    <div className="flex justify-between items-start mb-4">
                        <div>
                            <div className="text-slate-500 text-sm font-bold uppercase tracking-widest mb-1">{w.date}</div>
                            <h3 className="text-xl font-bold text-white">{w.plan?.focus || 'Workout'}</h3>
                        </div>
                        <div className="text-xs text-slate-600 font-mono">{w.created_at.substring(11,16)}</div>
                    </div>

                    {w.plan?.reasoning && (
                        <div className="bg-blue-900/20 border border-blue-500/30 p-4 rounded-xl mb-6">
                            <div className="text-blue-400 text-xs font-bold uppercase tracking-widest mb-2 flex items-center gap-2">
                                <Monitor size={14}/> Coach's Reasoning
                            </div>
                            <p className="text-blue-100 text-sm italic">"{w.plan.reasoning}"</p>
                        </div>
                    )}

                    <div className="mb-6 space-y-2">
                        {w.plan?.parts?.map((p, i) => (
                            <div key={i} className="flex items-center gap-2 text-sm text-slate-400">
                                <span className="bg-slate-800 px-2 py-1 rounded text-xs font-bold">{p.type}</span>
                                <span>{p.duration_min}min</span>
                                <span className="text-slate-500">•</span>
                                <span className="text-slate-300 truncate">{p.format || 'Standard'}</span>
                            </div>
                        ))}
                    </div>

                    {w.logs && w.logs.length > 0 && (
                        <div className="border-t border-slate-800 pt-4">
                            <h4 className="text-slate-500 text-xs font-bold uppercase tracking-widest mb-3">Results</h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {w.logs.map((log, i) => (
                                    <div key={i} className="bg-slate-950 p-3 rounded-xl flex items-center gap-3">
                                        <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center font-bold text-xs text-slate-300">
                                            {log.user_id.substring(0,2).toUpperCase()}
                                        </div>
                                        <div className="flex-grow">
                                            <div className="font-bold text-sm text-white">{log.result}</div>
                                            {log.notes && <div className="text-xs text-slate-500 truncate">{log.notes}</div>}
                                        </div>
                                        <div className="text-lg" title={log.feeling}>{
                                            log.feeling === 'Easy' ? '😎' :
                                            log.feeling === 'Good' ? '💪' :
                                            log.feeling === 'Hard' ? '🥵' :
                                            log.feeling === 'Dead' ? '💀' : ''
                                        }</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            ))}
            {workouts.length === 0 && <div className="text-center text-slate-500 italic">No workouts recorded yet.</div>}
        </div>
      )}
    </div>
  );
}
