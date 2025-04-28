import json
import os
import yaml
import ramlfications
from ramlfications import errors as raml_errors
import traceback
from ramlfications.loader import RAMLLoader
import configparser # Import for specific error handling

# Note: Ensure 'ramlfications' and 'PyYAML' are installed

# --- Monkey Patching Setup ---
_original_yaml_include = None
_project_root_dir = None
POSSIBLE_ROOT_DIRS = ["examples", "traits", "dataTypes", "exchange_modules"]

# Add specific non-RAML filenames or extensions to check
NON_RAML_INCLUDE_FILENAMES = ["CHANGELOG.raml"] # Add others if needed (case-sensitive on some OS)
NON_RAML_INCLUDE_EXTENSIONS = [".md", ".txt", ".json", ".xml", ".sample"] # Examples

def _complex_patched_yaml_include(self, loader, node):
    """
    Complex wrapper for !include:
    1. Strips '/', normalizes paths.
    2. Constructs absolute path.
    3. Checks if the included file is likely non-RAML (CHANGELOG, .md, .json example).
    4. If non-RAML, reads and returns raw content as string.
    5. If RAML, calls original handler with absolute path.
    """
    global _original_yaml_include, _project_root_dir
    if not _project_root_dir:
        print("Warning: Project root not set for patch.")
        if _original_yaml_include: return _original_yaml_include(self, loader, node)
        else: raise RuntimeError("Original !include handler not found.")

    original_value = node.value; corrected_value = original_value; path_changed = False
    is_likely_incorrectly_rooted = False; final_abs_path = None
    including_file_path = getattr(getattr(loader, 'stream', None), 'name', None)
    if not including_file_path: including_file_path = "unknown"

    # 1. Strip leading '/'
    if original_value.startswith('/'): corrected_value = original_value.lstrip('/'); path_changed = True

    # 2. Normalize separators
    try: normalized_value = os.path.normpath(corrected_value)
    except Exception: normalized_value = corrected_value
    if normalized_value != corrected_value: path_changed = True; corrected_value = normalized_value

    # 3. Detect if ../ needed
    try:
        path_parts = corrected_value.split(os.sep); first_part = path_parts[0] if path_parts else ""
        if os.path.isabs(including_file_path): abs_including_file_path = including_file_path
        else: abs_including_file_path = os.path.abspath(including_file_path)
        is_nested_include = os.path.dirname(abs_including_file_path) != _project_root_dir
        if is_nested_include and first_part in POSSIBLE_ROOT_DIRS: is_likely_incorrectly_rooted = True
    except Exception: pass

    # 4. Construct ABSOLUTE PATH
    try:
        if is_likely_incorrectly_rooted: final_abs_path = os.path.abspath(corrected_value)
        else:
            if os.path.isabs(including_file_path): including_dir = os.path.dirname(including_file_path)
            else: including_dir = os.getcwd()
            final_abs_path = os.path.abspath(os.path.join(including_dir, corrected_value))
        if final_abs_path: final_abs_path = os.path.normpath(final_abs_path)
    except Exception as e:
        print(f"Warning: Error calculating absolute path for '{original_value}': {e}")
        final_abs_path = normalized_value # Fallback path

    # --- 5. Check if file should be read raw ---
    is_non_raml = False
    if final_abs_path:
        include_filename = os.path.basename(final_abs_path)
        include_extension = os.path.splitext(include_filename)[1].lower()
        if include_filename in NON_RAML_INCLUDE_FILENAMES: is_non_raml = True; print(f"Patch: Detected non-RAML file: '{include_filename}'")
        elif include_extension in NON_RAML_INCLUDE_EXTENSIONS: is_non_raml = True; print(f"Patch: Detected non-RAML extension '{include_extension}' for: '{include_filename}'")

    if is_non_raml and final_abs_path:
        try:
            print(f"===> Reading raw content from: '{final_abs_path}'")
            with open(final_abs_path, 'r', encoding='utf-8') as f_raw: raw_content = f_raw.read()
            return raw_content # Return the string content
        except FileNotFoundError: print(f"ERROR: Patched path '{final_abs_path}' not found for raw read."); raise
        except Exception as e_raw: print(f"ERROR: Failed reading raw content '{final_abs_path}': {e_raw}"); raise RuntimeError(f"Failed raw read: {e_raw}") from e_raw
    else:
        # --- If RAML or path failed, proceed with original handler ---
        if final_abs_path and node.value != final_abs_path:
             node.value = final_abs_path; path_changed = True
             # print(f"===> Final Patched Path for RAML include '{original_value}': '{node.value}' (from '{including_file_path}')") # Noise
        elif path_changed: node.value = corrected_value # Ensure normalized/stripped value is used
             # print(f"===> Final Patched Path for RAML include '{original_value}': '{node.value}' (from '{including_file_path}')") # Noise
        # else: print(f"===> No change to Path for RAML include '{original_value}' (from '{including_file_path}')") # Noise

        # Call original handler
        if _original_yaml_include:
            # print(f"===> Calling original handler with node value: '{node.value}'") # Noise
            return _original_yaml_include(self, loader, node)
        else: raise RuntimeError("Original !include handler not found for patch call.")
# --- End Monkey Patching Setup ---

def raml_type_to_json_schema(raml_type_obj):
    # ... (Keep the full function from previous versions - unchanged) ...
    if raml_type_obj is None: return {}
    json_schema = {}
    raml_base_type = getattr(raml_type_obj, 'type', 'object')
    if not isinstance(raml_base_type, str):
        if hasattr(raml_type_obj, 'properties') and raml_type_obj.properties is not None: raml_base_type = 'object'
        elif hasattr(raml_type_obj, 'items') and raml_type_obj.items is not None: raml_base_type = 'array'
        else: raml_base_type = 'object'
    type_mapping = { 'string': 'string', 'number': 'number', 'integer': 'integer', 'boolean': 'boolean', 'array': 'array', 'object': 'object', 'file': 'string', 'datetime': 'string', 'datetime-only': 'string', 'date-only': 'string', 'time-only': 'string', 'nil': 'null' }
    if raml_base_type in type_mapping:
        json_schema['type'] = type_mapping[raml_base_type]
        if raml_base_type in ['datetime', 'datetime-only']: json_schema['format'] = 'date-time'
        if raml_base_type == 'date-only': json_schema['format'] = 'date'
        if raml_base_type == 'time-only': json_schema['format'] = 'time'
        if raml_base_type == 'file': json_schema.setdefault('description', 'Represents file content (e.g., base64 or URI).')
    elif isinstance(raml_base_type, str):
        json_schema['$ref'] = f'#/$defs/{raml_base_type}'; return json_schema
    else: json_schema['type'] = 'object'
    desc_obj = getattr(raml_type_obj, 'description', None);
    if desc_obj: json_schema['description'] = getattr(desc_obj, 'raw', str(desc_obj))
    if getattr(raml_type_obj, 'default', None) is not None: json_schema['default'] = raml_type_obj.default
    if getattr(raml_type_obj, 'enum', None): json_schema['enum'] = raml_type_obj.enum
    if getattr(raml_type_obj, 'pattern', None): json_schema['pattern'] = raml_type_obj.pattern
    if getattr(raml_type_obj, 'min_length', None) is not None: json_schema['minLength'] = raml_type_obj.min_length
    if getattr(raml_type_obj, 'max_length', None) is not None: json_schema['maxLength'] = raml_type_obj.max_length
    if getattr(raml_type_obj, 'minimum', None) is not None: json_schema['minimum'] = raml_type_obj.minimum
    if getattr(raml_type_obj, 'maximum', None) is not None: json_schema['maximum'] = raml_type_obj.maximum
    num_format = getattr(raml_type_obj, 'format', None)
    if num_format and json_schema.get('type') in ['number', 'integer']:
        json_schema.setdefault('description', ''); existing_desc = json_schema.get('description', ''); format_desc = f" (RAML format: {num_format})"
        if existing_desc and format_desc not in existing_desc: json_schema['description'] = f"{existing_desc.strip()}{format_desc.strip()}"
        elif not existing_desc: json_schema['description'] = format_desc.strip()
    if json_schema.get('type') == 'object':
        required_props = []; object_properties = getattr(raml_type_obj, 'properties', None)
        if object_properties:
            json_schema['properties'] = {}
            for prop_obj in object_properties:
                prop_name = getattr(prop_obj, 'name', None);
                if not prop_name: continue
                json_schema['properties'][prop_name] = raml_type_to_json_schema(prop_obj)
                if getattr(prop_obj, 'required', False): required_props.append(prop_name)
        if required_props: json_schema['required'] = sorted(list(set(required_props)))
        add_props = getattr(raml_type_obj, 'additional_properties', getattr(raml_type_obj, 'allow_additional_properties', None));
        if isinstance(add_props, bool): json_schema['additionalProperties'] = add_props
    if json_schema.get('type') == 'array':
        array_items = getattr(raml_type_obj, 'items', None)
        if array_items:
           if isinstance(array_items, str):
               items_schema = {}; item_type_name = array_items
               if item_type_name in type_mapping:
                    items_schema['type'] = type_mapping[item_type_name]
                    if item_type_name in ['datetime', 'datetime-only']: items_schema['format'] = 'date-time'
                    if item_type_name == 'date-only': items_schema['format'] = 'date'
                    if item_type_name == 'time-only': items_schema['format'] = 'time'
               else: items_schema['$ref'] = f'#/$defs/{item_type_name}'
               json_schema['items'] = items_schema
           else: json_schema['items'] = raml_type_to_json_schema(array_items)
        else: json_schema['items'] = {}
        if getattr(raml_type_obj, 'min_items', None) is not None: json_schema['minItems'] = raml_type_obj.min_items
        if getattr(raml_type_obj, 'max_items', None) is not None: json_schema['maxItems'] = raml_type_obj.max_items
        if getattr(raml_type_obj, 'unique_items', None) is not None: json_schema['uniqueItems'] = raml_type_obj.unique_items
    if 'description' in json_schema and not json_schema.get('description','').strip(): del json_schema['description']
    if '$ref' in json_schema and 'type' in json_schema: del json_schema['type']
    return json_schema


def generate_json_schema_from_raml_file(raml_file_path):
    global _original_yaml_include, _project_root_dir

    original_cwd = os.getcwd()
    abs_raml_path = os.path.abspath(raml_file_path)
    root_dir = os.path.dirname(abs_raml_path)
    raml_filename = os.path.basename(abs_raml_path)
    patch_applied = False
    _project_root_dir = root_dir
    temp_config_path = None

    try:
        # Create Temp Config File
        temp_config_filename = "_temp_raml_config.ini"
        temp_config_content = "[ramlfications]\nvalidate = false\nparse_includes = true\n"
        temp_config_path = os.path.join(root_dir, temp_config_filename)
        try:
            print(f"Creating temporary INI config file: {temp_config_path}")
            with open(temp_config_path, 'w') as f: f.write(temp_config_content)
        except IOError as e: print(f"ERROR: Could not create temp config file '{temp_config_path}': {e}"); return None

        # Apply patch
        if hasattr(RAMLLoader, '_yaml_include'):
            _original_yaml_include = RAMLLoader._yaml_include
            RAMLLoader._yaml_include = _complex_patched_yaml_include
            patch_applied = True
            print("Applied complex !include path correction patch (raw read).")
        else: print("Warning: Could not find _yaml_include method to patch.")

        # Change CWD
        print(f"Changing working directory to: {root_dir}")
        os.chdir(root_dir)

        print(f"Parsing RAML file using ramlfications: {raml_filename} (relative to CWD)")
        # Pass temp INI config file path
        parsed_raml_api = ramlfications.parse(raml_filename, config_file=temp_config_path)
        print("RAML parsing successful (validation disabled via config file).")

        # Schema Generation
        json_schema_output = { "$schema": "http://json-schema.org/draft-07/schema#", "title": getattr(parsed_raml_api, 'title', 'API Types Schema'), "$defs": {} }
        top_desc = getattr(parsed_raml_api, 'description', None)
        if top_desc: json_schema_output['description'] = getattr(top_desc, 'raw', str(top_desc))
        api_types = getattr(parsed_raml_api, 'types', None)
        if not api_types: print("Warning: No 'types' section found."); return json_schema_output
        print(f"Found {len(api_types)} types. Converting to JSON Schema...")
        type_count = 0
        for type_obj in api_types:
            type_name = getattr(type_obj, 'name', None)
            if not type_name: continue
            try:
                converted_schema = raml_type_to_json_schema(type_obj)
                json_schema_output["$defs"][type_name] = converted_schema; type_count += 1
            except Exception as conversion_error:
                print(f"ERROR converting type '{type_name}': {conversion_error}"); traceback.print_exc()
                json_schema_output["$defs"][type_name] = {"description": f"Error converting: {conversion_error}"}
        print(f"Successfully attempted conversion for {type_count} types.")
        return json_schema_output

    # Exception Handling
    except FileNotFoundError as e: print(f"Error: File not found: {e}"); return None
    except ImportError as e: print(f"Import error: {e}"); return None
    except raml_errors.BaseRAMLError as e: print(f"RAML Error: {e}\n  File: {getattr(e, 'fname', 'N/A')}, Line: {getattr(e, 'line', 'N/A')}"); return None
    except yaml.YAMLError as e: print(f"YAML Error: {e}"); return None
    except configparser.MissingSectionHeaderError as e: print(f"Config File Error: {e}"); return None
    except TypeError as e:
         if 'unexpected keyword argument' in str(e) and 'parse()' in str(e): print(f"TypeError during parse call: {e}")
         elif '_path_isfile' in str(e) or 'path should be string' in str(e): print(f"TypeError during config processing: {e}")
         else: print(f"Unexpected TypeError: {e}"); traceback.print_exc()
         return None
    except Exception as e: print(f"Unexpected Error: {e}"); traceback.print_exc(); return None
    finally:
        # Delete Temp Config File
        if temp_config_path and os.path.exists(temp_config_path):
            try:
                print(f"Deleting temporary config file: {temp_config_path}")
                os.remove(temp_config_path)
            except OSError as e_remove: print(f"Warning: Could not delete temp config file '{temp_config_path}': {e_remove}")

        # Restore CWD and Unpatch
        if os.getcwd() != original_cwd:
             print(f"Changing working directory back to: {original_cwd}")
             os.chdir(original_cwd)
        if patch_applied and _original_yaml_include:
            RAMLLoader._yaml_include = _original_yaml_include
            print("Restored original !include handler.")
            _original_yaml_include = None; _project_root_dir = None
        # -------------------------------

# --- Example Usage ---
if __name__ == "__main__":
    raml_path = 'api.raml'
    print("-" * 30); print("Starting RAML to JSON Schema Generation (using ramlfications + raw read patch + INI config)")
    print(f"Input RAML file: {os.path.abspath(raml_path)}"); print("-" * 30)
    final_schema = generate_json_schema_from_raml_file(raml_path); print("-" * 30)
    if final_schema:
        schema_str = json.dumps(final_schema, indent=2, ensure_ascii=False)
        print("Generated JSON Schema Document:"); print(schema_str)
        output_filename = 'generated_schema_ramlfications_raw_read.json' # New name
        try:
            with open(output_filename, 'w', encoding='utf-8') as f: json.dump(final_schema, f, indent=2, ensure_ascii=False)
            print("-" * 30); print(f"Schema successfully saved to: {output_filename}")
        except IOError as e: print(f"\nError saving schema: {e}")
    else: print("JSON Schema generation failed.")
    print("-" * 30)