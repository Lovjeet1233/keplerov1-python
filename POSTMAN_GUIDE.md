# Island AI API - Postman Collection Guide

## 📦 Files Included

1. **ISLAND_AI_API.postman_collection.json** - Complete API collection with all endpoints
2. **ISLAND_AI_API.postman_environment.json** - Environment variables for local development

## 🚀 Getting Started

### Step 1: Import Collection

1. Open Postman
2. Click **Import** button (top left)
3. Drag and drop `ISLAND_AI_API.postman_collection.json` or click to browse
4. Click **Import**

### Step 2: Import Environment

1. Click the **Environments** tab (left sidebar)
2. Click **Import**
3. Select `ISLAND_AI_API.postman_environment.json`
4. Click **Import**

### Step 3: Select Environment

1. In the top-right corner, click the environment dropdown
2. Select **ISLAND AI - Local**

### Step 4: Start Your API Server

Make sure your FastAPI server is running:

```bash
python api.py
```

Or with uvicorn:

```bash
uvicorn api:app --host localhost --port 8000 --reload
```

## 📚 API Endpoints Overview

### 1. General Endpoints
- **GET /** - API information and available endpoints
- **GET /health** - Health check for all services

### 2. RAG Service (`/rag`)
- **POST /rag/chat** - Chat with RAG system
- **POST /rag/data_ingestion** - Ingest data from sources
- **POST /rag/create_collection** - Create new collection
- **POST /rag/delete_collection** - Delete collection
- **GET /rag/conversation_history/{thread_id}** - Get conversation history

### 3. Calls Service (`/calls`)
- **POST /calls/outbound** - Initiate outbound call

### 4. LLM Service (`/llm`)
- **POST /llm/elaborate_prompt** - Elaborate and enhance prompts

### 5. SMS Service (`/sms`)
- **POST /sms/send** - Send SMS via Twilio

### 6. Email Service (`/email`)
- **POST /email/send** - Send plain text or HTML email

## 🔧 Configuration

### Environment Variables

The collection uses the following environment variable:
- `base_url` - Base URL for the API (default: `http://localhost:8000`)

To change the base URL:
1. Go to Environments
2. Select **ISLAND AI - Local**
3. Edit the `base_url` value
4. Save changes

### Creating Additional Environments

You can create separate environments for different stages:

#### Production Environment
```json
{
    "base_url": "https://api.yourdomain.com",
    "api_host": "api.yourdomain.com",
    "api_port": "443"
}
```

#### Staging Environment
```json
{
    "base_url": "https://staging-api.yourdomain.com",
    "api_host": "staging-api.yourdomain.com",
    "api_port": "443"
}
```

## 📝 Usage Examples

### Example 1: Send Email

1. Navigate to **Email Service** → **Send Email**
2. Make sure your `.env` file has:
   ```
   EMAIL_ADDRESS=your-email@gmail.com
   EMAIL_PASSWORD=your-app-password
   ```
3. Update the request body:
   ```json
   {
       "receiver_email": "recipient@example.com",
       "subject": "Test Email",
       "body": "Hello from Island AI!",
       "is_html": false
   }
   ```
4. Click **Send**

### Example 2: Send SMS

1. Navigate to **SMS Service** → **Send SMS**
2. Make sure your `.env` file has:
   ```
   TWILIO_ACCOUNT_SID=your-account-sid
   TWILIO_AUTH_TOKEN=your-auth-token
   TWILIO_NUMBER=your-twilio-number
   ```
3. Update the request body:
   ```json
   {
       "body": "Test SMS from Island AI",
       "number": "+1234567890"
   }
   ```
4. Click **Send**

### Example 3: Chat with RAG

1. Navigate to **RAG Service** → **Chat with RAG**
2. Update the request body with your query and collection:
   ```json
   {
       "query": "What is machine learning?",
       "collection_name": "ai_knowledge",
       "top_k": 5,
       "thread_id": "user-123"
   }
   ```
3. Click **Send**

## 🔑 Required Credentials

Make sure your `.env` file contains all necessary credentials:

```env
# OpenAI
OPENAI_API_KEY=your-openai-key

# Qdrant
QDRANT_URL=your-qdrant-url
QDRANT_API_KEY=your-qdrant-key

# MongoDB
MONGODB_URI=your-mongodb-uri

# Email (Gmail)
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-password

# Twilio SMS
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_NUMBER=your-twilio-number

# API Configuration
API_HOST=localhost
API_PORT=8000
```

## 🧪 Testing Tips

1. **Start with Health Check**: Always begin by testing the `/health` endpoint to ensure all services are operational

2. **Check API Info**: Use the root `/` endpoint to see all available endpoints and their documentation

3. **Use Postman Collections Runner**: 
   - Select the collection
   - Click **Run** to test multiple endpoints sequentially
   - Great for integration testing

4. **Save Responses**: Click **Save Response** to create example responses for documentation

5. **Use Variables**: Store frequently used values as environment variables for easy reuse

## 🐛 Troubleshooting

### Connection Refused
- Ensure your API server is running
- Check that `base_url` matches your server configuration

### 500 Internal Server Error
- Check your `.env` file has all required credentials
- Review server logs for detailed error messages

### 400 Bad Request
- Verify request body format matches the schema
- Check that all required fields are provided

### Email Not Sending
- For Gmail, enable 2FA and generate an App Password
- Don't use your regular Gmail password

### SMS Not Sending
- Verify phone number format (must start with `+` and country code)
- Check Twilio account balance and number verification

## 📖 Additional Resources

- **FastAPI Docs**: Visit `http://localhost:8000/docs` for interactive API documentation
- **ReDoc**: Visit `http://localhost:8000/redoc` for alternative API documentation
- **Postman Documentation**: [https://learning.postman.com/](https://learning.postman.com/)

## 💡 Pro Tips

1. **Use Pre-request Scripts**: Add authentication tokens or dynamic values before sending requests

2. **Create Tests**: Add test scripts to validate responses automatically
   ```javascript
   pm.test("Status code is 200", function () {
       pm.response.to.have.status(200);
   });
   ```

3. **Monitor APIs**: Use Postman Monitors to schedule collection runs and track API health

4. **Share with Team**: Export and share collections with your team for consistent testing

5. **Version Control**: Keep your Postman collections in Git for version tracking

---

**Happy Testing! 🚀**

For issues or questions, refer to the API documentation at `/docs` when the server is running.

