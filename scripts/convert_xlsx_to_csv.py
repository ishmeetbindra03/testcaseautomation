#!/usr/bin/env python3
"""
Script to convert all XLSX files in a directory to CSV files.
Supports converting single or multiple sheets, with options to customize output.
"""

import argparse
import csv
import os
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("Error: The 'openpyxl' library is required to run this script.", file=sys.stderr)
    print("Please install it using: pip install openpyxl", file=sys.stderr)
    sys.exit(1)


def convert_xlsx_to_csv(xlsx_path: Path, output_dir: Path, convert_all_sheets: bool = True) -> int:
    """
    Converts a single XLSX file to CSV(s).

    Args:
        xlsx_path: Path to the .xlsx file.
        output_dir: Path to the directory where CSVs should be written.
        convert_all_sheets: If True, converts all worksheets. If False, only converts the active sheet.

    Returns:
        The number of CSV files successfully created.
    """
    print(f"Processing: {xlsx_path.name}")
    try:
        # Load workbook with data_only=True to get evaluated cell values rather than formulas
        workbook = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    except Exception as e:
        print(f"  Error loading workbook {xlsx_path.name}: {e}", file=sys.stderr)
        return 0

    sheets_to_convert = []
    if convert_all_sheets:
        sheets_to_convert = workbook.sheetnames
    else:
        sheets_to_convert = [workbook.active.title]

    csv_count = 0
    base_name = xlsx_path.stem

    for sheet_name in sheets_to_convert:
        try:
            # We must load without read_only=True to access worksheet easily if needed,
            # but since we used read_only=True for loading, let's make sure we access properly.
            sheet = workbook[sheet_name]
            
            # Determine output filename
            if len(sheets_to_convert) == 1:
                csv_filename = f"{base_name}.csv"
            else:
                # Replace whitespace or special characters in sheet name to make a clean filename
                clean_sheet_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in sheet_name)
                csv_filename = f"{base_name}_{clean_sheet_name}.csv"

            csv_path = output_dir / csv_filename
            print(f"  -> Converting sheet '{sheet_name}' to {csv_path.name}...")

            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Iterate through all rows and write to CSV
                for row in sheet.iter_rows(values_only=True):
                    # Only write row if it's not completely empty (optional, but clean)
                    if any(cell is not None for cell in row):
                        # Convert None values to empty strings
                        cleaned_row = ["" if cell is None else str(cell) for cell in row]
                        writer.writerow(cleaned_row)
                    else:
                        # Write empty row or skip? Writing empty row matches original excel layout
                        writer.writerow([])

            csv_count += 1
        except Exception as e:
            print(f"  Error converting sheet '{sheet_name}': {e}", file=sys.stderr)

    return csv_count


def main():
    parser = argparse.ArgumentParser(
        description="Convert all XLSX files in a directory to CSV files."
    )
    parser.add_argument(
        "input_directory",
        nargs="?",
        default=".",
        help="Directory containing XLSX files (default: current directory)."
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Directory to save CSV files (default: same as input directory)."
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only convert the active sheet in each workbook instead of all sheets."
    )

    args = parser.parse_args()

    input_dir = Path(args.input_directory).resolve()
    if not input_dir.is_dir():
        print(f"Error: Input directory '{input_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = input_dir

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all .xlsx files in the directory
    xlsx_files = list(input_dir.glob("*.xlsx"))
    
    # Filter out temporary/lock files (e.g., ~$workbook.xlsx)
    xlsx_files = [f for f in xlsx_files if not f.name.startswith("~$")]

    if not xlsx_files:
        print(f"No .xlsx files found in '{input_dir}'.")
        return

    print(f"Found {len(xlsx_files)} .xlsx file(s) in '{input_dir}'.")
    print(f"CSVs will be saved to '{output_dir}'.")
    print("-" * 50)

    total_csvs = 0
    successful_files = 0

    for xlsx_file in xlsx_files:
        count = convert_xlsx_to_csv(
            xlsx_path=xlsx_file,
            output_dir=output_dir,
            convert_all_sheets=not args.active_only
        )
        if count > 0:
            successful_files += 1
            total_csvs += count

    print("-" * 50)
    print(f"Done! Successfully converted {successful_files}/{len(xlsx_files)} file(s).")
    print(f"Generated {total_csvs} CSV file(s) in '{output_dir}'.")


if __name__ == "__main__":
    main()
