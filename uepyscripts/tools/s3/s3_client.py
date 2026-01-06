import os
from pathlib import Path
from typing import List
import boto3
import tqdm

class S3Client:
    def __init__(self, access_key: str, secret_key: str, region: str):
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )

    def get_bucket_files(self, bucket_name: str, prefix: str, filter_func) -> List[str]:
        """
        Retrieve a list of files from an S3 bucket with optional filtering.
        Args:
            bucket_name (str): The name of the S3 bucket to query.
            prefix (str): The prefix (directory path) within the bucket to search under.
            filter_func: A callable that takes an S3 object and returns True if the object should be included.
        Returns:
            List[str]: A list of S3 object keys (file paths) that match the filter criteria.
        """
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        
        files = []
        for page in pages:
            if 'Contents' in page:
                files.extend([obj['Key'] for obj in page['Contents'] if filter_func(obj)])
        
        return files
    
    def download_file(self, bucket_name: str, key: str, local_folder: Path, show_progress_bar: bool = False):
        filename = os.path.basename(key)
        local_path = local_folder.joinpath(filename)
        
        response = self.s3.head_object(Bucket=bucket_name, Key=key)
        file_size = response['ContentLength']

        pbar = None

        if show_progress_bar:
            pbar = tqdm.tqdm(total=file_size, unit='B', unit_scale=True, desc=filename)
        
        self.s3.download_file(
            bucket_name, 
            key, 
            local_path,
            Callback=lambda bytes_transferred: pbar.update(bytes_transferred) if pbar else None
            )
