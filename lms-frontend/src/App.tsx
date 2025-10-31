import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import TeacherUpload from "./pages/TeacherUpload";
import StudentSubmit from "./pages/StudentSubmit";

export default function App() {
  return (
    <BrowserRouter>
      <nav style={{ padding: 10, borderBottom: "1px solid #eee" }}>
        <Link to="/teacher">Teacher</Link>
      </nav>
      <Routes>
        <Route path="/teacher" element={<TeacherUpload />} />
        <Route path="/student/:assignmentId" element={<StudentSubmit />} />
        <Route path="*" element={<div style={{ padding: 20 }}>
          Go to <Link to="/teacher">/teacher</Link>
        </div>} />
      </Routes>
    </BrowserRouter>
  );
}

