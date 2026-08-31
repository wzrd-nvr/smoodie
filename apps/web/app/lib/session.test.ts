import { describe, expect, test } from "vitest";
import { safeRedirect } from "./session.server";

describe("safeRedirect", () => {
  test("allows same-origin paths", () => {
    expect(safeRedirect("/settings/profile")).toBe("/settings/profile");
  });

  test("falls back when nothing was supplied", () => {
    expect(safeRedirect(null)).toBe("/");
    expect(safeRedirect(null, "/home")).toBe("/home");
  });

  test.each([
    ["https://evil.example.com/steal", "absolute url"],
    ["//evil.example.com", "protocol-relative url"],
    ["http://evil.example.com", "plain http host"],
  ])("refuses to bounce to %s (%s)", (target) => {
    expect(safeRedirect(target)).toBe("/");
  });

  test("ignores non-string form values", () => {
    expect(safeRedirect(new File([], "x"))).toBe("/");
  });
});
