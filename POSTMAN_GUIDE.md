# Postman Collection Guide

## 📦 Import the Collection

1. Open Postman
2. Click **Import** button (top left)
3. Select **File** tab
4. Choose `Island_AI_API.postman_collection.json`
5. Click **Import**

## 🔧 Configure Base URL

The collection uses a variable `{{base_url}}` which is set to `http://localhost:8000` by default.

### To Change the Base URL:

1. Click on the collection name "Island AI API Collection"
2. Go to **Variables** tab
3. Change the `base_url` value (e.g., `http://your-server:8000`)
4. Click **Save**

## 📚 Collection Structure

The collection is organized into folders:

### 1. **Health & Info** (2 endpoints)
- Root endpoint - Get API information
- Health check

### 2. **RAG Service** (7 endpoints)
- Chat with RAG
- Create Collection
- Delete Collection
- Data Ingestion (URL, PDF, Excel)
- Get Conversation History

### 3. **Calls** (6 endpoints)
- Basic outbound call
- Call with custom AI instructions
- Call in Spanish (multilingual example)
- **Outbound call with escalation** - Basic
- **Outbound call with escalation** - Customer Support
- **Outbound call with escalation** - Sales Follow-up

### 4. **LLM Service** (1 endpoint)
- Elaborate Prompt

### 5. **SMS** (2 endpoints)
- Send SMS
- Send appointment reminder SMS

### 6. **Email** (2 endpoints)
- Send plain text email
- Send HTML email

### 7. **Bulk Communication** (6 endpoints)
- Single contact - all channels (call + SMS + email)
- Single contact - call only
- Single contact - SMS & email only
- Multiple contacts - all channels
- Multiple contacts - email newsletter
- Multiple contacts - SMS campaign

## 🚀 Quick Start

### Test the API:

1. **Check if API is running:**
   - Open `Health & Info` → `Health Check`
   - Click **Send**
   - You should see: `"status": "healthy"`

2. **Make your first call:**
   - Open `Calls` → `Outbound Call - Basic`
   - Update the `phone_number` in the body
   - Click **Send**

3. **Try outbound call with escalation:**
   - First, ensure `outbound.py` agent worker is running
   - Open `Calls` → `Outbound Call with Escalation - Basic`
   - Update the `phone_number` in the body
   - Click **Send**
   - During the call, say "I want to speak to a supervisor" to test escalation

4. **Send bulk communications:**
   - Open `Bulk Communication` → `Single Contact - All Channels`
   - Update contact details
   - Update SMS and email body
   - Click **Send**

## 💡 Tips

### 1. **Environment Variables**
Create a Postman environment for different setups (dev, staging, production):
- Click **Environments** (left sidebar)
- Click **+** to create new environment
- Add variables: `base_url`, `api_key`, etc.

### 2. **Save Responses**
Right-click on any request → **Save Response** → **Save as example**
This helps document expected responses.

### 3. **Test Scripts**
Add test scripts to validate responses:
```javascript
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

pm.test("Response has status field", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('status');
});
```

### 4. **Pre-request Scripts**
Use pre-request scripts for dynamic data:
```javascript
// Generate random phone number
pm.variables.set("phone", "+1" + Math.floor(Math.random() * 9000000000 + 1000000000));

// Set current timestamp
pm.variables.set("timestamp", new Date().toISOString());
```

## 📝 Modify Request Examples

### Update Phone Numbers:
Search for `+1234567890` in the collection and replace with your test number.

### Update Email Addresses:
Search for `example@example.com` and replace with your test email.

### Update Contact Details:
Each request has placeholder data. Update it according to your needs.

## 🔐 Authentication (If Needed)

If you add authentication to your API later, you can:

1. **API Key Authentication:**
   - Edit collection → **Authorization** tab
   - Select type: **API Key**
   - Add key name and value

2. **Bearer Token:**
   - Select type: **Bearer Token**
   - Add token value

3. **OAuth 2.0:**
   - Select type: **OAuth 2.0**
   - Configure OAuth settings

All requests in the collection will inherit this authentication.

## ⚙️ Outbound Call with Escalation Setup

The new escalation endpoints require additional setup:

### Required Environment Variables:
```properties
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
LIVEKIT_URL=wss://your-server.livekit.cloud
LIVEKIT_SIP_OUTBOUND_TRUNK=ST_vEtSehKXAp4d
LIVEKIT_SUPERVISOR_PHONE_NUMBER=+919911062767
```

### Before Testing:
1. **Start the agent worker:**
   ```bash
   python outbound.py
   ```
   This must be running for escalation to work.

2. **Verify supervisor phone number:**
   - Set `LIVEKIT_SUPERVISOR_PHONE_NUMBER` in `.env`
   - Use E.164 format: `+[country code][number]`

3. **Test the flow:**
   - Agent calls customer
   - Customer says "I want to speak to a supervisor"
   - Agent puts customer on hold (with music 🎵)
   - Agent calls supervisor and explains situation
   - Supervisor says "ready" or "connect me"
   - Calls are merged, agent disconnects

### Endpoints Available:
- **Basic** - Simple test with minimal configuration
- **Customer Support** - Pre-configured support scenario
- **Sales Follow-up** - Pre-configured sales scenario

## 🐛 Troubleshooting

### Connection Refused Error:
- Make sure the API server is running
- Check if `base_url` matches your server address
- Verify the port number (default: 8000)

### 400 Bad Request:
- Check request body format
- Ensure required fields are provided
- Validate phone number format (must start with +)
- Validate email format

### 500 Internal Server Error:
- Check API logs
- Verify environment variables are set (.env file)
- Ensure Twilio credentials are configured (for SMS)
- Ensure SMTP credentials are configured (for email)

### Escalation Endpoint Errors:

**"LiveKit credentials not configured":**
- Ensure `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_URL`, and `LIVEKIT_SIP_OUTBOUND_TRUNK` are set

**"Escalation will fail if requested":**
- Set `LIVEKIT_SUPERVISOR_PHONE_NUMBER` in `.env`
- Warning only - call will work but escalation won't be available

**"Agent not responding":**
- Make sure `python outbound.py` is running before initiating calls
- Check agent logs for errors

**"Call doesn't connect":**
- Verify SIP trunk ID is correct
- Check phone number format (E.164)
- Ensure LiveKit URL is accessible

## 📊 Collection Runner

To test multiple requests:

1. Click **Runner** button (bottom right)
2. Select "Island AI API Collection"
3. Select which requests to run
4. Set iterations and delay
5. Click **Run Island AI API Collection**

This is useful for:
- Testing all endpoints at once
- Load testing
- Regression testing

## 🎯 Best Practices

1. **Use Variables** - Don't hardcode values
2. **Add Tests** - Validate responses automatically
3. **Document** - Add descriptions to requests
4. **Organize** - Keep requests in logical folders
5. **Version Control** - Commit collection to git
6. **Share** - Export and share with team members

## 📤 Exporting

To share the collection:

1. Right-click on collection name
2. Click **Export**
3. Choose **Collection v2.1** (recommended)
4. Save the JSON file
5. Share with team or commit to repository

---

Happy testing! 🎉
