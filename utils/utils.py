
import json
import os
import logging
from litellm import OpenAI, acompletion
from Message.message import Message
from typing import Union, List, Tuple, Dict
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

# Initialize Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fast_finger_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def send_whatsapp_message(response: str, chat_id: str, sent_first_message: bool):
    if sent_first_message:
        return
    logger.info(f"Sending WhatsApp message to chat_id={chat_id}")
    api_key = os.getenv("WHAPI_API_KEY")
    if not api_key:
        logger.critical("WHAPI_API_KEY environment variable not set")
        raise ValueError("WHAPI_API_KEY environment variable not set")

    async with httpx.AsyncClient() as client:
        headers = {
            'accept': 'application/json',
            'authorization': f'Bearer {api_key}',
            'content-type': 'application/json'
        }
        data = {
            'to': chat_id,
            'body': response
        }
        try:
            if response:
                logger.debug(f"Sending POST request to WHAPI with data: {data}")
                resp = await client.post(
                    'https://gate.whapi.cloud/messages/text',
                    headers=headers,
                    json=data
                )
                resp.raise_for_status()
                logger.info(f"Message sent successfully to chat_id={chat_id}")
        except httpx.HTTPError as e:
            logger.error(f"Failed to send message to chat_id={chat_id}: {e}")
            raise 