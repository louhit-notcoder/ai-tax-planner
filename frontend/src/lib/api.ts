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
  await axios.post(`${API}/auth/refresh`, {}, { withCredentials: true, timeout: 30_000 });
}

api.interceptors.response.use(undefined, async (error: AxiosError) => {
  const config = error.config as (InternalAxiosRequestConfig & {_retried?: boolean}) | undefined;
  const isRefreshOrLogin = Boolean(config?.url?.includes("/auth/refresh") || config?.url?.includes("/auth/login") || config?.url?.includes("/auth/bootstrap"));
  if (error.response?.status === 401 && config && !config._retried && !isRefreshOrLogin) {
    config._retried = true;
    try {
      refreshPromise ||= refreshSession().finally(() => { refreshPromise = null; });
      await refreshPromise;
      return api(config);
    } catch {
      window.location.assign("/");
    }
  }
  return Promise.reject(error);
});

export default api;
