# LCA Data Files

Place DOL OFLC LCA disclosure `.xlsx` files in this directory.

## Download

1. Go to https://www.dol.gov/agencies/eta/foreign-labor/performance
2. Under **Disclosure Data**, find **LCA Programs (H-1B, H-1B1, E-3)**
3. Download the quarterly or annual `.xlsx` files (e.g., `LCA_Disclosure_Data_FY2024_Q4.xlsx`)
4. Place them in this `data/` folder
5. Run `python src/ingest.py` from the project root to load into SQLite
