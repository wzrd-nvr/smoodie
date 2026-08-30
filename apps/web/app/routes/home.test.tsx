import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home, { meta } from "./home";
import type { Route } from "./+types/home";

test("home renders the smoodie shell", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { name: "smoodie" })).toBeInTheDocument();
});

test("home meta sets the page title", () => {
  const tags = meta({} as Route.MetaArgs);
  expect(tags).toContainEqual({ title: "smoodie — eat, drink, cook, share" });
});
