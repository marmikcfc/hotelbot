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

from utils.utils import send_whatsapp_message
from prompts import SYSTEM_PROMPT_BOOKING_ROOMS, SYSTEM_PROMPT_NEEDS_ROOMS, SYSTEM_PROMPT_NUMBER_OF_ROOMS
from utils import *

# Load environment variables
load_dotenv()

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

class RoomResponse(BaseModel):
    needs_rooms: bool
    date: str #something

class BookingResponse(BaseModel):
    booking_room: bool
    number_of_rooms: int

class NumberOfRooms(BaseModel):
    number_of_rooms: int
    date: str

class FastFingerBot:
    def __init__(self):
        logger.info("Initializing FastFingerBot")
        try:
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            logger.debug("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise

        self.history = []
        self.conversation = ""
        self.system_prompt_needs_rooms = SYSTEM_PROMPT_NEEDS_ROOMS
        self.system_prompt_number_of_rooms = SYSTEM_PROMPT_NUMBER_OF_ROOMS
        self.system_prompt_booking_rooms = SYSTEM_PROMPT_BOOKING_ROOMS 
        self.sent_first_message = False
        self.confirmation_notification_chat_id = os.getenv("CONFIRMATION_NOTIFICATION_CHAT_ID")
        logger.info("FastFingerBot initialization complete")
        

    async def whatsapp_confirmation(self, message: str):
        await send_whatsapp_message(message, self.confirmation_notification_chat_id, False)
        logger.info("Whatsapp confirmation sent")
        return
    
    async def handle_whatsapp_group(self, chat_id: str, message: str, user_id: str):
        if message == "RP Can":
            logger.info("RP Can message received, not sending response")
            return
        
        logger.info(f"Handling WhatsApp message from user_id={user_id} in chat_id={chat_id}")
        self.chat_id = chat_id
        self.conversation += f"{user_id}: {message}\n"
        logger.debug(f"Updated conversation: {self.conversation}")
        
        try:
            room_need = await self.__determine_room_need(message)
            logger.info(f"Room need determination: {room_need.needs_rooms}")
        except Exception as e:
            logger.error(f"Error determining room need: {e}")
            #self.sent_first_message = True
            return
        
        try:
            available_rooms = self.__get_available_rooms()
            logger.debug(f"Available rooms: {available_rooms}")
        except Exception as e:
            logger.error(f"Error fetching available rooms: {e}")
            return

        if not room_need.needs_rooms:
            logger.info("User does not need rooms, Checking if they are booking a room")
            booking_response = await self.__determine_room_booking(message)
            logger.info(f"Booking response: {booking_response}")        
            
            if booking_response.booking_room:
                logger.info(f"User is booking {booking_response.number_of_rooms} rooms")
                is_possible = self.__calculate_if_possible(booking_response.number_of_rooms, available_rooms)
                room_need_date = datetime.datetime.strptime(self.current_room_need_date, "%Y-%m-%d").strftime("%Y-%m-%d")
                logger.info(f"Parsed room need date: {room_need_date}")
                logger.info(f"Today's date: {room_need_date}")
                # Get availability for today from the available_rooms dictionary
                total_available = available_rooms[room_need_date]["availability"] if room_need_date in available_rooms else 0

                logger.info(f"Is possible: {is_possible} Total available: {total_available}")

                if is_possible == -1:
                    logger.info(f"Enough rooms not available")
                    await send_whatsapp_message(f"No, we cannot accommodate {booking_response.number_of_rooms} rooms.", chat_id, self.sent_first_message)
                else:
                    logger.info(f"Enough rooms available")
                    self.__update_available_rooms(booking_response.number_of_rooms)
                    await self.whatsapp_confirmation(f"SQ booking {booking_response.number_of_rooms} rooms")
            else:
                logger.info("User is not booking rooms")
            return


        if room_need.needs_rooms:
            try:
                number_of_rooms = await self.__get_number_of_rooms(message)
                room_need_date = datetime.datetime.strptime(number_of_rooms.date, "%Y-%m-%d").strftime("%Y-%m-%d")
                logger.info(f"Number of rooms requested: {number_of_rooms.number_of_rooms}")
            except Exception as e:
                logger.error(f"Error getting number of rooms: {e}")
                #self.sent_first_message = True
                return

            try:
                
                available_rooms = self.__calculate_if_possible(number_of_rooms.number_of_rooms, available_rooms)
                logger.debug(f"Calculated available rooms: {available_rooms}")
                if available_rooms != -1:
                    response = "RP Can"
                    self.current_room_need_date = room_need_date
                    await send_whatsapp_message(response, chat_id, self.sent_first_message)
                else:
                    response = "No, we cannot accommodate you."
                logger.info(f"Response to user: {response}")
                
                #self.sent_first_message = True
            except Exception as e:
                logger.error(f"Error calculating room availability: {e}")
                #self.sent_first_message = True
        else:
            response = "No rooms needed."
            logger.info(f"Response to user: {response}")
            #self.sent_first_message = True

    async def __determine_room_need(self, user_message: str) -> RoomResponse:
        # if "SQ" not in user_message:
        #     logger.info("SQ not found in message, not determining room need")
        #     return RoomResponse(needs_rooms=False)
        
        logger.debug("Determining if user needs rooms")
        messages = [
            {"role": "system", "content": self.system_prompt_needs_rooms + "\n\nToday's date: " + datetime.datetime.now().strftime("%Y-%m-%d")},
            {"role": "user", "content": user_message}
        ]
        try:
            response = await acompletion(
                model="gpt-4o-mini",
                messages=messages,
                response_format=RoomResponse
            )

            response = RoomResponse.parse_obj(json.loads(response.choices[0].message.content))
            logger.debug(f"Room need response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error during room need completion: {e}")
            raise

    
    async def __determine_room_booking(self, user_message: str) -> BookingResponse:
        # if "SQ" not in user_message:
        #     logger.info("SQ not found in message, not determining room need")
        #     return RoomResponse(needs_rooms=False)
        
        logger.info("Determining if user is booking rooms")
        messages = [
            {"role": "system", "content": self.system_prompt_booking_rooms + "\n\nToday's date: " + datetime.datetime.now().strftime("%Y-%m-%d")},
            {"role": "user", "content": user_message}
        ]
        try:
            response = await acompletion(
                model="gpt-4o-mini",
                messages=messages,
                response_format=BookingResponse
            )

            logger.info(f"Booking rooms response from LLM: {response}")

            response = BookingResponse.parse_obj(json.loads(response.choices[0].message.content))
            logger.info(f"Booking rooms response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error during room need completion: {e}")
            raise

    async def __get_number_of_rooms(self, user_message: str) -> NumberOfRooms:
        logger.debug("Fetching number of rooms required by user")
        messages = [
            {"role": "system", "content": self.system_prompt_number_of_rooms + "\n\nToday's date: " + datetime.datetime.now().strftime("%Y-%m-%d")},
            {"role": "user", "content": user_message}
        ]
        try:
            response = await acompletion(
                model="gpt-4o-mini",
                messages=messages,
                response_format=NumberOfRooms
            )
            response = NumberOfRooms.parse_obj(json.loads(response.choices[0].message.content))
            logger.debug(f"Number of rooms response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error during number of rooms completion: {e}")
            raise

    def __get_available_rooms(self):
        logger.debug("Fetching available rooms from file")
        room_requirements_file = os.getenv("ROOM_REQUIREMENTS_FILE")
        if not room_requirements_file:
            logger.critical("ROOM_REQUIREMENTS_FILE environment variable not set")
            raise ValueError("ROOM_REQUIREMENTS_FILE environment variable not set")

        try:
            with open(room_requirements_file, 'r') as f:
                available_rooms = json.load(f)
                logger.debug(f"Loaded available rooms: {available_rooms}")
                return available_rooms
        except FileNotFoundError:
            logger.error(f"Room requirements file not found: {room_requirements_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from room requirements file: {e}")
            raise

    def __update_available_rooms(self, rooms_to_book: int):
        logger.debug(f"Updating available rooms, booking {rooms_to_book} rooms")
        room_requirements_file = os.getenv("ROOM_REQUIREMENTS_FILE")
        if not room_requirements_file:
            logger.critical("ROOM_REQUIREMENTS_FILE environment variable not set")
            raise ValueError("ROOM_REQUIREMENTS_FILE environment variable not set")

        try:
            with open(room_requirements_file, 'r') as f:
                available_rooms = json.load(f)
            
            #today = datetime.datetime.now().strftime("%Y-%m-%d")
            
            if self.current_room_need_date not in available_rooms:
                logger.error(f"No availability data for date: {self.current_room_need_date}")
                raise ValueError(f"No availability data for date: {self.current_room_need_date}")
                
            if available_rooms[self.current_room_need_date]["availability"] < rooms_to_book:
                logger.error("Not enough rooms available to book")
                raise ValueError("Not enough rooms available to book")
                
            available_rooms[self.current_room_need_date]["availability"] -= rooms_to_book
            logger.debug(f"Updated room availability to: {available_rooms[self.current_room_need_date]['availability']}")
            
            with open(room_requirements_file, 'w') as f:
                json.dump(available_rooms, f, indent=4)
                
            return available_rooms
        except FileNotFoundError:
            logger.error(f"Room requirements file not found: {room_requirements_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error handling JSON for room requirements file: {e}")
            raise

    def __calculate_if_possible(self, room_requirements: Union[int, List[Tuple]], available_rooms: Dict[str, int]):
        logger.debug("Calculating room availability based on requirements")
        try:
            # Case 1: When room_requirements is an integer
            if isinstance(room_requirements, int):
                # Get today's date in the required format
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                logger.info(f"Today's date: {today}")
                # Get availability for today from the available_rooms dictionary
                total_available = available_rooms[today]["availability"] if today in available_rooms else 0
                logger.info(f"Total available rooms: {total_available}, Rooms needed: {room_requirements}")

                if total_available >= room_requirements:
                    logger.info("Sufficient rooms available")
                    return room_requirements
                else:
                    logger.warning("Insufficient rooms available")
                    return -1

            # Case 2: When room_requirements is a list of tuples
            elif isinstance(room_requirements, list):
                result = []
                for room_type, count in room_requirements:
                    available = available_rooms.get(room_type, 0)
                    result.append((room_type, available))
                logger.debug(f"Room availability per type: {result}")
                return result

            else:
                logger.error("Invalid input type for room_requirements")
                raise ValueError("Invalid input type. Must be either int or list of tuples.")
        except Exception as e:
            logger.error(f"Error during room calculation: {e}")
            raise

    