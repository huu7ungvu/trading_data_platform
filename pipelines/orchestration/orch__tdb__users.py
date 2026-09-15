import prefect

@prefect.task(name="tdb_users", description="Orchestration for tdb_users pipeline")
def orch__tdb__users():
    from side_prj.trading_data_platform.pipelines.ingestion.ingest__tdb import run_cdc_export

    logger = prefect.get_run_logger()
    logger.info("Starting tdb_users orchestration task...")

    # Define your parameters
    slot_name = "cdc_users_slot"
    bucket = "landing"
    prefix = "tdb/users"

    # Run the CDC export
    result = run_cdc_export(slot_name=slot_name, bucket=bucket, prefix=prefix)

    if result:
        logger.info(f"Exported: {result}")
    else:
        logger.info("Nothing to export.")