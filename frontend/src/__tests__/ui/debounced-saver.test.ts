import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createDebouncedSaver } from "@/lib/debounced-saver";

describe("createDebouncedSaver", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("writes once after typing pauses, with the latest value", () => {
    const save = vi.fn();
    const s = createDebouncedSaver<string>(save, 500);
    s.schedule("a");
    vi.advanceTimersByTime(200);
    s.schedule("ab");
    vi.advanceTimersByTime(200);
    s.schedule("abc");
    expect(save).not.toHaveBeenCalled();
    vi.advanceTimersByTime(500);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("abc");
  });

  it("flush saves the pending value immediately and only once", () => {
    const save = vi.fn();
    const s = createDebouncedSaver<string>(save, 500);
    s.schedule("note");
    s.flush();
    s.flush();
    vi.advanceTimersByTime(1000);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("note");
  });

  it("cancel drops the pending value", () => {
    const save = vi.fn();
    const s = createDebouncedSaver<string>(save, 500);
    s.schedule("x");
    s.cancel();
    vi.advanceTimersByTime(1000);
    expect(save).not.toHaveBeenCalled();
  });
});
