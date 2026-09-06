import ast
import logging

def safe_parse_strategy_parameters(code_string: str, class_name: str) -> dict:
    """
    Safely parses the `_parameters` class variable from a strategy's code string.

    Uses Python's Abstract Syntax Tree (AST) to find the class definition and
    the `_parameters` dictionary, then uses `ast.literal_eval` to safely
    evaluate the dictionary structure without executing any code.

    Args:
        code_string (str): The string containing the Python code for the strategy.
        class_name (str): The name of the class to look for.

    Returns:
        A dictionary of the parsed parameters, or an empty dictionary if not found or unsafe.
    """
    try:
        tree = ast.parse(code_string)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for class_body_node in node.body:
                    if (isinstance(class_body_node, ast.Assign) and
                            len(class_body_node.targets) == 1 and
                            isinstance(class_body_node.targets[0], ast.Name) and
                            class_body_node.targets[0].id == 'parameters'):
                        
                        # We found the `parameters` assignment.
                        # Now, safely evaluate its value.
                        params_dict = ast.literal_eval(class_body_node.value)
                        if isinstance(params_dict, dict):
                            logging.info(f"Successfully parsed parameters for class {class_name}.")
                            return params_dict
                        else:
                            logging.warning(f"parameters in {class_name} is not a dictionary.")
                            return {}

                    # NEW: Support for @property def parameters(self):
                    elif (isinstance(class_body_node, ast.FunctionDef) and 
                          class_body_node.name == 'parameters'):
                        
                        # Check for return statement in the function body
                        for stmt in class_body_node.body:
                            if isinstance(stmt, ast.Return):
                                try:
                                    # Attempt to evaluate the returned expression
                                    params_dict = ast.literal_eval(stmt.value)
                                    if isinstance(params_dict, dict):
                                        logging.info(f"Successfully parsed parameters property for class {class_name}.")
                                        return params_dict
                                except (ValueError, SyntaxError):
                                    # The return value might be too complex for literal_eval (not a static dict)
                                    logging.debug(f"Could not literal_eval return value of parameters property in {class_name}")
                                    pass
                        return {} # Found the function but couldn't parse a valid dict return

    except (ValueError, SyntaxError, MemoryError, TypeError) as e:
        logging.error(f"Failed to parse _parameters from strategy code: {e}", exc_info=True)
    return {}