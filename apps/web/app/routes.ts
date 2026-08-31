import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("login", "routes/login.tsx"),
  route("signup", "routes/signup.tsx"),
  route("logout", "routes/logout.tsx"),
  route("settings/profile", "routes/settings.profile.tsx"),
  // Last: a bare :username would otherwise shadow the literal paths above.
  route("u/:username", "routes/profile.tsx"),
] satisfies RouteConfig;
