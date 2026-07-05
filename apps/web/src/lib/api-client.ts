import axios from "axios";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

// Attach access token to every request
apiClient.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Token refresh queue to prevent concurrent refresh requests
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (token) resolve(token);
    else reject(error);
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If no response at all (network error / CORS block / Cloudflare challenge)
    // and the request hasn't been retried, check if token might be stale
    if (!error.response && !originalRequest._retry) {
      const token = localStorage.getItem("access_token");
      if (token) {
        // Token exists but request failed with no response — likely expired
        // and Cloudflare or network blocked it. Try refreshing once.
        originalRequest._retry = true;
        try {
          const refreshToken = localStorage.getItem("refresh_token");
          if (refreshToken) {
            const { data } = await axios.post(
              `${API_BASE_URL}/api/v1/auth/refresh`,
              { refresh_token: refreshToken }
            );
            localStorage.setItem("access_token", data.access_token);
            localStorage.setItem("refresh_token", data.refresh_token);
            originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
            return apiClient(originalRequest);
          }
        } catch {
          // Refresh also failed — redirect to login
        }
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        document.cookie = "auth_status=; path=/; max-age=0";
        window.location.href = "/login";
        return Promise.reject(error);
      }
      return Promise.reject(error);
    }

    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return apiClient(originalRequest);
      });
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const refreshToken = localStorage.getItem("refresh_token");
      if (!refreshToken) throw new Error("No refresh token");

      const { data } = await axios.post(
        `${API_BASE_URL}/api/v1/auth/refresh`,
        { refresh_token: refreshToken }
      );

      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      processQueue(null, data.access_token);

      originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
      return apiClient(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      if (typeof window !== "undefined") {
        document.cookie = "auth_status=; path=/; max-age=0";
        window.location.href = "/login";
      }
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);
