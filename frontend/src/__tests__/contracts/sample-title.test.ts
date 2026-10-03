import { describe, expect, it } from "vitest";
import { mockApi, prototypeControls } from "@/mocks/mock-api";

describe("sample records and the case title", () => {
  it("keeps the title the person chose when sample reports are added", async () => {
    const created = await mockApi.createCase({ intent: "Understanding my treatment", concern: "A procedure was recommended.", ageYears: 52, sex: "F" });
    const before = (await mockApi.getCase(created.id))!.title;
    await prototypeControls.attachSampleRecords(created.id, "cardiology");
    const after = await mockApi.getCase(created.id);
    expect(after!.title).toBe(before);
    expect(after!.documentCount).toBeGreaterThan(0);
  });
});
