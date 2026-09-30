import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, useEffect } from "react";
import { useAuthStore } from "@/stores/authStore";
import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
const Login = lazy(() => import("@/pages/Login"));
const Register = lazy(() => import("@/pages/Register"));
const Home = lazy(() => import("@/pages/Home"));
const IDVSubmission = lazy(() => import("@/pages/IDVSubmission"));
const IDVStatus = lazy(() => import("@/pages/IDVStatus"));
const AdminDashboard = lazy(() => import("@/pages/AdminDashboard"));
const MobileSelfiePage = lazy(() => import("@/pages/MobileSelfiePage"));
const Demo = lazy(() => import("@/pages/Demo"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

function AppRoutes() {
  const { isAuthenticated, fetchUser } = useAuthStore();
  const { pathname } = useLocation();

  useEffect(() => {
    if (pathname !== "/demo" && !pathname.startsWith("/m/")) fetchUser();
  }, [fetchUser, pathname]);

  return (
    <Routes>
      {/* Fully public routes (no auth required) */}
      <Route path="/m/:token" element={<MobileSelfiePage />} />
      <Route path="/demo" element={<Demo />} />

      {/* Public routes */}
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/register"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Register />}
      />

      {/* Protected routes */}
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/idv" element={<IDVSubmission />} />
          <Route path="/idv/status" element={<IDVStatus />} />
        </Route>
      </Route>

      {/* Admin routes */}
      <Route element={<ProtectedRoute requireAdmin />}>
        <Route element={<Layout />}>
          <Route path="/admin" element={<AdminDashboard />} />
        </Route>
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<div role="status" className="p-8 text-center text-muted-foreground">Loading application…</div>}><AppRoutes /></Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
