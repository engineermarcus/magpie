import { useState, useEffect } from "react";

export function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function useToast() {
  const [toast, setToast] = useState(null);
  const show = (msg, type = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };
  return { toast, showToast: show };
}

export function useJobPoller(jobKey, onDone, onError) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!jobKey) return;
    let cancelled = false;

    const poll = async () => {
      while (!cancelled) {
        try {
          const res = await fetch("/api/jobs");
          const jobs = await res.json();
          const job = jobs[jobKey] || null;
          if (!cancelled) setStatus(job);
          if (job?.status === "done") { onDone?.(); break; }
          if (job?.status === "error") { onError?.(job.error); break; }
        } catch (e) {
          // silently retry
        }
        await new Promise(r => setTimeout(r, 2000));
      }
    };

    poll();
    return () => { cancelled = true; };
  }, [jobKey]);

  return status;
}
