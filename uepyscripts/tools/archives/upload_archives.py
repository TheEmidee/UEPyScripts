#!/usr/bin/env python3
"""
S3 Folder Upload Script

Uploads a local folder to an S3 bucket with collision detection and cleanup.
"""

import argparse
import sys
from pathlib import Path
import threading
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from tqdm import tqdm

from ... import logger
from ...context import config
from ...context import project

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Upload a folder to S3 with cleanup of old versions'
    )
    parser.add_argument(
        '--local_folder',
        help='Path to the local folder to upload'
    )
    parser.add_argument(
        '--bucket_name',
        help='Name of the S3 bucket'
    )
    parser.add_argument(
        '--destination_folder',
        help='Destination folder name in the S3 bucket'
    )
    parser.add_argument(
        '--keep',
        type=int,
        default=5,
        help='Number of folders to keep after cleanup (default: 5)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing folder if it exists'
    )
    parser.add_argument(
        '--region',
        help='AWS region (optional)'
    )
    parser.add_argument(
        '--access_key',
        help='AWS access key ID'
    )
    parser.add_argument(
        '--secret_key',
        help='AWS secret access key'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bars'
    )
    
    return parser.parse_args()


def create_s3_client(region=None, access_key=None, secret_key=None):
    """Create and return an S3 client."""
    try:
        # Use provided access key and secret key
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        return s3_client
    except NoCredentialsError:
        print("Error: AWS credentials not found. Please configure your credentials or provide --access-key and --secret-key.")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating S3 client: {e}")
        sys.exit(1)


def folder_exists_in_bucket(s3_client, bucket_name, folder_name):
    """Check if a folder exists in the S3 bucket."""
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=f"{folder_name}/",
            MaxKeys=1
        )
        return 'Contents' in response
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"Error: Bucket '{bucket_name}' does not exist.")
            sys.exit(1)
        else:
            print(f"Error checking folder existence: {e}")
            sys.exit(1)

class ProgressCallback:
    """Callback class for tracking upload progress."""
    
    def __init__(self, filename, file_size, pbar=None):
        self.filename = filename
        self.file_size = file_size
        self.pbar = pbar
        self.bytes_transferred = 0
        self._lock = threading.Lock()
    
    def __call__(self, bytes_amount):
        with self._lock:
            self.bytes_transferred += bytes_amount
            if self.pbar:
                self.pbar.update(bytes_amount)


def upload_folder_to_s3(s3_client, local_path: Path, bucket_name : str, destination_folder : str, show_progress: bool = True):
    """Upload all files in a local folder to S3."""

    folder_name = f"{destination_folder}/{local_path.name}".replace('\\', '/')
    
    if folder_exists_in_bucket(s3_client, bucket_name, folder_name):
        print(f"Error: Folder '{destination_folder}' already exists in bucket '{bucket_name}'.")
        print("Use --force to overwrite the existing folder.")
        sys.exit(1)
    
    uploaded_files = 0
    all_files = []
    total_size = 0
    
    for file_path in local_path.rglob('*'):
        if file_path.is_file():
            file_size = file_path.stat().st_size
            all_files.append((file_path, file_size))
            total_size += file_size
    
    if not all_files:
        print(f"No files found in '{local_path}'")
        return False
    
    print(f"Found {len(all_files)} files ({total_size / (1024*1024):.1f} MB) to upload")
    
    # Create progress bars
    overall_pbar = None
    file_pbar = None
    
    if show_progress:
        try:
            overall_pbar = tqdm(
                total=total_size,
                unit='B',
                unit_scale=True,
                desc='Overall Progress',
                position=0,
                leave=True
            )
        except ImportError:
            print("Warning: tqdm not installed. Install with 'pip install tqdm' for progress bars.")
            show_progress = False
    
    # Walk through all files in the directory
    for file_path, file_size in all_files:
        # Calculate relative path from the base folder
        relative_path = file_path.relative_to(local_path)
        s3_key = f"{folder_name}/{relative_path}".replace('\\', '/')
        
        try:
            if show_progress:
                # Create individual file progress bar
                file_pbar = tqdm(
                    total=file_size,
                    unit='B',
                    unit_scale=True,
                    desc=f'Uploading {file_path.name}',
                    position=1,
                    leave=False
                )
                
                # Create callback for progress tracking
                callback = ProgressCallback(file_path.name, file_size, overall_pbar)
                
                # Upload with progress callback
                s3_client.upload_file(
                    str(file_path), 
                    bucket_name, 
                    s3_key,
                    Callback=callback
                )
                
                file_pbar.update(file_size)  # Complete the file progress bar
                file_pbar.close()
            else:
                print(f"Uploading {file_path} -> s3://{bucket_name}/{s3_key}")
                s3_client.upload_file(str(file_path), bucket_name, s3_key)
            
            uploaded_files += 1
            
        except ClientError as e:
            if show_progress and file_pbar:
                file_pbar.close()
            print(f"Error uploading {file_path}: {e}")
            continue
    
    if show_progress and overall_pbar:
        overall_pbar.close()
    
    print(f"Successfully uploaded {uploaded_files} files to s3://{bucket_name}/{destination_folder}/")
    return uploaded_files > 0


def get_folders_in_bucket(s3_client, bucket_name):
    """Get all top-level folders in the S3 bucket."""
    folders = set()
    
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Delimiter='/')
        
        for page in pages:
            if 'CommonPrefixes' in page:
                for prefix in page['CommonPrefixes']:
                    folder_name = prefix['Prefix'].rstrip('/')
                    folders.add(folder_name)
    
    except ClientError as e:
        print(f"Error listing folders: {e}")
        return []
    
    return list(folders)


def delete_folder_from_s3(s3_client, bucket_name, folder_name):
    """Delete all objects in a folder from S3."""
    try:
        # List all objects with the folder prefix
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=f"{folder_name}/")
        
        objects_to_delete = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    objects_to_delete.append({'Key': obj['Key']})
        
        if objects_to_delete:
            # Delete objects in batches of 1000 (S3 limit)
            for i in range(0, len(objects_to_delete), 1000):
                batch = objects_to_delete[i:i+1000]
                s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': batch}
                )
            
            print(f"Deleted folder '{folder_name}' ({len(objects_to_delete)} objects)")
        else:
            print(f"Folder '{folder_name}' was already empty")
    
    except ClientError as e:
        print(f"Error deleting folder '{folder_name}': {e}")


def cleanup_old_folders(s3_client, bucket_name, keep_count):
    """Remove old folders, keeping only the specified number of most recent ones."""
    folders = get_folders_in_bucket(s3_client, bucket_name)
    
    if len(folders) <= keep_count:
        print(f"Found {len(folders)} folders, keeping all (limit: {keep_count})")
        return
    
    # Sort folders by name in descending order (assuming names are sortable)
    folders.sort(reverse=True)
    
    folders_to_keep = folders[:keep_count]
    folders_to_delete = folders[keep_count:]
    
    print(f"Keeping {len(folders_to_keep)} folders: {folders_to_keep}")
    print(f"Deleting {len(folders_to_delete)} old folders: {folders_to_delete}")
    
    for folder in folders_to_delete:
        delete_folder_from_s3(s3_client, bucket_name, folder)


def main():
    """Main function."""
    args = parse_arguments()

    local_path = Path(args.local_folder)
    
    if not local_path.exists():
        print(f"Error: Local folder '{local_path}' does not exist.")
        sys.exit(1)
    
    if not local_path.is_dir():
        print(f"Error: '{local_path}' is not a directory.")
        sys.exit(1)
    
    s3_client = create_s3_client(args.region, args.access_key, args.secret_key)
    success = upload_folder_to_s3(
        s3_client,
        local_path,
        args.bucket_name,
        args.destination_folder,
        show_progress=not args.no_progress
    )
    
    if not success:
        print("Upload failed or no files were uploaded.")
        sys.exit(1)
    
    # Cleanup old folders
    cleanup_old_folders(s3_client, args.bucket_name, args.keep)
    
    print("Script completed successfully!")


if __name__ == '__main__':
    main()