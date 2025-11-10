import asyncio
from services.call_service import make_outbound_call

if __name__ == "__main__":
    print(" Incruiter - Outbound Call Initiator")
    print("=" * 50)
    phone_number = input("Enter the mobile number to call (with country code, e.g. +1234567890): ")
    asyncio.run(make_outbound_call(phone_number))