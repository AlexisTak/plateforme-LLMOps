"use client";

import { useState } from "react";
import { humanError } from "@/lib/errors";
import { useToast } from "@/components/toast";

export function useAction<Args extends unknown[], R>(
  fn: (...args: Args) => Promise<R>,
  opts?: { success?: string | ((result: R) => string) },
) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const run = async (...args: Args): Promise<R | undefined> => {
    if (busy) return undefined;
    setBusy(true);
    setError(null);
    try {
      const result = await fn(...args);
      if (opts?.success) toast(typeof opts.success === "function" ? opts.success(result) : opts.success, "success");
      return result;
    } catch (e) {
      const message = humanError(e);
      setError(message);
      toast(message, "error");
      return undefined;
    } finally {
      setBusy(false);
    }
  };

  return { run, busy, error };
}
