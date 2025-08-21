#!/usr/bin/env python3
"""
S3 Folder Upload Script

Uploads a local folder to an S3 bucket with collision detection and cleanup.
Generates download URLs for all uploaded files.
"""

import argparse
import os
import sys
from pathlib import Path
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from tqdm import tqdm
import threading
from urllib.parse import quote


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Upload a folder to S3 with cleanup of old versions and generate download URLs'
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
        help='Base destination folder in the S3 bucket (local folder name will be appended)'
    )
    parser.add_argument(
        '--output_file',
        help='Path to output file where download URLs will be written'
    )
    parser.add_argument(
        '--keep_count',
        type=int,
        default=5,
        help='Number of folders to keep after cleanup (default: 5)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing folder (otherwise auto-increment)'
    )
    parser.add_argument(
        '--region',
        help='AWS region (optional)'
    )
    parser.add_argument(
        '--access_key',
        required=True,
        help='AWS access key ID'
    )
    parser.add_argument(
        '--secret_key',
        required=True,
        help='AWS secret access key'
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bars'
    )
    
    return parser.parse_args()


def create_s3_client(access_key, secret_key, region=None):
    """Create and return an S3 client."""
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        return s3_client
    except NoCredentialsError:
        print("Error: Invalid AWS credentials.")
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


def find_available_folder_name(s3_client, bucket_name, base_folder_name):
    """Find an available folder name by auto-incrementing if needed."""
    if not folder_exists_in_bucket(s3_client, bucket_name, base_folder_name):
        return base_folder_name
    
    # Find the next available increment
    counter = 1
    while True:
        candidate_name = f"{base_folder_name}_{counter:02d}"
        if not folder_exists_in_bucket(s3_client, bucket_name, candidate_name):
            return candidate_name
        counter += 1
        
        # Safety check to prevent infinite loop
        if counter > 999:
            print(f"Error: Too many folders with base name '{base_folder_name}' (reached limit of 999)")
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


def generate_download_url(bucket_name, s3_key, region=None):
    """Generate a direct download URL for an S3 object."""
    if region and region != 'us-east-1':
        base_url = f"https://{bucket_name}.s3.{region}.amazonaws.com"
    else:
        base_url = f"https://{bucket_name}.s3.amazonaws.com"
    
    # URL encode the key to handle special characters
    encoded_key = quote(s3_key, safe='/')
    return f"{base_url}/{encoded_key}"


def upload_folder_to_s3(s3_client, local_folder, bucket_name, destination_folder, region=None, show_progress=True):
    """Upload all files in a local folder to S3 and return list of uploaded files."""
    local_path = Path(local_folder)
    
    if not local_path.exists():
        print(f"Error: Local folder '{local_folder}' does not exist.")
        sys.exit(1)
    
    if not local_path.is_dir():
        print(f"Error: '{local_folder}' is not a directory.")
        sys.exit(1)
    
    uploaded_files = 0
    uploaded_objects = []  # Store info about uploaded files
    
    # Collect all files first to show overall progress
    all_files = []
    total_size = 0
    
    for file_path in local_path.rglob('*'):
        if file_path.is_file():
            file_size = file_path.stat().st_size
            all_files.append((file_path, file_size))
            total_size += file_size
    
    if not all_files:
        print(f"No files found in '{local_folder}'")
        return False, []
    
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
        s3_key = f"{destination_folder}/{relative_path}".replace('\\', '/')
        
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
            
            # Store uploaded file info
            download_url = generate_download_url(bucket_name, s3_key, region)
            uploaded_objects.append({
                'local_path': str(file_path),
                's3_key': s3_key,
                'download_url': download_url,
                'file_size': file_size
            })
            
        except ClientError as e:
            if show_progress and file_pbar:
                file_pbar.close()
            print(f"Error uploading {file_path}: {e}")
            continue
    
    if show_progress and overall_pbar:
        overall_pbar.close()
    
    print(f"Successfully uploaded {uploaded_files} files to s3://{bucket_name}/{destination_folder}/")
    return uploaded_files > 0, uploaded_objects


def write_download_urls(uploaded_objects, output_file):
    """Write download URLs to output file in format 'URL : FileName'."""
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for obj in uploaded_objects:
                # Extract just the filename from the local path
                filename = Path(obj['local_path']).name
                f.write(f"{obj['download_url']} : {filename}\n")
        
        print(f"Download URLs written to: {output_file}")
        print(f"Total URLs generated: {len(uploaded_objects)}")
        
    except Exception as e:
        print(f"Error writing download URLs to file: {e}")


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
    
    # Create S3 client
    s3_client = create_s3_client(args.access_key, args.secret_key, args.region)
    
    # Construct the full destination path
    local_folder_name = Path(args.local_folder).name
    full_destination = f"{args.destination_folder}/{local_folder_name}".replace('\\', '/')
    
    # Handle folder name collision
    final_destination = full_destination
    
    if folder_exists_in_bucket(s3_client, args.bucket_name, full_destination):
        if args.force:
            print(f"Folder '{full_destination}' exists, but --force specified. Overwriting...")
            final_destination = full_destination
        else:
            final_destination = find_available_folder_name(
                s3_client, 
                args.bucket_name, 
                full_destination
            )
            print(f"Folder '{full_destination}' exists. Using '{final_destination}' instead.")
    else:
        print(f"Using destination folder: '{final_destination}'")
    
    # Upload the folder
    success, uploaded_objects = upload_folder_to_s3(
        s3_client, 
        args.local_folder, 
        args.bucket_name, 
        final_destination,
        args.region,
        show_progress=not args.no_progress
    )
    
    if not success:
        print("Upload failed or no files were uploaded.")
        sys.exit(1)

    if args.output_file:
        # Write download URLs to output file
        write_download_urls(uploaded_objects, args.output_file)
    
    # Cleanup old folders
    cleanup_old_folders(s3_client, args.bucket_name, args.keep_count)
    
    print("Script completed successfully!")


if __name__ == '__main__':
    main()