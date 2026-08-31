import { Form, redirect, useNavigation } from "react-router";
import type { Route } from "./+types/settings.profile";
import { apiFetch } from "../lib/api.server";
import { requireUser, type Profile } from "../lib/session.server";

export function meta(_args: Route.MetaArgs) {
  return [{ title: "Edit profile — smoodie" }];
}

export async function loader({ request }: Route.LoaderArgs) {
  return { profile: await requireUser(request) };
}

/**
 * A plain route action, so the form works before (or without) JavaScript.
 * Field errors come back from the API already addressed to their input.
 */
export async function action({ request }: Route.ActionArgs) {
  const user = await requireUser(request);
  const form = await request.formData();

  const changes: Record<string, string | null> = {};
  const username = String(form.get("username") ?? "").trim();
  const displayName = String(form.get("display_name") ?? "").trim();
  const bio = String(form.get("bio") ?? "").trim();

  if (username && username !== user.username) changes.username = username;
  if (displayName && displayName !== user.display_name) changes.display_name = displayName;
  if (bio !== (user.bio ?? "")) changes.bio = bio || null;

  if (Object.keys(changes).length === 0) {
    return { ok: true as const, message: "Nothing to change." };
  }

  const result = await apiFetch<Profile>("/v1/users/me", {
    method: "PATCH",
    request,
    body: changes,
  });

  if (!result.ok) {
    return {
      ok: false as const,
      message: result.error.message,
      fieldErrors: result.error.fieldErrors,
    };
  }

  // Username changes move the profile URL, so land on the new one.
  return redirect(`/u/${result.data.username}`);
}

export default function ProfileSettings({ loaderData, actionData }: Route.ComponentProps) {
  const { profile } = loaderData;
  const navigation = useNavigation();
  const fieldErrors = actionData && !actionData.ok ? actionData.fieldErrors : {};
  const saving = navigation.state === "submitting";

  return (
    <main className="mx-auto flex w-full max-w-lg flex-col gap-6 px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Edit profile</h1>

      {actionData && !actionData.ok ? (
        <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm">
          {actionData.message}
        </p>
      ) : null}

      <Form method="post" className="flex flex-col gap-4">
        <Field
          name="username"
          label="Username"
          defaultValue={profile.username}
          hint="Letters, numbers and underscores. This is your profile URL."
          error={fieldErrors?.username}
          maxLength={30}
        />
        <Field
          name="display_name"
          label="Display name"
          defaultValue={profile.display_name}
          error={fieldErrors?.display_name}
          maxLength={80}
        />
        <label className="flex flex-col gap-1 text-sm">
          <span>Bio</span>
          <textarea
            name="bio"
            rows={4}
            maxLength={500}
            defaultValue={profile.bio ?? ""}
            className="rounded-md border px-3 py-2"
          />
          {fieldErrors?.bio ? (
            <span className="text-sm text-red-600">{fieldErrors.bio}</span>
          ) : null}
        </label>

        <button
          type="submit"
          disabled={saving}
          className="self-start rounded-md bg-emerald-700 px-4 py-2 text-white disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
      </Form>
    </main>
  );
}

function Field({
  name,
  label,
  defaultValue,
  hint,
  error,
  maxLength,
}: {
  name: string;
  label: string;
  defaultValue: string;
  hint?: string;
  error?: string;
  maxLength?: number;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span>{label}</span>
      <input
        name={name}
        type="text"
        defaultValue={defaultValue}
        maxLength={maxLength}
        aria-invalid={error ? true : undefined}
        className="rounded-md border px-3 py-2"
      />
      {hint && !error ? <span className="opacity-60">{hint}</span> : null}
      {error ? <span className="text-red-600">{error}</span> : null}
    </label>
  );
}
