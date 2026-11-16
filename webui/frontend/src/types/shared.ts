// The props every page gets (webui/app.py's `inertia_page`), typed for `usePage()`.
import type { Layout } from "./generated/webui.service.layout";

export type Errors = Record<string, string>;

declare module "@inertiajs/core" {
  export interface InertiaConfig {
    sharedPageProps: {
      layout: Layout;
      errors: Errors;
    };
  }
}
