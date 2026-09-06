import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, test } from "vitest";
import {
  applyIntent,
  emptyIngredient,
  emptyStep,
  ingredientKey,
  initialState,
  mapServerErrors,
  MIN_INGREDIENTS,
  MIN_STEP_LENGTH,
  MIN_STEPS,
  parseComposerForm,
  parseIntent,
  setRowIdFactory,
  stepKey,
  toCreatePayload,
  validate,
  type ComposerState,
} from "./recipe-form";

const here = dirname(fileURLToPath(import.meta.url));
const postPy = join(here, "../../../api/src/smoodie_api/schemas/post.py");

let counter = 0;
beforeEach(() => {
  counter = 0;
  setRowIdFactory(() => `row-${(counter += 1)}`);
});

function recipe(overrides: Partial<ComposerState> = {}): ComposerState {
  return {
    ...initialState("recipe"),
    title: "A dependable weeknight loaf",
    prepMinutes: "10",
    mediaIds: ["media-1"],
    ingredients: [
      { ...emptyIngredient(), quantity: "200", unit: "g", name: "flour" },
      { ...emptyIngredient(), quantity: "300", unit: "ml", name: "water" },
    ],
    steps: [
      { ...emptyStep(), instruction: "Combine the flour and water." },
      { ...emptyStep(), instruction: "Bake until golden and firm." },
    ],
    ...overrides,
  };
}

function formFrom(entries: Array<[string, string]>): FormData {
  const form = new FormData();
  for (const [key, value] of entries) form.append(key, value);
  return form;
}

describe("listing requirements match the API", () => {
  const source = readFileSync(postPy, "utf8");

  function constantFromPython(name: string): number {
    const match = new RegExp(`^${name} = (\\d+)$`, "m").exec(source);
    if (!match) throw new Error(`${name} not found in post.py`);
    return Number(match[1]);
  }

  test("the thresholds are the same on both sides", () => {
    expect(MIN_INGREDIENTS).toBe(constantFromPython("MIN_INGREDIENTS"));
    expect(MIN_STEPS).toBe(constantFromPython("MIN_STEPS"));
    expect(MIN_STEP_LENGTH).toBe(constantFromPython("MIN_STEP_LENGTH"));
  });
});

describe("row intents", () => {
  test("adds a row to the end", () => {
    const next = applyIntent(recipe(), { kind: "add", list: "ing" });
    expect(next.ingredients).toHaveLength(3);
    expect(next.ingredients[2].name).toBe("");
  });

  test("removes the named row and keeps the others in order", () => {
    const state = applyIntent(recipe(), { kind: "add", list: "ing" });
    const next = applyIntent(state, { kind: "remove", list: "ing", index: 0 });
    expect(next.ingredients.map((r) => r.name)).toEqual(["water", ""]);
  });

  test("blanks rather than removes when at the minimum", () => {
    const next = applyIntent(recipe(), { kind: "remove", list: "ing", index: 0 });
    expect(next.ingredients).toHaveLength(MIN_INGREDIENTS);
    expect(next.ingredients[0].name).toBe("");
    expect(next.ingredients[1].name).toBe("water");
  });

  test("reorders rows", () => {
    const next = applyIntent(recipe(), { kind: "move", list: "ing", index: 1, direction: -1 });
    expect(next.ingredients.map((r) => r.name)).toEqual(["water", "flour"]);
  });

  test("moving past either end changes nothing", () => {
    const state = recipe();
    expect(applyIntent(state, { kind: "move", list: "ing", index: 0, direction: -1 })).toEqual(
      state,
    );
    expect(applyIntent(state, { kind: "move", list: "step", index: 1, direction: 1 })).toEqual(
      state,
    );
  });

  test("a row keeps its id when its neighbours move", () => {
    // The id is what lets React move the input instead of rewriting it; if it
    // changed on reorder, the typed value would follow the position, not the row.
    const state = recipe();
    const waterId = state.ingredients[1].id;
    const next = applyIntent(state, { kind: "move", list: "ing", index: 1, direction: -1 });
    expect(next.ingredients[0].id).toBe(waterId);
  });

  test("switching type keeps what was already typed", () => {
    const next = applyIntent(recipe(), { kind: "switch", to: "discussion" });
    expect(next.kind).toBe("discussion");
    expect(next.title).toBe("A dependable weeknight loaf");
    expect(next.ingredients).toHaveLength(2);
  });
});

describe("parseIntent", () => {
  test.each([
    ["add-ing", { kind: "add", list: "ing" }],
    ["remove-step:2", { kind: "remove", list: "step", index: 2 }],
    ["up-ing:1", { kind: "move", list: "ing", index: 1, direction: -1 }],
    ["down-step:0", { kind: "move", list: "step", index: 0, direction: 1 }],
    ["draft", { kind: "save", status: "draft" }],
    ["switch-recipe", { kind: "switch", to: "recipe" }],
  ])("reads %s", (raw, expected) => {
    expect(parseIntent(raw)).toEqual(expected);
  });

  test("anything unrecognized publishes rather than silently doing nothing", () => {
    expect(parseIntent(null)).toEqual({ kind: "save", status: "published" });
    expect(parseIntent("publish")).toEqual({ kind: "save", status: "published" });
  });
});

describe("parseComposerForm", () => {
  test("reads rows back out of a submitted form", () => {
    const state = parseComposerForm(
      formFrom([
        ["kind", "recipe"],
        ["title", "  Spaced  out  title "],
        ["ing.0.id", "a"],
        ["ing.0.quantity", "2"],
        ["ing.0.unit", "cup"],
        ["ing.0.name", "flour"],
        ["ing.1.id", "b"],
        ["ing.1.name", "salt"],
        ["ing.1.to_taste", "on"],
        ["step.0.id", "c"],
        ["step.0.instruction", "Mix them together well."],
        ["step.1.id", "d"],
        ["step.1.instruction", "Bake until golden."],
        ["media_ids", "m1"],
        ["media_ids", "m2"],
        ["dietary", "vegan"],
      ]),
    );

    expect(state.title).toBe("Spaced out title");
    expect(state.ingredients).toHaveLength(2);
    expect(state.ingredients[0]).toMatchObject({ id: "a", quantity: "2", unit: "cup" });
    expect(state.ingredients[1].toTaste).toBe(true);
    expect(state.ingredients[0].toTaste).toBe(false);
    expect(state.mediaIds).toEqual(["m1", "m2"]);
    expect(state.dietaryTags).toEqual(["vegan"]);
    expect(state.steps.map((s) => s.id)).toEqual(["c", "d"]);
  });

  test("counts rows from the keys present, not from a claimed total", () => {
    const state = parseComposerForm(
      formFrom([
        ["kind", "recipe"],
        ["ing.0.name", "a"],
        ["ing.1.name", "b"],
        ["ing.2.name", "c"],
      ]),
    );
    expect(state.ingredients.map((r) => r.name)).toEqual(["a", "b", "c"]);
  });

  test("an empty form still yields the minimum rows to fill in", () => {
    const state = parseComposerForm(formFrom([["kind", "recipe"]]));
    expect(state.ingredients).toHaveLength(MIN_INGREDIENTS);
    expect(state.steps).toHaveLength(MIN_STEPS);
  });
});

describe("validate", () => {
  const published = { status: "published" } as const;

  test("accepts a complete recipe", () => {
    expect(validate(recipe(), published)).toEqual({});
  });

  test("asks how much, naming the ingredient", () => {
    const state = recipe();
    state.ingredients[0] = { ...state.ingredients[0], quantity: "", unit: "" };
    expect(validate(state, published)[ingredientKey(0)]).toBe(
      "How much flour? Give an amount, or mark it as to taste.",
    );
  });

  test("accepts a to-taste ingredient with no amount at all", () => {
    const state = recipe();
    state.ingredients[0] = {
      ...state.ingredients[0],
      quantity: "",
      unit: "",
      toTaste: true,
    };
    expect(validate(state, published)).toEqual({});
  });

  test("asks for a unit once an amount is given", () => {
    const state = recipe();
    state.ingredients[0] = { ...state.ingredients[0], unit: "" };
    expect(validate(state, published)[ingredientKey(0)]).toMatch(/What unit is the 200 of flour/);
  });

  test("rejects a unit the API would not accept", () => {
    const state = recipe();
    state.ingredients[0] = { ...state.ingredients[0], unit: "glug" };
    expect(validate(state, published)[ingredientKey(0, "unit")]).toMatch(/isn't a unit/);
  });

  test("rejects an amount that is not a positive number", () => {
    const state = recipe();
    state.ingredients[0] = { ...state.ingredients[0], quantity: "-2" };
    expect(validate(state, published)[ingredientKey(0, "quantity")]).toMatch(/above zero/);
  });

  test("ignores rows left blank rather than complaining about them", () => {
    const state = recipe();
    state.ingredients = [...state.ingredients, emptyIngredient()];
    state.steps = [...state.steps, emptyStep()];
    expect(validate(state, published)).toEqual({});
  });

  test("counts only filled rows toward the minimum", () => {
    const state = recipe({ ingredients: [emptyIngredient(), emptyIngredient()] });
    expect(validate(state, published).ingredients).toMatch(/at least 2 ingredients/);
  });

  test("rejects a step too short to be an instruction", () => {
    const state = recipe();
    state.steps[0] = { ...state.steps[0], instruction: "Mix" };
    expect(validate(state, published)[stepKey(0, "instruction")]).toMatch(
      /at least 10 characters/,
    );
  });

  test("wants a prep time or a cook time, and takes either alone", () => {
    expect(validate(recipe({ prepMinutes: "", cookMinutes: "" }), published).times).toBeTruthy();
    expect(validate(recipe({ prepMinutes: "", cookMinutes: "40" }), published)).toEqual({});
    expect(validate(recipe({ prepMinutes: "10", cookMinutes: "" }), published)).toEqual({});
  });

  test("requires a photo to publish but not to draft", () => {
    const state = recipe({ mediaIds: [] });
    expect(validate(state, published).media_ids).toMatch(/at least one photo/);
    expect(validate(state, { status: "draft" })).toEqual({});
  });

  test("rejects a servings count outside the allowed range", () => {
    expect(validate(recipe({ servings: "0" }), published).servings).toBeTruthy();
    expect(validate(recipe({ servings: "2.5" }), published).servings).toBeTruthy();
    expect(validate(recipe({ servings: "101" }), published).servings).toBeTruthy();
  });

  test("a discussion needs a body or a photo, and no recipe fields", () => {
    const bare = { ...initialState("discussion"), title: "Anyone else hate cilantro?" };
    expect(validate(bare, published)[""]).toMatch(/text or a photo/);
    expect(validate({ ...bare, bodyMd: "I do." }, published)).toEqual({});
  });

  test("still requires a title on a draft", () => {
    expect(validate(recipe({ title: "no" }), { status: "draft" }).title).toBeTruthy();
  });
});

describe("toCreatePayload", () => {
  test("renumbers positions so removed rows leave no gap", () => {
    const state = recipe();
    state.ingredients = [
      state.ingredients[0],
      emptyIngredient(), // never filled in
      state.ingredients[1],
    ];
    const payload = toCreatePayload(state, { status: "published" }) as {
      recipe: { ingredients: Array<{ position: number; ingredient_name: string }> };
    };
    expect(payload.recipe.ingredients.map((i) => [i.position, i.ingredient_name])).toEqual([
      [1, "flour"],
      [2, "water"],
    ]);
  });

  test("a to-taste ingredient carries no quantity or unit", () => {
    const state = recipe();
    state.ingredients[0] = { ...state.ingredients[0], toTaste: true };
    const payload = toCreatePayload(state, { status: "published" }) as {
      recipe: { ingredients: Array<Record<string, unknown>> };
    };
    expect(payload.recipe.ingredients[0]).not.toHaveProperty("quantity");
    expect(payload.recipe.ingredients[0]).not.toHaveProperty("unit");
    expect(payload.recipe.ingredients[0].to_taste).toBe(true);
  });

  test("omits optional fields rather than sending empty strings", () => {
    const payload = toCreatePayload(recipe(), { status: "published" }) as Record<string, unknown> & {
      recipe: Record<string, unknown>;
    };
    expect(payload).not.toHaveProperty("body_md");
    expect(payload.recipe).not.toHaveProperty("cuisine");
    expect(payload.recipe).not.toHaveProperty("cook_time_minutes");
    expect(payload.recipe.prep_time_minutes).toBe(10);
  });

  test("a discussion carries no recipe at all", () => {
    const payload = toCreatePayload(
      { ...initialState("discussion"), title: "Hello", bodyMd: "Hi" },
      { status: "published" },
    );
    expect(payload).not.toHaveProperty("recipe");
    expect(payload.type).toBe("discussion");
  });

  test("sends the status that was asked for", () => {
    expect(toCreatePayload(recipe(), { status: "draft" }).status).toBe("draft");
  });
});

describe("mapServerErrors", () => {
  // These paths are the real ones the API produces, pinned on that side by
  // test_validation_errors_address_the_offending_row.
  test("places a row error beside the row that caused it", () => {
    const state = recipe();
    const errors = mapServerErrors(
      {
        "recipe.recipe.ingredients.0.unit": "'glug' isn't a unit we recognize.",
        "recipe.recipe.steps.1.instruction": "Steps need at least 10 characters.",
      },
      state,
    );
    expect(errors[ingredientKey(0, "unit")]).toMatch(/glug/);
    expect(errors[stepKey(1, "instruction")]).toMatch(/at least 10/);
  });

  test("places a whole-row error on the row", () => {
    const errors = mapServerErrors({ "recipe.recipe.ingredients.1": "How much water?" }, recipe());
    expect(errors[ingredientKey(1)]).toBe("How much water?");
  });

  test("re-indexes onto the rendered row when blank rows were dropped", () => {
    // The payload omitted the blank row, so the API's row 1 is the form's row 2.
    const state = recipe();
    state.ingredients = [state.ingredients[0], emptyIngredient(), state.ingredients[1]];
    const errors = mapServerErrors({ "recipe.recipe.ingredients.1.unit": "bad unit" }, state);
    expect(errors[ingredientKey(2, "unit")]).toBe("bad unit");
    expect(errors[ingredientKey(1, "unit")]).toBeUndefined();
  });

  test("a whole-recipe rule becomes a form-level message", () => {
    const errors = mapServerErrors(
      { "recipe.recipe": "Give a prep time, a cook time, or both." },
      recipe(),
    );
    expect(errors[""]).toMatch(/prep time/);
  });

  test("the missing-photo error is form-level too", () => {
    const errors = mapServerErrors({ recipe: "Add at least one photo." }, recipe());
    expect(errors[""]).toBe("Add at least one photo.");
  });

  test("a field error keeps its own slot", () => {
    const errors = mapServerErrors({ "recipe.title": "Titles need 3 characters." }, recipe());
    expect(errors.title).toBe("Titles need 3 characters.");
  });

  test("a row index the form no longer has is surfaced, not dropped", () => {
    const errors = mapServerErrors({ "recipe.recipe.ingredients.9.unit": "bad unit" }, recipe());
    expect(errors[""]).toBe("bad unit");
  });
});
