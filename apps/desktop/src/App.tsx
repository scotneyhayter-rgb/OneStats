import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { EmptyState, LoadingState } from "./components/states/States";
import { Dashboard } from "./features/Dashboard";
import { Ask, Matches, People, Settings, Statistics } from "./features/sections";
import { BackendDown, Login, Setup } from "./features/auth/Auth";
import { MyWorkspaces } from "./features/workspaces/MyWorkspaces";
import { OnboardingWizard } from "./features/onboarding/OnboardingWizard";
import { useAuth } from "./lib/auth";
import { WorkspaceProvider } from "./lib/workspace-context";

function NotFound() {
  return (
    <AppShell title="Not found" subtitle="The page you requested does not exist">
      <EmptyState title="Page not found" description="Use the sidebar to navigate." />
    </AppShell>
  );
}

function AuthedApp() {
  return (
    <WorkspaceProvider>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/workspaces" element={<MyWorkspaces />} />
        <Route path="/onboarding" element={<OnboardingWizard />} />
        <Route path="/matches" element={<Matches />} />
        <Route path="/people" element={<People />} />
        <Route path="/statistics" element={<Statistics />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </WorkspaceProvider>
  );
}

export default function App() {
  const { user, loading, backendError, setupRequired } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <LoadingState label="Starting OneStats..." />
      </div>
    );
  }
  if (backendError) return <BackendDown message={backendError} />;
  if (!user && setupRequired) return <Setup />;
  if (!user) return <Login />;
  return <AuthedApp />;
}
