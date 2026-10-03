/**
 * Trailing-edge debounce for text that is saved while typing. `flush()` writes
 * any pending value immediately (blur, unmount); `cancel()` drops it.
 */
export interface DebouncedSaver<T> {
  schedule(value: T): void;
  flush(): void;
  cancel(): void;
}

export function createDebouncedSaver<T>(save: (value: T) => void, delayMs: number): DebouncedSaver<T> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending: { value: T } | null = null;

  const run = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    if (pending) {
      const { value } = pending;
      pending = null;
      save(value);
    }
  };

  return {
    schedule(value) {
      pending = { value };
      if (timer) clearTimeout(timer);
      timer = setTimeout(run, delayMs);
    },
    flush: run,
    cancel() {
      if (timer) clearTimeout(timer);
      timer = null;
      pending = null;
    },
  };
}
