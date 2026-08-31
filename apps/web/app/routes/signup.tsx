import { useState } from "react";
import { Link, redirect, useNavigation, useSearchParams } from "react-router";
import type { Route } from "./+types/signup";
import { apiFetch } from "../lib/api.server";
import { getUser, safeRedirect } from "../lib/session.server";
import { describeAuthError, signUp, type FirebaseConfig } from "../lib/firebase.client";
import { AuthForm } from "../components/auth-form";

export function meta(_args: Route.MetaArgs) {
  return [{ title: "Join smoodie" }];
}

export async function loader({ request }: Route.LoaderArgs) {
  if (await getUser(request)) throw redirect("/");
  return {
    firebase: {
      apiKey: process.env.FIREBASE_API_KEY ?? "",
      authDomain: process.env.FIREBASE_AUTH_DOMAIN ?? "",
      projectId: process.env.FIREBASE_PROJECT_ID ?? "",
      appId: process.env.FIREBASE_APP_ID ?? "",
    } satisfies FirebaseConfig,
  };
}

export async function action({ request }: Route.ActionArgs) {
  const form = await request.formData();
  const idToken = form.get("idToken");
  const next = safeRedirect(form.get("next"));

  if (typeof idToken !== "string" || !idToken) {
    return { error: "Something went wrong creating your account. Try again." };
  }

  const result = await apiFetch<unknown>("/v1/auth/session", {
    method: "POST",
    body: { id_token: idToken },
  });

  if (!result.ok) return { error: result.error.message };

  const headers = new Headers();
  if (result.setCookie) headers.append("set-cookie", result.setCookie);
  return redirect(next, { headers });
}

export default function Signup({ loaderData, actionData }: Route.ComponentProps) {
  const [params] = useSearchParams();
  const navigation = useNavigation();
  const [clientError, setClientError] = useState<string | null>(null);

  return (
    <AuthForm
      title="Join smoodie"
      subtitle="Share recipes, and tell people how they actually turned out."
      submitLabel="Create account"
      busy={navigation.state !== "idle"}
      error={clientError ?? actionData?.error ?? null}
      next={params.get("next")}
      withDisplayName
      onCredentials={async (email, password, displayName) => {
        setClientError(null);
        try {
          return await signUp(loaderData.firebase, email, password, displayName);
        } catch (err) {
          setClientError(describeAuthError((err as { code?: string }).code ?? ""));
          return null;
        }
      }}
      footer={
        <p>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      }
    />
  );
}
