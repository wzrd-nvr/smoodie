import { Form, Link } from "react-router";
import type { Route } from "./+types/home";
import { getUser } from "../lib/session.server";

export function meta(_args: Route.MetaArgs) {
  return [
    { title: "smoodie — eat, drink, cook, share" },
    {
      name: "description",
      content:
        "A community for people who cook, eat, and drink. Share recipes, report back on your cooks, and find what's actually worth making.",
    },
  ];
}

export async function loader({ request }: Route.LoaderArgs) {
  return { user: await getUser(request) };
}

export default function Home({ loaderData }: Route.ComponentProps) {
  const { user } = loaderData;

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="flex flex-col gap-3">
        <h1 className="text-4xl font-bold tracking-tight">smoodie</h1>
        <p className="text-lg opacity-80">
          Recipes worth making, verdicts from people who actually cooked them.
        </p>
      </div>

      {user ? (
        <div className="flex flex-col items-center gap-3">
          <p>
            Signed in as{" "}
            <Link to={`/u/${user.username}`} className="underline">
              @{user.username}
            </Link>
          </p>
          <Form method="post" action="/logout">
            <button type="submit" className="rounded-md border px-3 py-2 text-sm">
              Sign out
            </button>
          </Form>
        </div>
      ) : (
        <div className="flex gap-3">
          <Link to="/signup" className="rounded-md bg-emerald-700 px-4 py-2 text-white">
            Join smoodie
          </Link>
          <Link to="/login" className="rounded-md border px-4 py-2">
            Sign in
          </Link>
        </div>
      )}

      <p className="text-sm opacity-60">The feed arrives with recipes in M2.</p>
    </main>
  );
}
