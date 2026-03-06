import { useState, useEffect, useRef, useCallback } from 'react';
import { buildWsUrl } from '../config';

const RECONNECT_DELAY = 2000;

export function useWebSocket(accessToken, onUnauthorized) {
  const [state, setState] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(function connectSocket() {
    if (!accessToken) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(buildWsUrl("/ws", accessToken));

    ws.onopen = () => {
      setConnected(true);
      console.log('[WS] Connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setState(data);
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    ws.onclose = (event) => {
      setConnected(false);
      if (event.code === 4401) {
        console.warn('[WS] Unauthorized');
        if (onUnauthorized) {
          Promise.resolve(onUnauthorized()).catch(() => {});
        }
        return;
      }
      console.log('[WS] Disconnected — reconnecting...');
      reconnectTimer.current = setTimeout(connectSocket, RECONNECT_DELAY);
    };

    ws.onerror = (err) => {
      console.error('[WS] Error:', err);
      ws.close();
    };

    wsRef.current = ws;
  }, [accessToken, onUnauthorized]);

  useEffect(() => {
    setState(null);
    setConnected(false);
    clearTimeout(reconnectTimer.current);
    wsRef.current?.close();
    if (!accessToken) return undefined;

    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect, accessToken]);

  const sendMessage = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { state, connected, sendMessage };
}
