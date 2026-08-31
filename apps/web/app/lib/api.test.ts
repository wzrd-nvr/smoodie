import { describe, expect, test } from "vitest";
import { parseApiError } from "./api.server";

describe("parseApiError", () => {
  test("passes through a plain string detail", () => {
    const error = parseApiError(409, { detail: "That username is already taken." });
    expect(error.message).toBe("That username is already taken.");
    expect(error.fieldErrors).toEqual({});
  });

  test("addresses validation errors to their field", () => {
    const error = parseApiError(422, {
      detail: [
        { loc: ["body", "username"], msg: "Usernames need at least 3 characters." },
      ],
    });
    expect(error.fieldErrors.username).toBe("Usernames need at least 3 characters.");
    expect(error.message).toBe("Usernames need at least 3 characters.");
  });

  test("keeps the first error per field when several are reported", () => {
    const error = parseApiError(422, {
      detail: [
        { loc: ["body", "username"], msg: "first" },
        { loc: ["body", "username"], msg: "second" },
        { loc: ["body", "bio"], msg: "bio problem" },
      ],
    });
    expect(error.fieldErrors).toEqual({ username: "first", bio: "bio problem" });
  });

  test("survives a body that is not shaped like an API error", () => {
    const error = parseApiError(400, null);
    expect(error.message).toBeTruthy();
    expect(error.fieldErrors).toEqual({});
  });

  test("does not blame the user for a server fault", () => {
    const error = parseApiError(500, {});
    expect(error.message).toMatch(/problem/i);
  });

  test("ignores numeric loc entries that are not field names", () => {
    const error = parseApiError(422, { detail: [{ loc: ["body", 0], msg: "x" }] });
    expect(error.fieldErrors).toEqual({});
  });
});
