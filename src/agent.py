"""PocketSense agent initialization using Strands Agents SDK and BedrockModel."""

import os
from typing import Optional

from dotenv import load_dotenv
from strands import Agent
from strands.models.bedrock import BedrockModel

from src.tools.anomaly_detector import detect_anomalies
from src.tools.categorizer import categorize_merchant
from src.tools.digest import build_digest, send_digest
from src.tools.parser import parse_email
from src.tools.transfer_handler import handle_transfer


def create_agent(model_id: Optional[str] = None, region_name: Optional[str] = None) -> Agent:
    """
    Create and configure the PocketSense Strands Agent.

    Reads AWS_REGION and BEDROCK_MODEL_ID from environment variables.
    AWS credentials are read automatically from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.
    Registers all 5 tools:
      - parse_email
      - categorize_merchant
      - handle_transfer
      - detect_anomalies
      - build_digest / send_digest

    Args:
        model_id: Optional model override. Defaults to BEDROCK_MODEL_ID env var.
        region_name: Optional region override. Defaults to AWS_REGION env var.

    Returns:
        Agent: Configured Strands Agent instance.
    """
    load_dotenv()

    resolved_model_id = model_id or os.getenv("BEDROCK_MODEL_ID")
    if not resolved_model_id:
        raise ValueError(
            "BEDROCK_MODEL_ID is not set in environment or .env file. "
            "Please configure BEDROCK_MODEL_ID with your Amazon Bedrock model ID."
        )

    resolved_region = region_name or os.getenv("AWS_REGION", "us-east-1")

    bedrock_model = BedrockModel(
        model_id=resolved_model_id,
        region_name=resolved_region,
    )

    system_prompt = (
        "You are PocketSense, an autonomous financial intelligence agent designed for the "
        "'Agents for Humans' hackathon. Your role is to read bank notification emails, "
        "parse transaction parameters, categorize card purchases and fund transfers, "
        "remember masked recipients, detect spending anomalies, and construct weekly digests."
    )

    agent = Agent(
        model=bedrock_model,
        tools=[
            parse_email,
            categorize_merchant,
            handle_transfer,
            detect_anomalies,
            build_digest,
            send_digest,
        ],
        system_prompt=system_prompt,
        name="PocketSense",
        description="Autonomous background financial agent for everyday spending intelligence",
    )

    return agent
