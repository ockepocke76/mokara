import logging
import os
from google import genai
from config import CONFIG

# Initialize the global client
# Note: Google GenAI SDK automatically looks for GEMINI_API_KEY or GOOGLE_API_KEY environment variables
# but we provide it explicitly from our CONFIG if present.
_client = None

def _get_client(api_key=None):
    global _client
    if api_key:
        return genai.Client(api_key=api_key)
        
    if _client is None:
        # Priority: CONFIG -> Environment Variables
        env_key = CONFIG.get('google_api_key') or CONFIG.get('api_key') or os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
        
        if env_key:
            _client = genai.Client(api_key=env_key)
        else:
            # Fallback to SDK automatic environment detection (looks for GOOGLE_API_KEY)
            logging.info("No explicit Gemini API key found in CONFIG or environment. Falling back to SDK default detection.")
            _client = genai.Client()
    return _client

def call_gemini_safe(model_name: str, prompt: str, generation_config=None, api_key=None) -> tuple[str | None, str | None, dict | None]:
    """
    Safely calls the Gemini API with centralized error handling.

    Args:
        model_name (str): The model name (e.g., 'gemini-1.5-flash').
        prompt (str): The text prompt.
        generation_config (dict, optional): Generation parameters.

    Returns:
        tuple: (response_text, error_message, usage_metadata)
            - response_text: The generated text if successful, else None.
            - error_message: A user-friendly error message if failed, else None.
            - usage_metadata: A dict with token counts if available, else None.
    """
    try:
        client = _get_client(api_key)
        
        # New SDK uses 'contents' instead of 'prompt' and 'model' instead of positional argument
        # config can be a dict
        response = client.models.generate_content(
            model=model_name, 
            contents=prompt, 
            config=generation_config
        )
        
        # Extract usage metadata if available
        usage = {}
        try:
            if hasattr(response, 'usage_metadata'):
                # New SDK attributes might differ Slightly, checking common pattern
                usage = {
                    'prompt_tokens': getattr(response.usage_metadata, 'prompt_token_count', 0),
                    'completion_tokens': getattr(response.usage_metadata, 'candidates_token_count', 0),
                    'total_tokens': getattr(response.usage_metadata, 'total_token_count', 0)
                }
        except Exception:
            logging.warning("Could not extract usage metadata from Gemini response")

        return response.text, None, usage

    except Exception as e:
        err_msg = str(e)
        logging.error(f"Gemini API call failed: {e}", exc_info=True)
        
        # quota/429 check
        if "429" in err_msg or "quota" in err_msg.lower() or "resourceexhausted" in err_msg.lower():
            return None, "We are experiencing high load at the moment and cannot handle your request. Please try again later.", None
        
        # General error
        return None, f"An unexpected error occurred while processing your request: {err_msg}", None

