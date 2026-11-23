import axios from "axios";

// Token storage. Access token: short-lived; refresh token: rotated on every use.
const ACCESS_KEY = "acc.access_token";
const REFRESH_KEY = "acc.refresh_token";

export const tokenStore = {
  get access() {
    return safeGet(ACCESS_KEY);
  },
  get refresh() {
    return safeGet(REFRESH_KEY);
  },
  set({ access_token, refresh_token }) {
    safeSet(ACCESS_KEY, access_token);
    safeSet(REFRESH_KEY, refresh_token);
  },
  clear() {
    safeRemove(ACCESS_KEY);
    safeRemove(REFRESH_KEY);
  },
};

function safeGet(k) {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
}
function safeSet(k, v) {
  try {
    localStorage.setItem(k, v);
  } catch {
    /* storage unavailable: session lasts until reload */
  }
}
function safeRemove(k) {
  try {
    localStorage.removeItem(k);
  } catch {
    /* ignore */
  }
}

export const api = axios.create({ baseURL: "/api", timeout: 30000 });

api.interceptors.request.use((config) => {
  const token = tokenStore.access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Called when refresh fails; AuthContext registers a handler that logs the user out.
let onAuthLost = () => {};
export function setAuthLostHandler(fn) {
  onAuthLost = fn;
}

// One shared refresh request, so parallel 401s don't each rotate the token
// (a second rotation of the same token would be treated as token theft).
let refreshPromise = null;
async function refreshTokens() {
  if (!refreshPromise) {
    const refresh_token = tokenStore.refresh;
    refreshPromise = (async () => {
      if (!refresh_token) throw new Error("no refresh token");
      const { data } = await axios.post("/api/auth/refresh", { refresh_token });
      tokenStore.set(data);
      return data;
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    // Credential endpoints report their own 401s; /auth/me is a normal protected call.
    const isAuthCall = /^\/auth\/(login|register|refresh|logout)$/.test(original?.url || "");
    if (status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      try {
        await refreshTokens();
        return api(original);
      } catch (refreshError) {
        // Only a rejected refresh token ends the session; network errors keep it.
        const s = refreshError.response?.status;
        if (refreshError.message === "no refresh token" || s === 401 || s === 403) {
          tokenStore.clear();
          onAuthLost();
        }
      }
    }
    return Promise.reject(error);
  }
);

// Turn any API error into one readable sentence for the UI.
export function errorMessage(error, fallback = "Something went wrong. Please try again.") {
  if (!error?.response) return "Cannot reach the server. Is the backend running on port 8000?";
  const data = error.response.data;
  if (data?.errors?.length) {
    return data.errors.map((e) => (e.field ? `${e.field}: ${e.message}` : e.message)).join(" · ");
  }
  if (typeof data?.detail === "string") return data.detail;
  return fallback;
}
