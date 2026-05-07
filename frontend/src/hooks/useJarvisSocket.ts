import { useEffect, useState, useCallback, useRef } from 'react';
import { OrbStatus, isJarvisWSMessage } from '../types/ws';
import type { JarvisWSMessage } from '../types/ws';

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? 'ws://localhost:8000/ws/jarvis';
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS  = 30_000;

export type ConnectionState = 'connecting' | 'connected' | 'disconnected';

export interface UseJarvisSocketReturn {
  data      : JarvisWSMessage;
  connState : ConnectionState;
  connected : boolean;
  send      : (text: string) => void;
}

export const useJarvisSocket = (): UseJarvisSocketReturn => {
  const [data, setData]           = useState<JarvisWSMessage>({ status: OrbStatus.idle });
  const [connState, setConnState] = useState<ConnectionState>('connecting');

  const socketRef      = useRef<WebSocket | null>(null);
  const attemptRef     = useRef(0);
  const unmountedRef   = useRef(false);
  const reconnTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;
    setConnState('connecting');
    const ws = new WebSocket(WS_URL);
    socketRef.current = ws;

    ws.onopen = () => {
      setConnState('connected');
      attemptRef.current = 0;
      console.info('[JARVIS WS] connected');
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const raw: unknown = JSON.parse(event.data as string);
        if (isJarvisWSMessage(raw)) {
          setData(raw);
        } else {
          console.warn('[JARVIS WS] invalid schema ignored:', raw);
        }
      } catch (err) {
        console.warn('[JARVIS WS] unparseable message:', event.data, err);
      }
    };

    ws.onclose = () => {
      setConnState('disconnected');
      if (!unmountedRef.current) {
        const attempt  = ++attemptRef.current;
        const expDelay = Math.min(BASE_DELAY_MS * Math.pow(2, attempt - 1), MAX_DELAY_MS);
        const jitter   = Math.random() * 1_000;
        const delay    = Math.round(expDelay + jitter);
        console.warn(`[JARVIS WS] disconnected. Reconnect #${attempt} in ${delay}ms`);
        reconnTimerRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      setConnState('disconnected');
    };
  }, []);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      if (reconnTimerRef.current) clearTimeout(reconnTimerRef.current);
      socketRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((text: string) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(text);
    } else {
      console.warn('[JARVIS WS] send() called while not connected');
    }
  }, []);

  return { data, connState, connected: connState === 'connected', send };
};
