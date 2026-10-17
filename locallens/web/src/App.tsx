import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Spinner } from "./ui";
import Shell from "./Shell";
import { ChangePasswordPage, LoginPage, SetupPage } from "./pages/AuthPages";
import DatasetsPage from "./pages/DatasetsPage";
import DatasetLoader from "./pages/DatasetLoader";
import AskPage from "./pages/AskPage";
import DataPage from "./pages/DataPage";
import ColumnsPage from "./pages/ColumnsPage";
import DefinitionsPage from "./pages/DefinitionsPage";
import ExamplesPage from "./pages/ExamplesPage";
import DatasetSettingsPage from "./pages/DatasetSettingsPage";
import SettingsPage from "./pages/SettingsPage";
import AdminPage from "./pages/AdminPage";

export default function App() {
  const { state, user } = useAuth();
  if (state.phase === "loading") return <div className="auth"><Spinner /></div>;
  if (state.phase === "error") return <div className="auth"><div className="card auth-card"><h2>Cannot reach the server</h2><p className="muted">{state.message}</p><button className="btn primary" onClick={() => location.reload()}>Try again</button></div></div>;
  if (state.phase === "setup") return <SetupPage />;
  if (state.phase === "anonymous") return <LoginPage />;
  if (user?.must_change_password) return <ChangePasswordPage forced />;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/datasets" replace />} />
        <Route path="datasets" element={<DatasetsPage />} />
        <Route path="d/:id" element={<DatasetLoader />}>
          <Route index element={<Navigate to="ask" replace />} />
          <Route path="ask/:cid?" element={<AskPage />} />
          <Route path="data" element={<DataPage />} />
          <Route path="columns" element={<ColumnsPage />} />
          <Route path="definitions" element={<DefinitionsPage />} />
          <Route path="examples" element={<ExamplesPage />} />
          <Route path="settings" element={<DatasetSettingsPage />} />
        </Route>
        <Route path="settings" element={<SettingsPage />} />
        {user?.role === "admin" && <Route path="admin" element={<AdminPage />} />}
        <Route path="*" element={<Navigate to="/datasets" replace />} />
      </Route>
    </Routes>
  );
}
