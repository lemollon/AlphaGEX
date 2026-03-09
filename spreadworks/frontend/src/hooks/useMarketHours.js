import { useState, useEffect, useRef } from 'react';

export function isMarketOpen() {
  const et = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const day = et.getDay(); // 0=Sun, 6=Sat
  const mins = et.getHours() * 60 + et.getMinutes();
  return day >= 1 && day <= 5 && mins >= 570 && mins < 960; // 9:30-16:00
}

export function getMarketStatusText() {
  const et = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const day = et.getDay();
  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${dayNames[day]} ${monthNames[et.getMonth()]} ${et.getDate()}`;
}

/**
 * Hook that tracks market open/closed state and seconds since last refresh.
 */
export default function useMarketHours() {
  const [open, setOpen] = useState(isMarketOpen);
  const [secondsAgo, setSecondsAgo] = useState(0);
  const lastRefreshRef = useRef(Date.now());

  // Check market status every 30s
  useEffect(() => {
    const timer = setInterval(() => {
      setOpen(isMarketOpen());
    }, 30000);
    return () => clearInterval(timer);
  }, []);

  // Count up seconds since last refresh
  useEffect(() => {
    const timer = setInterval(() => {
      setSecondsAgo(Math.floor((Date.now() - lastRefreshRef.current) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const markRefreshed = () => {
    lastRefreshRef.current = Date.now();
    setSecondsAgo(0);
  };

  return { isOpen: open, secondsAgo, markRefreshed, statusText: getMarketStatusText() };
}
