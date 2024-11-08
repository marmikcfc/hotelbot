import datetime
import json
import os
import logging
from litellm import OpenAI, acompletion
import pytz
from Message.message import Message
from typing import Union, List, Tuple, Dict
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from utils.utils import send_whatsapp_message
from prompts import SYSTEM_PROMPT_BOOKING_ROOMS, SYSTEM_PROMPT_NEEDS_ROOMS, SYSTEM_PROMPT_NUMBER_OF_ROOMS
from utils import *

from typing import TypedDict, Optional
from dataclasses import dataclass
import json

import openai
# from dspy import OpenAI
# lm = OpenAI(model='gpt-4o-mini')
# dspy.settings.configure(lm=lm)
# from dspy.teleprompt import BootstrapFewShotWithRandomSearch
from utils.utils import send_whatsapp_message, calculate_hotel_days

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


class BasicExtraction(BaseModel):
    needs_rooms: bool = Field(desc="Whether rooms are needed")
    arrival_date: str = Field(desc="Arrival date in YYYY-MM-DD format")
    arrival_time: str = Field(desc="Arrival time in HH:MM format")
    departure_date: str = Field(desc="Departure date in YYYY-MM-DD format")
    departure_time: str = Field(desc="Departure time in HH:MM format")
    number_of_rooms: int = Field(desc="Number of rooms needed")


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
        self.message = None
        self.current_state = None
        self.bids = []
        
        # self.loaded_extractor = FlightInfoExtractor()
        # self.loaded_extractor.load("compiled_flight_info_extractor.dspy")

        # Initialize class variables for dates
        self.arrival_date: Optional[str] = None
        self.departure_date: Optional[str] = None

        logger.info("FastFingerBot initialization complete")
        

    async def __calculate_booking_days(self, arrival_date: str, departure_date: str, departure_time: str = "00:00") -> int:
        logger.debug(f"Calculating booking days from {arrival_date} to {departure_date}")
        try:
            booking_days = calculate_hotel_days(arrival_date, departure_date, departure_time)
            logger.info(f"Calculated booking days: {booking_days}")
            return booking_days
        except Exception as e:
            logger.error(f"Error calculating booking days: {e}")
            raise

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
            if self.current_state == None:
                logger.info(f"Current state is None, returning")
                return
            logger.info("User does not need rooms, Checking if they are booking a room")
            booking_response = await self.__determine_room_booking(message)
            logger.info(f"Booking response: {booking_response}")        
            
            if booking_response.booking_room:
                # if room_need.needs_rooms != self.current_state.needs_rooms:
                #     logger.info(f"User needs rooms changed, not booking")

                #     await send_whatsapp_message(
                #         f"No, we cannot accommodate {booking_response.number_of_rooms} rooms for the selected dates.",
                #         chat_id,
                #         self.sent_first_message
                #     )
                #     return
                logger.info(f"User is booking {booking_response.number_of_rooms} rooms")
                try:
                    booking_days = await self.__calculate_booking_days(self.arrival_date, self.departure_date)
                except Exception as e:
                    logger.error(f"Error calculating booking days: {e}")
                    return

                is_possible = await self.__calculate_if_possible(
                    booking_response.number_of_rooms,
                    available_rooms
                )



                if not is_possible:
                    logger.info(f"Not enough rooms available, not booking")
                    await send_whatsapp_message(
                        f"No, we cannot accommodate {booking_response.number_of_rooms} rooms for the selected dates.",
                        chat_id,
                        self.sent_first_message
                    )
                else:
                    try:
                        await self.__update_available_rooms(
                            booking_response.number_of_rooms,
                            self.arrival_date,
                            self.departure_date
                        )
                        logger.info(f"Booking {booking_response.number_of_rooms} rooms from {self.arrival_date} to {self.departure_date}")
                        await self.whatsapp_confirmation(f"SQ booking {booking_response.number_of_rooms} rooms from {self.arrival_date} to {self.departure_date}.\n\n*Original Message*\n{self.message}")
                    except Exception as e:
                        logger.error(f"Error updating available rooms: {e}")
            else:
                logger.info("User is not booking rooms")
            return
        
        if room_need.needs_rooms:
            try:
                # Store arrival and departure dates as class variables
                self.arrival_date = room_need.arrival_date
                self.departure_date = room_need.departure_date

                # # Check if arrival date is before today in Singapore timezone
                # sg_tz = pytz.timezone('Asia/Singapore')
                # sg_today = datetime.datetime.now(sg_tz).date()
                # arrival = datetime.datetime.strptime(self.arrival_date, "%Y-%m-%d").date()
                
                # if arrival < sg_today:
                #     logger.info(f"Arrival date {arrival} is before today {sg_today}, not processing")
                #     return


                number_of_rooms = await self.__get_number_of_rooms(message)
                logger.info(f"Number of rooms requested: {number_of_rooms.number_of_rooms}")
            except Exception as e:
                logger.error(f"Error getting number of rooms: {e}")
                #self.sent_first_message = True
                return
            try:
                is_possible = await self.__calculate_if_possible(
                    number_of_rooms.number_of_rooms,
                    available_rooms
                )
                if is_possible:
                    response = "RP Can"
                    self.message = message
                    self.bids.append((message, number_of_rooms.number_of_rooms))
                    await send_whatsapp_message(response, chat_id, self.sent_first_message)
                else:
                    response = "No, we cannot accommodate you."
                logger.info(f"Response to user: {response}")
            except Exception as e:
                logger.error(f"Error calculating room availability: {e}")
            
            self.current_state = room_need
        else:
            response = "No rooms needed."
            logger.info(f"Response to user: {response}")
            #self.sent_first_message = True

    async def __determine_room_need(self, user_message: str) -> BasicExtraction:
        # if "SQ" not in user_message:
        #     logger.info("SQ not found in message, not determining room need")
        #     return RoomResponse(needs_rooms=False)
        
        logger.info("Determining if user needs rooms")
        messages = [
            {"role": "system", "content": self.system_prompt_needs_rooms + "\n\nToday's date: " + datetime.datetime.now().strftime("%Y-%m-%d")},
            {"role": "user", "content": user_message}
        ]
        try:
            response = await acompletion(
                model="gpt-4o-mini",
                messages=messages,
                response_format=BasicExtraction
            )

            response = BasicExtraction.parse_obj(json.loads(response.choices[0].message.content))

            # Adjust arrival date if arrival time is before 1:00 PM
            if response.arrival_time:
                arrival_hour = int(response.arrival_time.split(":")[0])
                if arrival_hour < 13:  # Before 1:00 PM
                    arrival_date = datetime.datetime.strptime(response.arrival_date, "%Y-%m-%d")
                    response.arrival_date = (arrival_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                    logger.info(f"Adjusted arrival date to {response.arrival_date} due to early arrival time")
            logger.info(f"Room need response: {response}")
            return response
        
        # try:
        #     response = self.loaded_extractor(user_message)
        #     logger.info(f"Room need response: {response}")
        #     return response
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

    async def __update_available_rooms(self, rooms_to_book: int, arrival_date: str, departure_date: str) -> Dict[str, int]:
        logger.info(f"Updating available rooms, booking {rooms_to_book} rooms from {arrival_date} to {departure_date}.")
        room_requirements_file = os.getenv("ROOM_REQUIREMENTS_FILE")
        if not room_requirements_file:
            logger.critical("ROOM_REQUIREMENTS_FILE environment variable not set")
            raise ValueError("ROOM_REQUIREMENTS_FILE environment variable not set")

        try:
            with open(room_requirements_file, 'r') as f:
                available_rooms = json.load(f)

            booking_days = await self.__calculate_booking_days(self.current_state.arrival_date, self.current_state.departure_date, self.current_state.departure_time)
            current_date = datetime.datetime.strptime(arrival_date, "%Y-%m-%d")
            dates = [current_date + datetime.timedelta(days=i) for i in range(booking_days)]
            date_strings = [date.strftime("%Y-%m-%d") for date in dates]
            logger.info(f"Date strings: {date_strings}, \n dates: {dates}, \n booking days: {booking_days}, \n current date: {current_date}")
            for date in date_strings:
                if date not in available_rooms:
                    logger.error(f"No availability data for date: {date}")
                    raise ValueError(f"No availability data for date: {date}")

                if available_rooms[date]["availability"] < rooms_to_book:
                    logger.error(f"Not enough rooms available on {date}")
                    raise ValueError(f"Not enough rooms available on {date}")

                available_rooms[date]["availability"] -= rooms_to_book
                logger.debug(f"Updated room availability on {date} to: {available_rooms[date]['availability']}")

            with open(room_requirements_file, 'w') as f:
                json.dump(available_rooms, f, indent=4)

            logger.info("Successfully updated room availability for all booking dates")
            return available_rooms
        except FileNotFoundError:
            logger.error(f"Room requirements file not found: {room_requirements_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error handling JSON for room requirements file: {e}")
            raise

    async def __calculate_if_possible(self, room_requirements: int, available_rooms: Dict[str, int], booking = False) -> bool:
        logger.debug("Calculating room availability across all booking dates")
        try:
            booking_days = await self.__calculate_booking_days(self.arrival_date, self.departure_date)
            logger.info(f"Booking spans {booking_days} days")

            current_date = datetime.datetime.strptime(self.arrival_date, "%Y-%m-%d")
            dates = [current_date + datetime.timedelta(days=i) for i in range(booking_days)]
            date_strings = [date.strftime("%Y-%m-%d") for date in dates]

            # Check for missing dates and add them
            room_requirements_file = os.getenv("ROOM_REQUIREMENTS_FILE")
            updated = False

            for date in date_strings:
                if date not in available_rooms:
                    available_rooms[date] = {"availability": 10}
                    logger.info(f"Added missing date {date} with 10 rooms")
                    updated = True
                
                if available_rooms[date]['availability'] < room_requirements:
                    logger.warning(f"Insufficient rooms on {date}")
                    return False

            # Save updated file if any dates were added
            if updated:
                with open(room_requirements_file, 'w') as f:
                    json.dump(available_rooms, f, indent=4)

            logger.info("Sufficient rooms available for all booking dates")
            return True
        except Exception as e:
            logger.error(f"Error during room availability calculation: {e}")
            raise
    