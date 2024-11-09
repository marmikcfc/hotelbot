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
from prompts import SYSTEM_PROMPT_BOOKING_ROOMS, SYSTEM_PROMPT_GET_DATE, SYSTEM_PROMPT_GET_ORIGINATOR, SYSTEM_PROMPT_NEEDS_ROOMS, SYSTEM_PROMPT_NUMBER_OF_ROOMS, SYSTEM_PROMPT_CONFIRMATION_MENU, SYSTEM_PROMPT_OVERRIDE
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

from enum import Enum
from pydantic import BaseModel

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


class ResponseType(str, Enum):
    SHUT_DOWN_AGENT = "shut_down_agent"
    START_AGENT = "start_agent"
    ROOMS_BOOKED_QUERY = "rooms_booked_query"
    REPORT = "report"
    OVERRIDE_ROOMS = "override_rooms"
    OTHERS = "others"
    ROOMS_EMPTY_QUERY = "rooms_empty_query"
    CHANGE_MESSAGE_ORIGINATOR = "change_message_originator"
    GET_ORIGINATOR = "get_originator"
    HELP = "help"

class ConfirmationResponse(BaseModel):
    response_type: ResponseType

class OverrideResponse(BaseModel):
    date: str
    number_of_rooms: int


class DateResponse(BaseModel):
    date: str = Field(..., description="Date for which rooms booked are queried in YYYY-MM-DD format")


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
        self.system_prompt_confirmation_menu = SYSTEM_PROMPT_CONFIRMATION_MENU
        self.system_prompt_get_date= SYSTEM_PROMPT_GET_DATE
        self.system_prompt_get_originator = SYSTEM_PROMPT_GET_ORIGINATOR
        self.sent_first_message = False
        self.confirmation_notification_chat_id = os.getenv("CONFIRMATION_NOTIFICATION_CHAT_ID")
        self.message = None
        self.current_state = None
        self.bids = []
        self.agent_switched_on = True
        self.agent_started = True

        # Initialize class variables for dates
        self.arrival_date: Optional[str] = None
        self.departure_date: Optional[str] = None

        self.report = {}
        self.report_file = os.getenv("REPORT_FILE", "data/report.json")
        # self.__load_report()
        
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
    
    async def __process_confirmation_group_message(self, message: str, user_id: str):
        logger.info("Processing confirmation group message")
        # Only needed for dev
        if message == "Successfully shut down agent" or message =="Successfully started agent" or "daily booking report" in message.lower() or "successfully overridden room availability" in message.lower() or "rooms empty for the date" in message.lower() or "current message originator for the system is" in message.lower() or "originator updated from" in message.lower() or "you can try following messages to command the bot" in message.lower():
            logger.info("Message is a confirmation notification, not processing")
            return
        
        messages = [
            {"role": "system", "content": self.system_prompt_confirmation_menu},
            {"role": "user", "content": message}
        ]
        
        try:
            response = await acompletion(
                model="gpt-4o-mini",
                messages=messages,
                response_format=ConfirmationResponse
            )
            response = ConfirmationResponse.parse_obj(json.loads(response.choices[0].message.content))
            logger.info(f"Confirmation response: {response}")
            
            if response.response_type == ResponseType.SHUT_DOWN_AGENT:
                self.agent_switched_on = False
                await send_whatsapp_message(f"Successfully shut down agent", self.confirmation_notification_chat_id, self.sent_first_message)
                
            elif response.response_type == ResponseType.START_AGENT:
                self.agent_switched_on = True
                await send_whatsapp_message(f"Successfully started agent", self.confirmation_notification_chat_id, self.sent_first_message)
                
            elif response.response_type == ResponseType.ROOMS_BOOKED_QUERY:
                report = self.__load_report()
                today = datetime.datetime.now(pytz.timezone('Asia/Singapore')).strftime("%Y-%m-%d")

                # Get date from message if specified, otherwise use today's date
                date_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT_GET_DATE.format(today)},
                    {"role": "user", "content": message}
                ]
                date_response = await acompletion(
                    model="gpt-4o-mini", 
                    messages=date_messages,
                    response_format=DateResponse
                )
                date_response = DateResponse.parse_obj(json.loads(date_response.choices[0].message.content))
                rooms_booked = report.get(date_response.date, {}).get("number_of_rooms_booked", 0)
                await send_whatsapp_message(f"We've booked {rooms_booked} rooms for {date_response.date}", self.confirmation_notification_chat_id, self.sent_first_message)
                
            elif response.response_type == ResponseType.ROOMS_EMPTY_QUERY:
                today = datetime.datetime.now(pytz.timezone('Asia/Singapore')).strftime("%Y-%m-%d")
                available_rooms = self.__get_available_rooms()
                # Get date from message if specified, otherwise use today's date
                date_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT_GET_DATE.format(today)},
                    {"role": "user", "content": message}
                ]
                date_response = await acompletion(
                    model="gpt-4o-mini", 
                    messages=date_messages,
                    response_format=DateResponse
                )
                date_response = DateResponse.parse_obj(json.loads(date_response.choices[0].message.content))
                logger.info(f"Date response: {date_response}")
                rooms_available = available_rooms.get(date_response.date, {}).get("availability", 0)
                await send_whatsapp_message(f"We've {rooms_available} rooms empty for the date {date_response.date}", self.confirmation_notification_chat_id, self.sent_first_message)
                


            elif response.response_type == ResponseType.REPORT:
                # Handle generating a report
                try:
                    # Load both report and room requirements data
                    with open('data/report.json', 'r') as f:
                        report_data = json.load(f)
                    
                    with open(os.getenv("ROOM_REQUIREMENTS_FILE"), 'r') as f:
                        rooms_data = json.load(f)
                    
                    if not report_data:
                        await send_whatsapp_message("No report data available", self.confirmation_notification_chat_id, self.sent_first_message)
                        return

                    # Format the report message
                    report_message = "📊 *Daily Booking Report*\n\n"
                    for date, data in report_data.items():
                        report_message += f"*Date:* {date}\n"
                        report_message += f"Rooms Booked: {data.get('number_of_rooms_booked', 0)}\n"
                        report_message += f"Rooms Available: {rooms_data.get(date, {}).get('availability', 'N/A')}\n"
                        report_message += f"Messages from Airlines: {data.get('number_of_messages_from_airlines', 0)}\n"
                        if 'bookings' in data:
                            report_message += "Booking Details:\n"
                            for booking in data['bookings']:
                                report_message += f"- Room Type: {booking.get('room_type', 'N/A')}\n"
                                report_message += f"  Check-in: {booking.get('check_in', 'N/A')}\n"
                                report_message += f"  Check-out: {booking.get('check_out', 'N/A')}\n"
                        report_message += "\n"

                    await send_whatsapp_message(report_message, self.confirmation_notification_chat_id, self.sent_first_message)
                    logger.info("Report sent successfully")
                    
                except Exception as e:
                    logger.error(f"Error generating report: {e}")
                    await send_whatsapp_message("Error generating report", self.confirmation_notification_chat_id, self.sent_first_message)
                    raise
            elif response.response_type == ResponseType.OVERRIDE_ROOMS:
                # Handle overriding the agent's decision
                try:
                    override_messages = [
                        {"role": "system", "content": SYSTEM_PROMPT_OVERRIDE+"\n\nToday's date: " + datetime.datetime.now().strftime("%Y-%m-%d")},
                        {"role": "user", "content": message}
                    ]
                    override_response = await acompletion(
                        model="gpt-4o-mini",
                        messages=override_messages,
                        response_format=OverrideResponse
                    )
                    override_response = OverrideResponse.parse_obj(json.loads(override_response.choices[0].message.content))
                    
                    # Update the room availability for the specified date
                    available_rooms = self.__get_available_rooms()
                    
                    if override_response.date not in available_rooms:
                        available_rooms[override_response.date] = {"availability": override_response.number_of_rooms}
                    else:
                        available_rooms[override_response.date]["availability"] = override_response.number_of_rooms
                    
                    room_requirements_file = os.getenv("ROOM_REQUIREMENTS_FILE")
                    with open(room_requirements_file, 'w') as f:
                        json.dump(available_rooms, f, indent=4)
                    
                    logger.info(f"Successfully overridden room availability for {override_response.date} to {override_response.number_of_rooms} rooms")
                    await send_whatsapp_message(f"Successfully overridden room availability for {override_response.date} to {override_response.number_of_rooms} rooms", self.confirmation_notification_chat_id, self.sent_first_message)

                except Exception as e:
                    logger.error(f"Error during override processing: {e}")
                    await send_whatsapp_message("Error during override processing", self.confirmation_notification_chat_id, self.sent_first_message)
                    raise

            elif response.response_type == ResponseType.CHANGE_MESSAGE_ORIGINATOR:
                logger.info(f"Originator query received: {message}")
                try:
                    originator_messages = [
                        {"role": "system", "content": self.system_prompt_get_originator},
                        {"role": "user", "content": message}
                    ]
                    originator_response = await acompletion(
                        model="gpt-4o-mini", 
                        messages=originator_messages,
                        temperature=0
                    )
                    originator = originator_response.choices[0].message.content
                    
                    if originator and originator.lower() != "null":
                        # Load current metadata
                        metadata_file = os.getenv("DATA_METADATA_FILE", "data/metadata.json")
                        try:
                            with open(metadata_file, 'r') as f:
                                metadata = json.load(f)
                        except FileNotFoundError:
                            metadata = {}
                        
                        original_originator = metadata.get('message_originator', None)
                        # Update originator
                        metadata['message_originator'] = originator
                        
                        # Save updated metadata
                        with open(metadata_file, 'w') as f:
                            json.dump(metadata, f, indent=4)
                            
                        self.originator = originator
                        logger.info(f"Successfully updated originator to {originator}")
                    else:
                        logger.info("No valid originator found in message")
                        
                except Exception as e:
                    logger.error(f"Error processing originator update: {e}")
                    await send_whatsapp_message("Error updating originator", self.confirmation_notification_chat_id, self.sent_first_message)
                    raise
                await send_whatsapp_message(f"Originator updated from {original_originator} to {self.originator}", self.confirmation_notification_chat_id, self.sent_first_message)
            
            elif response.response_type == ResponseType.GET_ORIGINATOR:
                logger.info(f"Originator query received: {message}")
                try:
                    originator = self.__get_message_originator()
                    logger.info(f"Successfully retrieved originator: {originator}")
                    await send_whatsapp_message(f"current message originator for the system is {originator}", self.confirmation_notification_chat_id, self.sent_first_message)
                except Exception as e:
                    logger.error(f"Error retrieving originator: {e}")
                    await send_whatsapp_message("Error retrieving originator", self.confirmation_notification_chat_id, self.sent_first_message)
                    raise
            elif response.response_type == ResponseType.HELP:
                logger.info(f"Help query received: {message}")
                try:
                    metadata_file = os.getenv("DATA_METADATA_FILE", "data/metadata.json")
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    help_menu = metadata.get('help_menu', "Help menu not found")
                    await send_whatsapp_message(help_menu, self.confirmation_notification_chat_id, self.sent_first_message)
                except Exception as e:
                    logger.error(f"Error retrieving help menu: {e}")
                    await send_whatsapp_message("Error retrieving help menu", self.confirmation_notification_chat_id, self.sent_first_message)
                    raise
            else:
                logger.info(f"Unknown response type: {response.response_type}")
                pass
            
        except Exception as e:
            logger.error(f"Error during confirmation response processing: {e}")
            raise

    def __get_message_originator(self) -> str:
        """Get the message originator from metadata file"""
        metadata_file = os.getenv("DATA_METADATA_FILE", "data/metadata.json")
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        except FileNotFoundError:
            metadata = {}
        
        return metadata.get('message_originator', None)

    async def handle_whatsapp_group(self, chat_id: str, message: str, user_id: str, from_number: str):
        if message == "RP Can":
            logger.info("RP Can message received, not sending response")
            return
        
        if chat_id == self.confirmation_notification_chat_id:
            logger.info("in confirmation notification chat, so invoking menu")
            await self.__process_confirmation_group_message(message, user_id)
            return
        
        if not self.agent_switched_on:
            logger.info("Agent is shut down, not processing message")
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
                    booking_days = await self.__calculate_booking_days(self.current_state.arrival_date, self.current_state.departure_date)
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
                            self.current_state.arrival_date,
                            self.current_state.departure_date
                        )

                        departure_hour = int(self.current_state.departure_time.split(":")[0])
                        if departure_hour >= 19:
                            departure_date = (datetime.datetime.strptime(self.current_state.departure_date, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                        else:
                            departure_date = self.current_state.departure_date
                        logger.info(f"Booking {booking_response.number_of_rooms} rooms from {self.current_state.arrival_date} to {departure_date}")
                        await self.whatsapp_confirmation(f"SQ booking {booking_response.number_of_rooms} rooms from {self.current_state.arrival_date} to {departure_date}.\n\n*Original Message*\n{self.message}")
                    except Exception as e:
                        logger.error(f"Error updating available rooms: {e}")
            else:
                logger.info("User is not booking rooms")
            return
        
        if room_need.needs_rooms:

            with open("data/metadata.json") as f:
                message_originator = str(json.load(f)["message_originator"])
            
            # Check if message is from someone other than the originator
            if str(from_number) != message_originator:
                logger.info(f"Message from {from_number} is not from the originator {message_originator}, not processing")
                return
            
            try:
                self.__update_report(datetime.datetime.now(pytz.timezone('Asia/Singapore')).strftime("%Y-%m-%d"), message_from_airlines=True)
                # Store arrival and departure dates as class variables
                self.current_state = room_need
                self.current_state.arrival_date = room_need.arrival_date
                self.current_state.departure_date = room_need.departure_date

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
            available_rooms = self.__get_available_rooms()
            booking_days = await self.__calculate_booking_days(self.current_state.arrival_date, self.current_state.departure_date, self.current_state.departure_time)
            current_date = datetime.datetime.strptime(arrival_date, "%Y-%m-%d")
            dates = [current_date + datetime.timedelta(days=i) for i in range(booking_days)]
            date_strings = [date.strftime("%Y-%m-%d") for date in dates]
            logger.info(f"Date strings: {date_strings}, \n dates: {dates}, \n booking days: {booking_days}, \n current date: {current_date}")
            for date in date_strings:
                if date not in available_rooms:
                    available_rooms[date] = {"availability": 10}
                    logger.info(f"Added missing date {date} with 10 rooms")

                if available_rooms[date]["availability"] < rooms_to_book:
                    logger.error(f"Not enough rooms available on {date}")
                    raise ValueError(f"Not enough rooms available on {date}")

                available_rooms[date]["availability"] -= rooms_to_book
                self.__update_report(date, rooms_to_book)
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
            booking_days = await self.__calculate_booking_days(self.current_state.arrival_date, self.current_state.departure_date, self.current_state.departure_time)
            logger.info(f"Booking spans {booking_days} days")

            current_date = datetime.datetime.strptime(self.current_state.arrival_date, "%Y-%m-%d")
            dates = [current_date + datetime.timedelta(days=i) for i in range(booking_days)]
            date_strings = [date.strftime("%Y-%m-%d") for date in dates]
            logger.info(f"Date strings while checking for availability: {date_strings}")
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
    
    def __load_report(self):
        if os.path.exists(self.report_file):
            with open(self.report_file, 'r') as f:
                report = json.load(f)
        else:
            report = {}
        return report

    def __save_report(self, report: Dict[str, Dict[str, int]]):
        with open(self.report_file, 'w') as f:
            json.dump(report, f, indent=4)

    def __update_report(self, date: str, rooms_booked: int = 0, message_from_airlines: bool = False):
        try:    
            logger.info(f"Updating report for date: {date}, rooms booked: {rooms_booked}, message from airlines: {message_from_airlines}")
            report = self.__load_report()
            if date not in report:
                report[date] = {"number_of_messages_from_airlines": 0, "number_of_rooms_booked": 0}
        
            if message_from_airlines:
                report[date]["number_of_messages_from_airlines"] += 1
            else:
                report[date]["number_of_rooms_booked"] += rooms_booked
            self.__save_report(report)
        except Exception as e:
            logger.error(f"Error updating report: {e}")
            raise
    