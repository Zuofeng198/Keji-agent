
import asyncio, json, threading, time, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

app_id = "cli_aa86efb826f81bb4"
app_secret = "uaGzIG1dj9ptxrDC1ozbvdleOBbx4zb7"

import lark_oapi as lark
from lark_oapi.ws.client import Client as WSClient

received_events = []
handler_called = threading.Event()

def on_message(data):
    print(f"[HANDLER CALLED] at {time.time()}")
    handler_called.set()
    received_events.append(data)
    try:
        event = data.event
        msg = event.message
        sender = event.sender
        print(f"  chat_type: {msg.chat_type}")
        print(f"  msg_type: {msg.message_type}")
        print(f"  content: {msg.content[:200] if msg.content else 'None'}")
        print(f"  sender: {sender.sender_id}")
        print(f"  chat_id: {msg.chat_id}")
        print(f"  message_id: {msg.message_id}")
    except Exception as e:
        print(f"  Error parsing: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

builder = lark.EventDispatcherHandler.builder("", "")
builder.register_p2_im_message_receive_v1(on_message)
event_handler = builder.build()

ws_client = lark.ws.Client(
    app_id=app_id,
    app_secret=app_secret,
    log_level=lark.LogLevel.DEBUG,
    event_handler=event_handler,
    domain=lark.FEISHU_DOMAIN,
)

print(f"[{time.time()}] Starting WS client...")
print(f"[{time.time()}] PLEASE SEND A MESSAGE TO THE BOT IN FEISHU NOW")
print(f"[{time.time()}] Listening for 30 seconds...")

ws_connected = threading.Event()

def run_ws():
    import lark_oapi.ws.client as _ws_client_mod
    ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(ws_loop)
    _ws_client_mod.loop = ws_loop
    try:
        print(f"[{time.time()}] WS thread started")
        ws_client.start()
        print(f"[{time.time()}] WS client stopped")
    except Exception as e:
        print(f"[{time.time()}] WS thread error: {type(e).__name__}: {e}")
    finally:
        ws_loop.close()

ws_thread = threading.Thread(target=run_ws, daemon=True)
ws_thread.start()

# Wait for connection
time.sleep(3)
print(f"[{time.time()}] Now listening... send a message to the bot in Feishu!")

# Wait for events or timeout
for i in range(30):
    if handler_called.is_set():
        print(f"[{time.time()}] Event received! Stopping early.")
        break
    time.sleep(1)
    if i % 5 == 0 and i > 0:
        print(f"[{time.time()}] Still listening... ({i}s elapsed)")

print(f"\n[{time.time()}] Test complete")
print(f"Events received: {len(received_events)}")
if received_events:
    print("SUCCESS: Messages are reaching the WS client!")
else:
    print("FAIL: No messages received in 30 seconds")
    print("The issue is on the Feishu platform side - events are NOT being pushed.")
    print("Check: event subscription (im.message.receive_v1), permissions, app publish status.")
