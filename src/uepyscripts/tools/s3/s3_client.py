import os
import boto3
import tqdm
import threading
from botocore.exceptions import ClientError
from pathlib import Path
from typing import List
from urllib.parse import quote


class S3Client:
    def __init__(self, access_key: str, secret_key: str, region: str):
        self.s3 = boto3.client("s3", aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)

    def get_bucket_files(self, bucket_name: str, prefix: str, filter_func=None) -> List[str]:
        """
        Retrieve a list of files from an S3 bucket with optional filtering.
        Args:
            bucket_name (str): The name of the S3 bucket to query.
            prefix (str): The prefix (directory path) within the bucket to search under.
            filter_func: A callable that takes an S3 object and returns True if the object should be included.
        Returns:
            List[str]: A list of S3 object keys (file paths) that match the filter criteria.
        """
        paginator = self.s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

        files = []
        for page in pages:
            if "Contents" in page:
                files.extend([obj["Key"] for obj in page["Contents"] if filter_func is None or filter_func(obj)])

        return files

    def folder_exists_in_bucket(self, bucket_name: str, folder_name: str) -> bool:
        """Check if a folder exists in the S3 bucket."""
        response = self.s3.list_objects_v2(Bucket=bucket_name, Prefix=f"{folder_name}/", MaxKeys=1)
        return "Contents" in response

    def find_available_folder_name(self, bucket_name: str, base_folder_name: str) -> str:
        """Find an available folder name by auto-incrementing if needed."""
        if not self.folder_exists_in_bucket(bucket_name, base_folder_name):
            return base_folder_name

        # Find the next available increment
        counter = 1
        while True:
            candidate_name = f"{base_folder_name}_{counter:02d}"
            if not self.folder_exists_in_bucket(bucket_name, candidate_name):
                return candidate_name
            counter += 1

            # Safety check to prevent infinite loop
            if counter > 999:
                raise RuntimeError(f"Too many folders with base name '{base_folder_name}' (reached limit of 999)")

    def download_file(self, bucket_name: str, key: str, local_folder: Path, show_progress_bar: bool = False) -> bool:
        """
        Download a file from an S3 bucket to a local folder.
        Args:
            bucket_name (str): The name of the S3 bucket.
            key (str): The S3 object key (path) of the file to download.
            local_folder (Path): The local folder path where the file will be saved.
            show_progress_bar (bool, optional): Whether to display a progress bar during download. Defaults to False.
        Returns:
            bool: True if the download was successful.
        """
        filename = os.path.basename(key)
        local_path = local_folder.joinpath(filename)

        response = self.s3.head_object(Bucket=bucket_name, Key=key)
        file_size = response["ContentLength"]

        pbar = None

        if show_progress_bar:
            pbar = tqdm.tqdm(total=file_size, unit="B", unit_scale=True, desc=filename)

        self.s3.download_file(bucket_name, key, local_path, Callback=lambda bytes_transferred: pbar.update(bytes_transferred) if pbar else None)

        if pbar:
            pbar.close()

        return True

    def upload_folder_to_s3(
        self, local_folder: str, bucket_name: str, destination_folder: str, region: str = None, show_progress: bool = True
    ) -> (bool, List[dict]):
        """Upload all files in a local folder to S3 and return list of uploaded files."""
        local_path = Path(local_folder)

        if not local_path.exists():
            print(f"Error: Local folder '{local_folder}' does not exist.")
            return False, []

        if not local_path.is_dir():
            print(f"Error: '{local_folder}' is not a directory.")
            return False, []

        uploaded_files = 0
        uploaded_objects = []  # Store info about uploaded files

        # Collect all files first to show overall progress
        all_files = []
        total_size = 0

        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                file_size = file_path.stat().st_size
                all_files.append((file_path, file_size))
                total_size += file_size

        if not all_files:
            print(f"No files found in '{local_folder}'")
            return False, []

        print(f"Found {len(all_files)} files ({total_size / (1024 * 1024):.1f} MB) to upload")

        # Create progress bars
        overall_pbar = None
        file_pbar = None

        if show_progress:
            try:
                overall_pbar = tqdm.tqdm(total=total_size, unit="B", unit_scale=True, desc="Overall Progress", position=0, leave=True)
            except ImportError:
                print("Warning: tqdm not installed. Install with 'pip install tqdm' for progress bars.")
                show_progress = False

        # Walk through all files in the directory
        for file_path, file_size in all_files:
            # Calculate relative path from the base folder
            relative_path = file_path.relative_to(local_path)
            s3_key = f"{destination_folder}/{relative_path}".replace("\\", "/")

            try:
                if show_progress:
                    # Create individual file progress bar
                    file_pbar = tqdm.tqdm(total=file_size, unit="B", unit_scale=True, desc=f"Uploading {file_path.name}", position=1, leave=False)

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

                    # Create callback for progress tracking
                    callback = ProgressCallback(file_path.name, file_size, overall_pbar)

                    # Upload with progress callback
                    self.s3.upload_file(str(file_path), bucket_name, s3_key, Callback=callback)

                    file_pbar.update(file_size)  # Complete the file progress bar
                    file_pbar.close()
                else:
                    print(f"Uploading {file_path} -> s3://{bucket_name}/{s3_key}")
                    self.s3.upload_file(str(file_path), bucket_name, s3_key)

                uploaded_files += 1

                # Store uploaded file info
                download_url = self.generate_download_url(bucket_name, s3_key, region)
                uploaded_objects.append({"local_path": str(file_path), "s3_key": s3_key, "download_url": download_url, "file_size": file_size})

            except ClientError as e:
                if show_progress and file_pbar:
                    file_pbar.close()
                print(f"Error uploading {file_path}: {e}")
                continue

        if show_progress and overall_pbar:
            overall_pbar.close()

        print(f"Successfully uploaded {uploaded_files} files to s3://{bucket_name}/{destination_folder}/")
        return uploaded_files > 0, uploaded_objects

    def generate_download_url(self, bucket_name, s3_key, region=None):
        """Generate a direct download URL for an S3 object."""
        if region and region != "us-east-1":
            base_url = f"https://{bucket_name}.s3.{region}.amazonaws.com"
        else:
            base_url = f"https://{bucket_name}.s3.amazonaws.com"

        # URL encode the key to handle special characters
        encoded_key = quote(s3_key, safe="/")
        return f"{base_url}/{encoded_key}"

    def cleanup_old_folders(self, bucket_name: str, keep_count: int):
        """Remove old folders, keeping only the specified number of most recent ones."""
        folders = self.get_folders_in_bucket(bucket_name)

        if keep_count <= 0:
            print("Warning: keep_count must be positive. No cleanup performed.")
            return

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
            self.delete_folder_from_s3(bucket_name, folder)

    def get_folders_in_bucket(self, bucket_name: str) -> List[str]:
        """Get all top-level folders in the S3 bucket."""
        folders = set()

        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket_name, Delimiter="/")

            for page in pages:
                if "CommonPrefixes" in page:
                    for prefix in page["CommonPrefixes"]:
                        folder_name = prefix["Prefix"].rstrip("/")
                        folders.add(folder_name)

        except ClientError as e:
            print(f"Error listing folders: {e}")
            return []

        return list(folders)

    def delete_folder_from_s3(self, bucket_name: str, folder_name: str):
        """Delete all objects in a folder from S3."""
        try:
            # List all objects with the folder prefix
            objects_to_delete = self.get_bucket_files(bucket_name, f"{folder_name}/")

            if objects_to_delete:
                # Delete objects in batches of 1000 (S3 limit)
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i : i + 1000]
                    self.s3.delete_objects(Bucket=bucket_name, Delete={"Objects": batch})

                print(f"Deleted folder '{folder_name}' ({len(objects_to_delete)} objects)")
            else:
                print(f"Folder '{folder_name}' was already empty")

        except ClientError as e:
            print(f"Error deleting folder '{folder_name}': {e}")
