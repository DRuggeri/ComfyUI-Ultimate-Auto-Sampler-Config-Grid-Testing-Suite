/**
 * Help note for the UltimateSamplerGrid node.
 * After the widget cleanup (commit 30e3aa9), the node is nearly empty —
 * just one required input (configs_json), six optional sockets, and a
 * single output. New users don't know how to wire it up. This adds a
 * small always-visible footnote at the bottom of the node.
 */

import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "UltimateSamplerGrid.HelpNote",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "UltimateSamplerGrid") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);

            const helpDiv = document.createElement("div");
            helpDiv.textContent =
                "Connect the configs_json from the Builder node to this node, " +
                "and connect this node to the Dashboard node";
            helpDiv.style.cssText = [
                "font-size: 11px",
                "color: #888",
                "padding: 8px 12px",
                "line-height: 1.4",
                "text-align: center",
                "white-space: normal",
                "background: #1a1a1a",
                "border-top: 1px solid #2a2a2a",
                "border-radius: 0 0 4px 4px",
                "user-select: none",
                "pointer-events: none",
            ].join("; ");

            this.addDOMWidget("help_note", "div", helpDiv, {
                serialize: false,
                hideOnZoom: false,
                getHeight: () => 44,
            });

            return result;
        };
    },
});
