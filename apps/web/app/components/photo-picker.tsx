/**
 * Photo attachment, browser-side.
 *
 * A signed-URL upload is a three-step conversation the browser has to conduct
 * itself, so unlike the rest of the composer this part genuinely needs
 * JavaScript. Without it the fields below still submit, and a recipe can still
 * be saved as a draft — the API exempts drafts from the photo requirement for
 * exactly this reason. Publishing is what needs the photo, and by then there is
 * a picture to attach.
 *
 * Each finished upload leaves a hidden input behind, so the surrounding form
 * submits media ids the same way with or without this component's involvement.
 */

import { useRef, useState } from "react";

export type Attachment = { id: string; url: string | null; name: string };

type Props = { initial?: Attachment[]; max: number; error?: string };

async function post(body: FormData): Promise<Response> {
  return fetch("/uploads", { method: "POST", body });
}

export function PhotoPicker({ initial = [], max, error }: Props) {
  const [photos, setPhotos] = useState<Attachment[]>(initial);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function upload(file: File) {
    setBusy(true);
    setProblem(null);
    try {
      const ticketForm = new FormData();
      ticketForm.set("intent", "ticket");
      ticketForm.set("content_type", file.type);
      ticketForm.set("size_bytes", String(file.size));

      const ticketResponse = await post(ticketForm);
      const ticket = await ticketResponse.json();
      if (!ticketResponse.ok) {
        setProblem(ticket?.message ?? "That image couldn't be uploaded.");
        return;
      }

      // Straight to storage. The signed URL pins the content type, so it has to
      // match the one the ticket was issued for.
      const put = await fetch(ticket.upload_url, {
        method: "PUT",
        headers: { "content-type": ticket.content_type },
        body: file,
      });
      if (!put.ok) {
        setProblem("The upload didn't finish. Try again.");
        return;
      }

      const completeForm = new FormData();
      completeForm.set("intent", "complete");
      completeForm.set("media_id", ticket.media_id);
      const completeResponse = await post(completeForm);
      const media = await completeResponse.json();
      if (!completeResponse.ok) {
        setProblem(media?.message ?? "That image couldn't be saved.");
        return;
      }

      setPhotos((current) => [...current, { id: media.id, url: media.url, name: file.name }]);
    } catch {
      setProblem("The upload didn't finish. Try again.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  const full = photos.length >= max;

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="text-sm font-medium">Photos</legend>

      {photos.map((photo) => (
        <div key={photo.id} className="flex items-center gap-3 text-sm">
          <input type="hidden" name="media_ids" value={photo.id} />
          {photo.url ? (
            <img src={photo.url} alt="" className="h-16 w-16 rounded object-cover" />
          ) : null}
          <span className="grow truncate opacity-70">{photo.name}</span>
          <button
            type="button"
            className="rounded border px-2 py-1"
            onClick={() => setPhotos((current) => current.filter((p) => p.id !== photo.id))}
          >
            Remove
          </button>
        </div>
      ))}

      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        disabled={busy || full}
        className="text-sm"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void upload(file);
        }}
      />

      {busy ? <span className="text-sm opacity-70">Uploading…</span> : null}
      {full ? <span className="text-sm opacity-70">That's the maximum of {max}.</span> : null}
      {problem ? (
        <span role="alert" className="text-sm text-red-600">
          {problem}
        </span>
      ) : null}
      {error ? (
        <span role="alert" className="text-sm text-red-600">
          {error}
        </span>
      ) : null}
    </fieldset>
  );
}
