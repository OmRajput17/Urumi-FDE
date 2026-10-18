import { useCallback, useEffect, useRef, useState } from "react";

// Load data now, then again every `ms` milliseconds. Changing `dep` reloads at once.
// Only the newest response is kept, so a slow old request cannot overwrite a newer one.
export function usePoll(load, ms, dep) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  const loadRef = useRef(load);
  const alive = useRef(true);
  const seq = useRef(0);

  useEffect(() => {
    loadRef.current = load;
  });
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    const id = ++seq.current;
    try {
      const data = await loadRef.current();
      if (alive.current && id === seq.current) setState({ data, error: "", loading: false });
    } catch (e) {
      if (alive.current && id === seq.current) setState((s) => ({ ...s, error: e.message, loading: false }));
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, ms);
    return () => clearInterval(timer);
  }, [refresh, ms, dep]);

  return { ...state, refresh };
}