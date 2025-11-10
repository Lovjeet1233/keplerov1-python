import asyncio

from livekit import api
from livekit.protocol.models import ListUpdate


async def main():
    livekit_api = api.LiveKitAPI()
    
    # To update specific trunk fields, use the update_sip_inbound_trunk_fields method.
    trunk = await livekit_api.sip.update_sip_inbound_trunk_fields(
        trunk_id="ST_bpkhY3edJzk4",
        numbers=ListUpdate(add=['+14789002879']),         # Add to existing list
        # allowed_numbers=["+13105550100", "+17145550100"], # Replace existing list
        name="iitroorkee3",
    )
    
    print(f"Successfully updated trunk {trunk}")

    await livekit_api.aclose()


if __name__ == "__main__":
    asyncio.run(main())

