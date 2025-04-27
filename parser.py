import json
import os
import yaml  # PyYAML might be needed by ramlfications
import ramlfications
# Corrected import for BaseRAMLError: Import the errors module
from ramlfications import errors as raml_errors
import traceback # Import traceback for better error details

# Note: Ensure 'ramlfications' and 'PyYAML' are installed:
# pip install ramlfications PyYAML

def raml_type_to_json_schema(raml_type_obj):
    """
    Converts a single RAML type definition object (from ramlfications)
    to a JSON schema fragment.
    This is a simplified converter and needs extension for full RAML spec coverage.
    """
    if raml_type_obj is None:
        # Handle cases where a type reference might be broken or missing
        print("Warning: Encountered None instead of a type object. Returning empty schema.")
        return {}

    json_schema = {}

    # Determine the base RAML type (e.g., 'string', 'object', 'array', or a custom type name)
    # ramlfications might store the effective type in '.type' after resolving inheritance
    raml_base_type = getattr(raml_type_obj, 'type', 'object') # Default to object

    # Handle inheritance - ramlfications usually resolves this, so '.type'
    # might already be the effective base type (e.g., 'object' even if it inherited).
    # If raml_base_type is still a complex object/list, more sophisticated handling needed.
    if not isinstance(raml_base_type, str):
        # If the type itself is complex (e.g., inline definition without explicit 'type')
        # or if inheritance resolution isn't simple, default to 'object' for structure.
        # We primarily rely on presence of 'properties' or 'items' below.
        # Check if it looks like an object or array based on properties/items
        if hasattr(raml_type_obj, 'properties') and raml_type_obj.properties is not None:
             raml_base_type = 'object'
        elif hasattr(raml_type_obj, 'items') and raml_type_obj.items is not None:
             raml_base_type = 'array'
        else:
             raml_base_type = 'object' # Fallback assumption
        # print(f"Info: Complex base type detected for '{getattr(raml_type_obj, 'name', 'anonymous')}'. Inferred as '{raml_base_type}'.") # Optional debug


    # Basic Type Mapping
    type_mapping = {
        'string': 'string',
        'number': 'number',
        'integer': 'integer',
        'boolean': 'boolean',
        'array': 'array',
        'object': 'object',
        'file': 'string', # JSON Schema doesn't have a direct file type
        'datetime': 'string', # Usually with format
        'datetime-only': 'string', # Usually with format 'date-time' (check ramlfications specifics)
        'date-only': 'string', # Usually with format
        'time-only': 'string', # Usually with format
        'nil': 'null'       # RAML nil type
    }

    if raml_base_type in type_mapping:
        json_schema['type'] = type_mapping[raml_base_type]
        # Add format for specific string types
        # Note: RAML 'datetime-only' is just 'date-time' format in JSON Schema
        if raml_base_type in ['datetime', 'datetime-only']: json_schema['format'] = 'date-time'
        if raml_base_type == 'date-only': json_schema['format'] = 'date'
        if raml_base_type == 'time-only': json_schema['format'] = 'time'
        if raml_base_type == 'file': json_schema.setdefault('description', 'Represents file content (e.g., base64 or URI).')
    elif isinstance(raml_base_type, str):
        # If it's a string type not in our basic map, it's likely a reference
        # to another custom type defined in the RAML file.
        # In JSON Schema, this is typically represented using $ref.
        # We assume the calling function places this within a $defs structure.
        json_schema['$ref'] = f'#/$defs/{raml_base_type}'
        # print(f"Info: Creating $ref for referenced type '{raml_base_type}'.") # Optional debug print
        # Return immediately as $ref replaces other keywords at the same level
        return json_schema
    else:
        # Fallback if type is still not determined
        print(f"Warning: Could not determine JSON schema type for RAML type '{raml_base_type}'. Defaulting to object.")
        json_schema['type'] = 'object'


    # --- Map Common RAML Facets/Attributes to JSON Schema Keywords ---
    # Use getattr for safe access as not all attributes exist on all types/properties
    desc_obj = getattr(raml_type_obj, 'description', None)
    if desc_obj:
        # ramlfications description objects have a 'raw' attribute for the markdown content
        json_schema['description'] = getattr(desc_obj, 'raw', str(desc_obj)) # Fallback to string conversion
    if getattr(raml_type_obj, 'default', None) is not None: # Default can be False/0/etc.
        json_schema['default'] = raml_type_obj.default
    if getattr(raml_type_obj, 'enum', None):
        json_schema['enum'] = raml_type_obj.enum

    # String Facets (check ramlfications attribute names)
    if getattr(raml_type_obj, 'pattern', None):
        json_schema['pattern'] = raml_type_obj.pattern
    # ramlfications might use min_length/max_length
    if getattr(raml_type_obj, 'min_length', None) is not None:
        json_schema['minLength'] = raml_type_obj.min_length
    if getattr(raml_type_obj, 'max_length', None) is not None:
        json_schema['maxLength'] = raml_type_obj.max_length

    # Number Facets
    if getattr(raml_type_obj, 'minimum', None) is not None:
        json_schema['minimum'] = raml_type_obj.minimum
    if getattr(raml_type_obj, 'maximum', None) is not None:
        json_schema['maximum'] = raml_type_obj.maximum
    # ramlfications might have 'format' for numbers (int32, etc.) - can add to description
    num_format = getattr(raml_type_obj, 'format', None)
    if num_format and json_schema.get('type') in ['number', 'integer']:
        json_schema.setdefault('description', '')
        # Append format info, handling potential existing description
        existing_desc = json_schema['description']
        format_desc = f" (RAML format: {num_format})"
        if existing_desc:
            # Check if description already has the format string to avoid duplicates
            if format_desc not in existing_desc:
                 json_schema['description'] = f"{existing_desc.strip()}{format_desc.strip()}"
        else:
            json_schema['description'] = format_desc.strip()


    # --- Object Specific ---
    # Check the inferred or explicit type
    if json_schema.get('type') == 'object':
        required_props = []
        # Check for properties attribute
        object_properties = getattr(raml_type_obj, 'properties', None)
        if object_properties: # Should be a list of Property objects in ramlfications
            json_schema['properties'] = {}
            for prop_obj in object_properties:
                prop_name = getattr(prop_obj, 'name', None)
                if not prop_name:
                    print("Warning: Skipping property with no name.")
                    continue

                # Recursively convert the property's type definition
                # A Property object in ramlfications often holds the type info directly
                # or references another type. Pass the prop_obj itself.
                json_schema['properties'][prop_name] = raml_type_to_json_schema(prop_obj)

                # Check requirement (ramlfications usually has a boolean 'required' attribute)
                if getattr(prop_obj, 'required', False): # Default to False if attribute missing
                    required_props.append(prop_name)

        # Add 'required' array if any properties are required
        if required_props:
            # Sort for consistency and remove duplicates just in case
            json_schema['required'] = sorted(list(set(required_props)))

        # Handle additionalProperties (check ramlfications attributes)
        # Common patterns: additional_properties (bool) or allow_additional_properties (bool)
        add_props = getattr(raml_type_obj, 'additional_properties', None)
        if add_props is None:
             # Check alternative name, defaulting to None if neither exists
             add_props = getattr(raml_type_obj, 'allow_additional_properties', None)

        if isinstance(add_props, bool):
             json_schema['additionalProperties'] = add_props
        # If add_props is None (neither attribute exists), RAML default is usually true
        # JSON Schema default for additionalProperties is also true (implicitly)
        # So, we only need to explicitly set it if it's defined as false in RAML.
        elif add_props is None:
             pass # Let JSON schema default handle it (true)


        # Could also check minProperties, maxProperties if ramlfications supports them


    # --- Array Specific ---
     # Check the inferred or explicit type
    if json_schema.get('type') == 'array':
        # RAML 'items' defines the type of array elements
        array_items = getattr(raml_type_obj, 'items', None)
        if array_items:
           # 'items' in ramlfications should be another type object or a simple type string
           if isinstance(array_items, str):
               # If items is just a string (like 'string'), create a basic type schema for it
               items_schema = {}
               item_type_name = array_items
               if item_type_name in type_mapping:
                    items_schema['type'] = type_mapping[item_type_name]
                    # Add format for specific string types in items
                    if item_type_name in ['datetime', 'datetime-only']: items_schema['format'] = 'date-time'
                    if item_type_name == 'date-only': items_schema['format'] = 'date'
                    if item_type_name == 'time-only': items_schema['format'] = 'time'
               else:
                   # Assume it's a reference to a defined type
                   items_schema['$ref'] = f'#/$defs/{item_type_name}'
               json_schema['items'] = items_schema
           else:
                # If items is a type object, recurse
                json_schema['items'] = raml_type_to_json_schema(array_items)
        else:
            # JSON schema default: allows any type if 'items' is missing/empty schema
            json_schema['items'] = {}
            item_name = getattr(raml_type_obj, 'name', 'anonymous array')
            print(f"Warning: Array type '{item_name}' definition found without 'items'. Assuming items can be of any type.")

        # RAML array constraints (check ramlfications attribute names)
        # Common names: min_items, max_items, unique_items
        if getattr(raml_type_obj, 'min_items', None) is not None:
            json_schema['minItems'] = raml_type_obj.min_items
        if getattr(raml_type_obj, 'max_items', None) is not None:
            json_schema['maxItems'] = raml_type_obj.max_items
        if getattr(raml_type_obj, 'unique_items', None) is not None:
             # RAML 'uniqueItems' maps directly to JSON schema 'uniqueItems'
            json_schema['uniqueItems'] = raml_type_obj.unique_items


    # Clean up potentially empty description added for format/etc.
    if 'description' in json_schema and not json_schema.get('description','').strip():
        del json_schema['description']
    # Remove 'type' if a '$ref' was added, as they are mutually exclusive
    if '$ref' in json_schema and 'type' in json_schema:
        del json_schema['type']


    return json_schema


def generate_json_schema_from_raml_file(raml_file_path):
    """
    Loads a root RAML file using ramlfications, resolves references,
    extracts type definitions from the 'types' section, and converts
    them into a JSON schema document with definitions under '$defs'.

    Args:
        raml_file_path (str): The path to the root RAML file (e.g., api.raml).

    Returns:
        dict: A dictionary representing the JSON schema for the types,
              structured with a '$defs' section, or None if an error occurs.
    """
    original_cwd = os.getcwd() # Store original CWD
    abs_raml_path = os.path.abspath(raml_file_path)
    root_dir = os.path.dirname(abs_raml_path)
    raml_filename = os.path.basename(abs_raml_path) # Get just the filename

    try:
        # --- SOLUTION: Change CWD to the RAML file's directory ---
        print(f"Changing working directory to: {root_dir}")
        os.chdir(root_dir)
        # --- End Solution ---

        print(f"Parsing RAML file using ramlfications: {raml_filename} (relative to CWD)")

        # Config WITHOUT root_path, as CWD should handle includes now
        config = {
            "validate": True,
            "parse_includes": True
            }

        # Parse using just the filename (relative to the new CWD)
        parsed_raml_api = ramlfications.parse(raml_filename, config)
        print("RAML parsing successful.")

        # --- Rest of the function remains largely the same ---

        # Prepare the base JSON schema structure
        json_schema_output = {
            "$schema": "http://json-schema.org/draft-07/schema#", # Or another draft
            "title": getattr(parsed_raml_api, 'title', 'API Types Schema'),
            "$defs": {} # Use $defs for reusable definitions (Draft 7+)
        }
        # Add top-level description if present in RAML
        top_desc = getattr(parsed_raml_api, 'description', None)
        if top_desc:
             json_schema_output['description'] = getattr(top_desc, 'raw', str(top_desc))

        # Check if the 'types' attribute exists and has content
        api_types = getattr(parsed_raml_api, 'types', None)
        if not api_types:
             print("Warning: No 'types' section found or it is empty in the parsed RAML.")
             return json_schema_output

        print(f"Found {len(api_types)} types in the RAML definition. Converting to JSON Schema...")

        # Convert each defined RAML type found in the 'types' section
        type_count = 0
        for type_obj in api_types:
            type_name = getattr(type_obj, 'name', None)
            if not type_name:
                 print("Warning: Skipping type definition with no name.")
                 continue

            print(f"  Converting type: '{type_name}'...")
            try:
                converted_schema = raml_type_to_json_schema(type_obj)
                json_schema_output["$defs"][type_name] = converted_schema
                type_count += 1
            except Exception as conversion_error:
                print(f"ERROR: Failed to convert type '{type_name}'. Error: {conversion_error}")
                traceback.print_exc()
                json_schema_output["$defs"][type_name] = {
                    "description": f"Error converting RAML type '{type_name}': {conversion_error}"
                }


        print(f"Successfully attempted conversion for {type_count} types.")
        return json_schema_output

    # --- Exception handling remains the same ---
    except FileNotFoundError as e:
        print(f"Error: File not found during parsing: {e}")
        return None
    except ImportError as e:
        if 'ramlfications' in str(e):
             print("Error: Required library 'ramlfications' not found or import failed.")
             print("Please install it using: pip install ramlfications PyYAML")
        else:
             print(f"An import error occurred: {e}")
        return None
    except raml_errors.BaseRAMLError as e:
        print(f"A RAML parsing/validation error occurred: {e}")
        print(f"  File: {getattr(e, 'fname', 'N/A')}, Line: {getattr(e, 'line', 'N/A')}")
        return None
    except yaml.YAMLError as e:
        print(f"A YAML syntax error occurred: {e}")
        if hasattr(e, 'problem_mark'):
            mark = e.problem_mark
            print(f"  Error is near line {mark.line + 1}, column {mark.column + 1}")
            if hasattr(e, 'problem'): print(f"  Problem: {e.problem}")
            if hasattr(e, 'context_mark') and e.context_mark:
                 cmark = e.context_mark
                 print(f"  Context is near line {cmark.line + 1}, column {cmark.column + 1}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()
        return None
    # --- CRUCIAL: Change back to original CWD ---
    finally:
        # Ensure we change back even if errors occur
        if os.getcwd() != original_cwd:
             print(f"Changing working directory back to: {original_cwd}")
             os.chdir(original_cwd)
        # --- End Finally ---

# --- Example Usage ---
if __name__ == "__main__":
    # Set the path to the main RAML specification file.
    # Assumes 'api.raml' is in the same directory as 'parser.py'
    raml_path = 'api.raml' # <--- Point to your main RAML file

    print("-" * 30)
    print("Starting RAML to JSON Schema Generation (using ramlfications)")
    print(f"Input RAML file: {os.path.abspath(raml_path)}")
    print("-" * 30)

    final_schema = generate_json_schema_from_raml_file(raml_path)

    print("-" * 30)
    if final_schema:
        # Limit printing very large schemas to console if necessary
        schema_str = json.dumps(final_schema, indent=2, ensure_ascii=False)
        # if len(schema_str) > 5000: # Example limit
        #    print("Generated JSON Schema is large. See output file.")
        # else:
        print("Generated JSON Schema Document:")
        print(schema_str)


        # --- Optional: Save to a file ---
        output_filename = 'generated_schema_ramlfications.json' # Use a different name
        try:
            # Ensure correct encoding for potentially diverse characters in RAML descriptions
            with open(output_filename, 'w', encoding='utf-8') as f:
                # ensure_ascii=False allows non-ASCII characters (like accents, symbols)
                # to be written directly instead of escaped sequences (\uXXXX)
                json.dump(final_schema, f, indent=2, ensure_ascii=False)
            print("-" * 30)
            print(f"Schema successfully saved to: {output_filename}")
        except IOError as e:
            print(f"\nError saving schema to file '{output_filename}': {e}")
        # --- End Optional Save ---

    else:
        print("JSON Schema generation failed.")
    print("-" * 30)