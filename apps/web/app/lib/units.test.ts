/**
 * The unit list is duplicated from the API on purpose (see `units.ts`). This is
 * what stops the copy rotting: it reads the Python source and fails the build
 * if a unit is added, removed or renamed on one side only.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { CANONICAL_UNITS, isKnownUnit, UNIT_GROUPS } from "./units";

const here = dirname(fileURLToPath(import.meta.url));
const unitsPy = join(here, "../../../api/src/smoodie_api/services/units.py");

/** The canonical unit is the dict key; the tuple after it holds the aliases,
 * which the API normalizes and the composer never offers. */
function canonicalUnitsFromPython(source: string): string[] {
  const units: string[] = [];
  for (const line of source.split("\n")) {
    const match = /^\s{4}"([^"]+)":\s*\(/.exec(line);
    if (match) units.push(match[1]);
  }
  return units;
}

describe("unit vocabulary", () => {
  const fromPython = canonicalUnitsFromPython(readFileSync(unitsPy, "utf8"));

  test("the Python source was actually parsed", () => {
    // Guards the guard: a regex that silently matches nothing would make every
    // assertion below vacuous.
    expect(fromPython.length).toBeGreaterThan(15);
    expect(fromPython).toContain("tbsp");
  });

  test("offers exactly the units the API accepts", () => {
    expect([...CANONICAL_UNITS].sort()).toEqual([...fromPython].sort());
  });

  test("no unit appears in two groups", () => {
    expect(new Set(CANONICAL_UNITS).size).toBe(CANONICAL_UNITS.length);
  });

  test("recognizes a canonical unit and rejects anything else", () => {
    expect(isKnownUnit("cup")).toBe(true);
    // An alias the API would accept is deliberately not offered: the composer
    // only ever submits canonical units.
    expect(isKnownUnit("cups")).toBe(false);
    expect(isKnownUnit("glug")).toBe(false);
    expect(isKnownUnit("")).toBe(false);
  });

  test("every group has a label and at least one unit", () => {
    for (const group of UNIT_GROUPS) {
      expect(group.label).toBeTruthy();
      expect(group.units.length).toBeGreaterThan(0);
    }
  });
});
