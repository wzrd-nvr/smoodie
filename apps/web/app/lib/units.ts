/**
 * The measurement vocabulary the composer offers.
 *
 * This mirrors `apps/api/src/smoodie_api/services/units.py`, which is the
 * authority — the API rejects anything outside it. The duplication is
 * deliberate: a <select> has to be rendered before any request is made, and
 * fetching a vocabulary that changes a few times a year on every page load
 * would be worse. `units.test.ts` reads the Python source and fails if the two
 * ever drift, so the copy cannot rot quietly.
 */

export const UNIT_GROUPS: ReadonlyArray<{
  label: string;
  units: readonly string[];
}> = [
  { label: "Volume", units: ["tsp", "tbsp", "cup", "ml", "l", "fl oz", "pint", "quart", "gallon"] },
  { label: "Weight", units: ["g", "kg", "oz", "lb"] },
  {
    label: "Count",
    units: [
      "count",
      "clove",
      "slice",
      "sprig",
      "bunch",
      "can",
      "package",
      "pinch",
      "dash",
    ],
  },
];

export const CANONICAL_UNITS: readonly string[] = UNIT_GROUPS.flatMap((g) => g.units);

export function isKnownUnit(value: string): boolean {
  return CANONICAL_UNITS.includes(value);
}
