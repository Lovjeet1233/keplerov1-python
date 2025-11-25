import asyncio
from twilio.rest import Client
from livekit import api
from dotenv import load_dotenv
import os
import uuid
from datetime import datetime

load_dotenv()


LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_SIP_DOMAIN = os.getenv("LIVEKIT_SIP_URL")  # e.g., 64cb0p5o65e.sip.livekit.cloud


async def create_twilio_sip_trunk(
    account_sid: str,
    auth_token: str,
    friendly_name: str = "MyOutboundTrunk",
    username: str = "agent_user",
    password: str = "StrongPass123"
):
    print("Logging into Twilio...")
    twilio_client = Client(account_sid, auth_token)

    print("Creating SIP Trunk...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_trunk_name = f"{friendly_name}_{timestamp}"
    
    # Create trunk with secure trunking enabled
    sip_trunk = twilio_client.trunking.v1.trunks.create(
        friendly_name=unique_trunk_name,
        secure=False,  # Set to False for compatibility with LiveKit
    )
    print(f"✔ Twilio SIP Trunk SID: {sip_trunk.sid}")
    trunk_domain = f"{sip_trunk.sid.lower()}.pstn.twilio.com"
    print(f"✔ Trunk Domain (Termination URI): {trunk_domain}")
    
    # IMPORTANT: Update trunk to set the geographic location (Active Configuration)
    # Also configure call transfer settings
    print("Setting trunk geographic location to US1 and configuring call transfer...")
    updated_trunk = twilio_client.trunking.v1.trunks(sip_trunk.sid).update(
        domain_name=trunk_domain,
        disaster_recovery_method="POST",
        disaster_recovery_url="",
        friendly_name=unique_trunk_name,
        secure=False,
        cnam_lookup_enabled=False,
        transfer_mode="enable-all",  # Enable all transfer modes (SIP REFER and PSTN)
        transfer_caller_id="from-transferor"  # Set caller ID as transferor for transfer target
    )
    print(f"✔ Trunk configured for US1 region")
    print(f"✔ Call Transfer (SIP REFER): Enabled")
    print(f"✔ Caller ID for Transfer Target: Set as Transferor")
    print(f"✔ Enable PSTN Transfer: Enabled")

    print("Creating Credential List...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    credential_list_name = f"{friendly_name}_CredList_{timestamp}_{unique_id}"
    
    credential_list = twilio_client.sip.credential_lists.create(
        friendly_name=credential_list_name
    )
    print(f"✔ Credential List SID: {credential_list.sid}")

    print("Adding Credential Username/Password...")
    credential = twilio_client.sip.credential_lists(credential_list.sid).credentials.create(
        username=username,
        password=password
    )
    print(f"✔ Credential SID: {credential.sid}")

    print("Attaching Credential List to Trunk...")
    twilio_client.trunking.v1.trunks(sip_trunk.sid).credentials_lists.create(
        credential_list_sid=credential_list.sid
    )

    # CRITICAL FIX 1: Add IP Access Control List to allow LiveKit's IPs
    print("Creating IP Access Control List...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    ip_acl_name = f"{friendly_name}_IPACL_{timestamp}_{unique_id}"
    
    ip_access_control_list = twilio_client.sip.ip_access_control_lists.create(
        friendly_name=ip_acl_name
    )
    print(f"✔ IP Access Control List SID: {ip_access_control_list.sid}")

    # Add LiveKit's IP addresses (you'll need to get these from LiveKit)
    # For LiveKit Cloud, these are the common outbound IPs
    # Check LiveKit documentation or contact support for exact IPs
    livekit_ips = [
        "0.0.0.0/0"  # WARNING: This allows all IPs - use specific IPs in production!
    ]
    
    print("Adding IP addresses to ACL...")
    for ip_addr in livekit_ips:
        try:
            ip_entry = twilio_client.sip.ip_access_control_lists(
                ip_access_control_list.sid
            ).ip_addresses.create(
                friendly_name=f"LiveKit_{ip_addr.replace('/', '_')}",
                ip_address=ip_addr
            )
            print(f"✔ Added IP: {ip_addr}")
        except Exception as e:
            print(f"⚠ Warning adding IP {ip_addr}: {e}")

    print("Attaching IP ACL to Trunk...")
    twilio_client.trunking.v1.trunks(sip_trunk.sid).ip_access_control_lists.create(
        ip_access_control_list_sid=ip_access_control_list.sid
    )
    print(f"✔ IP ACL attached to trunk")

    # Get the trunk details to show the Termination SIP URI
    trunk_details = twilio_client.trunking.v1.trunks(sip_trunk.sid).fetch()
    termination_uri = f"{trunk_details.sid.lower()}.pstn.twilio.com"
    print(f"✔ Termination SIP URI: {termination_uri}")
    print(f"   (This is what LiveKit will connect to)")

    # CRITICAL FIX 2: Add Origination URI (for INBOUND calls if needed)
    print("Adding Origination URI...")
    
    # Use LIVEKIT_SIP_DOMAIN from .env if available, otherwise derive from LIVEKIT_URL
    if LIVEKIT_SIP_DOMAIN:
        # Check if it already starts with "sip:"
        if LIVEKIT_SIP_DOMAIN.startswith("sip:"):
            origination_url = LIVEKIT_SIP_DOMAIN
            sip_domain = LIVEKIT_SIP_DOMAIN.replace("sip:", "")
        else:
            sip_domain = LIVEKIT_SIP_DOMAIN
            origination_url = f"sip:{sip_domain}"
        print(f"Using SIP domain from .env: {LIVEKIT_SIP_DOMAIN}")
    else:
        # Fallback: Extract from LIVEKIT_URL
        # Example: wss://incruiter-kcxtv094.livekit.cloud -> incruiter-kcxtv094.sip.livekit.cloud
        livekit_domain = LIVEKIT_URL.replace("wss://", "").replace("https://", "").replace("ws://", "").replace("http://", "")
        livekit_domain = livekit_domain.split(":")[0]  # Remove port if present
        
        if "livekit.cloud" in livekit_domain:
            project_name = livekit_domain.split(".livekit.cloud")[0]
            sip_domain = f"{project_name}.sip.livekit.cloud"
        else:
            sip_domain = livekit_domain
        origination_url = f"sip:{sip_domain}"
        print(f"Derived SIP domain from LIVEKIT_URL: {sip_domain}")
    
    print(f"Final Origination URL: {origination_url}")
    
    try:
        origination_uri = twilio_client.trunking.v1.trunks(sip_trunk.sid).origination_urls.create(
            weight=1,
            priority=1,
            enabled=True,
            friendly_name=f"{friendly_name}_LiveKit_URI",
            sip_url=origination_url
        )
        print(f"✔ Origination URI added: {origination_url}")
        print(f"✔ Origination URI SID: {origination_uri.sid}")
    except Exception as e:
        print(f"⚠ Error adding Origination URI: {e}")
        origination_uri = None

    print("✔ Twilio SIP Trunk is fully configured")
    print("")
    print("=" * 70)
    print("⚠ IMPORTANT: For outbound calls")
    print("=" * 70)
    print("1. Make sure you have a Twilio phone number purchased")
    print("2. The number must be active in your Twilio account")
    print("3. Use this Termination URI in LiveKit:")
    print(f"   {termination_uri}")
    print("=" * 70)

    return {
        "trunk_sid": sip_trunk.sid,
        "trunk_name": unique_trunk_name,
        "termination_uri": termination_uri,
        "credential_list_sid": credential_list.sid,
        "credential_list_name": credential_list_name,
        "ip_acl_sid": ip_access_control_list.sid,
        "username": username,
        "password": password,
        "origination_uri": origination_url if origination_uri else None,
        "origination_uri_sid": origination_uri.sid if origination_uri else None,
    }


async def create_livekit_trunk(
    twilio_trunk_sid: str,
    username: str,
    password: str,
    phone_number: str,
    trunk_name: str = "Outbound-Trunk"
):
    print("Creating LiveKit SIP Trunk...")

    lk = api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET
    )

    from livekit.protocol import sip
    
    trunk_info = sip.SIPOutboundTrunkInfo()
    trunk_info.name = trunk_name
    trunk_info.metadata = f'{{"provider":"twilio","trunk_sid":"{twilio_trunk_sid}"}}'
    trunk_info.address = f"{twilio_trunk_sid}.pstn.twilio.com"
    trunk_info.auth_username = username
    trunk_info.auth_password = password
    trunk_info.numbers.append(phone_number)
    
    request = sip.CreateSIPOutboundTrunkRequest()
    request.trunk.CopyFrom(trunk_info)
    
    trunk = await lk.sip.create_outbound_trunk(request)

    await lk.aclose()
    print(f"✔ LiveKit SIP Trunk Created: {trunk.sip_trunk_id}")
    print(f"   Phone Numbers: {', '.join(trunk_info.numbers)}")
    return trunk.sip_trunk_id




async def create_livekit_trunk_from_address(
    sip_address: str,
    username: str,
    password: str,
    phone_number: str,
    trunk_name: str = "Outbound-Trunk"
):
    """
    Create a LiveKit SIP trunk from an existing Twilio SIP address.
    Use this when you already have a Twilio trunk configured.
    
    Args:
        sip_address: Twilio SIP address (e.g., example.pstn.twilio.com)
        username: SIP username for authentication
        password: SIP password for authentication
        phone_number: Phone number associated with the trunk
        trunk_name: Name for the LiveKit trunk
    
    Returns:
        str: LiveKit trunk ID
    """
    print("Creating LiveKit SIP Trunk from existing Twilio address...")
    
    lk = api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET
    )
    
    from livekit.protocol import sip
    
    # Create the trunk info object
    trunk_info = sip.SIPOutboundTrunkInfo()
    trunk_info.name = trunk_name
    trunk_info.metadata = f'{{"provider":"twilio","address":"{sip_address}"}}'
    trunk_info.address = sip_address
    trunk_info.auth_username = username
    trunk_info.auth_password = password
    # Add phone number(s) to the trunk
    trunk_info.numbers.append(phone_number)
    
    # Create the request with the trunk info
    request = sip.CreateSIPOutboundTrunkRequest()
    request.trunk.CopyFrom(trunk_info)
    
    # Create the trunk
    trunk = await lk.sip.create_outbound_trunk(request)
    
    await lk.aclose()
    print(f"✔ LiveKit SIP Trunk Created: {trunk.sip_trunk_id}")
    print(f"   SIP Address: {sip_address}")
    print(f"   Phone Numbers: {', '.join(trunk_info.numbers)}")
    return trunk.sip_trunk_id


async def main():
    print("==== TWILIO CREDENTIAL INPUT ====")
    account_sid = input("Enter Twilio ACCOUNT SID: ").strip()
    auth_token = input("Enter Twilio AUTH TOKEN: ").strip()
    phone_number = input("Enter Phone Number (e.g., +1234567890): ").strip()

    # Step 1 — Create Twilio Trunk
    twilio_data = await create_twilio_sip_trunk(
        account_sid=account_sid,
        auth_token=auth_token,
        friendly_name="OutboundTrunkDemo",
        username="my_agent",
        password="Password@123"
    )

    # Step 2 — Create LiveKit Trunk
    trunk_id = await create_livekit_trunk(
        twilio_trunk_sid=twilio_data["trunk_sid"],
        username=twilio_data["username"],
        password=twilio_data["password"],
        phone_number=phone_number
    )

    print("\n==== FINAL RESULTS ====")
    print("Twilio Trunk SID:", twilio_data["trunk_sid"])
    print("LiveKit Trunk ID:", trunk_id)


if __name__ == "__main__":
    asyncio.run(main())
