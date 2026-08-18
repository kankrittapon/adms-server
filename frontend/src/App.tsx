import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./api/client";
import { AuthProvider, useAuth } from "./auth";
import { useTranslation } from "./i18n";
import { Layout } from "./components/Layout";
import { Attendance, AttendanceDetail } from "./pages/Attendance";
import { Dashboard } from "./pages/Dashboard";
import { Devices } from "./pages/Devices";
import { Enrollments } from "./pages/Enrollments";
import { Login } from "./pages/Login";
import { Mappings } from "./pages/Mappings";
import { Audit } from "./pages/Audit";
import { HumanDetail, Personnel } from "./pages/Personnel";
import { System } from "./pages/System";
import { TerminalManagement } from "./pages/TerminalManagement";

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/** UX-only guard: gives a deep-link to an unauthorized page a clear "access
 * denied" screen instead of a partially-empty one. The backend 403 remains
 * the actual authorization boundary — this never grants or blocks a real
 * request, it only decides what the page shell renders. */
function RequireRole({ roles, children }: { roles: string[]; children: React.ReactNode }) {
  const { me, loading } = useAuth();
  const { t } = useTranslation();
  if (loading) return null;
  if (!me || !roles.includes(me.role)) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-xl font-bold text-rose-700">
          !
        </div>
        <h1 className="mt-4 text-sm font-bold text-slate-900">{t.common.forbidden}</h1>
      </div>
    );
  }
  return <>{children}</>;
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
        <Route path="/" element={<Dashboard />} />
        <Route path="/personnel" element={<Personnel />} />
        <Route path="/personnel/:employeeId" element={<HumanDetail />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/attendance" element={<Attendance />} />
        <Route path="/attendance/:id" element={<AttendanceDetail />} />
        <Route path="/enrollments" element={<Enrollments />} />
        <Route path="/mappings" element={<Mappings />} />
        <Route path="/terminal-management" element={<TerminalManagement />} />
        <Route
          path="/audit"
          element={
            <RequireRole roles={["ADMIN"]}>
              <Audit />
            </RequireRole>
          }
        />
        <Route path="/system" element={<System />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
