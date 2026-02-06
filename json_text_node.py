import json

class SmartJSONTextNode:
    """
    A text input node with smart JSON parsing and validation.
    Displays errors inline when JSON is invalid.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "json_text": ("STRING", {
                    "multiline": True,
                    "default": "{\n  \"key\": \"value\"\n}",
                    "dynamicPrompts": False
                }),
            },
            "optional": {
                "validate_on_input": ("BOOLEAN", {"default": True}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("json_text", "parsed_json")
    FUNCTION = "process_json"
    CATEGORY = "text"
    
    def process_json(self, json_text, validate_on_input=True):
        """
        Process and validate JSON text.
        Returns both the raw text and parsed JSON (as string).
        """
        parsed_result = json_text
        
        if validate_on_input:
            try:
                # Try to parse the JSON
                parsed = json.loads(json_text)
                # Re-serialize with pretty printing
                parsed_result = json.dumps(parsed, indent=2)
            except json.JSONDecodeError as e:
                # If parsing fails, return the original text
                # The error will be shown in the UI via the widget
                parsed_result = json_text
        
        return (json_text, parsed_result)
    
    @classmethod
    def IS_CHANGED(cls, json_text, validate_on_input=True):
        # Always re-evaluate when text changes
        return json_text

NODE_CLASS_MAPPINGS = {
    "SmartJSONText": SmartJSONTextNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SmartJSONText": "Smart JSON Text"
}
