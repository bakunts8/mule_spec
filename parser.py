import yaml
import json
import os
from pyraml import parser
from urllib.parse import urlparse

def resolve_raml_references(data, base_path):
    """
    Recursively resolves !include tags in RAML data.
    NOTE: This is a simplified resolver. pyraml-parser handles this internally,
          but this shows the manual concept if needed.
    """
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if k == '!include':
                include_path = os.path.normpath(os.path.join(base_path, v))
                if os.path.exists(include_path):
                    with open(include_path, 'r') as f:
                        # Decide whether to parse as YAML or return raw content
                        # based on file extension or context (simplifying here)
                        if include_path.endswith(('.yaml', '.raml')):
                             # Important: Use safe_load
                            included_content = yaml.safe_load(f)
                            # Recursively resolve includes within the included file
                            resolved_content = resolve_raml_references(included_content, os.path.dirname(include_path))
                            # If the included file just returns a simple value (like a string)
                            # return it directly. Otherwise, return the resolved dict/list.
                            # This part might need adjustment based on RAML structure.
                            return resolved_content
                        else: # Handle JSON, XML, text examples etc.
                             return f.read()
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
    """
    if not isinstance(raml_type_def, dict):
        # Handle simple type names like 'string', 'integer'
        # This might need more context depending on how types are defined/referenced
        return {'type': raml_type_def}

    json_schema = {}
    raml_type = raml_type_def.get('type', 'object') # Default to object if not specified

    # Type mapping
    type_mapping = {
        'string': 'string',
        'number': 'number',
        'integer': 'integer',
        'boolean': 'boolean',
        'array': 'array',
        'object': 'object',
        'file': 'string', # JSON Schema doesn't have a direct file type, often represented as string (e.g., base64)
        'datetime': 'string', # Often 'string' with 'format': 'date-time'
        'date-only': 'string', # Often 'string' with 'format': 'date'
        'time-only': 'string', # Often 'string' with 'format': 'time'
        # Add other RAML types as needed
    }

    # Handle inheritance (simplified)
    if isinstance(raml_type, list):
         # Very basic handling: use the first type for now
         # Complex inheritance requires merging properties/schemas
        raml_type = raml_type[0]

    if isinstance(raml_type, str) and raml_type in type_mapping:
       json_schema['type'] = type_mapping[raml_type]
    elif isinstance(raml_type, str):
       # This could be a reference to another type defined elsewhere
       # The parser should resolve this, but you might need specific handling
       # For simplicity, treating as object for now
       print(f"Warning: Unrecognized or unresolved type reference '{raml_type}'. Treating as object.")
       json_schema['type'] = 'object'


    # Properties mapping (for objects)
    if json_schema.get('type') == 'object' and 'properties' in raml_type_def:
        json_schema['properties'] = {}
        required_props = []
        for prop_name, prop_def in raml_type_def['properties'].items():
            # Handle required property notation (e.g., "name:" vs "name?:")
            clean_prop_name = prop_name.replace('?', '')
            is_required = not prop_name.endswith('?')

            if isinstance(prop_def, str): # Simple type declaration, e.g., name: string
                json_schema['properties'][clean_prop_name] = raml_type_to_json_schema(prop_def)
            elif isinstance(prop_def, dict): # Inline type definition
                json_schema['properties'][clean_prop_name] = raml_type_to_json_schema(prop_def)

            if is_required:
                required_props.append(clean_prop_name)

        if required_props:
            json_schema['required'] = required_props

    # Items mapping (for arrays)
    if json_schema.get('type') == 'array' and 'items' in raml_type_def:
       json_schema['items'] = raml_type_to_json_schema(raml_type_def['items'])

    # Other common constraints
    if 'description' in raml_type_def:
        json_schema['description'] = raml_type_def['description']
    if 'default' in raml_type_def:
        json_schema['default'] = raml_type_def['default']
    if 'enum' in raml_type_def:
        json_schema['enum'] = raml_type_def['enum']
    if 'pattern' in raml_type_def:
        json_schema['pattern'] = raml_type_def['pattern']
    if 'minLength' in raml_type_def:
        json_schema['minLength'] = raml_type_def['minLength']
    if 'maxLength' in raml_type_def:
        json_schema['maxLength'] = raml_type_def['maxLength']
    # Add mappings for minimum, maximum, format, etc.

    return json_schema


def generate_json_schema_from_raml_file(raml_file_path):
    """
    Loads a RAML file, resolves references, extracts type definitions,
    and converts them into a JSON schema.

    Args:
        raml_file_path (str): The path to the root RAML file.

    Returns:
        dict: A dictionary representing the JSON schema for the types,
              or None if an error occurs.
              The schema structure might contain definitions under a 'definitions'
              or '$defs' key, mapping RAML type names to their JSON schema.
    """
    try:
        # pyraml-parser automatically handles !include and 'uses' resolution
        # when loading the root file.
        parsed_raml = parser.load(raml_file_path)

        # --- Manual Include Resolution (Alternative/Fallback if parser doesn't handle everything) ---
        # base_path = os.path.dirname(raml_file_path)
        # with open(raml_file_path, 'r') as f:
        #     raw_raml_data = yaml.safe_load(f) # Use safe_load!
        # resolved_raml_data = resolve_raml_references(raw_raml_data, base_path)
        # parsed_raml = resolved_raml_data # Use this if pyraml-parser is not used/available
        # --- End Manual Resolution ---


        json_schema_output = {
            "$schema": "http://json-schema.org/draft-07/schema#", # Or another version
            "title": parsed_raml.title,
            "$defs": {} # Using $defs for reusable definitions (common practice)
                         # 'definitions' is also used in older drafts
        }

        if not hasattr(parsed_raml, 'types') or not parsed_raml.types:
             print("Warning: No 'types' section found in the RAML.")
             # Attempt to generate schema from resource bodies if types are missing
             # This requires iterating through parsed_raml.resources and their methods/bodies
             # For now, returning an empty schema for types.
             return json_schema_output # Return basic schema structure

        # Convert each defined RAML type
        for type_name, type_definition in parsed_raml.types.items():
            # The parser gives you objects; access raw data if needed via .raw
            raml_type_def = type_definition.raw
            json_schema_output["$defs"][type_name] = raml_type_to_json_schema(raml_type_def)

        # Optionally: If you want a schema specifically for a request/response body
        # of a particular resource/method, you'd navigate parsed_raml.resources
        # find the specific body (e.g., application/json) and convert its 'type' reference.
        # Example: Find first POST request body for /users
        # user_post_body_type = parsed_raml.resources['/users'].methods['post'].body['application/json'].type
        # if user_post_body_type in json_schema_output["$defs"]:
        #    specific_schema = json_schema_output["$defs"][user_post_body_type]
        # else: # Handle inline type definitions if not referencing a global type
        #    specific_schema = raml_type_to_json_schema(parsed_raml.resources['/users'].methods['post'].body['application/json'].raw)


        return json_schema_output

    except FileNotFoundError:
        print(f"Error: RAML file not found at {raml_file_path}")
        return None
    except Exception as e:
        print(f"An error occurred during RAML parsing or schema generation: {e}")
        # Consider more specific error handling based on pyraml-parser exceptions
        return None

# --- Example Usage ---
# Make sure you have a RAML file (e.g., 'api.raml') in the same directory
# or provide the full path.
raml_path = 'path/to/your/api.raml' # <--- CHANGE THIS TO YOUR RAML FILE PATH

final_schema = generate_json_schema_from_raml_file(raml_path)

if final_schema:
    print("\nGenerated JSON Schema:")
    # Use json.dumps for pretty printing
    print(json.dumps(final_schema, indent=2))

    # Example: Save to a file
    # output_filename = 'generated_schema.json'
    # with open(output_filename, 'w') as f:
    #     json.dump(final_schema, f, indent=2)
    # print(f"\nSchema saved to {output_filename}")