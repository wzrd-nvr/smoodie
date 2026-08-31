import { redirect } from "react-router";
import type { Route } from "./+types/logout";
import { apiFetch } from "../lib/api.server";

/**
 * Action-only route. Sign-out is a POST so it cannot be triggered by a link
 * prefetch or an <img> tag pointed at /logout.
 */
export async function action({ request }: Route.ActionArgs) {
  const result = await apiFetch<unknown>("/v1/auth/session", {
    method: "DELETE",
    request,
  });

  const headers = new Headers();
  if (result.ok && result.setCookie) {
    headers.append("set-cookie", result.setCookie);
  }
  return redirect("/", { headers });
}

/** Someone landing here via GET just goes home. */
export async function loader() {
  return redirect("/");
}
