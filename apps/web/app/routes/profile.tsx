import { Form, Link, data } from "react-router";
import type { Route } from "./+types/profile";
import { apiFetch } from "../lib/api.server";
import { getUser, type Profile } from "../lib/session.server";

export function meta({ loaderData }: Route.MetaArgs) {
  // loaderData is undefined when the loader threw (e.g. a 404 profile).
  if (!loaderData?.profile) return [{ title: "Profile not found — smoodie" }];
  const { display_name, username, bio } = loaderData.profile;
  return [
    { title: `${display_name} (@${username}) — smoodie` },
    { name: "description", content: bio ?? `${display_name} on smoodie.` },
    { property: "og:title", content: `${display_name} (@${username})` },
    { property: "og:type", content: "profile" },
  ];
}

/** Public: renders for signed-out visitors and search crawlers alike. */
export async function loader({ params, request }: Route.LoaderArgs) {
  const [result, viewer] = await Promise.all([
    apiFetch<Profile>(`/v1/users/${encodeURIComponent(params.username)}`),
    getUser(request),
  ]);

  if (!result.ok) {
    throw data({ message: "No such profile." }, { status: result.status });
  }
  return { profile: result.data, viewer };
}

export default function ProfilePage({ loaderData }: Route.ComponentProps) {
  const { profile, viewer } = loaderData;
  const isSelf = viewer?.id === profile.id;
  const joined = new Date(profile.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
  });

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-10">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{profile.display_name}</h1>
        <p className="text-sm opacity-70">@{profile.username}</p>
        {profile.bio ? <p className="max-w-prose">{profile.bio}</p> : null}
        <p className="text-sm opacity-60">Cooking here since {joined}</p>
      </header>

      {isSelf ? (
        <div className="flex gap-3">
          <Link to="/settings/profile" className="rounded-md border px-3 py-2 text-sm">
            Edit profile
          </Link>
          <Form method="post" action="/logout">
            <button type="submit" className="rounded-md border px-3 py-2 text-sm">
              Sign out
            </button>
          </Form>
        </div>
      ) : null}

      <section className="border-t pt-6">
        <h2 className="text-lg font-medium">Posts</h2>
        <p className="mt-2 text-sm opacity-60">
          Nothing here yet — posting arrives with recipes in M2.
        </p>
      </section>
    </main>
  );
}
