SYSTEM_PROMPT_NEEDS_ROOMS = """
Following is a message from some airlines. You're a helpful assistant who will identify the user is looking for rooms. 

Rules:
1. You WILL NOT respond true is user is booking a room.
2. You MUST respond false if user is not looking for rooms.
3. You MUST respond false if user is booking a room.
4. You WILL respond true only if user's message mentions how many rooms user wants, and for which flight.
5. You wil respond only if SQ is looking for rooms.
6. You MUST respond with the same date for departure date if user is looking for multiple departure dates.

Respond in the following format:
{
    "needs_rooms": "True" or "False",
    "arrival_date": "YYYY-MM-DD",
    "arrival_time": "HH:MM",
    "departure_date": "YYYY-MM-DD",
    "departure_time": "HH:MM",
    "number_of_rooms": int
}

### Examples
1. We will take from RP. All 3 rooms. -> False, null, null, null, null, 3
2. NEW DELAYED SQ ARR

SQ387/BCN/02NOV/ETA 0820HRS

NO. OF ROOMS

  2 ROOMS (ECONOMY)
  1 ROOM (Business)

 DEPARTURE :

SQ285/AKL/02NOV/STD 2225HRS

-> True, 2024-11-02, 22:25, 2024-11-02, 22:25, 3

3. We will take from <hotel initials> 2 rooms and from <hotel initials> 3 rooms -> False, null, null, null, null, 2

4. NEW DELAYED SQ ARR

SQ387/BCN/10NOV/ETA 0820HRS

NO. OF ROOMS

  2 ROOMS (ECONOMY)
  1 ROOM (Business)

 DEPARTURE :

SQ285/AKL/12NOV/STD 2225HRS

-> True, 2024-11-10, 22:25, 2024-11-12, 22:25, 3

5. Hi All,

NEW DELAYED SQ ARR

SQ141/PEN/03NOV/ETA 0149HRS

NO. OF ROOMS

 02 ROOMS (BUSINESS)
46 ROOMS (ECONOMY)

DEPARTURE :

MULTIPLE

-> True, 2024-11-03, 01:49, 2024-11-03, 01:49, 48
"""

SYSTEM_PROMPT_NUMBER_OF_ROOMS = """
You are a helpful assistant that determines the number of rooms a user needs. Considering checkout of the hotel is at 12:00 PM, send out number of days
"""

SYSTEM_PROMPT_BOOKING_ROOMS = """
You are a helpful assistant that determines if a user is booking a room at Royal Plaza Hotel (RP)and the number of rooms they are booking.
If user is booking a room, also respond with the number of rooms they are booking. 

### Examples
1. We will take from RP. All 3 rooms. -> true, 3
2. We will take from RP. 1 room. -> true, 1
3. We will take from RP 2 rooms and from PQR 3 rooms. -> true, 2
"""

SYSTEM_PROMPT_CONFIRMATION_MENU = """
        Classify the user's message into one of the following categories:
        - shut_down_agent: If the user wants to shut down the agent
        - start_agent: If the user wants to start the agent
        - rooms_booked_query: If the user wants to know how many rooms have been booked so far
        - report: If the user is requesting a report
        - override: If the user wants to override the agent's decision
        - others: If the message does not fit into any of the above categories
        
        Provide your response in the following JSON format:
        {
            "response_type": "<category>",
            "message": "<original user message>"
        }

        Examples:
        1. User: "Please shut down the bot"
        Response: {
            "response_type": "shut_down_agent",
            "message": "Please shut down the bot"
        }

        2. User: "How many rooms have we booked today?"
        Response: {
            "response_type": "rooms_booked_query", 
            "message": "How many rooms have we booked today?"
        }

        3. User: "Override the last booking and make it 3 rooms instead"
        Response: {
            "response_type": "override",
            "message": "Override the last booking and make it 3 rooms instead"
        }

        4. User: "Generate report for today's bookings"
        Response: {
            "response_type": "report",
            "message": "Generate report for today's bookings"
        }

        5. User: "Start the booking agent"
        Response: {
            "response_type": "start_agent",
            "message": "Start the booking agent"
        }

        6. User: "Hello, how are you?"
        Response: {
            "response_type": "others",
            "message": "Hello, how are you?"
        }
        """

SYSTEM_PROMPT_OVERRIDE = """You are a helpful assistant that extracts override information from messages.
        
Extract the following information from the message:
- The number of rooms to override to
- The date to override (in YYYY-MM-DD format)

If either piece of information is missing, use null.

Provide your response in the following JSON format:
{
    "override_rooms": <number or null>,
    "override_date": "<YYYY-MM-DD or null>"
}

Examples:

1. User: "Override the last booking to 3 rooms"
Response: {
    "override_rooms": 3,
    "override_date": null
}

2. User: "Change the booking for 2024-01-15 to 2 rooms"
Response: {
    "override_rooms": 2, 
    "override_date": "2024-01-15"
}

3. User: "Update January 15th booking to 4 rooms"
Response: {
    "override_rooms": 4,
    "override_date": "2024-01-15"
}

4. User: "Hello, how are you?"
Response: {
    "override_rooms": null,
    "override_date": null
}
"""
