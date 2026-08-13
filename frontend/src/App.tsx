import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Attendance, AttendanceDetail } from "./pages/Attendance";
import { Dashboard } from "./pages/Dashboard";
import { Devices } from "./pages/Devices";
import { Enrollments } from "./pages/Enrollments";
import { Mappings } from "./pages/Mappings";
import { HumanDetail, Personnel } from "./pages/Personnel";
import { System } from "./pages/System";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
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
