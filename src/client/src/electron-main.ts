"""
Electron 主进程 — AI-CAD 桌面应用
"""
import { app, BrowserWindow, Menu, ipcMain } from 'electron';
import * as path from 'path';
import * as url from 'url';

let mainWindow: BrowserWindow | null = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 768,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    title: 'AI-CAD 智能体施工图深化系统',
  });

  // 开发模式加载本地服务器
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    // 生产模式加载打包后的文件
    mainWindow.loadURL(url.format({
      pathname: path.join(__dirname, '../dist/index.html'),
      protocol: 'file:',
      slashes: true,
    }));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ─── IPC Handlers ──────────────────────────────────────────────

function registerIPCHandlers() {
  // 健康检查
  ipcMain.handle('health:check', async () => {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      phase: 'Phase 0',
    };
  });

  // Agent 状态
  ipcMain.handle('agent:status', async () => {
    return {
      currentStep: 'idle',
      isRunning: false,
      pendingConfirmations: [],
    };
  });

  // 规则列表
  ipcMain.handle('rules:list', async () => {
    return [
      { id: 'residential-door-main-width', name: '户门宽度', code: 'GB 50096-2011' },
      { id: 'residential-door-interior-width', name: '户内门宽度', code: 'GB 50096-2011' },
      { id: 'residential-window-sill-height', name: '窗台高度', code: 'GB 50096-2011' },
    ];
  });

  // RAG 知识库检索
  ipcMain.handle('rag:search', async (_event, query: string) => {
    // TODO: 集成真实 RAG 检索
    return {
      query,
      results: [],
      count: 0,
    };
  });
}

// ─── Menu ──────────────────────────────────────────────────────

function createMenu() {
  const template: any = [
    {
      label: '文件',
      submenu: [
        { label: '打开 DWG', accelerator: 'CmdOrCtrl+O', click: () => {} },
        { label: '导出 DWG', accelerator: 'CmdOrCtrl+E', click: () => {} },
        { type: 'separator' },
        { label: '退出', accelerator: 'CmdOrCtrl+Q', click: () => app.quit() },
      ],
    },
    {
      label: '视图',
      submenu: [
        { label: '刷新', accelerator: 'CmdOrCtrl+R', click: () => mainWindow?.reload() },
        { label: '切换开发者工具', accelerator: 'F12', click: () => mainWindow?.webContents.toggleDevTools() },
      ],
    },
    {
      label: '帮助',
      submenu: [
        { label: '关于 AI-CAD', click: () => {
          const { dialog } = require('electron');
          dialog.showMessageBox({
            title: '关于 AI-CAD',
            message: 'AI辅助施工图深化系统 v0.1.0',
            detail: '规则引擎保准确 + LLM保灵活 + 人在回路保可控',
          });
        }},
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

// ─── App Lifecycle ─────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();
  createMenu();
  registerIPCHandlers();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

export { mainWindow };
