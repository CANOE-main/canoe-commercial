# CANOE - Commercial Sector Model

This repository contains the commercial sector model for CANOE (Canadian Opportunities for Emissions Reduction). It aggregates data primarily from the NRCan Comprehensive Energy Use Database and Annual Energy Outlook technology assumptions to build a modular commercial sector database.

Access comprehensive document: [Here](https://canoe-main.github.io/canoe-commercial/)

## Overview

The model builds a database representing the commercial buildings sector. It supports:
- Aggregation of subcomponents configured via input files.
- Caching of downloaded data to speed up subsequent runs.
- Currency conversion and database cloning to Excel.

## Usage

### 1. Environment Setup

It is recommended to use `conda` for environment management.

1.  **Create the environment**:
     Navigate to the `canoe-commercial` directory (or where your `environment.yml` is located if separate):
    ```bash
    conda env create -f environment.yml
    ```
    *Note: If specific environment instructions differ, follow the standard CANOE backend setup.*

2.  **Activate the environment**:
    ```bash
    conda activate canoe-backend
    ```

### 2. Running the Aggregation

1.  Navigate to the repository directory:
    ```bash
    cd path/to/canoe-commercial
    ```

2.  Run the model using one of the following commands:
    
    Execute the module directly:
    ```bash
    python .
    ```
    
    Or run the main script:
    ```bash
    python commercial_sector.py
    ```

    The script will:
    - Download necessary data (first run only, cached locally).
    - Aggregate the commercial sector data.
    - Output the result to a SQLite database (and optionally an Excel file).

## Configuration

Configuration is managed through files in the `input_files/` directory.

- **`params.yml`**: Contains various aggregation parameters and switches (e.g., specific technologies, boolean flags).
- **Other files**: Database schema, mapping files, and spreadsheet templates.

Start by reviewing `params.yml` to adjust aggregation settings such as "Aggregation switches".

## Directory Structure

- **`input_files/`**: Configuration files, database schema, and parameters.
- **`input_files/data_cache/`** (created on run): localized cache for downloaded data.
- **`docs/`**: Documentation (in progress).
- **`__main__.py`**: Entry point for running the directory as a module.
- **`commercial_sector.py`**: Main script handling the execution flow.
- **`all_subsectors.py`**: Handles aggregation of different commercial subsectors.
- **`utils.py`**: Utility functions, including robust data fetching and caching.
- **`setup.py`**: configuration object builder.

## License

See [LICENSE](LICENSE) file for details.
