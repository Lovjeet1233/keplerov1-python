# Bulk Communication Endpoint Examples

The bulk communication endpoint allows you to send calls, SMS, and emails to one or multiple contacts in a single request.

**Endpoint:** `POST /bulk-communication/send`

## Features

- ✅ Process single or multiple contacts
- ✅ Select communication types: `call`, `sms`, `email`
- ✅ Get comprehensive response with transcript, statuses, and timestamps
- ✅ Calls are made first, then SMS and email follow
- ✅ Graceful error handling for each communication channel

---

## Example 1: Call + SMS + Email to Single Contact

```json
{
  "contacts": [
    {
      "name": "Amar",
      "email": "amarc8399@gmail.com",
      "phone": "+919911062767"
    }
  ],
  "communication_types": ["call", "sms", "email"],
  "sms_body": {
    "message": "Hi Amar, thanks for connecting with us! We just called you."
  },
  "email_body": {
    "subject": "Follow-up from our call",
    "body": "Hi Amar,\n\nThank you for taking our call. We appreciate your time.\n\nBest regards,\nYour Team",
    "is_html": false
  },
  "dynamic_instruction": "You are a friendly sales representative calling to follow up on a product inquiry.",
  "language": "en",
  "emotion": "Calm"
}
```

## Example 2: Only Call (No SMS or Email)

```json
{
  "contacts": [
    {
      "name": "John Doe",
      "phone": "+1234567890"
    }
  ],
  "communication_types": ["call"],
  "dynamic_instruction": "You are calling to schedule an appointment.",
  "language": "en",
  "emotion": "Professional"
}
```

## Example 3: Only SMS and Email (No Call)

```json
{
  "contacts": [
    {
      "name": "Jane Smith",
      "email": "jane@example.com",
      "phone": "+1234567890"
    }
  ],
  "communication_types": ["sms", "email"],
  "sms_body": {
    "message": "Your appointment is confirmed for tomorrow at 10 AM."
  },
  "email_body": {
    "subject": "Appointment Confirmation",
    "body": "<h1>Appointment Confirmed</h1><p>Your appointment is scheduled for tomorrow at 10 AM.</p>",
    "is_html": true
  }
}
```

## Example 4: Multiple Contacts

```json
{
  "contacts": [
    {
      "name": "Alice",
      "email": "alice@example.com",
      "phone": "+1234567890"
    },
    {
      "name": "Bob",
      "email": "bob@example.com",
      "phone": "+0987654321"
    },
    {
      "name": "Charlie",
      "email": "charlie@example.com",
      "phone": "+1122334455"
    }
  ],
  "communication_types": ["call", "email"],
  "email_body": {
    "subject": "Important Update",
    "body": "We have an important update to share with you.",
    "is_html": false
  },
  "dynamic_instruction": "You are calling to inform about an important company update.",
  "language": "en",
  "emotion": "Serious"
}
```

## Example 5: Only Email to Multiple Contacts

```json
{
  "contacts": [
    {
      "name": "Customer 1",
      "email": "customer1@example.com"
    },
    {
      "name": "Customer 2",
      "email": "customer2@example.com"
    },
    {
      "name": "Customer 3",
      "email": "customer3@example.com"
    }
  ],
  "communication_types": ["email"],
  "email_body": {
    "subject": "Newsletter - November 2025",
    "body": "<html><body><h1>Monthly Newsletter</h1><p>Check out our latest updates!</p></body></html>",
    "is_html": true
  }
}
```

---

## Response Format

The endpoint returns a detailed response for each contact:

```json
{
  "status": "success",
  "message": "Processed 1 contact(s) successfully",
  "total_contacts": 1,
  "results": [
    {
      "name": "Amar",
      "email": "amarc8399@gmail.com",
      "phone": "+919911062767",
      "call_status": "success",
      "transcript": {
        "conversation": [...],
        "duration": "120s",
        "sentiment": "positive"
      },
      "sms_status": "success",
      "email_status": "success",
      "created_at": "2025-11-10T13:42:00.405657",
      "ended_at": "2025-11-10T13:44:15.490852",
      "errors": null
    }
  ]
}
```

### Response Fields

- **call_status**: `success`, `failed`, or `skipped`
- **transcript**: Full conversation transcript (if call was made)
- **sms_status**: `success`, `failed`, or `skipped`
- **email_status**: `success`, `failed`, or `skipped`
- **created_at**: Timestamp when processing started
- **ended_at**: Timestamp when processing completed
- **errors**: Object containing error messages for failed communications

---

## Important Notes

1. **Required Fields**:
   - If `"sms"` is in `communication_types`, you **must** provide `sms_body`
   - If `"email"` is in `communication_types`, you **must** provide `email_body`
   - If `"call"` is in `communication_types`, contact must have a `phone` number

2. **Optional Contact Fields**:
   - `email` is optional if you're not sending emails
   - `phone` is optional if you're not making calls or sending SMS

3. **Call Parameters** (optional):
   - `dynamic_instruction`: Custom instructions for the AI agent
   - `language`: TTS language (default: "en")
   - `emotion`: TTS emotion (default: "Calm")

4. **Processing Order**:
   - Calls are made **first** (if selected)
   - Then SMS is sent (if selected)
   - Finally, email is sent (if selected)

5. **Error Handling**:
   - If one communication channel fails, others will still be attempted
   - Errors are captured in the `errors` field of each contact result

