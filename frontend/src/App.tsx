import { Routes, Route, Navigate } from "react-router-dom";
import { ProtectedLayout } from "./components/ProtectedLayout";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import AssistantPage from "./pages/AssistantPage";
import MaterialsPage from "./pages/MaterialsPage";
import ProfilePage from "./pages/ProfilePage";
import AdminMonitoringPage from "./pages/AdminMonitoringPage";
import AdminUsersPage from "./pages/AdminUsersPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/materials" element={<MaterialsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/admin/monitoring" element={<AdminMonitoringPage />} />
        <Route path="/admin/users" element={<AdminUsersPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/assistant" replace />} />
    </Routes>
  );
}
