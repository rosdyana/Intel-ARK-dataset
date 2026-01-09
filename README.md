# Intel ARK Scraper

A web scraper for collecting Intel processor specifications from [Intel ARK](https://ark.intel.com/).

## Features

- Scrapes processor specifications from Intel ARK website
- Captures all specification sections: Essentials, CPU Specifications, Memory Specifications, GPU Specifications, Expansion Options, Package Specifications, Advanced Technologies, Security & Reliability, and more
- Supports resumable scraping with SQLite state tracking
- Multiple output formats for different use cases

## Requirements

- Python 3.10+
- Playwright

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

### 1. Scrape Intel ARK

```bash
# Scrape all processors (resumable)
python scrape_intel_ark.py

# Scrape specific category
python scrape_intel_ark.py --category "Intel® Core™ Processors"

# Limit number of products
python scrape_intel_ark.py --limit 100

# Reset and start fresh
python scrape_intel_ark.py --reset
```

Output: `intel_specs_long.csv` (long format - one row per spec)

### 2. Convert to Wide Format

Convert to one row per processor with all specs as columns:

```bash
python convert_to_wide.py
```

Output: `intel_specs_wide.csv`

### 3. Convert to LLM-Friendly Formats

Generate formats optimized for LLM retrieval and search:

```bash
# Generate all formats
python convert_to_llm.py

# Generate specific format
python convert_to_llm.py --format markdown
python convert_to_llm.py --format jsonl
python convert_to_llm.py --format json
python convert_to_llm.py --format text
```

Output formats:
- `intel_specs_llm.md` - Markdown (human-readable, RAG-friendly)
- `intel_specs_llm.jsonl` - JSON Lines (vector embeddings, chunked retrieval)
- `intel_specs_llm.json` - JSON keyed by model name (direct lookup)
- `intel_specs_llm.txt` - Plain text (semantic search)

## Output Schema

### Long Format (intel_specs_long.csv)

| Column | Description |
|--------|-------------|
| sku | Intel product SKU ID |
| product_name | Full product name |
| product_url | Intel ARK URL |
| category | Product category |
| family | Product family |
| spec_group | Specification group (e.g., "CPU Specifications") |
| spec_name | Specification name (e.g., "Total Cores") |
| spec_value | Specification value (e.g., "8") |
| scraped_at | Timestamp |

### Wide Format (intel_specs_wide.csv)

One row per product with columns for each specification, named as `"Group: Spec Name"`.

## License

MIT
