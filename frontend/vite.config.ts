import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发服务器层：把 API 与 WebSocket 请求代理给本地 FastAPI。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
});

