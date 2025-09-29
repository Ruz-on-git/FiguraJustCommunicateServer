import asyncio
import json
import websockets
import os
from typing import Dict, Set, Any

# --- Constants and Global State ---

# A dictionary mapping WebSocket connections to client information.
# CLIENTS[websocket] = {"user_id": str, "room_name": str, "whitelist": set | list}
CLIENTS: Dict[websockets.WebSocketServerProtocol, Dict[str, Any]] = {}

# A helper dictionary to quickly find a client's connection by their user_id.
# USER_ID_MAP[user_id] = websocket
USER_ID_MAP: Dict[str, websockets.WebSocketServerProtocol] = {}

# The maximum allowed size for an incoming WebSocket message in bytes (1MB).
MAX_MESSAGE_SIZE = 1_048_576

async def send_json(websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
    """
    Serializes a dictionary to a JSON string and sends it to a client.

    Args:
        websocket: The WebSocket connection to send the message to.
        data: The dictionary to serialize and send.
    """
    try:
        await websocket.send(json.dumps(data))
    except websockets.exceptions.ConnectionClosed:
        pass

def validate_schema(data: Dict[str, Any]) -> bool:
    """
    Validates the structure and types of an incoming message dictionary.

    This function acts as a security checkpoint, ensuring that incoming data
    conforms to the expected format before any processing occurs.

    Args:
        data: The deserialized JSON data from a client message.

    Returns:
        True if the data is valid, False otherwise.
    """
    msg_type = data.get("type")
    if not isinstance(msg_type, str):
        return False

    schema = {
        "register": {"user_id": str, "whitelist": list},
        "message": {"recipient_id": str, "payload": object},
        "whitelist_add": {"user_id": str},
        "whitelist_remove": {"user_id": str},
        "whitelist_toggle_wildcard": {"enabled": bool},
    }

    if msg_type not in schema:
        return False  # Unknown message type

    required_fields = schema[msg_type]
    for field, expected_type in required_fields.items():
        if field not in data:
            return False
        if expected_type is not object and not isinstance(data.get(field), expected_type):
            return False

    return True


async def register_client(websocket: websockets.WebSocketServerProtocol, room_name: str) -> bool:
    """
    Handles the initial registration and validation of a new client.

    A client has 10 seconds to send a valid 'register' message. If registration is successful, the client's state is stored in the global dictionaries.

    Args:
        websocket: The new WebSocket connection.
        room_name: The room the client is attempting to join.

    Returns:
        True if registration was successful, False otherwise.
    """
    try:
        message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
        data = json.loads(message)

        if validate_schema(data) and data.get("type") == "register":
            user_id = data["user_id"]
            whitelist = data["whitelist"]

            if not user_id or user_id in USER_ID_MAP:
                await websocket.close(1008, "User ID is invalid or already in use.")
                return False

            client_info = {
                "user_id": user_id,
                "room_name": room_name,
                "whitelist": ["*"] if whitelist == ["*"] else set(whitelist)
            }
            CLIENTS[websocket] = client_info
            USER_ID_MAP[user_id] = websocket
            print(f"Client '{user_id}' registered in room '{room_name}'.")
            return True
        else:
            await websocket.close(1002, "Protocol error: First message must be a valid 'register' type.")
            return False

    except (asyncio.TimeoutError, json.JSONDecodeError, websockets.exceptions.ConnectionClosed):
        return False

async def unregister_client(websocket: websockets.WebSocketServerProtocol):
    """
    Removes a disconnected client's state from the server.

    Args:
        websocket: The WebSocket connection that has been closed.
    """
    client_info = CLIENTS.pop(websocket, None)
    if client_info and "user_id" in client_info:
        user_id = client_info["user_id"]
        USER_ID_MAP.pop(user_id, None)
        print(f"Client '{user_id}' unregistered and cleaned up.")


async def handle_direct_message(sender_ws: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
    """
    Processes and relays a direct message after performing security checks.

    A message is delivered only if all conditions are met:
    1. The client is online in the same room.
    2. The sender's user_id is present in the recipient's whitelist (or the recipient's whitelist is a wildcard "*").

    Args:
        sender_ws: The WebSocket connection of the message sender.
        data: The validated message data containing recipient and payload.
    """
    sender_info = CLIENTS[sender_ws]
    sender_id = sender_info["user_id"]
    recipient_id = data["recipient_id"]

    # This generic message prevent probing for user presence.
    generic_failure_msg = {
        "type": "error",
        "message": f"Could not deliver message to '{recipient_id}'. The user may be offline or has not whitelisted you."
    }

    recipient_ws = USER_ID_MAP.get(recipient_id)
    if not recipient_ws:
        await send_json(sender_ws, generic_failure_msg)
        return

    recipient_info = CLIENTS[recipient_ws]

    is_in_room = recipient_info["room_name"] == sender_info["room_name"]
    is_whitelisted = (recipient_info["whitelist"] == ["*"] or sender_id in recipient_info["whitelist"])

    if is_in_room and is_whitelisted:
        forward_message = {
            "type": "incoming_message",
            "sender_id": sender_id,
            "payload": data["payload"]
        }
        await send_json(recipient_ws, forward_message)
    else:
        await send_json(sender_ws, generic_failure_msg)


async def handle_whitelist_command(websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
    """
    Updates a client's whitelist by adding or removing a user.

    If a client with a wildcard ("*") whitelist adds a user, the whitelist
    is automatically converted to a specific list containing only that user.

    Args:
        websocket: The connection of the client updating their whitelist.
        data: The validated command data.
    """
    client_info = CLIENTS[websocket]
    user_to_modify = data["user_id"]
    command = data["type"]
    action_text = ""

    if command == "whitelist_add":
        if client_info["whitelist"] == ["*"]:
            client_info["whitelist"] = {user_to_modify}
            action_text = "converted from wildcard and added"
        else:
            client_info["whitelist"].add(user_to_modify)
            action_text = "added"
    
    elif command == "whitelist_remove":
        if client_info["whitelist"] == ["*"]:
            client_info["whitelist"] = {}
        else:
            client_info["whitelist"].discard(user_to_modify)
        action_text = "removed"
    
    current_list = list(client_info["whitelist"]) if isinstance(client_info["whitelist"], set) else client_info["whitelist"]
    await send_json(websocket, {
        "type": "whitelist_updated",
        "message": f"User '{user_to_modify}' was {action_text}.",
        "current_whitelist": current_list
    })


async def handle_whitelist_toggle(websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
    """
    Enables or disables a client's wildcard whitelist.

    - Enabling sets the whitelist to ["*"], accepting messages from everyone.
    - Disabling sets the whitelist to an empty set, accepting from no one.

    Args:
        websocket: The client's WebSocket connection.
        data: The validated command data containing the 'enabled' boolean.
    """
    client_info = CLIENTS[websocket]
    
    if data["enabled"]:
        client_info["whitelist"] = ["*"]
        status_text = "enabled (accepting from all in room)"
    else:
        client_info["whitelist"] = set()
        status_text = "disabled (accepting from no one)"

    current_list = client_info["whitelist"] if isinstance(client_info["whitelist"], list) else list(client_info["whitelist"])
    await send_json(websocket, {
        "type": "whitelist_updated",
        "message": f"Wildcard whitelist has been {status_text}.",
        "current_whitelist": current_list
    })


async def main_handler(websocket: websockets.WebSocketServerProtocol):
    """
    The main handler for each client connection.

    This function manages the lifecycle of a single client connection:
    1. Gets the name of the room.
    2. Regesters the client to the room's websocket.
    3. Listens to client's requests.
    4. Removes client on disconnection.
    """
    room_name = websocket.request.path.strip('/')
    if not room_name:
        await websocket.close(1008, "Room name must be provided in the URL path (e.g., /my-room).")
        return

    if not await register_client(websocket, room_name):
        return

    handler_map = {
        "message": handle_direct_message,
        "whitelist_add": handle_whitelist_command,
        "whitelist_remove": handle_whitelist_command,
        "whitelist_toggle_wildcard": handle_whitelist_toggle,
    }

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if not validate_schema(data):
                    # Silently ignore messages that don't conform to the schema.
                    # This prevents wasting resources on malformed requests.
                    continue
                
                handler_func = handler_map.get(data["type"])
                if handler_func:
                    await handler_func(websocket, data)

            except json.JSONDecodeError:
                # Ignore messages that are not valid JSON.
                continue
    
    finally:
        await unregister_client(websocket)


async def main():
    """Starts the WebSocket server."""
    port = int(os.environ.get("PORT", 8080))
    
    server_settings = {
        "host": "0.0.0.0",
        "port": port,
        "max_size": MAX_MESSAGE_SIZE
    }

    async with websockets.serve(main_handler, **server_settings):
        print(f"WebSocket server started on port {port}.")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutting down.")