// Stylelint over webui/static/*.css and the Vue components' <style> blocks (`just css`, part of
// `just check`; Prettier formats, one declaration per line): the standard config, properties in one order everywhere
// (stylelint-order, with the clean-order preset's groups: interaction, positioning, layout, box
// model, typography, appearance, transition), and native nesting no deeper than 3.
//
// Left to the components: specificity (no-descending-specificity flags ordinary component
// overrides). The order goes without the preset's blank lines between groups (a rule's
// declarations are one block). Font family names keep their capitals; -webkit-text-size-adjust
// stays (iOS Safari).
import order from "stylelint-order";
import { propertyGroups } from "stylelint-config-clean-order";

export default {
  extends: ["stylelint-config-standard"],
  plugins: [order],
  rules: {
    "order/order": [
      "custom-properties",
      "declarations",
      "rules",
      { type: "at-rule", name: "media", hasBlock: true },
    ],
    "order/properties-order": [
      propertyGroups.map((properties) => ({ properties })),
      { unspecified: "bottomAlphabetical" },
    ],
    // Sizes and colours come from theme.css's tokens: no rem literals in spacing, font sizes
    // or radii (em stays, for sizes relative to their context; px for hairlines), no raw
    // colours outside custom properties, no bare durations in transitions.
    "declaration-property-value-disallowed-list": [
      {
        "/^(margin|padding|gap|row-gap|column-gap|inset|top|right|bottom|left)(-|$)/": [
          "/\\drem/",
        ],
        "font-size": ["/\\d(rem|px)/"],
        "/^border(-[a-z]+)*-radius$/": ["/\\d(rem|px)/"],
        "/^transition/": ["/\\dm?s\\b/"],
        "/^(color|background|border|outline|box-shadow|text-shadow|fill|stroke|text-decoration)/":
          ["/#[0-9a-f]{3,8}\\b/i", "/\\b(rgb|hsl|hwb|lab|lch|oklab|oklch)a?\\(/"],
      },
      { message: (property, value) => `"${property}: ${value}": use a theme.css token` },
    ],
    "no-descending-specificity": null,
    "max-nesting-depth": 3,
    "value-keyword-case": ["lower", { ignoreProperties: ["font-family", "/^--font/"] }],
    // iOS Safari still wants it prefixed.
    "property-no-vendor-prefix": [
      true,
      { ignoreProperties: ["text-size-adjust", "-webkit-text-size-adjust"] },
    ],
  },
  // A component's <style scoped> is checked like the stylesheets. Its template's inline styles
  // are too: the primitives' parameters (`--space: …; --align: …`) sit on one line there.
  overrides: [
    {
      files: ["**/*.vue"],
      customSyntax: "postcss-html",
      rules: { "custom-property-empty-line-before": null },
    },
  ],
};
