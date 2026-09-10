from fileinput import filename

from minio import Minio
from oauthlib.uri_validate import query
import psycopg2
import pandas as pd
from io import BytesIO

def connect_postgres():
    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        database="simulated_app",
        user="trading",
        password="trading"
    )
    return conn

def connect_minio():
    client = Minio(
        "localhost:9005",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )
    return client

def get_min_max_ids(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(id), MAX(id) FROM test.users;")
    min_id, max_id = cursor.fetchone()
    cursor.close()
    return min_id, max_id

def read_data_from_postgres(conn, current_id, next_id, column_names):
    cursor = conn.cursor()
    query = ("SELECT * FROM test.users where id >= %s AND id <= %s;")
    cursor.execute(query, (current_id, next_id))
    data = cursor.fetchall()
    if len(column_names) == 0:
        column_names.extend([desc[0] for desc in cursor.description])
    cursor.close()
    return data

def convert(data, column_names):
    buffer = BytesIO()
    # Convert the data to a pandas DataFrame
    df = pd.DataFrame(data, columns=column_names)
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    print(df)
    return buffer

def create_bucket(client, bucket_name):
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        print(f"Bucket '{bucket_name}' created.")
    else:
        print(f"Bucket '{bucket_name}' already exists.")
        
def put_data_to_minio(client, buffer, file_name):
    client.put_object(
        "test",
        file_name,
        buffer,
        length=buffer.getbuffer().nbytes,
        content_type="application/octet-stream"
    )
    print("Data uploaded to MinIO successfully.")
    
def main():
    # Connect to the PostgreSQL database
    conn = connect_postgres()
    client = connect_minio()
    create_bucket(client, "test")
    chunksize = 1000
    part_number = 1
    column_names = []
    current_id, max_id = get_min_max_ids(conn)
    
    while current_id <= max_id:
        next_id = current_id + chunksize
        data = read_data_from_postgres(conn, current_id, next_id, column_names)
        
        if data:
            buffer = convert(data, column_names)
            file_name = f"user_backfill_part_{part_number}.parquet"
            put_data_to_minio(client, buffer, file_name)
        
        current_id = next_id + 1
        part_number += 1
    conn.close()
    
if __name__ == "__main__":
    main()