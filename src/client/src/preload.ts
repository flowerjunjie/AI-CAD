/**
 * Electron Preload Script
 * 暴露安全 API 给渲染进程
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // 健康检查
  healthCheck: () => ipcRenderer.invoke('health:check'),

  // Agent 状态
  getAgentStatus: () => ipcRenderer.invoke('agent:status'),

  // 规则列表
  listRules: () => ipcRenderer.invoke('rules:list'),

  // RAG 检索
  searchKnowledge: (query: string) => ipcRenderer.invoke('rag:search', query),

  // 文件操作
  openFile: () => ipcRenderer.invoke('file:open'),
  saveFile: (path: string) => ipcRenderer.invoke('file:save', path),
});
