// Saving a setting from a page: posted as form data (webui/forms parse it), the server sends
// the page back, and only `only` (the page's own prop, by default) is reloaded.
import { router } from "@inertiajs/vue3";

export function save(url: string, fields: Record<string, string>, only: string[] = ["page"]) {
  router.post(url, fields, {
    forceFormData: true,
    preserveScroll: true,
    preserveState: true,
    only,
  });
}
