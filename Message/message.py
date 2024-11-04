from pydantic import BaseModel, Field
from typing import List

class Text(BaseModel):
    body: str

class MessageData(BaseModel):
    id: str
    from_me: bool
    type: str
    chat_id: str
    timestamp: int
    source: str
    device_id: int
    chat_name: str
    status: str
    text: Text
    from_: str = Field(..., alias="from")
    from_name: str

class Message(BaseModel):
    messages: List[MessageData]
    channel_id: str
