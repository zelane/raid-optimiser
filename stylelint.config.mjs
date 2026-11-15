// Stylelint over webui/static/*.css (`just css`, part of `just check`; Prettier formats, one
// declaration per line): the standard config, properties in one order everywhere
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
    "no-descending-specificity": null,
    "max-nesting-depth": 3,
    "value-keyword-case": ["lower", { ignoreProperties: ["font-family", "/^--font/"] }],
    // iOS Safari still wants it prefixed.
    "property-no-vendor-prefix": [
      true,
      { ignoreProperties: ["text-size-adjust", "-webkit-text-size-adjust"] },
    ],
  },
};
