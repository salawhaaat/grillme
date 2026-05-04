import { BrowserRouter, Routes, Route } from "react-router-dom"
import Home from "@/pages/Home"
import SessionPage from "@/pages/Session"
import ScorecardPage from "@/pages/Scorecard"
import HistoryPage from "@/pages/History"
import FeedbackPage from "@/pages/Feedback"
import NotesPage from "@/pages/Notes"
import WhiteboardPage from "@/pages/Whiteboard"
import ResourcesPage from "@/pages/Resources"
import SettingsPage from "@/pages/Settings"
import ProfilePage from "@/pages/Profile"
import STTTestPage from "@/pages/STTTest"
import AvatarTestPage from "@/pages/AvatarTest"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/session/:id" element={<SessionPage />} />
        <Route path="/session/:id/scorecard" element={<ScorecardPage />} />
        <Route path="/session/:id/feedback" element={<FeedbackPage />} />
        <Route path="/notes" element={<NotesPage />} />
        <Route path="/whiteboard" element={<WhiteboardPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/stt-test" element={<STTTestPage />} />
        <Route path="/avatar-test" element={<AvatarTestPage />} />
      </Routes>
    </BrowserRouter>
  )
}
