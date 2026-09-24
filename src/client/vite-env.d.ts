/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** GUI 引擎桥地址 (默认 http://127.0.0.1:8642, 可用 VITE_API 覆写) */
  readonly VITE_API?: string;
}
