import routeData from "./routes.json";

export type RouteSection = "home" | "training" | "tools" | "help" | "more";

export interface AppRoute {
  path: string;
  title: string;
  section: RouteSection;
  description: string;
}

export const routes = routeData as AppRoute[];

export const routeByPath = new Map(routes.map((route) => [route.path, route]));

export const navGroups: { section: RouteSection; label: string }[] = [
  { section: "training", label: "训练" },
  { section: "tools", label: "工具与调试" },
  { section: "help", label: "帮助" },
  { section: "more", label: "其他" },
];

export function normalizePath(pathname: string): string {
  if (!pathname || pathname === "/index.html") return "/";
  return pathname.endsWith(".md") ? `${pathname.slice(0, -3)}.html` : pathname;
}

export function currentRoute(pathname = window.location.pathname): AppRoute {
  return routeByPath.get(normalizePath(pathname)) ?? {
    path: normalizePath(pathname),
    title: "兼容路由",
    section: "home",
    description: "This route is not migrated yet; it is reserved for compatibility.",
  };
}
