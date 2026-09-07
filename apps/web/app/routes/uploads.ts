/**
 * Upload brokering for the browser.
 *
 * The browser cannot call the API directly: the session cookie belongs to this
 * origin and the API's address is internal. So it asks here for a signed URL,
 * PUTs the file straight to storage itself — the bytes never pass through this
 * server — and comes back to have the upload marked complete.
 *
 * A resource route: no component, no HTML, JSON only.
 */

import { apiFetch } from "../lib/api.server";
import { requireUser } from "../lib/session.server";
import type { Route } from "./+types/uploads";

type UploadTicket = {
  media_id: string;
  upload_url: string;
  content_type: string;
  max_bytes: number;
};

export type MediaOut = {
  id: string;
  status: string;
  content_type: string;
  bytes: number | null;
  url: string | null;
};

export async function action({ request }: Route.ActionArgs) {
  await requireUser(request);
  const form = await request.formData();
  const intent = form.get("intent");

  if (intent === "ticket") {
    const contentType = String(form.get("content_type") ?? "");
    const rawSize = Number(form.get("size_bytes"));
    const result = await apiFetch<UploadTicket>("/v1/media/uploads", {
      method: "POST",
      request,
      body: {
        content_type: contentType,
        ...(Number.isFinite(rawSize) && rawSize > 0 ? { size_bytes: rawSize } : {}),
      },
    });
    return result.ok
      ? Response.json(result.data)
      : Response.json({ message: result.error.message }, { status: result.status });
  }

  if (intent === "complete") {
    const mediaId = String(form.get("media_id") ?? "");
    const result = await apiFetch<MediaOut>(`/v1/media/${mediaId}/complete`, {
      method: "POST",
      request,
    });
    return result.ok
      ? Response.json(result.data)
      : Response.json({ message: result.error.message }, { status: result.status });
  }

  return Response.json({ message: "Unknown upload step." }, { status: 400 });
}
