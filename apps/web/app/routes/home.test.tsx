import { expect, test } from "vitest";
import { meta } from "./home";
import type { Route } from "./+types/home";

/** meta only reads the fields it needs; the rest of the args are router noise. */
function metaArgs(): Route.MetaArgs {
  return {} as unknown as Route.MetaArgs;
}

test("home meta sets the page title", () => {
  const tags = meta(metaArgs());
  expect(tags).toContainEqual({ title: "smoodie — eat, drink, cook, share" });
});

test("home meta includes a description for search results", () => {
  const tags = meta(metaArgs());
  const description = tags.find((tag) => "name" in tag && tag.name === "description");
  expect(description).toBeDefined();
});
