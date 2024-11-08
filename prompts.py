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