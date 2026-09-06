import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("login", "routes/login.tsx"),
  route("signup", "routes/signup.tsx"),
  route("logout", "routes/logout.tsx"),
  route("settings/profile", "routes/settings.profile.tsx"),
  route("posts/new", "routes/posts.new.tsx"),
  // Resource route: the browser's half of the signed-URL upload conversation.
  route("uploads", "routes/uploads.ts"),
  // Last: a bare :username would otherwise shadow the literal paths above.
  route("u/:username", "routes/profile.tsx"),
] satisfies RouteConfig;
