import prefect
from prefect import task, flow

 
@prefect.task(name="tdb_users", description="Orchestration for tdb_users pipeline")
def orch__tdb__users():
    from pipelines.ingestion.ingest__tdb import run_cdc_export

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
               
@task(name="tdb_users_backfill", description="Backfill for tdb_users pipeline", retries=3, retry_delay_seconds=5)
def task_run_backfill():
    from pipelines.ingestion.ingest__tdb import back_fill_data

    logger = prefect.get_run_logger()
    logger.info("Starting tdb_users backfill task...")

    # Define your parameters
    bucket = "landing"
    prefix = "tdb"
    schema_name = "test"
    table_name = "users"    
    max_changes = 1000    

    # Run the backfill
    back_fill_data(bucket=bucket, prefix=prefix, schema_name=schema_name, table_name=table_name, max_changes=max_changes)
    
    
@flow(name="tdb_users_backfill_flow", description="Flow to orchestrate tdb_users backfill")
def flow_run_backfill():
    task_run_backfill()
    
if __name__ == "__main__":
    # Test: Try scheduling the task to run daily at 11:05 AM.
    flow_run_backfill.serve(
        name="test_deployment_tdb_users_backfill",
        cron="5 4 * * *",
    )