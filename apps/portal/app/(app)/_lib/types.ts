"use client";

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scope: "prod" | "dev";
  model: string;
  rate: string;
  expires: string;
  calls7d: number;
  lastUsed: string;
  status: "active" | "expiring" | "revoked";
  daysToExpiry?: number;
}

export interface Request {
  time: string;
  model: string;
  status: "200" | "429" | "503";
  tokensIn: number;
  tokensOut: number;
  cost: number | null;
  cached?: boolean;
}

export interface Session {
  id: string;
  type: "playground" | "agent" | "prompt";
  label: string;
  model?: string;
  turns?: number;
  tool?: string;
  timeAgo: string;
  description: string;
}

export interface Model {
  id: string;
  name: string;
  provider: "Anthropic" | "Google" | "Azure OpenAI" | "OpenAI" | "Self-hosted";
  providerShort: string;
  logoColor: string;
  logoText: string;
  description: string;
  context: string;
  priceIn?: string;
  priceOut?: string;
  priceFlat?: string;
  caps: string[];
  status: "healthy" | "degraded" | "down";
  note?: string;
  fallback?: string;
  requiresScope?: string;
  errorRate?: string;
}

export interface PromptTemplate {
  id: string;
  title: string;
  version: string;
  versionPill: "pill--info" | "";
  description: string;
  preview: string;
  author: string;
  uses?: number;
  lastEdited?: string;
  model?: string;
  stars?: number;
  mine?: boolean;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  tools: number;
  model: string;
  status: "running" | "scheduled" | "draft";
  lastRun?: string;
  successRate?: string;
}

export interface AgentStep {
  type: "plan" | "tool" | "pending";
  label: string;
  tool?: string;
  time?: string;
  duration?: string;
  body?: string;
  running?: boolean;
}

export interface McpServer {
  id: string;
  name: string;
  description: string;
  type: "internal" | "vendored";
  version: string;
  maintainer: string;
  tools: number;
  calls24h: number;
  p50: string;
  transport: "stdio" | "http+sse" | "http";
  status: "healthy" | "degraded" | "auth failing";
  markBg: string;
  markText: string;
  logoLetters: string;
  endpoint?: string;
  image?: string;
  auth?: string;
  scopes?: string;
  owners?: string;
  toolList?: McpTool[];
}

export interface McpTool {
  name: string;
  args: string;
  description: string;
  cap: "read" | "write";
}

export interface Skill {
  id: string;
  name: string;
  version: string;
  model: string;
  description: string;
  tools: number;
  usesPerWeek: number;
  stars: number;
  variant: "s-purple" | "s-teal" | "s-pink" | "s-blue" | "s-amber";
  iconPath: string;
}

export interface Plugin {
  id: string;
  name: string;
  by: string;
  category: string;
  description: string;
  stars: number;
  installs: number;
  logoLetters: string;
  logoCss: string;
  installed: boolean;
}

export interface ChatMessage {
  id: string;
  role: "system" | "user" | "assistant";
  content: string;
  model?: string;
  tokensIn?: number;
  tokensOut?: number;
  cost?: number;
  latency?: string;
  streaming?: boolean;
  toolCalls?: ToolCall[];
}

export interface ToolCall {
  name: string;
  args: string;
  result: string;
  latencyMs: number;
}
