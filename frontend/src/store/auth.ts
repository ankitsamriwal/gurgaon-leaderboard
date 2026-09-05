import { create } from "zustand";
import type { CurrentUser } from "../types";

const STORAGE_KEY = "gurgaon-leaderboard-auth";

interface StoredAuth {
  accessToken: string;
  refreshToken: string;
  user: CurrentUser;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: CurrentUser | null;
  setSession: (session: StoredAuth) => void;
  clearSession: () => void;
}

function loadStored(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAuth) : null;
  } catch {
    return null;
  }
}

const stored = loadStored();

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: stored?.accessToken ?? null,
  refreshToken: stored?.refreshToken ?? null,
  user: stored?.user ?? null,
  setSession: (session) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } catch {
      // Private browsing / storage disabled — session still works for this tab.
    }
    set({ accessToken: session.accessToken, refreshToken: session.refreshToken, user: session.user });
  },
  clearSession: () => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    set({ accessToken: null, refreshToken: null, user: null });
  },
}));
