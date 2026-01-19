#!/usr/bin/env python3
"""
S3 Folder Upload Script

Uploads a local folder to an S3 bucket.
You can provide the folder to create in the bucket.
The script will automatically append the date using the format YYYYMMDD to the folder.
It will handle folder name collisions and will suffix the folder with _XX.

It can also clean up old folders in the bucket, keeping only a specified number of the most recent ones.
Finally, it can output a text file that will contain the download URLs for all uploaded files.
"""

import argparse
import sys
from pathlib import Path

from ...tools.helpers import get_date_formatted_name
from ...tools.s3.s3_client import S3Client, S3UploadedObject


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Upload a folder to S3 with cleanup of old versions and generate download URLs")
    parser.add_argument("--local_folder", help="Path to the local folder to upload")
    parser.add_argument("--bucket_name", help="Name of the S3 bucket")
    parser.add_argument("--destination_folder", help="Base destination folder in the S3 bucket")
    parser.add_argument("--output_file", help="Path to output file where download URLs will be written")
    parser.add_argument("--keep_count", type=int, default=5, help="Number of folders to keep after cleanup (default: 5)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing folder (otherwise auto-increment)")
    parser.add_argument("--region", help="AWS region (optional)")
    parser.add_argument("--access_key", required=True, help="AWS access key ID")
    parser.add_argument("--secret_key", required=True, help="AWS secret access key")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bars")

    return parser.parse_args()


def write_download_urls(uploaded_objects : list[S3UploadedObject], output_file : Path) -> None:
    """Write download URLs to output file in format 'URL : FileName'."""
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            for obj in uploaded_objects:
                f.write(f"{obj.download_url} : {obj.file_path.name}\n")

        print(f"Download URLs written to: {output_file}")
        print(f"Total URLs generated: {len(uploaded_objects)}")

    except Exception as e:
        print(f"Error writing download URLs to file: {e}")


def main() -> None:
    """Main function."""
    args = parse_arguments()

    s3_client = S3Client(args.access_key, args.secret_key, args.region)

    date_name = get_date_formatted_name()
    full_destination = f"{args.destination_folder}/{date_name}".replace("\\", "/")

    final_destination = full_destination

    if s3_client.folder_exists_in_bucket(args.bucket_name, full_destination):
        if args.force:
            print(f"Folder '{full_destination}' exists, but --force specified. Overwriting...")
            final_destination = full_destination
        else:
            final_destination = s3_client.find_available_folder_name(args.bucket_name, full_destination)
            print(f"Folder '{full_destination}' exists. Using '{final_destination}' instead.")
    else:
        print(f"Using destination folder: '{final_destination}'")

    # Upload the folder
    success, uploaded_objects = s3_client.upload_folder_to_s3(
        args.local_folder, args.bucket_name, final_destination, args.region, show_progress=not args.no_progress
    )

    if not success:
        print("Upload failed or no files were uploaded.")
        sys.exit(1)

    if args.output_file:
        # Write download URLs to output file
        write_download_urls(uploaded_objects, Path(args.output_file))

    # Cleanup old folders
    s3_client.cleanup_old_folders(args.bucket_name, args.keep_count)

    print("Script completed successfully!")


if __name__ == "__main__":
    main()
