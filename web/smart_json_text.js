import { app } from "../../scripts/app.js";

// Register the custom widget for JSON text input with validation
app.registerExtension({
    name: "SmartJSONText.Widget",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "SmartJSONText") {

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);

                const jsonWidget = this.widgets?.find(w => w.name === "json_text");

                if (jsonWidget) {
                    const originalCallback = jsonWidget.callback;

                    // Validation function
                    const validateJSON = (value) => {
                        try {
                            JSON.parse(value);
                            return { valid: true, error: null, line: null, column: null };
                        } catch (e) {
                            let errorMsg = e.message;
                            let line = null;
                            let column = null;

                            // Extract position from error message - this is most reliable
                            const positionMatch = errorMsg.match(/position (\d+)/i);
                            
                            if (positionMatch) {
                                const pos = parseInt(positionMatch[1]);
                                const upToError = value.substring(0, pos);
                                const lines = upToError.split('\n');
                                line = lines.length;
                                column = lines[lines.length - 1].length + 1;
                            } else {
                                // Try line/column directly from message
                                const lineMatch = errorMsg.match(/line (\d+)/i);
                                const columnMatch = errorMsg.match(/column (\d+)/i);
                                
                                if (lineMatch) {
                                    line = parseInt(lineMatch[1]);
                                }
                                if (columnMatch) {
                                    column = parseInt(columnMatch[1]);
                                }
                            }
                            
                            // Last resort: extract the snippet and find it in the text
                            if (!line) {
                                const snippetMatch = errorMsg.match(/"([^"]*?)"/);
                                if (snippetMatch) {
                                    let snippet = snippetMatch[1];
                                    // The snippet shows the start of the text, error is usually right after
                                    // e.g., "[f\n[\n"" means error is at 'f'
                                    
                                    // Find first non-whitespace, non-bracket character as likely error
                                    const errorCharMatch = snippet.match(/[^\[\]\s\n]/);
                                    if (errorCharMatch) {
                                        const errorChar = errorCharMatch[0];
                                        const errorOffset = snippet.indexOf(errorChar);
                                        
                                        // Count newlines up to this point in snippet
                                        const upToErrorChar = snippet.substring(0, errorOffset + 1);
                                        const newlines = (upToErrorChar.match(/\n/g) || []).length;
                                        line = newlines + 1;
                                    } else {
                                        // Just count newlines in snippet
                                        const newlines = (snippet.match(/\n/g) || []).length;
                                        line = newlines + 1;
                                    }
                                }
                            }

                            console.log(`JSON Error - Line: ${line}, Col: ${column}, Msg: ${errorMsg}`);

                            return { valid: false, error: errorMsg, line, column };
                        }
                    };

                    jsonWidget.validationResult = { valid: true };

                    // Function to apply styling to the textarea
                    const applyTextareaStyle = () => {
                        if (!jsonWidget.inputEl) return;

                        const validation = jsonWidget.validationResult;

                        // Clear all styles first to prevent stacking
                        jsonWidget.inputEl.style.background = "";
                        jsonWidget.inputEl.style.backgroundColor = "";
                        jsonWidget.inputEl.style.backgroundAttachment = "";
                        jsonWidget.inputEl.style.color = "";

                        if (!validation.valid) {
                            jsonWidget.inputEl.style.color = "#ffffff";

                            // Create line highlighting with linear gradient if we have error line
                            if (validation.line) {
                                // Get actual computed line height from textarea
                                const computedStyle = window.getComputedStyle(jsonWidget.inputEl);
                                const lineHeightStr = computedStyle.lineHeight;
                                const paddingTop = parseFloat(computedStyle.paddingTop) || 0;
                                
                                let lineHeight = 16; // Default fallback
                                
                                if (lineHeightStr && lineHeightStr !== 'normal') {
                                    lineHeight = parseFloat(lineHeightStr);
                                }
                                
                                const errorLine = validation.line - 1; // 0-indexed
                                // Account for textarea padding
                                const startPx = paddingTop + (errorLine * lineHeight);
                                const endPx = startPx + lineHeight;

                                console.log(`Applying gradient: lineHeight=${lineHeight}px, paddingTop=${paddingTop}px, errorLine=${validation.line}, range=${startPx}px-${endPx}px`);

                                // Use gradient with bright highlighted line
                                jsonWidget.inputEl.style.background = `linear-gradient(to bottom, #501414 ${startPx}px, #ff4444 ${startPx}px, #ff4444 ${endPx}px, #501414 ${endPx}px)`;
                                jsonWidget.inputEl.style.backgroundAttachment = "local";
                            } else {
                                // Just solid dark red if no line info
                                console.log('No line number detected, using solid background');
                                jsonWidget.inputEl.style.backgroundColor = "#501414";
                            }
                        }
                    };

                    // Callback with validation
                    jsonWidget.callback = function (value) {
                        const validation = validateJSON(value);
                        jsonWidget.validationResult = validation;

                        // Update node colors
                        if (!validation.valid) {
                            this.boxColor = "#ff4444";
                            this.color = "#2a0a0a";
                        } else {
                            this.boxColor = null;
                            this.color = null;
                        }

                        // Apply textarea styling
                        applyTextareaStyle();

                        if (originalCallback) {
                            originalCallback.call(this, value);
                        }

                        app.graph.setDirtyCanvas(true, true);
                    };

                    // Monitor for when the textarea element is created
                    const checkForTextarea = () => {
                        if (jsonWidget.inputEl && !jsonWidget._styledTextarea) {
                            jsonWidget._styledTextarea = true;
                            applyTextareaStyle();

                            // Re-apply on focus/blur to ensure it sticks
                            jsonWidget.inputEl.addEventListener('focus', applyTextareaStyle);
                            jsonWidget.inputEl.addEventListener('blur', applyTextareaStyle);
                        }
                    };

                    // Check periodically until textarea is created
                    const intervalId = setInterval(() => {
                        checkForTextarea();
                        if (jsonWidget._styledTextarea) {
                            clearInterval(intervalId);
                        }
                    }, 100);

                    // Also check on serialize (when element gets created)
                    const originalSerializeValue = jsonWidget.serializeValue;
                    jsonWidget.serializeValue = function () {
                        checkForTextarea();
                        return originalSerializeValue ? originalSerializeValue.call(this) : this.value;
                    };

                    // Initial validation
                    jsonWidget.callback(jsonWidget.value);

                    // Error message display
                    const originalDrawForeground = this.onDrawForeground;
                    this.onDrawForeground = function (ctx) {
                        if (originalDrawForeground) {
                            originalDrawForeground.call(this, ctx);
                        }

                        if (jsonWidget.validationResult && !jsonWidget.validationResult.valid) {
                            const result = jsonWidget.validationResult;
                            const x = 10;
                            const y = this.size[1] + 5;

                            ctx.save();
                            ctx.font = "12px monospace";
                            ctx.fillStyle = "#ff6666";

                            let errorText = "⚠ JSON Error";
                            if (result.line) {
                                errorText += ` (Line ${result.line}`;
                                if (result.column) errorText += `, Col ${result.column}`;
                                errorText += ")";
                            }

                            ctx.fillText(errorText, x, y);

                            ctx.font = "10px monospace";
                            ctx.fillStyle = "#ffaaaa";

                            const maxWidth = 400;
                            const words = result.error.split(' ');
                            let line = '';
                            let lineY = y + 15;

                            for (let word of words) {
                                const testLine = line + word + ' ';
                                const metrics = ctx.measureText(testLine);

                                if (metrics.width > maxWidth && line !== '') {
                                    ctx.fillText(line, x, lineY);
                                    line = word + ' ';
                                    lineY += 12;
                                } else {
                                    line = testLine;
                                }
                            }
                            ctx.fillText(line, x, lineY);
                            ctx.restore();
                        }
                    };
                }

                return result;
            };
        }
    }
});