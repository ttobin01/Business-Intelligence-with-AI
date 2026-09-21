# HW2 Specification — Wildcat Capital Transaction EDA

**Author:** Tyler Tobin
**Course:** MIS3060 Business Intelligence with AI
**Date:** 2026-09-21

## Instruction to Claude Cowork

Write one single Python script named `hw02_eda.py` that performs exploratory data analysis on `data/raw/fact_transactions.csv`, the Wildcat Capital client transaction dataset. All of the steps below must run together, in this order, in a single execution of one file — not as separate scripts.

The script should:

1. Load `data/raw/fact_transactions.csv` into a pandas DataFrame.
2. Print the shape of the DataFrame (number of rows and columns).
3. Print every column name together with its data type.
4. Print the count of missing values for every column.
5. Print descriptive statistics — count, mean, standard deviation, minimum, 25th percentile, median, 75th percentile, and maximum — for every numeric column.
6. Print the value counts and percentages for the `txn_type` column, sorted from the most frequent type to the least frequent.
7. Print the number of unique clients, the number of unique advisors, and the number of unique securities referenced anywhere in the file.
8. Print the earliest and latest transaction date found in the `txn_date` column.
9. Check for duplicate rows based on `txn_id` and print how many duplicates were found.
10. Print the mean, median, and skewness of the `amount` column.
11. Group the data by `txn_type` and, for each transaction type, print the count of rows and the mean and median of `amount`, each rounded to two decimal places, sorted so the transaction type with the highest mean amount appears first.
12. Compute the correlation matrix for `shares`, `price`, and `amount`, rounded to two decimal places; print it; and separately identify and print the three strongest correlations, excluding a variable's correlation with itself.
13. Print the minimum, maximum, and count of negative values in the `shares` column, broken out separately for each `txn_type`.
14. Print a clearly labeled warning if the DataFrame's shape is not exactly 298,772 rows by 9 columns.
15. Create and save three charts to a `hw02/charts/` folder:
    - A histogram of the `amount` column with vertical lines marking the mean and the median, each clearly labeled, saved as `hw02/charts/hist_amount.png`.
    - A horizontal box plot showing the distribution of `amount` broken out by `txn_type`, saved as `hw02/charts/box_amount_by_type.png`.
    - A scatter plot with `shares` on the x-axis and `amount` on the y-axis, with points colored by `txn_type`, saved as `hw02/charts/scatter_shares_amount.png`.
16. Save a plain-text summary of everything printed in steps 2 through 13 to `hw02/hw02_profile.txt`.
17. Include a comment block at the very top of the script identifying the script's name, the dataset it uses, the author, and the date it was generated.

Write the script so it can be run once from the terminal with `python hw02/hw02_eda.py` and produce all of the above in a single pass, with no manual steps in between.
