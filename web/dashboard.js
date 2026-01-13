import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

app.registerExtension({
    name: "UltimateGrid.Dashboard",

    setup(app) {
        // 1. INJECT CSS
        if (!document.getElementById('ultimate-grid-css')) {
            const style = document.createElement('style');
            style.id = 'ultimate-grid-css';
            style.innerHTML = `
                .dashboard-fullscreen {
                    position: fixed !important;
                    top: 0; left: 0; width: 100vw !important; height: 100vh !important;
                    z-index: 99999 !important;
                    background: #0b0b0b;
                    border: none !important;
                }
            `;
            document.head.appendChild(style);
        }

        // 2. LIVE UPDATE LISTENER (FIXED)

        // 2. LIVE UPDATE LISTENER - AUTO-LOAD SESSION
        api.addEventListener("ultimate_grid.update", (event) => {
            const payload = event.detail;
            const { session_name, node } = payload;  // node is the SAMPLER node ID

            console.log(`[UltimateGrid] Received update for session: ${session_name}`);

            // Find all dashboard nodes
            const nodes = app.graph._nodes.filter(n => n.type === "UltimateGridDashboard");

            nodes.forEach(dashboardNode => {
                const sessionWidget = dashboardNode.widgets.find(w => w.name === "session_name");

                if (!sessionWidget) {
                    console.warn(`[UltimateGrid] Dashboard node ${dashboardNode.id} has no session_name widget`);
                    return;
                }

                const currentSessionName = sessionWidget.value;

                // CASE 1: Session matches and dashboard is loaded → send update
                if (currentSessionName === session_name &&
                    dashboardNode.loaded_session === session_name &&
                    dashboardNode.iframe &&
                    dashboardNode.iframe.contentWindow) {

                    console.log(`[UltimateGrid] Sending live update to loaded dashboard ${dashboardNode.id}`);
                    dashboardNode.iframe.contentWindow.postMessage({
                        type: 'update_data',
                        data: payload
                    }, '*');
                }

                // CASE 2: Session matches but dashboard not loaded → auto-load
                else if (currentSessionName === session_name &&
                    dashboardNode.loaded_session !== session_name) {

                    console.log(`[UltimateGrid] Auto-loading session ${session_name} in dashboard ${dashboardNode.id}`);
                    if (dashboardNode.forceLoadSession) {
                        dashboardNode.forceLoadSession(session_name);
                    }
                }

                // CASE 3: Session doesn't match but dashboard is connected to this sampler
                // This happens when dashboard is blank/empty but connected
                else if (currentSessionName !== session_name) {
                    // Check if this dashboard is connected to the sampler node
                    // by looking at node connections
                    const isConnected = dashboardNode.inputs?.some(input => {
                        const link = app.graph.links[input.link];
                        return link && link.origin_id === parseInt(node);
                    });

                    if (isConnected) {
                        console.log(`[UltimateGrid] Dashboard ${dashboardNode.id} is connected to sampler - updating session name to ${session_name}`);

                        // Update the session_name widget
                        sessionWidget.value = session_name;

                        // Auto-load the session
                        if (dashboardNode.forceLoadSession) {
                            dashboardNode.forceLoadSession(session_name);
                        }
                    }
                }
            });
        });
        ;

        // 3. FULLSCREEN LISTENER
        window.addEventListener("message", (event) => {
            if (event.data && event.data.type === 'toggle_fullscreen') {
                const nodeId = parseInt(event.data.node_id);
                const graphNode = app.graph.getNodeById(nodeId);

                if (graphNode && graphNode.iframe) {
                    const el = graphNode.iframe;

                    if (el.classList.contains('dashboard-fullscreen')) {
                        el.classList.remove('dashboard-fullscreen');
                        if (graphNode.fs_placeholder && graphNode.fs_placeholder.parentNode) {
                            graphNode.fs_placeholder.parentNode.insertBefore(el, graphNode.fs_placeholder);
                            graphNode.fs_placeholder.remove();
                        }
                        graphNode.fs_placeholder = null;
                        el.style.width = (graphNode.size[0] - 20) + "px";
                        el.style.height = "100%";
                    } else {
                        const ph = document.createElement("div");
                        ph.style.display = "none";
                        graphNode.fs_placeholder = ph;
                        if (el.parentNode) el.parentNode.insertBefore(ph, el);
                        document.body.appendChild(el);
                        el.classList.add('dashboard-fullscreen');
                    }
                }
            }
        });
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "UltimateGridDashboard") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                this.resizable = true;
                const node = this;
                node.loaded_session = null;

                const getSessionName = () => {
                    const w = node.widgets.find(w => w.name === "session_name");
                    return w ? w.value : null;
                };

                this.forceLoadSession = async (sessionName) => {
                    if (node.is_fetching) return;
                    node.is_fetching = true;
                    try {
                        const response = await fetch("/config_tester/get_session_html", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ session_name: sessionName, node_id: node.id })
                        });
                        if (response.ok) {
                            const html = await response.text();
                            if (node.iframe) {
                                node.iframe.srcdoc = html;
                                node.loaded_session = sessionName;
                            }
                        }
                    } catch (e) { console.error(e); }
                    finally { node.is_fetching = false; }
                };

                this.addWidget("button", "RELOAD / SHOW SESSION", null, () => {
                    const s = getSessionName();
                    if (s) this.forceLoadSession(s);
                });

                this.addWidget("button", "DELETE SESSION (Files)", null, async () => {
                    const s = getSessionName();
                    if (!s) return alert("No session name set.");
                    if (!confirm("Are you sure you want to delete this session?")) return;
                    try {
                        const resp = await fetch("/config_tester/delete_session", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ session_name: s })
                        });
                        if (resp.ok) {
                            node.iframe.srcdoc = "<h3 style='color:#888; text-align:center; padding:20px;'>Session Deleted.</h3>";
                            node.loaded_session = null;
                        } else { alert("Error: " + await resp.text()); }
                    } catch (e) { alert("Connection Error: " + e); }
                });

                this.onExecuted = function (message) {
                    if (message?.html) {
                        // Logic to prevent full reload if session is same
                        if (node.loaded_session === getSessionName()) {
                            const newHtml = message.html[0];
                            const pattern = /\/\*__JSON_START__\*\/\s*let fullManifest = (\{[\s\S]*?\});\s*\/\*__JSON_END__\*\//;
                            const match = newHtml.match(pattern);
                            if (match && match[1]) {
                                try {
                                    const newData = JSON.parse(match[1]);
                                    // Send full manifest update to iframe
                                    node.iframe.contentWindow.postMessage({ type: 'update_data', data: { manifest: newData } }, '*');
                                    return;
                                } catch (e) { }
                            }
                        }
                        node.iframe.srcdoc = message.html[0];
                        node.loaded_session = getSessionName();
                    }
                    if (message?.update_session_name && message.update_session_name[0]) {
                        const w = node.widgets.find(w => w.name === "session_name");
                        if (w) { w.value = message.update_session_name[0]; node.setDirtyCanvas(true, true); }
                    }
                };

                const widget = {
                    type: "div",
                    name: "dashboard_container",
                    draw(ctx, node, widget_width, y, widget_height) {
                        const availableHeight = (node.size[1] - y) - 26;
                        if (this.iframe) {
                            const isFullScreen = this.iframe.classList.contains('dashboard-fullscreen');
                            if (!isFullScreen) {
                                const targetW = (widget_width - 20) + "px";
                                const targetH = Math.max(100, availableHeight) + "px";
                                if (this.iframe.style.width !== targetW) this.iframe.style.width = targetW;
                                if (this.iframe.style.height !== targetH) this.iframe.style.height = targetH;
                            }
                            this.iframe.hidden = false;
                        }
                    },
                };

                const iframe = document.createElement("iframe");
                Object.assign(iframe.style, {
                    border: "none", background: "#0b0b0b", width: "100%", height: "100%",
                    display: "block", borderRadius: "0 0 4px 4px"
                });
                this.iframe = iframe;
                this.addDOMWidget("dashboard_viewer", "iframe", iframe);

                this.onResize = function (size) { node.setDirtyCanvas(true, true); }
                this.setSize([900, 750]);
                return r;
            };
        }
    },
});