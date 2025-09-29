# Just Communicate Relay Server

This is the WebSocket relay server that the **Just Communicate** library uses, designed for the **Figura** Minecraft mod.

This repo is setup so you can host your own relay servers for communications between avatars, if/when the one im hosting goes down, or you would rather host your own

### Key Features
- **Server-Based Communication**: Clients connect to "rooms", which are different servers, so users cannot on different servers cannot communicate.
- **Secure Whitelisting**: Communication is based on an whitelist system, where a client can only receive messages from users on their whitelist. There is also an option for a wildcard (*) allowing messages from any user.
- **Direct Messaging**: Messages are sent directly to specific users using their minecraft userid.

---

## How to Use This Server

### 1. Requirements
- Python 3.8 or newer.
- The `websockets` Python library.

### 2. Running Locally for Testing
A local server is perfect for developing and testing your library.

**Step 1: Install the library**
Clone the repo and run
```bash
pip install requirements.txt
```

**Step 2: Run the server**
Navigate to the directory containing the main.py file and run:
```
python main.py
```

---

## Deploying to the Web (e.g., Render)
For your library to be used by others, the server needs to be publicly accessible. Render is where i have initially tried hosting this server, and here is how i set it up.
**1. Push to GitHub:**
Upload the main.py file and a requirements.txt file to a new GitHub repository.

**2. Deploy on Render:**
- Create a new "Web Service" on Render and connect your GitHub repository.
- Set the Build Command to: pip install -r requirements.txt
- Set the Start Command to: python app.py

Render will automatically build and deploy your server, providing you with a public URL (e.g., https://{your_server_name_here}.onrender.com).

---

## Communication Protocol Tutorial
Your Just Communicate library will need to follow this protocol to interact with the server.

### Connecting
A client connects to the server using a WebSocket URL. The path of the URL defines the room they are joining.
For Just Communicate, the room_name should be the IP address of the Minecraft server.

Local URL: ws://localhost:8080/{minecraft_server_ip}

Deployed URL: wss:{your_server_name_here}.onrender.com/{minecraft_server_ip}

### Message Formats
All communication is done via JSON strings. Each message must have a "type" field that defines its purpose.

#### Client to Server Messages
---
**1. Register a Client (register)**

Sent once, immediately after connecting.

`user_id`: The clients's Minecraft UUID.

`whitelist`: An array of UUIDs the client will accept messages from. Use ["*"] to accept from everyone in the room.
```JSON
{
  "type": "register",
  "user_id": "6d629d34-fc89-4506-bd68-1637b2aec196",
  "whitelist": ["9dc21885-3fb9-46b3-8979-0778e88657bc"]
}
```
---
**2. Send a Message (message)**

Sends a JSON payload to another user.

`recipient_id`: The Minecraft UUID of the user you want to send the message to.

`payload`: Any valid JSON object. This is where the data you send goes.
```JSON
{
  "type": "message",
  "recipient_id": "9dc21885-3fb9-46b3-8979-0778e88657bc",
  "payload": {
    "action": "wave",
    "coordinates": {"x": 100, "y": 64, "z": -50}
  }
}
```
---
**3. Add to Whitelist (whitelist_add)**

Adds a user's UUID to your whitelist.

`user_id`: The player's Minecraft UUID.
```JSON
{
  "type": "whitelist_add",
  "user_id": "9dc21885-3fb9-46b3-8979-0778e88657bc"
}
```
---
**4. Remove from Whitelist (whitelist_remove)**

Removes a user's UUID from your whitelist.

`user_id`: The player's Minecraft UUID.
```JSON
{
  "type": "whitelist_remove",
  "user_id": "9dc21885-3fb9-46b3-8979-0778e88657bc"
}
```
---
**5. Toggle Wildcard Whitelist (whitelist_toggle_wildcard)**

Turns the wildcard (*) mode on or off.

`enabled`: `true`: Accept messages from everyone in the room.

`enabled`: `false`: Accept messages from no one (an empty whitelist).
```JSON
{
  "type": "whitelist_toggle_wildcard",
  "enabled": true
}
```
---
#### Server to Client Messages
---
**1. Incoming Message (incoming_message)**

This is what a client receives when another user sends them a message.
```JSON
{
  "type": "incoming_message",
  "sender_id": "6d629d34-fc89-4506-bd68-1637b2aec196",
  "payload": {
    "action": "wave",
    "coordinates": {"x": 100, "y": 64, "z": -50}
  }
}
```
---
**2. Whitelist Updated (whitelist_updated)**

A confirmation sent after a whitelist command is successfully processed.
```JSON
{
  "type": "whitelist_updated",
  "message": "User '9dc21885-3fb9-46b3-8979-0778e88657bc' was added.",
  "current_whitelist": ["9dc21885-3fb9-46b3-8979-0778e88657bc", "6d629d34-fc89-4506-bd68-1637b2aec196"]
}
```
---
**3. Error Message (error)**

Sent when an action fails. The message is intentionally generic for security.
```JSON
{
  "type": "error",
  "message": "Could not deliver message to '...'. The user may be offline or has not whitelisted you."
}
```
