/**
 * Server-side API client.
 *
 * Loaders and actions run on the server, so they talk to the API directly and
 * forward the caller's session cookie. Nothing here should ever run in the
 * browser — the API base URL is an internal service address.
 */

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export const SESSION_COOKIE = "smoodie_session";

export type ApiResult<T> =
  | { ok: true; data: T; setCookie: string | null }
  | { ok: false; status: number; error: ApiError };

/** Field-addressed errors so forms can render messages next to the input. */
export type ApiError = {
  message: string;
  fieldErrors: Record<string, string>;
};

type FastApiDetail =
  | string
  | Array<{ loc: (string | number)[]; msg: string; type?: string }>;

/**
 * FastAPI reports validation failures as a list of per-field entries and
 * everything else as a plain string. Both are normalized here so callers never
 * have to branch on the shape.
 */
export function parseApiError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: FastApiDetail } | null)?.detail;

  if (typeof detail === "string") {
    return { message: detail, fieldErrors: {} };
  }

  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    for (const item of detail) {
      const field = item.loc?.[item.loc.length - 1];
      if (typeof field === "string" && !(field in fieldErrors)) {
        fieldErrors[field] = item.msg;
      }
    }
    const first = Object.values(fieldErrors)[0];
    return {
      message: first ?? "Something in that form wasn't valid.",
      fieldErrors,
    };
  }

  return {
    message:
      status >= 500
        ? "smoodie is having a problem. Try again in a moment."
        : "That didn't work.",
    fieldErrors: {},
  };
}

export function sessionCookieHeader(request: Request): string | undefined {
  const cookie = request.headers.get("cookie");
  return cookie ?? undefined;
}

export async function apiFetch<T>(
  path: string,
  options: {
    request?: Request;
    method?: string;
    body?: unknown;
    cookie?: string;
  } = {},
): Promise<ApiResult<T>> {
  const { request, method = "GET", body, cookie } = options;

  const headers: Record<string, string> = { accept: "application/json" };
  const forwarded = cookie ?? (request ? sessionCookieHeader(request) : undefined);
  if (forwarded) headers.cookie = forwarded;
  if (body !== undefined) headers["content-type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // The API being unreachable is an outage, not a user error — say so plainly
    // rather than surfacing a fetch stack trace.
    return {
      ok: false,
      status: 503,
      error: {
        message: "Can't reach smoodie right now. Try again in a moment.",
        fieldErrors: {},
      },
    };
  }

  if (response.status === 204) {
    return {
      ok: true,
      data: undefined as T,
      setCookie: response.headers.get("set-cookie"),
    };
  }

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      error: parseApiError(response.status, payload),
    };
  }

  return {
    ok: true,
    data: payload as T,
    setCookie: response.headers.get("set-cookie"),
  };
}
