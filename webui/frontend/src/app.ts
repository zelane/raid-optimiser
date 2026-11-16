// The front end's entry: Inertia mounts the page the server names (`pages/<Name>.vue`) inside
// the app's frame (`layouts/AppLayout.vue`, kept across visits).
import { createInertiaApp } from "@inertiajs/vue3";
import { createApp, h, type DefineComponent } from "vue";
import AppLayout from "./layouts/AppLayout.vue";

const pages = import.meta.glob<DefineComponent>("./pages/**/*.vue");

createInertiaApp({
  title: (title) => (title ? `${title}: Raid optimiser` : "Raid optimiser"),
  resolve: async (name) => {
    const load = pages[`./pages/${name}.vue`];
    if (!load) throw new Error(`no page component ${name}`);
    return load();
  },
  layout: () => AppLayout,
  setup({ el, App, props, plugin }) {
    createApp({ render: () => h(App, props) })
      .use(plugin)
      .mount(el!);
  },
  progress: { color: "var(--primary)" },
});
