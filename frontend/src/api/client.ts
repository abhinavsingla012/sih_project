import axios from 'axios';
export const api = axios.create({baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`, withCredentials: true});
api.interceptors.request.use(config => {
  const token = document.cookie.split('; ').find(v => v.startsWith('samanvay_csrf='))?.split('=')[1];
  if (token) config.headers['X-CSRF-Token'] = decodeURIComponent(token);
  return config;
});
export const errorMessage = (error: any) => error?.response?.data?.error?.message || error?.userMessage || 'Something went wrong. Please try again.';
export const get = async (path: string) => (await api.get(path)).data;