export enum OrbStatus {
  idle = "idle",
  listening = "listening",
  thinking = "thinking",
  speaking = "speaking",
  error = "error",
  connecting = "connecting",
}

export interface JarvisWSMessage {
  status: OrbStatus;
  message?: string | null;
  audio_url?: string | null;
  data?: unknown;
  ts: number;
  source?: string | null;
  task_id?: string | null;
}
