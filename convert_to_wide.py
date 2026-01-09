"""
Convert the long-format Intel ARK specs CSV to wide format.

Long format: one row per (sku, spec_name) pair
Wide format: one row per SKU with all specs as columns
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import OrderedDict
from pathlib import Path


def configure_console_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def convert_long_to_wide(input_path: Path, output_path: Path) -> None:
    """Convert long-format CSV to wide-format CSV."""
    
    # First pass: collect all unique spec columns and SKU data
    sku_data: dict[str, dict[str, str]] = {}
    spec_columns: OrderedDict[str, None] = OrderedDict()  # Preserve order
    
    # Define the order of spec groups for column organization
    group_order = [
        "Essentials",
        "CPU Specifications",
        "Supplemental Information", 
        "Memory Specifications",
        "GPU Specifications",
        "Expansion Options",
        "Package Specifications",
        "Advanced Technologies",
        "Security & Reliability",
    ]
    
    print(f"Reading {input_path}...")
    
    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            sku = row["sku"]
            spec_group = row["spec_group"]
            spec_name = row["spec_name"]
            spec_value = row["spec_value"]
            
            # Create column name: "Group: Spec Name"
            col_name = f"{spec_group}: {spec_name}"
            spec_columns[col_name] = None
            
            # Initialize SKU entry if not exists
            if sku not in sku_data:
                sku_data[sku] = {
                    "sku": sku,
                    "product_name": row["product_name"],
                    "product_url": row["product_url"],
                    "category": row["category"],
                    "family": row["family"],
                    "scraped_at": row["scraped_at"],
                }
            
            # Store the spec value
            sku_data[sku][col_name] = spec_value
    
    print(f"Found {len(sku_data)} unique SKUs")
    print(f"Found {len(spec_columns)} unique spec columns")
    
    # Sort spec columns by group order, then alphabetically within each group
    def column_sort_key(col: str) -> tuple[int, str]:
        group = col.split(":")[0]
        try:
            group_idx = group_order.index(group)
        except ValueError:
            group_idx = len(group_order)  # Unknown groups go last
        return (group_idx, col)
    
    sorted_spec_cols = sorted(spec_columns.keys(), key=column_sort_key)
    
    # Build final column order
    meta_cols = ["sku", "product_name", "product_url", "category", "family", "scraped_at"]
    all_columns = meta_cols + sorted_spec_cols
    
    print(f"Writing {output_path}...")
    
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_columns, extrasaction="ignore")
        writer.writeheader()
        
        # Sort SKUs for consistent output
        for sku in sorted(sku_data.keys()):
            row_data = sku_data[sku]
            # Fill missing columns with empty string
            for col in sorted_spec_cols:
                if col not in row_data:
                    row_data[col] = ""
            writer.writerow(row_data)
    
    print(f"Done! Wrote {len(sku_data)} rows")
    
    # Print column summary by group
    print("\nColumns by group:")
    for group in group_order:
        group_cols = [c for c in sorted_spec_cols if c.startswith(f"{group}:")]
        if group_cols:
            print(f"  {group}: {len(group_cols)} columns")


def main() -> None:
    configure_console_utf8()
    
    parser = argparse.ArgumentParser(
        description="Convert Intel ARK specs from long format to wide format"
    )
    parser.add_argument(
        "--input", "-i",
        default="intel_specs_long.csv",
        help="Input long-format CSV file (default: intel_specs_long.csv)"
    )
    parser.add_argument(
        "--output", "-o",
        default="intel_specs_wide.csv",
        help="Output wide-format CSV file (default: intel_specs_wide.csv)"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)
    
    convert_long_to_wide(input_path, output_path)


if __name__ == "__main__":
    main()
