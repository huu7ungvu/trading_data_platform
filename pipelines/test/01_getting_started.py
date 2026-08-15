from prefect import flow, task
import random
from pathlib import Path

@task
def get_customer_ids() -> list[str]:
    # Fetch customer IDs from a database or API
    return [f"customer{n}" for n in random.choices(range(100), k=10)]

@task
def process_customer(customer_id: str) -> str:
    # Process a single customer
    return f"Processed {customer_id}"

@flow
def test_flow() -> list[str]:
    customer_ids = get_customer_ids()
    # Map the process_customer task across all customer IDs
    results = process_customer.map(customer_ids)
    return results


if __name__ == "__main__":
    # test_flow.serve(name="test_flow", cron="*/2 * * * *")
    test_flow.from_source(
        source=str(Path(__file__).parent),
        entrypoint="01_getting_started.py:test_flow",
    ).deploy(
        name="test-flow-deployment",
        cron="*/2 * * * *",  # your cron schedule
        work_pool_name="my-local-pool",
    )