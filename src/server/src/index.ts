"""
AI-CAD 后端服务入口
Express + TypeScript，提供 HTTP API 和 MCP 接口
"""
import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import winston from "winston";

dotenv.config();

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || "info",
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      ),
    }),
  ],
});

const app = express();
const PORT = parseInt(process.env.SERVER_PORT || "3456");

app.use(cors());
app.use(express.json());

// ─── Health Check ───────────────────────────────────────────────
app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    timestamp: new Date().toISOString(),
    version: "0.1.0",
  });
});

// ─── API Routes (Phase 0 stubs) ─────────────────────────────────
app.get("/api/status", (_req, res) => {
  res.json({
    phase: "Phase 0",
    stage: "技术预研",
    modules: {
      server: "running",
      agents: "initialized",
      rules: "loading",
      rag: "initializing",
    },
  });
});

// ─── Design API (MVP scope) ─────────────────────────────────────
app.post("/api/designs", (_req, res) => {
  res.status(200).json({
    message: "设计任务已提交",
    taskId: "demo-task-001",
    status: "pending",
  });
});

app.get("/api/designs/:id", (_req, res) => {
  res.json({
    id: _req.params.id,
    status: "awaiting_confirmation",
    currentStep: "cad_execute",
    pendingConfirmations: [
      { step: "cad_execute", message: "墙体生成完成，请确认" },
    ],
  });
});

// ─── Rules API ──────────────────────────────────────────────────
app.get("/api/rules/residential/doors", (_req, res) => {
  res.json([
    {
      id: "door-001",
      name: "户内门宽度",
      rule: "户内门宽度不应小于 0.9m",
      code_ref: "GB 50096-2011 第5.8.6条",
    },
    {
      id: "door-002",
      name: "卫生间门宽度",
      rule: "卫生间门宽度不应小于 0.8m",
      code_ref: "GB 50096-2011 第5.8.6条",
    },
  ]);
});

// ─── Start ──────────────────────────────────────────────────────
app.listen(PORT, () => {
  logger.info(`AI-CAD Server running on http://localhost:${PORT}`);
  logger.info(`Phase: ${process.env.PHASE || "0"}`);
});

export { app, logger };
