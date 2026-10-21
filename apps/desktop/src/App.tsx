import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { EmptyState } from "./components/states/States";
import { Dashboard } from "./features/Dashboard";
import { Ask, Matches, People, Settings, Statistics } from "./features/sections";

function NotFound() {
  return (
    <AppShell title="Not found" subtitle="The page you requested does not exist">
      <EmptyState
        title="Page not found"
        description="Use the sidebar to navigate to a section."
      />
    </AppShell>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/matches" element={<Matches />} />
      <Route path="/people" element={<People />} />
      <Route path="/statistics" element={<Statistics />} />
      <Route path="/ask" element={<Ask />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
