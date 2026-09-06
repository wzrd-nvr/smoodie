/**
 * The composer.
 *
 * Every control is a submit button on one form, so adding, removing and
 * reordering rows work without JavaScript: the action recomputes the state and
 * the page re-renders. With JavaScript, React Router turns the same submits
 * into client navigations, so the identical code path is simply faster. The
 * only part that needs a script is attaching a photo, which is a signed-URL
 * conversation the browser has to hold itself.
 *
 * The logic lives in `lib/recipe-form.ts`; this module only reads the session
 * and talks to the API.
 */

import { Form, Link, useNavigation } from "react-router";
import type { Route } from "./+types/posts.new";
import { apiFetch } from "../lib/api.server";
import { requireUser } from "../lib/session.server";
import { PhotoPicker } from "../components/photo-picker";
import { UNIT_GROUPS } from "../lib/units";
import {
  applyIntent,
  DIETARY_TAGS,
  DIFFICULTIES,
  ingredientKey,
  initialState,
  MAX_MEDIA,
  mapServerErrors,
  parseComposerForm,
  parseIntent,
  stepKey,
  toCreatePayload,
  validate,
  type ComposerState,
  type FormErrors,
  type IngredientRow,
  type StepRow,
} from "../lib/recipe-form";

type CreatedPost = { id: string; slug: string; title: string; status: string };

export function meta(_args: Route.MetaArgs) {
  return [{ title: "New post — smoodie" }];
}

export async function loader({ request }: Route.LoaderArgs) {
  await requireUser(request);
  return {};
}

export async function action({ request }: Route.ActionArgs) {
  await requireUser(request);
  const form = await request.formData();
  const intent = parseIntent(form.get("_intent"));
  const state = parseComposerForm(form);

  if (intent.kind !== "save") {
    return { state: applyIntent(state, intent), errors: {} as FormErrors, created: null };
  }

  // Checked here first so an obviously incomplete recipe never becomes a
  // request. The API checks the same rules again and is the authority.
  const local = validate(state, { status: intent.status });
  if (Object.keys(local).length > 0) {
    return { state, errors: local, created: null };
  }

  const result = await apiFetch<CreatedPost>("/v1/posts", {
    method: "POST",
    request,
    body: toCreatePayload(state, { status: intent.status }),
  });

  if (!result.ok) {
    const mapped = mapServerErrors(result.error.pathErrors, state);
    // Anything the mapper could not place still has to be seen.
    if (Object.keys(mapped).length === 0) mapped[""] = result.error.message;
    return { state, errors: mapped, created: null };
  }

  // No redirect yet: /p/:id/:slug arrives with issue #16, and sending someone
  // to a route that does not exist would be a worse ending than this one.
  return { state: initialState(state.kind), errors: {} as FormErrors, created: result.data };
}

export default function NewPost({ actionData }: Route.ComponentProps) {
  const navigation = useNavigation();
  const state = actionData?.state ?? initialState();
  const errors: FormErrors = actionData?.errors ?? {};
  const created = actionData?.created ?? null;
  const busy = navigation.state === "submitting";
  const isRecipe = state.kind === "recipe";

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">New post</h1>

      {created ? (
        <p role="status" className="rounded-md border border-emerald-600/40 bg-emerald-600/10 px-3 py-2 text-sm">
          {created.status === "published" ? "Published" : "Saved as a draft"}: {created.title}
        </p>
      ) : null}

      {errors[""] ? (
        <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm">
          {errors[""]}
        </p>
      ) : null}

      <Form method="post" className="flex flex-col gap-6">
        <input type="hidden" name="kind" value={state.kind} />

        <div className="flex gap-2">
          <TypeButton active={!isRecipe} intent="switch-discussion" label="Discussion" />
          <TypeButton active={isRecipe} intent="switch-recipe" label="Recipe" />
        </div>

        <Text
          name="title"
          label="Title"
          defaultValue={state.title}
          error={errors.title}
          maxLength={200}
        />

        <label className="flex flex-col gap-1 text-sm">
          <span>{isRecipe ? "Notes (optional)" : "Body"}</span>
          <textarea
            name="body_md"
            rows={isRecipe ? 3 : 8}
            maxLength={50_000}
            defaultValue={state.bodyMd}
            className="rounded-md border px-3 py-2"
          />
        </label>

        <PhotoPicker
          key={state.mediaIds.join(",")}
          initial={state.mediaIds.map((id) => ({ id, url: null, name: "Attached photo" }))}
          max={MAX_MEDIA}
          error={errors.media_ids}
        />

        {isRecipe ? <RecipeFields state={state} errors={errors} /> : null}

        <div className="flex gap-3">
          <button
            type="submit"
            name="_intent"
            value="publish"
            disabled={busy}
            className="rounded-md bg-emerald-700 px-4 py-2 text-white disabled:opacity-60"
          >
            {busy ? "Working…" : "Publish"}
          </button>
          <button
            type="submit"
            name="_intent"
            value="draft"
            disabled={busy}
            className="rounded-md border px-4 py-2 disabled:opacity-60"
          >
            Save draft
          </button>
          <Link to="/" className="self-center text-sm underline opacity-70">
            Cancel
          </Link>
        </div>
      </Form>
    </main>
  );
}

function RecipeFields({ state, errors }: { state: ComposerState; errors: FormErrors }) {
  return (
    <>
      <section className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Text
          name="servings"
          label="Servings"
          type="number"
          defaultValue={state.servings}
          error={errors.servings}
        />
        <Text
          name="prep_minutes"
          label="Prep (minutes)"
          type="number"
          defaultValue={state.prepMinutes}
        />
        <Text
          name="cook_minutes"
          label="Cook (minutes)"
          type="number"
          defaultValue={state.cookMinutes}
        />
        <Text
          name="yield_text"
          label="Yield (optional)"
          defaultValue={state.yieldText}
          maxLength={120}
        />
        <Text name="cuisine" label="Cuisine (optional)" defaultValue={state.cuisine} maxLength={60} />
        <label className="flex flex-col gap-1 text-sm">
          <span>Difficulty</span>
          <select
            name="difficulty"
            defaultValue={state.difficulty}
            className="rounded-md border px-3 py-2"
          >
            <option value="">Unspecified</option>
            {DIFFICULTIES.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </label>
      </section>

      {errors.times ? (
        <p role="alert" className="text-sm text-red-600">
          {errors.times}
        </p>
      ) : null}

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Dietary tags</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
          {DIETARY_TAGS.map((tag) => (
            <label key={tag} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                name="dietary"
                value={tag}
                defaultChecked={state.dietaryTags.includes(tag)}
              />
              {tag}
            </label>
          ))}
        </div>
      </fieldset>

      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-medium">Ingredients</h2>
          {errors.ingredients ? (
            <span role="alert" className="text-sm text-red-600">
              {errors.ingredients}
            </span>
          ) : null}
        </div>
        {state.ingredients.map((row, index) => (
          <IngredientFields
            key={row.id}
            row={row}
            index={index}
            last={index === state.ingredients.length - 1}
            errors={errors}
          />
        ))}
        <button
          type="submit"
          name="_intent"
          value="add-ing"
          className="self-start rounded-md border px-3 py-1.5 text-sm"
        >
          Add ingredient
        </button>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-medium">Steps</h2>
          {errors.steps ? (
            <span role="alert" className="text-sm text-red-600">
              {errors.steps}
            </span>
          ) : null}
        </div>
        {state.steps.map((row, index) => (
          <StepFields
            key={row.id}
            row={row}
            index={index}
            last={index === state.steps.length - 1}
            errors={errors}
          />
        ))}
        <button
          type="submit"
          name="_intent"
          value="add-step"
          className="self-start rounded-md border px-3 py-1.5 text-sm"
        >
          Add step
        </button>
      </section>
    </>
  );
}

function IngredientFields({
  row,
  index,
  last,
  errors,
}: {
  row: IngredientRow;
  index: number;
  last: boolean;
  errors: FormErrors;
}) {
  const rowError = errors[ingredientKey(index)];
  return (
    <div className="flex flex-col gap-2 rounded-md border p-3">
      <input type="hidden" name={`ing.${index}.id`} value={row.id} />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-[6rem_8rem_1fr]">
        <label className="flex flex-col gap-1 text-sm">
          <span className="sr-only">Amount for ingredient {index + 1}</span>
          <input
            name={`ing.${index}.quantity`}
            type="text"
            inputMode="decimal"
            placeholder="200"
            defaultValue={row.quantity}
            aria-label={`Amount for ingredient ${index + 1}`}
            className="rounded-md border px-2 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <select
            name={`ing.${index}.unit`}
            defaultValue={row.unit}
            aria-label={`Unit for ingredient ${index + 1}`}
            className="rounded-md border px-2 py-2"
          >
            <option value="">Unit</option>
            {UNIT_GROUPS.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.units.map((unit) => (
                  <option key={unit} value={unit}>
                    {unit}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <input
          name={`ing.${index}.name`}
          type="text"
          placeholder="Ingredient"
          defaultValue={row.name}
          maxLength={120}
          aria-label={`Ingredient ${index + 1}`}
          className="rounded-md border px-2 py-2"
        />
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <input
          name={`ing.${index}.note`}
          type="text"
          placeholder="Preparation (finely chopped)"
          defaultValue={row.note}
          maxLength={120}
          aria-label={`Preparation note for ingredient ${index + 1}`}
          className="rounded-md border px-2 py-2 text-sm"
        />
        <input
          name={`ing.${index}.group`}
          type="text"
          placeholder="Group (For the sauce)"
          defaultValue={row.groupLabel}
          maxLength={80}
          aria-label={`Group for ingredient ${index + 1}`}
          className="rounded-md border px-2 py-2 text-sm"
        />
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            name={`ing.${index}.to_taste`}
            defaultChecked={row.toTaste}
          />
          To taste
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" name={`ing.${index}.optional`} defaultChecked={row.isOptional} />
          Optional
        </label>
        <RowButtons list="ing" index={index} last={last} label="ingredient" />
      </div>

      {rowError ? (
        <span role="alert" className="text-sm text-red-600">
          {rowError}
        </span>
      ) : null}
      {errors[ingredientKey(index, "quantity")] ? (
        <span role="alert" className="text-sm text-red-600">
          {errors[ingredientKey(index, "quantity")]}
        </span>
      ) : null}
      {errors[ingredientKey(index, "unit")] ? (
        <span role="alert" className="text-sm text-red-600">
          {errors[ingredientKey(index, "unit")]}
        </span>
      ) : null}
      {errors[ingredientKey(index, "ingredient_name")] ? (
        <span role="alert" className="text-sm text-red-600">
          {errors[ingredientKey(index, "ingredient_name")]}
        </span>
      ) : null}
    </div>
  );
}

function StepFields({
  row,
  index,
  last,
  errors,
}: {
  row: StepRow;
  index: number;
  last: boolean;
  errors: FormErrors;
}) {
  const error = errors[stepKey(index, "instruction")] ?? errors[stepKey(index)];
  return (
    <div className="flex flex-col gap-2 rounded-md border p-3">
      <input type="hidden" name={`step.${index}.id`} value={row.id} />
      <div className="flex gap-2">
        <span className="pt-2 text-sm opacity-60">{index + 1}.</span>
        <textarea
          name={`step.${index}.instruction`}
          rows={2}
          placeholder="Say what to do, and what with."
          defaultValue={row.instruction}
          aria-label={`Step ${index + 1}`}
          className="grow rounded-md border px-2 py-2"
        />
      </div>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-1.5">
          Minutes
          <input
            name={`step.${index}.minutes`}
            type="number"
            min={0}
            defaultValue={row.minutes}
            aria-label={`Minutes for step ${index + 1}`}
            className="w-20 rounded-md border px-2 py-1"
          />
        </label>
        <RowButtons list="step" index={index} last={last} label="step" />
      </div>
      {error ? (
        <span role="alert" className="text-sm text-red-600">
          {error}
        </span>
      ) : null}
    </div>
  );
}

function RowButtons({
  list,
  index,
  last,
  label,
}: {
  list: "ing" | "step";
  index: number;
  last: boolean;
  label: string;
}) {
  const button = "rounded border px-2 py-1 disabled:opacity-40";
  return (
    <span className="ml-auto flex gap-2">
      <button
        type="submit"
        name="_intent"
        value={`up-${list}:${index}`}
        disabled={index === 0}
        aria-label={`Move ${label} ${index + 1} up`}
        className={button}
      >
        ↑
      </button>
      <button
        type="submit"
        name="_intent"
        value={`down-${list}:${index}`}
        disabled={last}
        aria-label={`Move ${label} ${index + 1} down`}
        className={button}
      >
        ↓
      </button>
      <button
        type="submit"
        name="_intent"
        value={`remove-${list}:${index}`}
        aria-label={`Remove ${label} ${index + 1}`}
        className={button}
      >
        Remove
      </button>
    </span>
  );
}

function TypeButton({
  active,
  intent,
  label,
}: {
  active: boolean;
  intent: string;
  label: string;
}) {
  return (
    <button
      type="submit"
      name="_intent"
      value={intent}
      aria-pressed={active}
      className={
        active
          ? "rounded-md bg-emerald-700 px-3 py-1.5 text-sm text-white"
          : "rounded-md border px-3 py-1.5 text-sm"
      }
    >
      {label}
    </button>
  );
}

function Text({
  name,
  label,
  defaultValue,
  error,
  maxLength,
  type = "text",
}: {
  name: string;
  label: string;
  defaultValue: string;
  error?: string;
  maxLength?: number;
  type?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span>{label}</span>
      <input
        name={name}
        type={type}
        defaultValue={defaultValue}
        maxLength={maxLength}
        aria-invalid={error ? true : undefined}
        className="rounded-md border px-3 py-2"
      />
      {error ? (
        <span role="alert" className="text-red-600">
          {error}
        </span>
      ) : null}
    </label>
  );
}
