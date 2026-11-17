import axios from "axios";

export const api = axios.create({
  baseURL: "/api"
});

api.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 && !error.config?.url?.startsWith("/auth/")) {
    window.location.reload();
  }
  return Promise.reject(error);
});
