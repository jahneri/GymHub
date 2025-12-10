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
    if (state.workout && state.workout.parts && state.workout.parts.length > 0) {
        setWorkout(state.workout);
    }
  }, [state.workout]);

  useEffect(() => {
      if (state.timerVal !== undefined) {
          setDisplayTime(state.timerVal);
      }
  }, [state.timerVal]);

  useEffect(() => {
    let interval;
    if (state.timerRunning) {
        interval = setInterval(() => setDisplayTime(t => t + 1), 1000);
    }
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
