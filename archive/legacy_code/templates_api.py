from dotenv import load_dotenv

load_dotenv()

import argparse

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from mailwright.templates.generator import create_template
from mailwright.templates.schema import TemplateRequest


# Define an envelope model that wraps the TemplateRequest along with clientId
class TemplateGenerationEnvelope(BaseModel):
    clientId: str
    request: TemplateRequest


# Initialize the FastAPI app
app = FastAPI()


@app.post("/mailwright/generate")
async def generate_template(envelope: TemplateGenerationEnvelope):
    # Extract the clientId (can be used for logging or auditing)
    client_id = envelope.clientId  # noqa: F841

    # Extract the TemplateRequest payload
    request_data = envelope.request

    # Generate the template using the existing create_template function
    template = create_template(request_data)

    # Return the entire template as JSON.
    # Depending on your Pydantic version, you might use template.dict() or template.model_dump()
    return template.dict()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run FastAPI server")
    parser.add_argument(
        "--dev", action="store_true", help="Run in development mode with auto-reload"
    )
    args = parser.parse_args()

    uvicorn.run(
        "mailwright.templates_api:app",
        host="0.0.0.0",
        port=8000,
        reload=args.dev,
    )
