import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

const configured = import.meta.env.VITE_BACKEND_URL as string | undefined;
const BACKEND_URL = configured || "http://localhost:8000";
export const API = `${BACKEND_URL.replace(/\/$/, "")}/api`;
const api = axios.create({ baseURL: API, timeout: 60_000, withCredentials: true });

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
