import type { Preview } from "@storybook/react";
import "../src/globals.css";

const preview: Preview = {
  parameters: { backgrounds: { default: "dark", values: [{ name: "dark", value: "#07080C" }, { name: "light", value: "#F5F7FA" }] } },
  globals: { backgrounds: { value: "#07080C" } },
};
export default preview;
