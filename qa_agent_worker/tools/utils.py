from google.adk.tools import ToolContext

def get_var(key, context: ToolContext) -> str:
    return context.state[key] if key in context.state else f"{key} does not exist."


def set_var(key, value, context: ToolContext) -> str:
    context.state[key] = value
    return {"name": key, "value": value, "status": "success"}

def generate_id() -> str:
    """Use this tool to generate UUID4

    Returns
        str: the unique ssesion id to use
    """
    return str(uuid.uuid4())
