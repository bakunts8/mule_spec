import yaml
import json
import os
from pyraml import parser
from urllib.parse import urlparse

# Note: Ensure 'pyraml-parser' and 'PyYAML' are installed:
# pip install pyraml-parser PyYAML

def resolve_raml_references(data, base_path):
    """
    Recursively resolves !include tags in RAML data.
    NOTE: This is a simplified resolver. pyraml-parser handles this internally,
          but this shows the manual concept if needed. Kept for reference.
    """
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if k == '!include':
                # Normalize path and join with base path
                include_path = os.path.normpath(os.path.join(base_path, v))
                if os.path.exists(include_path):
                    with open(include_path, 'r') as f:
                        # Decide whether to parse as YAML or return raw content
                        # based on file extension or context (simplifying here)
                        if include_path.endswith(('.yaml', '.raml')):
                            try:
                                # Important: Use safe_load
                                included_content = yaml.safe_load(f)
                                # Recursively resolve includes within the included file
                                resolved_content = resolve_raml_references(included_content, os.path.dirname(include_path))
                                # If the included file just returns a simple value (like a string)
                                # return it directly. Otherwise, return the resolved dict/list.
                                # This part might need adjustment based on RAML structure.
                                return resolved_content
                            except yaml.YAMLError as exc:
                                print(f"Warning: Error parsing included YAML file: {include_path} - {exc}")
                                return None # Or raise an error
                        else: # Handle JSON, XML, text examples etc.
                            try:
                                return f.read()
                            except Exception as e:
                                print(f"Warning: Error reading included file: {include_path} - {e}")
                                return None
                else:
                    print(f"Warning: Included file not found: {include_path}")
                    return None # Or raise an error
            else:
                new_dict[k] = resolve_raml_references(v, base_path)
        return new_dict
    elif isinstance(data, list):
        new_list = []
        for item in data:
            new_list.append(resolve_raml_references(item, base_path))
        return new_list
    else:
        return data

def raml_type_to_json_schema(raml_type_def):
    """
    Converts a single RAML type definition to a JSON schema fragment.
    This is a simplified converter and needs to be extended for full RAML spec.
    Handles basic types, object properties, array items, and common facets.
    """
    if not isinstance(raml_type_def, dict):
        # Handle simple type names like 'string', 'integer' passed directly
        # e.g. properties: { name: string }
        if isinstance(raml_type_def, str):
             # Basic type mapping for direct references
             type_mapping = {
                'string': 'string',
                'number': 'number',
                'integer': 'integer',
                'boolean': 'boolean',
                'array': 'array', # Needs 'items' usually defined inline
                'object': 'object', # Needs 'properties' usually defined inline
                'file': 'string',
                'datetime': 'string',
                'date-only': 'string',
                'time-only': 'string',
                'nil': 'null'
            }
             json_type = type_mapping.get(raml_type_def, 'object') # Default to object if unknown basic type
             schema = {'type': json_type}
             if raml_type_def == 'datetime': schema['format'] = 'date-time'
             if raml_type_def == 'date-only': schema['format'] = 'date'
             if raml_type_def == 'time-only': schema['format'] = 'time'
             return schema
        else:
             # If it's not a dict or string, it's unclear how to handle
             print(f"Warning: Unexpected format for type definition: {raml_type_def}. Skipping.")
             return {}


    json_schema = {}

    # Determine the base RAML type ('type' property)
    raml_base_type = raml_type_def.get('type', 'object') # Default to object if 'type' is not specified

    # Handle type inheritance (simplified - uses first type in list)
    # Proper handling requires merging schemas which is complex.
    if isinstance(raml_base_type, list):
        if not raml_base_type:
             print("Warning: Empty type list encountered.")
             raml_base_type = 'object' # Fallback
        else:
            # TODO: Implement proper merging strategy for multiple inheritance if needed
            print(f"Warning: Multiple inheritance detected ({raml_base_type}). Using first type '{raml_base_type[0]}' for basic conversion.")
            raml_base_type = raml_base_type[0]

    # Basic Type Mapping
    type_mapping = {
        'string': 'string',
        'number': 'number',
        'integer': 'integer',
        'boolean': 'boolean',
        'array': 'array',
        'object': 'object',
        'file': 'string', # Often represented as string (e.g., base64 or URI) in JSON Schema
        'datetime': 'string', # Usually with format
        'date-only': 'string', # Usually with format
        'time-only': 'string', # Usually with format
        'nil': 'null'       # Maps RAML nil type to JSON Schema null type
        # Add other custom or built-in RAML types if needed
    }

    if isinstance(raml_base_type, str) and raml_base_type in type_mapping:
       json_schema['type'] = type_mapping[raml_base_type]
       # Add format for specific string types
       if raml_base_type == 'datetime': json_schema['format'] = 'date-time'
       if raml_base_type == 'date-only': json_schema['format'] = 'date'
       if raml_base_type == 'time-only': json_schema['format'] = 'time'
       # File type doesn't have a standard format, maybe 'binary' or 'byte' sometimes used
       if raml_base_type == 'file': json_schema.setdefault('description', 'Represents file content, often as base64 or a URI.')

    elif isinstance(raml_base_type, str):
        # If the type is a string but not in our basic map,
        # it's likely a reference to another type defined elsewhere (e.g., in 'types:' or libraries).
        # We *assume* pyraml-parser resolves this, but the definition might be complex.
        # For JSON schema, we often represent this as a reference within the same document.
        # Here, we'll just mark it as potentially complex object or defer resolution.
        # A better approach might involve passing the full 'types' map for lookup.
        # For now, treating as 'object' as a fallback if structure isn't inline.
        print(f"Info: Type '{raml_base_type}' is likely a reference to another defined type.")
        # If properties are defined inline, it's likely an anonymous subtype/object
        if 'properties' in raml_type_def:
            json_schema['type'] = 'object'
        else:
             # It's likely just a reference. We can represent this in JSON Schema too.
             # This assumes the type name corresponds to a definition in $defs
             # json_schema['$ref'] = f'#/$defs/{raml_base_type}'
             # However, since this function converts *one* type, maybe just 'object' is safer
             # Or rely on the calling function to place this within $defs correctly.
             # Let's default to object if no properties are given inline.
             json_schema['type'] = 'object'
             json_schema.setdefault('description', f"Reference to RAML type: {raml_base_type}")


    # --- Map Common RAML Facets to JSON Schema Keywords ---

    if 'description' in raml_type_def:
        json_schema['description'] = raml_type_def['description']
    if 'default' in raml_type_def:
        json_schema['default'] = raml_type_def['default']
    if 'enum' in raml_type_def:
        json_schema['enum'] = raml_type_def['enum']

    # String Facets
    if 'pattern' in raml_type_def:
        json_schema['pattern'] = raml_type_def['pattern']
    if 'minLength' in raml_type_def:
        json_schema['minLength'] = raml_type_def['minLength']
    if 'maxLength' in raml_type_def:
        json_schema['maxLength'] = raml_type_def['maxLength']

    # Number Facets
    # RAML 'minimum'/'maximum' map directly
    if 'minimum' in raml_type_def:
        json_schema['minimum'] = raml_type_def['minimum']
    if 'maximum' in raml_type_def:
        json_schema['maximum'] = raml_type_def['maximum']
    # RAML 'format' for numbers (int, int8, int16, int32, int64, float, double)
    # JSON Schema doesn't have direct numeric formats, but 'type' (integer/number) covers it.
    # Could add validation pattern or comments if needed.
    if 'format' in raml_type_def and json_schema.get('type') in ['number', 'integer']:
         json_schema.setdefault('description', json_schema.get('description',''))
         json_schema['description'] += f" (RAML format: {raml_type_def['format']})"


    # --- Object Specific ---
    if json_schema.get('type') == 'object':
        required_props = []
        if 'properties' in raml_type_def and isinstance(raml_type_def['properties'], dict):
            json_schema['properties'] = {}
            for prop_name, prop_def in raml_type_def['properties'].items():
                # Handle required property notation (e.g., "name:" vs "name?:")
                clean_prop_name = prop_name.rstrip('?')
                # RAML 'required' facet overrides '?' marker if both present
                is_required = prop_def.get('required', True) if isinstance(prop_def, dict) else True # Default required=true
                if prop_name.endswith('?'): # Optional marker '?' sets required=false unless overridden
                    is_required = prop_def.get('required', False) if isinstance(prop_def, dict) else False


                # Recursively convert the property's type definition
                json_schema['properties'][clean_prop_name] = raml_type_to_json_schema(prop_def)

                if is_required:
                    required_props.append(clean_prop_name)

        # Add 'required' array if any properties are required
        if required_props:
            json_schema['required'] = sorted(list(set(required_props))) # Ensure uniqueness and sort

        # RAML allows additionalProperties directly; map it
        if 'additionalProperties' in raml_type_def:
            # JSON schema expects boolean or a schema for additionalProperties
            if isinstance(raml_type_def['additionalProperties'], bool):
                 json_schema['additionalProperties'] = raml_type_def['additionalProperties']
            elif isinstance(raml_type_def['additionalProperties'], (dict, str)): # Could be inline type or ref
                 # Simple case: assume 'true' if complex type provided, as standard schema allows any valid value.
                 # For stricter validation, convert the type schema:
                 # json_schema['additionalProperties'] = raml_type_to_json_schema(raml_type_def['additionalProperties'])
                 # For simplicity now, just allowing any additional properties if specified non-boolean:
                 if str(raml_type_def['additionalProperties']).lower() == 'false':
                     json_schema['additionalProperties'] = False
                 else:
                     json_schema['additionalProperties'] = True # Or convert the schema if needed
                     print(f"Info: Handling complex 'additionalProperties' for type '{raml_base_type}' as 'true'. For specific schema, enhance conversion.")

            # Could also check minProperties, maxProperties if needed


    # --- Array Specific ---
    if json_schema.get('type') == 'array':
        # RAML 'items' defines the type of array elements
        if 'items' in raml_type_def:
           json_schema['items'] = raml_type_to_json_schema(raml_type_def['items'])
        else:
            # If 'items' is missing, JSON schema typically assumes items can be of any type.
            # Add empty schema object {} for items to indicate any type is allowed.
             json_schema['items'] = {}
             print(f"Warning: Array type definition found without 'items'. Assuming items can be of any type.")


        # RAML array constraints
        if 'minItems' in raml_type_def:
            json_schema['minItems'] = raml_type_def['minItems']
        if 'maxItems' in raml_type_def:
            json_schema['maxItems'] = raml_type_def['maxItems']
        if 'uniqueItems' in raml_type_def:
            json_schema['uniqueItems'] = raml_type_def['uniqueItems']


    # Clean up empty descriptions that might have been added
    if 'description' in json_schema and not json_schema['description'].strip():
         del json_schema['description']

    return json_schema


def generate_json_schema_from_raml_file(raml_file_path):
    """
    Loads a root RAML file, resolves references using pyraml-parser,
    extracts type definitions from the 'types' section, and converts
    them into a JSON schema document with definitions under '$defs'.

    Args:
        raml_file_path (str): The path to the root RAML file.

    Returns:
        dict: A dictionary representing the JSON schema for the types,
              structured with a '$defs' section, or None if an error occurs.
    """
    try:
        print(f"Parsing RAML file: {raml_file_path}")
        # pyraml-parser automatically handles !include and 'uses' resolution
        # when loading the root file.
        parsed_raml = parser.load(raml_file_path)
        print("RAML parsing successful.")

        # Prepare the base JSON schema structure
        json_schema_output = {
            # Using Draft 7, but could be changed
            "$schema": "http://json-schema.org/draft-07/schema#",
             # Use RAML title if available, otherwise provide a default
            "title": getattr(parsed_raml, 'title', 'API Types Schema'),
             # Use $defs for reusable definitions (Draft 7+ standard)
            "$defs": {}
        }
         # Add top-level description if present in RAML
        if hasattr(parsed_raml, 'description') and parsed_raml.description:
             json_schema_output['description'] = str(parsed_raml.description) # Ensure it's a string

        # Check if the 'types' attribute exists and is not empty
        if not hasattr(parsed_raml, 'types') or not parsed_raml.types:
             print("Warning: No 'types' section found or it is empty in the parsed RAML.")
             # Consider checking resources for inline type definitions if needed
             # For now, returning the basic schema structure without type definitions.
             return json_schema_output

        print(f"Found {len(parsed_raml.types)} types in the RAML definition. Converting to JSON Schema...")

        # Convert each defined RAML type found in the 'types' section
        type_count = 0
        for type_name, type_definition in parsed_raml.types.items():
            # The parser provides objects; access raw RAML data via .raw
            # The .raw attribute holds the original dictionary structure for the type
            if hasattr(type_definition, 'raw') and isinstance(type_definition.raw, dict):
                raml_type_def_dict = type_definition.raw
                print(f"  Converting type: '{type_name}'...")
                converted_schema = raml_type_to_json_schema(raml_type_def_dict)
                # Add the converted schema to the $defs section
                json_schema_output["$defs"][type_name] = converted_schema
                type_count += 1
            else:
                print(f"Warning: Could not get raw dictionary definition for type '{type_name}'. Skipping.")

        print(f"Successfully converted {type_count} types.")
        return json_schema_output

    except FileNotFoundError:
        print(f"Error: RAML file not found at {raml_file_path}")
        return None
    except ImportError:
        print("Error: Required libraries ('pyraml-parser', 'PyYAML') not found.")
        print("Please install them using: pip install pyraml-parser PyYAML")
        return None
    except Exception as e:
        # Catching generic Exception to provide feedback on any parsing/conversion error
        print(f"An error occurred during RAML parsing or schema generation: {e}")
        import traceback
        traceback.print_exc() # Print stack trace for debugging
        # Consider more specific error handling based on pyraml-parser exceptions if possible
        return None

# --- Example Usage ---
if __name__ == "__main__": # Ensures this block runs only when script is executed directly
    # Set the path to the main RAML specification file.
    # Assumes 'spec.raml' is in the same directory as 'parser.py' or provide a full path.
    raml_path = 'spec.raml' # <--- MODIFIED TO POINT TO spec.raml

    print("-" * 30)
    print("Starting RAML to JSON Schema Generation")
    print(f"Input RAML file: {os.path.abspath(raml_path)}") # Show absolute path
    print("-" * 30)


    final_schema = generate_json_schema_from_raml_file(raml_path)

    print("-" * 30)
    if final_schema:
        print("Generated JSON Schema Document:")
        # Use json.dumps for pretty printing with indentation
        print(json.dumps(final_schema, indent=2))

        # --- Optional: Save to a file ---
        output_filename = 'generated_schema.json'
        try:
            with open(output_filename, 'w') as f:
                json.dump(final_schema, f, indent=2)
            print("-" * 30)
            print(f"Schema successfully saved to: {output_filename}")
        except IOError as e:
            print(f"Error saving schema to file '{output_filename}': {e}")
        # --- End Optional Save ---

    else:
        print("JSON Schema generation failed.")
    print("-" * 30)