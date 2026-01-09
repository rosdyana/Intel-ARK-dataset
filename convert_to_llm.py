"""
Convert Intel ARK specs to LLM-friendly format.

Generates a text file optimized for LLM retrieval, with product model name as the key.
Supports multiple output formats: markdown, jsonl, and plain text.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path


def configure_console_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_long_csv(input_path: Path) -> dict[str, dict]:
    """Load long-format CSV and organize by SKU."""
    
    sku_data: dict[str, dict] = {}
    
    # Define the order of spec groups
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
    
    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            sku = row["sku"]
            spec_group = row["spec_group"]
            spec_name = row["spec_name"]
            spec_value = row["spec_value"]
            
            if sku not in sku_data:
                sku_data[sku] = {
                    "sku": sku,
                    "product_name": row["product_name"],
                    "product_url": row["product_url"],
                    "category": row["category"],
                    "family": row["family"],
                    "specs": OrderedDict(),
                }
            
            # Organize specs by group
            if spec_group not in sku_data[sku]["specs"]:
                sku_data[sku]["specs"][spec_group] = OrderedDict()
            
            sku_data[sku]["specs"][spec_group][spec_name] = spec_value
    
    # Sort specs by group order
    for sku in sku_data:
        sorted_specs = OrderedDict()
        for group in group_order:
            if group in sku_data[sku]["specs"]:
                sorted_specs[group] = sku_data[sku]["specs"][group]
        # Add any remaining groups not in the predefined order
        for group in sku_data[sku]["specs"]:
            if group not in sorted_specs:
                sorted_specs[group] = sku_data[sku]["specs"][group]
        sku_data[sku]["specs"] = sorted_specs
    
    return sku_data


def extract_model_name(product_name: str) -> str:
    """Extract the processor model name from full product name."""
    # e.g., "Intel® Core™ i7-11850HE Processor (24M Cache, up to 4.70 GHz)"
    # -> "i7-11850HE" or "Intel Core i7-11850HE"
    
    # Try to find processor number in specs, fallback to parsing product name
    name = product_name.replace("®", "").replace("™", "").replace("  ", " ")
    
    # Remove common suffixes
    for suffix in ["Processor", "processor"]:
        if suffix in name:
            name = name.split(suffix)[0].strip()
    
    return name.strip()


def write_markdown(sku_data: dict[str, dict], output_path: Path) -> None:
    """Write LLM-friendly markdown format."""
    
    with output_path.open("w", encoding="utf-8") as f:
        f.write("# Intel Processor Specifications Database\n\n")
        f.write("This document contains detailed specifications for Intel processors.\n")
        f.write("Search by processor model name (e.g., 'i7-11850HE', 'Xeon Gold 5118').\n\n")
        f.write("---\n\n")
        
        # Sort by product name for easier searching
        sorted_skus = sorted(sku_data.keys(), key=lambda s: sku_data[s]["product_name"])
        
        for sku in sorted_skus:
            data = sku_data[sku]
            model_name = extract_model_name(data["product_name"])
            
            f.write(f"## {model_name}\n\n")
            f.write(f"**Full Name:** {data['product_name']}\n")
            f.write(f"**SKU:** {data['sku']}\n")
            f.write(f"**Category:** {data['category']}\n")
            f.write(f"**Family:** {data['family']}\n")
            f.write(f"**URL:** {data['product_url']}\n\n")
            
            for group, specs in data["specs"].items():
                f.write(f"### {group}\n\n")
                for spec_name, spec_value in specs.items():
                    f.write(f"- **{spec_name}:** {spec_value}\n")
                f.write("\n")
            
            f.write("---\n\n")
    
    print(f"Written markdown: {output_path}")


def write_jsonl(sku_data: dict[str, dict], output_path: Path) -> None:
    """Write JSONL format (one JSON object per line) - ideal for embeddings."""
    
    with output_path.open("w", encoding="utf-8") as f:
        sorted_skus = sorted(sku_data.keys(), key=lambda s: sku_data[s]["product_name"])
        
        for sku in sorted_skus:
            data = sku_data[sku]
            model_name = extract_model_name(data["product_name"])
            
            # Flatten specs for easier querying
            flat_specs = {}
            for group, specs in data["specs"].items():
                for spec_name, spec_value in specs.items():
                    flat_specs[f"{group}: {spec_name}"] = spec_value
            
            record = {
                "model": model_name,
                "full_name": data["product_name"],
                "sku": data["sku"],
                "category": data["category"],
                "family": data["family"],
                "url": data["product_url"],
                "specs": flat_specs,
                # Add searchable text block
                "text": generate_text_block(data, model_name),
            }
            
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    print(f"Written JSONL: {output_path}")


def generate_text_block(data: dict, model_name: str) -> str:
    """Generate a searchable text block for a product."""
    lines = [
        f"Processor: {model_name}",
        f"Full Name: {data['product_name']}",
        f"Category: {data['category']}",
        f"Family: {data['family']}",
        "",
    ]
    
    for group, specs in data["specs"].items():
        lines.append(f"{group}:")
        for spec_name, spec_value in specs.items():
            lines.append(f"  {spec_name}: {spec_value}")
        lines.append("")
    
    return "\n".join(lines)


def write_text(sku_data: dict[str, dict], output_path: Path) -> None:
    """Write plain text format optimized for semantic search."""
    
    with output_path.open("w", encoding="utf-8") as f:
        f.write("INTEL PROCESSOR SPECIFICATIONS DATABASE\n")
        f.write("=" * 50 + "\n\n")
        
        sorted_skus = sorted(sku_data.keys(), key=lambda s: sku_data[s]["product_name"])
        
        for sku in sorted_skus:
            data = sku_data[sku]
            model_name = extract_model_name(data["product_name"])
            
            f.write(f"{'='*60}\n")
            f.write(f"PROCESSOR: {model_name}\n")
            f.write(f"{'='*60}\n\n")
            
            f.write(f"Full Name: {data['product_name']}\n")
            f.write(f"SKU: {data['sku']}\n")
            f.write(f"Category: {data['category']}\n")
            f.write(f"Family: {data['family']}\n")
            f.write(f"URL: {data['product_url']}\n\n")
            
            for group, specs in data["specs"].items():
                f.write(f"[{group}]\n")
                for spec_name, spec_value in specs.items():
                    f.write(f"  {spec_name}: {spec_value}\n")
                f.write("\n")
            
            f.write("\n")
    
    print(f"Written text: {output_path}")


def write_json(sku_data: dict[str, dict], output_path: Path) -> None:
    """Write a single JSON file with all data, keyed by model name."""
    
    # Build lookup by model name
    by_model: dict[str, dict] = {}
    
    for sku, data in sku_data.items():
        model_name = extract_model_name(data["product_name"])
        
        # Convert OrderedDict to regular dict for JSON
        specs_dict = {}
        for group, specs in data["specs"].items():
            specs_dict[group] = dict(specs)
        
        record = {
            "model": model_name,
            "full_name": data["product_name"],
            "sku": data["sku"],
            "category": data["category"],
            "family": data["family"],
            "url": data["product_url"],
            "specs": specs_dict,
        }
        
        # Use model name as key (handle duplicates by appending SKU)
        key = model_name
        if key in by_model:
            key = f"{model_name} (SKU {sku})"
        by_model[key] = record
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(by_model, f, ensure_ascii=False, indent=2)
    
    print(f"Written JSON: {output_path}")


def main() -> None:
    configure_console_utf8()
    
    parser = argparse.ArgumentParser(
        description="Convert Intel ARK specs to LLM-friendly format"
    )
    parser.add_argument(
        "--input", "-i",
        default="intel_specs_long.csv",
        help="Input long-format CSV file (default: intel_specs_long.csv)"
    )
    parser.add_argument(
        "--output", "-o",
        default="intel_specs_llm",
        help="Output file base name without extension (default: intel_specs_llm)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "md", "jsonl", "text", "txt", "json", "all"],
        default="all",
        help="Output format (default: all)"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_base = Path(args.output)
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)
    
    print(f"Loading {input_path}...")
    sku_data = load_long_csv(input_path)
    print(f"Loaded {len(sku_data)} products")
    
    fmt = args.format.lower()
    
    if fmt in ("markdown", "md", "all"):
        write_markdown(sku_data, output_base.with_suffix(".md"))
    
    if fmt in ("jsonl", "all"):
        write_jsonl(sku_data, output_base.with_suffix(".jsonl"))
    
    if fmt in ("text", "txt", "all"):
        write_text(sku_data, output_base.with_suffix(".txt"))
    
    if fmt in ("json", "all"):
        write_json(sku_data, output_base.with_suffix(".json"))
    
    print("\nDone!")


if __name__ == "__main__":
    main()
