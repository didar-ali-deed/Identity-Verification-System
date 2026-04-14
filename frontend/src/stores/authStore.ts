import { create } from "zustand";
import { authApi } from "@/api/client";
import type { User, LoginRequest, RegisterRequest } from "@/types";

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!localStorage.getItem("access_token"),
  isLoading: false,
  error: null,

  login: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authApi.login(data);
      localStorage.setItem("access_token", response.data.access_token);
      localStorage.setItem("refresh_token", response.data.refresh_token);

      const userResponse = await authApi.me();
      set({
        user: userResponse.data,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      const message = typeof detail === "string" ? detail : "Login failed. Check your credentials.";
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  register: async (data) => {
    set({ isLoading: true, error: null });
    try {
      await authApi.register(data);
      // Register returns user, not tokens — log in after registering
      const loginResponse = await authApi.login({ email: data.email, password: data.password });
      localStorage.setItem("access_token", loginResponse.data.access_token);
      localStorage.setItem("refresh_token", loginResponse.data.refresh_token);

      const userResponse = await authApi.me();
      set({
        user: userResponse.data,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      const message = typeof detail === "string" ? detail : "Registration failed.";
      set({ error: message, isLoading: false });
      throw err;
    }
  },

  logout: async () => {
    try {
      await authApi.logout();
    } catch {
      // Ignore logout errors
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      set({ user: null, isAuthenticated: false });
    }
  },

  fetchUser: async () => {
    if (!localStorage.getItem("access_token")) {
      set({ isAuthenticated: false });
      return;
    }
    try {
      const response = await authApi.me();
      set({ user: response.data, isAuthenticated: true });
    } catch {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      set({ user: null, isAuthenticated: false });
    }
  },

  clearError: () => set({ error: null }),
}));
