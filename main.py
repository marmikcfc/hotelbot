import os
from fastapi import FastAPI, Request
from agents.agent import Agent
from Message.message import Message
from agents.customer_service_agent import CustomerServiceBot
from agents.fast_finger_agent import FastFingerBot
from agents.digital_gm_agent import DigitalGMBot
from Services.knowcross_service import KnowcrossService
from Services.simphony_service import SimphonyService
from Services.sinix_service import SinixService
from Services.rag_service import RAGService
import httpx

from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

agent = Agent()
customer_service_bot = CustomerServiceBot()
fast_finger_bot = FastFingerBot()
digital_gm_bot = DigitalGMBot()
knowcross_service = KnowcrossService()
simphony_service = SimphonyService()
sinix_service = SinixService()
rag_service = RAGService()

api_key = os.getenv("WHAPI_API_KEY")

# Make sure message is not from us
# Or rather not from_me
@app.post("/webhooks/whatsapp_group/messages")
async def post_whatsapp_group_payload(request: Request):

    #If it's a reply to yourself, ignore it
    #if it's yourself, ignore it
    body = await request.json()
    print("Received webhook payload:", body)
    from_me = body.get("messages")[0].get("from_me")
    context = body.get("messages")[0].get("context", None)
    type = body.get("messages")[0].get("type")

    if type == "text":
        message = body.get("messages")[0].get("text").get("body")
        # if context:
        #     quoted_message = context.get("quoted_content").get("body")
        #     print(f"Quoted message: {context} and hence it's a reply and not responding")
        
        # elif from_me:
        #     print(f"Message from self: {body.get('messages')[0]} and hence not responding")

        if body.get("messages")[0].get("chat_id") in os.getenv("WHATSAPP_GROUP_IDS").split(","):
            print("Group message received from our Group")
            response = await fast_finger_bot.handle_whatsapp_group(body.get('messages')[0].get('chat_id'), message , body.get('messages')[0].get('from_name', 'no_name'))
        else:
            print("Message not from our group, ignoring")

    elif type == "action" and body.get("messages")[0].get("action").get("type") == "edit" and body.get("messages")[0].get("action").get("edited_type") == "text":
        body = body.get("messages")[0].get("action").get("edited_content").get("body")
        print("Action message received")
        

#I'll do this now
@app.post("/webhooks/whatsapp_personal")
async def post_whatsapp_personal_payload(message: Message):
    response = fast_finger_bot.handle_whatsapp_personal(message)
    return {"message": response}

@app.post("/webhooks/digital_gm")
async def post_digital_gm_payload(message: Message):
    response = digital_gm_bot.handle_digital_gm(message)
    return {"message": response}
