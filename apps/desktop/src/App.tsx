import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { EmptyState, LoadingState } from "./components/states/States";
import { Dashboard } from "./features/Dashboard";
import { Settings } from "./features/sections";
import { Ask } from "./features/ask/Ask";
import { PlayerCompare } from "./features/statistics/PlayerCompare";
import { Statistics } from "./features/statistics/Statistics";
import { ReportCatalogue } from "./features/statistics/ReportCatalogue";
import { CaptaincyCompare } from "./features/statistics/CaptaincyCompare";
import { Publishing } from "./features/publishing/Publishing";
import { Scorecard } from "./features/scorecard/Scorecard";
import { PeopleManagement } from "./features/people/PeopleManagement";
import { PlayerProfile } from "./features/people/PlayerProfile";
import { BackendDown, Login, Setup } from "./features/auth/Auth";
import { ChangePassword } from "./features/auth/ChangePassword";
import { UserManagement } from "./features/admin/UserManagement";
import { SystemUpdates } from "./features/admin/SystemUpdates";
import { Integrations } from "./features/settings/Integrations";
import { MemberPortal } from "./features/portal/MemberPortal";
import { MyWorkspaces } from "./features/workspaces/MyWorkspaces";
import { OnboardingWizard } from "./features/onboarding/OnboardingWizard";
import { Organisations } from "./features/manage/Organisations";
import { TeamsVenues } from "./features/manage/TeamsVenues";
import { Competitions } from "./features/manage/Competitions";
import { PlayingConditions } from "./features/manage/PlayingConditions";
import { OrgHistory } from "./features/manage/OrgHistory";
import { ImportWizard } from "./features/import/ImportWizard";
import { AutoSync } from "./features/autosync/AutoSync";
import { ResearchCentre } from "./features/research/ResearchCentre";
import { MediaArchive } from "./features/media/MediaArchive";
import { Records } from "./features/records/Records";
import { ClubBrandingSync } from "./features/ClubBrandingSync";
import { useAuth } from "./lib/auth";
import { LayoutProvider } from "./lib/layout";
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
    <LayoutProvider>
      <WorkspaceProvider>
        <ClubBrandingSync />
        <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/workspaces" element={<MyWorkspaces />} />
        <Route path="/onboarding" element={<OnboardingWizard />} />
        <Route path="/manage/organisations" element={<Organisations />} />
        <Route path="/manage/teams-venues" element={<TeamsVenues />} />
        <Route path="/manage/competitions" element={<Competitions />} />
        <Route path="/manage/conditions" element={<PlayingConditions />} />
        <Route path="/manage/history" element={<OrgHistory />} />
        <Route path="/manage/import" element={<ImportWizard />} />
        <Route path="/manage/autosync" element={<AutoSync />} />
        <Route path="/manage/research" element={<ResearchCentre />} />
        <Route path="/manage/media" element={<MediaArchive />} />
        <Route path="/manage/records" element={<Records />} />
        <Route path="/manage/publishing" element={<Publishing />} />
        <Route path="/manage/portal" element={<MemberPortal />} />
        <Route path="/matches" element={<Scorecard />} />
        <Route path="/people" element={<PeopleManagement />} />
        <Route path="/people/:personId" element={<PlayerProfile />} />
        <Route path="/statistics" element={<Statistics />} />
        <Route path="/statistics/compare" element={<PlayerCompare />} />
        <Route path="/statistics/catalogue" element={<ReportCatalogue />} />
        <Route path="/statistics/captaincy-compare" element={<CaptaincyCompare />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/integrations" element={<Integrations />} />
        <Route path="/admin/users" element={<UserManagement />} />
        <Route path="/admin/system-updates" element={<SystemUpdates />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </WorkspaceProvider>
    </LayoutProvider>
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
  if (user.must_change_password) return <ChangePassword />;   // forced first-login change
  return <AuthedApp />;
}
