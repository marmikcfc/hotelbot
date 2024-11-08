
import datetime
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


async def send_whatsapp_message(response: str, chat_id: str, responding_to_our_message: bool):
    if responding_to_our_message:
        logger.info("First message already sent, not sending again")
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
                logger.info(f"Sending POST request to WHAPI with data: {data}")
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

def calculate_hotel_days(arrival_date: str, departure_date: str, departure_time: str = "00:00") -> int:
    """
    Calculate the number of days between arrival and departure dates.
    If departure time is after 19:00 and not same day as arrival, adds an extra day.

    Args:
        arrival_date (str): Arrival date in YYYY-MM-DD format.
        departure_date (str): Departure date in YYYY-MM-DD format.
        departure_time (str): Departure time in HH:MM format. Defaults to "00:00".

    Returns:
        int: Number of days for the hotel booking.
    """
    arrival = datetime.datetime.strptime(arrival_date, "%Y-%m-%d")
    departure = datetime.datetime.strptime(departure_date, "%Y-%m-%d")
    departure_hour = int(departure_time.split(":")[0])
    
    delta = departure - arrival
    days = delta.days
    
    # Add extra day if departure is after 19:00 and not same day
    if departure_hour >= 19:
        days += 1
        
    return days if days > 0 else 1 #For same day departure we still need to book a room atleast 1


def remove_tuples_before_number(tuple_list: list, target_number: int) -> tuple[list, tuple]:
    """
    Remove all tuples before the first occurrence where the second element equals target_number.

    Args:
        tuple_list (list): List of tuples where each tuple contains a message and number
        target_number (int): Target number to find in second element of tuples

    Returns:
        tuple[list, int, tuple]: Tuple containing:
            - Modified list with elements removed before first match
            - Index of first match (-1 if no match found)
            - First matching tuple (None if no match found)
    """
    try:
        # Find index of first tuple where second element matches target
        first_match_index = next(
            (i for i, t in enumerate(tuple_list) if t[1] == target_number),
            -1  # Return -1 if no match found
        )
        
        # Return tuple of sliced list, index and matching element
        if first_match_index == -1:
            return tuple_list, first_match_index, None
        return tuple_list[first_match_index+1:], tuple_list[first_match_index]
    except Exception as e:
        logger.error(f"Error removing tuples before number {target_number}: {e}")
        raise
