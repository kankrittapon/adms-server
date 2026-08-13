import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./api/client";
import { Layout } from "./components/Layout";
import { Attendance, AttendanceDetail } from "./pages/Attendance";
import { Dashboard } from "./pages/Dashboard";
import { Devices } from "./pages/Devices";
import { Enrollments } from "./pages/Enrollments";
import { Login } from "./pages/Login";
import { Mappings } from "./pages/Mappings";
import { HumanDetail, Personnel } from "./pages/Personnel";
import { System } from "./pages/System";

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export function App() {
  return (
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
        <Route path="/system" element={<System />} />
      </Route>
    </Routes>
  );
}
