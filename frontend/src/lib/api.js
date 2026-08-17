import axios from "axios";
axios.defaults.withCredentials = true;
export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const api = axios.create({ baseURL: API, withCredentials: true });
export const cx = (...parts) => parts.filter(Boolean).join(" ");
