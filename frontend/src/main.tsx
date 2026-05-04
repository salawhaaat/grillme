import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// StrictMode intentionally omitted — it double-invokes effects which
// destroys the AudioWorklet (Silero VAD / MicVAD) on mount, making STT
// permanently broken. AudioWorklet is not compatible with StrictMode.
createRoot(document.getElementById('root')!).render(<App />)
