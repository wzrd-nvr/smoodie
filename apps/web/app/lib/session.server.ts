/**
 * Reading the signed-in user inside loaders.
 *
 * The session cookie is minted and verified by the API, so the web app never
 * inspects or trusts it directly — it forwards the cookie and takes the API's
 * answer as the source of truth.
 */

import { redirect } from "react-router";
import { apiFetch } from "./api.server";

export type Profile = {
  id: string;
  username: string;
  display_name: string;
  bio: string | null;
  avatar_media_id: string | null;
  created_at: string;
};

export async function getUser(request: Request): Promise<Profile | null> {
  if (!request.headers.get("cookie")?.includes("smoodie_session")) return null;
  const result = await apiFetch<Profile>("/v1/users/me", { request });
  return result.ok ? result.data : null;
}

/**
 * For pages that require a session. Sends unauthenticated visitors to sign in
 * and brings them back to where they were headed afterwards.
 */
export async function requireUser(
  request: Request,
  redirectTo?: string,
): Promise<Profile> {
  const user = await getUser(request);
  if (user) return user;

  const target = redirectTo ?? new URL(request.url).pathname;
  const params = new URLSearchParams({ next: target });
  throw redirect(`/login?${params}`);
}

/**
 * Only same-origin paths are honoured, so a crafted `?next=` cannot bounce
 * someone to another site after they sign in.
 */
export function safeRedirect(target: FormDataEntryValue | null, fallback = "/"): string {
  if (typeof target !== "string") return fallback;
  if (!target.startsWith("/") || target.startsWith("//")) return fallback;
  return target;
}
