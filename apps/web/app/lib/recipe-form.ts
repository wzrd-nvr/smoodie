/**
 * The composer's logic, with no React and no network in it.
 *
 * Everything here is a pure function over form state so the row machinery and
 * the validation rules can be tested directly rather than through a rendered
 * page. The route module is left holding only the parts that genuinely need a
 * request: reading the session, and calling the API.
 */

import { isKnownUnit } from "./units";

// Mirrors the constants in apps/api/src/smoodie_api/schemas/post.py. The API
// enforces these; repeating them here is what lets the form say so before a
// round trip. `recipe-form.test.ts` pins them against the Python source.
export const MIN_INGREDIENTS = 2;
export const MIN_STEPS = 2;
export const MIN_STEP_LENGTH = 10;
export const MAX_MEDIA = 12;

export const DIETARY_TAGS = [
  "vegan",
  "vegetarian",
  "pescatarian",
  "gluten-free",
  "dairy-free",
  "nut-free",
  "egg-free",
  "soy-free",
  "shellfish-free",
  "halal",
  "kosher",
  "low-carb",
  "keto",
  "paleo",
  "whole30",
  "sugar-free",
  "low-sodium",
] as const;

export const DIFFICULTIES = ["easy", "medium", "hard"] as const;

export type PostKind = "discussion" | "recipe";

export type IngredientRow = {
  /** Stable across reorders so React moves the input rather than rewriting it.
   * Without it, removing row 2 leaves row 3's typed value sitting in row 2's
   * box: the keys match, React reuses the DOM node, and the form quietly shows
   * the wrong data. Carried through the form so it survives a no-JS round trip. */
  id: string;
  groupLabel: string;
  quantity: string;
  unit: string;
  name: string;
  note: string;
  isOptional: boolean;
  toTaste: boolean;
};

export type StepRow = {
  id: string;
  instruction: string;
  minutes: string;
};

export type ComposerState = {
  kind: PostKind;
  title: string;
  bodyMd: string;
  mediaIds: string[];
  servings: string;
  yieldText: string;
  prepMinutes: string;
  cookMinutes: string;
  difficulty: string;
  cuisine: string;
  dietaryTags: string[];
  ingredients: IngredientRow[];
  steps: StepRow[];
};

/** Injectable so tests get stable ids; the browser and the server both have
 * crypto.randomUUID, so nothing needs a polyfill. */
let newRowId: () => string = () => crypto.randomUUID();

export function setRowIdFactory(factory: () => string): void {
  newRowId = factory;
}

export function emptyIngredient(): IngredientRow {
  return {
    id: newRowId(),
    groupLabel: "",
    quantity: "",
    unit: "",
    name: "",
    note: "",
    isOptional: false,
    toTaste: false,
  };
}

export function emptyStep(): StepRow {
  return { id: newRowId(), instruction: "", minutes: "" };
}

/** A new recipe opens with the minimum number of rows already present, so the
 * shape of the requirement is visible before anyone is told about it. */
export function initialState(kind: PostKind = "recipe"): ComposerState {
  return {
    kind,
    title: "",
    bodyMd: "",
    mediaIds: [],
    servings: "4",
    yieldText: "",
    prepMinutes: "",
    cookMinutes: "",
    difficulty: "",
    cuisine: "",
    dietaryTags: [],
    ingredients: [emptyIngredient(), emptyIngredient()],
    steps: [emptyStep(), emptyStep()],
  };
}

// ------------------------------------------------------------------ parsing

function str(form: FormData, key: string): string {
  const value = form.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function flag(form: FormData, key: string): boolean {
  return form.get(key) != null;
}

/** How many `prefix.{n}.…` rows the form carried. Counting the submitted keys
 * rather than trusting a hidden count means a truncated or hand-built POST
 * cannot make the two disagree. */
function rowCount(form: FormData, prefix: string): number {
  let highest = -1;
  for (const key of form.keys()) {
    const match = new RegExp(`^${prefix}\\.(\\d+)\\.`).exec(key);
    if (match) highest = Math.max(highest, Number(match[1]));
  }
  return highest + 1;
}

export function parseComposerForm(form: FormData): ComposerState {
  const kind: PostKind = str(form, "kind") === "discussion" ? "discussion" : "recipe";

  const ingredients: IngredientRow[] = [];
  for (let i = 0; i < rowCount(form, "ing"); i += 1) {
    ingredients.push({
      id: str(form, `ing.${i}.id`) || newRowId(),
      groupLabel: str(form, `ing.${i}.group`),
      quantity: str(form, `ing.${i}.quantity`),
      unit: str(form, `ing.${i}.unit`),
      name: str(form, `ing.${i}.name`),
      note: str(form, `ing.${i}.note`),
      isOptional: flag(form, `ing.${i}.optional`),
      toTaste: flag(form, `ing.${i}.to_taste`),
    });
  }

  const steps: StepRow[] = [];
  for (let i = 0; i < rowCount(form, "step"); i += 1) {
    steps.push({
      id: str(form, `step.${i}.id`) || newRowId(),
      instruction: str(form, `step.${i}.instruction`),
      minutes: str(form, `step.${i}.minutes`),
    });
  }

  return {
    kind,
    title: str(form, "title"),
    bodyMd: str(form, "body_md"),
    mediaIds: form.getAll("media_ids").filter((v): v is string => typeof v === "string"),
    servings: str(form, "servings"),
    yieldText: str(form, "yield_text"),
    prepMinutes: str(form, "prep_minutes"),
    cookMinutes: str(form, "cook_minutes"),
    difficulty: str(form, "difficulty"),
    cuisine: str(form, "cuisine"),
    dietaryTags: form.getAll("dietary").filter((v): v is string => typeof v === "string"),
    ingredients: ingredients.length ? ingredients : [emptyIngredient(), emptyIngredient()],
    steps: steps.length ? steps : [emptyStep(), emptyStep()],
  };
}

// ------------------------------------------------------------------- intents

export type Intent =
  | { kind: "save"; status: "draft" | "published" }
  | { kind: "add"; list: "ing" | "step" }
  | { kind: "remove"; list: "ing" | "step"; index: number }
  | { kind: "move"; list: "ing" | "step"; index: number; direction: -1 | 1 }
  | { kind: "switch"; to: PostKind };

/** Row buttons submit the form, so every one of them arrives as a string. */
export function parseIntent(raw: FormDataEntryValue | null): Intent {
  const value = typeof raw === "string" ? raw : "";
  const [name, argument] = value.split(":");

  switch (name) {
    case "draft":
      return { kind: "save", status: "draft" };
    case "add-ing":
      return { kind: "add", list: "ing" };
    case "add-step":
      return { kind: "add", list: "step" };
    case "remove-ing":
      return { kind: "remove", list: "ing", index: Number(argument) };
    case "remove-step":
      return { kind: "remove", list: "step", index: Number(argument) };
    case "up-ing":
      return { kind: "move", list: "ing", index: Number(argument), direction: -1 };
    case "down-ing":
      return { kind: "move", list: "ing", index: Number(argument), direction: 1 };
    case "up-step":
      return { kind: "move", list: "step", index: Number(argument), direction: -1 };
    case "down-step":
      return { kind: "move", list: "step", index: Number(argument), direction: 1 };
    case "switch-discussion":
      return { kind: "switch", to: "discussion" };
    case "switch-recipe":
      return { kind: "switch", to: "recipe" };
    default:
      return { kind: "save", status: "published" };
  }
}

function move<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (index < 0 || index >= items.length) return items;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/**
 * Row edits never drop below the minimum. Removing the second-to-last
 * ingredient blanks it instead of deleting it, so the form keeps the shape the
 * requirement demands rather than letting someone reach a state the API will
 * reject and then having to explain why.
 */
export function applyIntent(state: ComposerState, intent: Intent): ComposerState {
  switch (intent.kind) {
    case "switch":
      return { ...state, kind: intent.to };

    case "add":
      return intent.list === "ing"
        ? { ...state, ingredients: [...state.ingredients, emptyIngredient()] }
        : { ...state, steps: [...state.steps, emptyStep()] };

    case "remove": {
      if (intent.list === "ing") {
        if (state.ingredients.length <= MIN_INGREDIENTS) {
          const kept = [...state.ingredients];
          if (intent.index >= 0 && intent.index < kept.length) {
            kept[intent.index] = emptyIngredient();
          }
          return { ...state, ingredients: kept };
        }
        return {
          ...state,
          ingredients: state.ingredients.filter((_, i) => i !== intent.index),
        };
      }
      if (state.steps.length <= MIN_STEPS) {
        const kept = [...state.steps];
        if (intent.index >= 0 && intent.index < kept.length) kept[intent.index] = emptyStep();
        return { ...state, steps: kept };
      }
      return { ...state, steps: state.steps.filter((_, i) => i !== intent.index) };
    }

    case "move":
      return intent.list === "ing"
        ? { ...state, ingredients: move(state.ingredients, intent.index, intent.direction) }
        : { ...state, steps: move(state.steps, intent.index, intent.direction) };

    case "save":
      return state;
  }
}

// ---------------------------------------------------------------- validation

/**
 * Keyed the same way the API addresses its own errors, so a message rendered
 * beside a row looks identical whether it was caught here or came back from
 * the server. The empty string is the form-level slot.
 */
export type FormErrors = Record<string, string>;

export function ingredientKey(index: number, field?: string): string {
  return field ? `ingredients.${index}.${field}` : `ingredients.${index}`;
}

export function stepKey(index: number, field?: string): string {
  return field ? `steps.${index}.${field}` : `steps.${index}`;
}

/** Rows left entirely blank are dropped rather than reported — an untouched
 * spare row is not a mistake the person made. */
export function usedIngredients(state: ComposerState): IngredientRow[] {
  return state.ingredients.filter((row) => row.name !== "");
}

export function usedSteps(state: ComposerState): StepRow[] {
  return state.steps.filter((row) => row.instruction !== "");
}

function positiveNumber(raw: string): number | null {
  if (raw === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function validate(
  state: ComposerState,
  { status }: { status: "draft" | "published" },
): FormErrors {
  const errors: FormErrors = {};

  if (state.title.length < 3) errors.title = "Titles need at least 3 characters.";

  if (state.kind === "discussion") {
    if (!state.bodyMd && state.mediaIds.length === 0) {
      errors[""] = "Add something to your post — text or a photo.";
    }
    return errors;
  }

  // Indexes are reported against the rendered rows, not the filtered ones, so
  // a message lands on the input the person is actually looking at.
  state.ingredients.forEach((row, index) => {
    if (row.name === "") return;
    if (row.toTaste) return;
    if (row.quantity === "") {
      errors[ingredientKey(index)] =
        `How much ${row.name}? Give an amount, or mark it as to taste.`;
      return;
    }
    if (positiveNumber(row.quantity) === null) {
      errors[ingredientKey(index, "quantity")] = "Amounts have to be a number above zero.";
      return;
    }
    if (row.unit === "") {
      errors[ingredientKey(index)] =
        `What unit is the ${row.quantity} of ${row.name}? Pick a unit, or mark it as to taste.`;
      return;
    }
    if (!isKnownUnit(row.unit)) {
      errors[ingredientKey(index, "unit")] =
        `'${row.unit}' isn't a unit we recognize. Use a standard measure, or mark the ingredient as to taste.`;
    }
  });

  state.steps.forEach((row, index) => {
    if (row.instruction === "") return;
    if (row.instruction.replace(/\s+/g, " ").length < MIN_STEP_LENGTH) {
      errors[stepKey(index, "instruction")] =
        `Steps need at least ${MIN_STEP_LENGTH} characters — say what to do with what.`;
    }
  });

  if (usedIngredients(state).length < MIN_INGREDIENTS) {
    errors.ingredients =
      `A recipe needs at least ${MIN_INGREDIENTS} ingredients. ` +
      "If it really has one, it might fit better as a discussion post.";
  }
  if (usedSteps(state).length < MIN_STEPS) {
    errors.steps = `A recipe needs at least ${MIN_STEPS} steps.`;
  }

  const servings = positiveNumber(state.servings);
  if (servings === null || !Number.isInteger(servings) || servings > 100) {
    errors.servings = "Servings has to be a whole number from 1 to 100.";
  }

  if (state.prepMinutes === "" && state.cookMinutes === "") {
    errors.times =
      "Give a prep time, a cook time, or both — otherwise nobody knows what they're committing to.";
  }

  // Drafts are exempt on purpose: the photo is the last thing you have, and
  // being unable to save work in progress would be worse than a photoless feed.
  if (status === "published" && state.mediaIds.length === 0) {
    errors.media_ids = "Add at least one photo before publishing a recipe.";
  }

  return errors;
}

// ------------------------------------------------------------------- payload

export type CreatePayload = Record<string, unknown>;

export function toCreatePayload(
  state: ComposerState,
  { status }: { status: "draft" | "published" },
): CreatePayload {
  const base: CreatePayload = {
    type: state.kind,
    title: state.title,
    status,
    media_ids: state.mediaIds,
  };
  if (state.bodyMd) base.body_md = state.bodyMd;
  if (state.kind === "discussion") return base;

  // Positions are assigned from the surviving order, so the API never sees the
  // gap a removed row would otherwise leave behind.
  return {
    ...base,
    recipe: {
      servings: Number(state.servings),
      ...(state.yieldText ? { yield_text: state.yieldText } : {}),
      ...(state.prepMinutes ? { prep_time_minutes: Number(state.prepMinutes) } : {}),
      ...(state.cookMinutes ? { cook_time_minutes: Number(state.cookMinutes) } : {}),
      ...(state.difficulty ? { difficulty: state.difficulty } : {}),
      ...(state.cuisine ? { cuisine: state.cuisine } : {}),
      dietary_tags: state.dietaryTags,
      ingredients: usedIngredients(state).map((row, index) => ({
        position: index + 1,
        ...(row.groupLabel ? { group_label: row.groupLabel } : {}),
        ...(row.toTaste ? {} : { quantity: Number(row.quantity), unit: row.unit }),
        ingredient_name: row.name,
        ...(row.note ? { preparation_note: row.note } : {}),
        is_optional: row.isOptional,
        to_taste: row.toTaste,
      })),
      steps: usedSteps(state).map((row, index) => ({
        position: index + 1,
        instruction: row.instruction,
        ...(row.minutes ? { duration_minutes: Number(row.minutes) } : {}),
      })),
    },
  };
}

// --------------------------------------------------- server error addressing

/**
 * Turn the API's dotted paths into the keys this form uses.
 *
 * The API's paths carry the discriminated union's tag before the field, so a
 * bad unit arrives as `recipe.recipe.ingredients.0.unit` rather than
 * `ingredients.0.unit` (pinned by `test_validation_errors_address_the
 * _offending_row` on the API side). Rather than hard-code that prefix, this
 * finds the `ingredients`/`steps` segment wherever it sits — the form only
 * cares which row broke, not how the payload was nested to get there.
 *
 * Rows are re-indexed on the way out: the payload omits blank rows, so row 1
 * of the request can be row 3 of the form.
 */
export function mapServerErrors(
  pathErrors: Record<string, string>,
  state: ComposerState,
): FormErrors {
  const ingredientRows = state.ingredients.flatMap((row, index) =>
    row.name === "" ? [] : [index],
  );
  const stepRows = state.steps.flatMap((row, index) => (row.instruction === "" ? [] : [index]));

  const errors: FormErrors = {};

  for (const [path, message] of Object.entries(pathErrors)) {
    const segments = path === "" ? [] : path.split(".");
    const listAt = segments.findIndex((s) => s === "ingredients" || s === "steps");

    if (listAt === -1) {
      // Not addressed to a row: a whole-recipe rule, or the whole post.
      const tail = segments[segments.length - 1];
      if (tail === "title" || tail === "servings" || tail === "media_ids") {
        errors[tail] = message;
      } else {
        errors[""] ??= message;
      }
      continue;
    }

    const list = segments[listAt];
    const sent = Number(segments[listAt + 1]);
    const field = segments[listAt + 2];
    const rendered = list === "ingredients" ? ingredientRows[sent] : stepRows[sent];

    if (rendered === undefined) {
      errors[""] ??= message;
      continue;
    }
    const key =
      list === "ingredients" ? ingredientKey(rendered, field) : stepKey(rendered, field);
    errors[key] ??= message;
  }

  return errors;
}
