import type { Route } from "./+types/home";

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

export default function Home() {
  return (
    <main className="mx-auto flex min-h-svh max-w-2xl flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-4xl font-bold tracking-tight">smoodie</h1>
      <p className="text-lg opacity-80">
        Recipes worth making, verdicts from people who actually cooked them.
      </p>
      <p className="text-sm opacity-60">The feed lands here in M2.</p>
    </main>
  );
}
