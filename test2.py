
    # 7. Recording Logic
    async def start_recording():
        nonlocal egress_id
        try:
            gcs_credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
            if not gcs_bucket or not gcs_credentials_json:
                logger.warning("GCS configuration missing - skipping recording")
                return

            egress_info = await ctx.api.egress.start_room_composite_egress(
                api.RoomCompositeEgressRequest(
                    room_name=ctx.room.name,
                    audio_only=True,
                    file_outputs=[
                        api.EncodedFileOutput(
                            file_type=api.EncodedFileType.OGG,
                            filepath=f"calls/{ctx.room.name}.ogg",
                            gcp=api.GCPUpload(
                                bucket=gcs_bucket,
                                credentials=gcs_credentials_json,
                            ),
                        )
                    ],
                )
            )
            egress_id = egress_info.egress_id
            logger.info(f"Recording started: {egress_id}")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")

    async def stop_recording():
        """
        Stop the egress recording while the connection is still active.
        This runs BEFORE the main cleanup to ensure API is still available.
        """
        nonlocal egress_id
        if not egress_id:
            logger.warning("stop_recording called but egress_id is None - recording may not have started")
            return
        
        logger.info(f"Attempting to stop recording with egress_id: {egress_id}")
            
        try:
            # Fetch the current status first to avoid stopping a failed egress
            egress_info = await ctx.api.egress.list_egress(api.ListEgressRequest(egress_id=egress_id))
            if not egress_info or len(egress_info.items) == 0:
                logger.warning(f"No egress info found for egress_id: {egress_id}")
                return

            status = egress_info.items[0].status
            logger.info(f"Egress {egress_id} current status: {status}")
            
            # Only attempt to stop if it's active or starting
            if status in [api.EgressStatus.EGRESS_STARTING, api.EgressStatus.EGRESS_ACTIVE]:
                await ctx.api.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
                logger.info(f"Recording stopped successfully: {egress_id}")
            else:
                logger.warning(f"Egress {egress_id} is in state {status}, skipping stop request.")
                
        except Exception as e:
            logger.error(f"Error during egress cleanup for egress_id {egress_id}: {e}")
