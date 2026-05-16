import { useEffect, useState, useCallback } from 'react';

interface AutonomyData {
  pending: number;
  status: string;
}

export const useAutonomy = () => {
  const [data, setData] = useState<AutonomyData>({ pending: 0, status: 'idle' });

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/system/heartbeat');
      const heartbeat = await res.json();
      setData({
        pending: heartbeat.autonomy_pending || 0,
        status: heartbeat.status,
      });
    } catch (e) {
      console.error('Autonomy fetch error:', e);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  return data;
};
