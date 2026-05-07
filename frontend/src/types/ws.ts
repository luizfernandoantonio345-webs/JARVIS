/**
 * Canonical WebSocket types for JARVIS v5.0.
 * SINGLE SOURCE OF TRUTH — mirror of backend/schemas/ws_messages.py.
 * Any change here must be reflected in the Python schema and vice-versa.
 */

/** All valid Orb states. Must match Python OrbStatus enum exactly. */
export enum OrbStatus {
  idle       = "idle",
  listening  = "listening",
  thinking   = "thinking",
  speaking   = "speaking",
  error      = "error",
  connecting = "connecting",  // frontend-only transient state
}

export type OrbStatusString = keyof typeof OrbStatus;

/** Severity levels for security findings reported by the Sentinel. */
export type RiskSeverity = "critical" | "high" | "medium";

/** A single security finding from the JARVIS Sentinel. */
export interface RiskFinding {
  file    : string;
  line    : number;
  pattern : string;
  severity: RiskSeverity;
  snippet : string;
}

/** Arbitrary data payload carried by a WS message. */
export interface JarvisWSData {
  findings?: RiskFinding[];
  [key: string]: unknown;
}

/**
 * Canonical WebSocket message shape.
 * Every message received from /ws/jarvis conforms to this interface.
 */
export interface JarvisWSMessage {
  status   : OrbStatus;
  message ?: string;
  audio_url?: string;
  data    ?: JarvisWSData;
  ts      ?: number;        // Unix timestamp (seconds, UTC)
  source  ?: string;        // originating agent/component
  task_id ?: string;
}

/** Type guard — validates that an unknown value is a JarvisWSMessage */
export function isJarvisWSMessage(value: unknown): value is JarvisWSMessage {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  const validStatuses = Object.values(OrbStatus) as string[];
  return typeof v.status === "string" && validStatuses.includes(v.status);
}
