import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

// Environment variable OR explicit fallback - both options checked
const configured = import.meta.env.VITE_BACKEND_URL as string | undefined;
const BACKEND_URL = configured || "https://green-papaya-backend.onrender.com";

console.log("[API] VITE_BACKEND_URL env:", import.meta.env.VITE_BACKEND_URL);
console.log("[API] Using backend URL:", BACKEND_URL);

export const API = `${BACKEND_URL.replace(/\/$/, "")}/api`;
console.log("[API] Full API base URL:", API);

const api = axios.create({ baseURL: API, timeout: 60_000, withCredentials: true });

api.interceptors.request.use((config) => {
  const token = typeof window !== "undefined" ? localStorage.getItem("gp_access_token") : null;
  if (token && !config.headers["Authorization"]) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  console.log("[API] Request:", config.method?.toUpperCase(), config.url);
  return config;
});

api.interceptors.response.use(
  (response) => {
    console.log("[API] Response:", response.status, response.config.url);
    return response;
  },
  (error: AxiosError) => {
    console.error("[API] Error:", error.message, error.config?.url);
    if (error.response) {
      console.error("[API] Response data:", error.response.data);
    }
    return Promise.reject(error);
  }
);

let refreshPromise: Promise<void> | null = null;
async function refreshSession(): Promise<void> {
  const refreshToken = typeof window !== "undefined" ? localStorage.getItem("gp_refresh_token") : null;
  const headers = refreshToken ? { Authorization: `Bearer ${refreshToken}` } : {};
  const { data } = await axios.post<{ access_token?: string; refresh_token?: string }>(
    `${API}/auth/refresh`,
    {},
    { headers, withCredentials: true, timeout: 30_000 }
  );
  if (data?.access_token) {
    localStorage.setItem("gp_access_token", data.access_token);
    api.defaults.headers.common["Authorization"] = `Bearer ${data.access_token}`;
  }
  if (data?.refresh_token) {
    localStorage.setItem("gp_refresh_token", data.refresh_token);
  }
}

api.interceptors.response.use(undefined, async (error: AxiosError) => {
  const config = error.config as (InternalAxiosRequestConfig & {_retried?: boolean}) | undefined;
  // Endpoints where a 401 is an expected/terminal answer and must NOT trigger a
  // refresh+redirect. `/auth/me` is the initial "am I logged in?" probe — a 401
  // there simply means "not logged in", handled by AuthContext.
  const url = config?.url ?? "";
  const isAuthProbeOrEntry = Boolean(
    url.includes("/auth/refresh") ||
    url.includes("/auth/login") ||
    url.includes("/auth/bootstrap") ||
    url.includes("/auth/me")
  );
  if (error.response?.status === 401 && config && !config._retried && !isAuthProbeOrEntry) {
    config._retried = true;
    try {
      refreshPromise ||= refreshSession().finally(() => { refreshPromise = null; });
      await refreshPromise;
      return api(config);
    } catch {
      // Session truly expired mid-use. Send the user back to login, but never
      // reload if we are already on the login page — that is what caused the
      // infinite reload loop.
      if (window.location.pathname !== "/") {
        window.location.assign("/");
      }
    }
  }
  return Promise.reject(error);
});

export default api;
