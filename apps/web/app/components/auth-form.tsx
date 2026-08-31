import { useRef, useState, type ReactNode } from "react";
import { useSubmit } from "react-router";

type Props = {
  title: string;
  subtitle: string;
  submitLabel: string;
  busy: boolean;
  error: string | null;
  next: string | null;
  /** Authenticates with Firebase, returning an ID token or null on failure. */
  onCredentials: (
    email: string,
    password: string,
    displayName?: string,
  ) => Promise<string | null>;
  withDisplayName?: boolean;
  footer: ReactNode;
};

/**
 * Credentials never reach our server: the browser authenticates with Firebase
 * and only the resulting ID token is posted to the action, which trades it for
 * a session cookie.
 */
export function AuthForm({
  title,
  subtitle,
  submitLabel,
  busy,
  error,
  next,
  onCredentials,
  withDisplayName = false,
  footer,
}: Props) {
  const submit = useSubmit();
  const formRef = useRef<HTMLFormElement>(null);
  const [pending, setPending] = useState(false);

  const working = busy || pending;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "");
    const password = String(data.get("password") ?? "");
    const displayName = String(data.get("displayName") ?? "");

    setPending(true);
    try {
      const idToken = await onCredentials(email, password, displayName || undefined);
      if (!idToken) return;

      // Only the ID token crosses to our server — never the password.
      const payload = new FormData();
      payload.set("idToken", idToken);
      if (next) payload.set("next", next);
      submit(payload, { method: "post" });
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-sm flex-col justify-center gap-6 px-6 py-12">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm opacity-70">{subtitle}</p>
      </header>

      {error ? (
        <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm">
          {error}
        </p>
      ) : null}

      <form ref={formRef} method="post" onSubmit={handleSubmit} className="flex flex-col gap-4">
        {withDisplayName ? (
          <label className="flex flex-col gap-1 text-sm">
            <span>Display name</span>
            <input
              name="displayName"
              type="text"
              autoComplete="name"
              maxLength={80}
              className="rounded-md border px-3 py-2"
            />
          </label>
        ) : null}

        <label className="flex flex-col gap-1 text-sm">
          <span>Email</span>
          <input
            name="email"
            type="email"
            required
            autoComplete="email"
            className="rounded-md border px-3 py-2"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span>Password</span>
          <input
            name="password"
            type="password"
            required
            minLength={6}
            autoComplete={withDisplayName ? "new-password" : "current-password"}
            className="rounded-md border px-3 py-2"
          />
        </label>

        <button
          type="submit"
          disabled={working}
          className="rounded-md bg-emerald-700 px-3 py-2 text-white disabled:opacity-60"
        >
          {working ? "One moment…" : submitLabel}
        </button>
      </form>

      <div className="text-sm opacity-70">{footer}</div>
    </main>
  );
}
