import unittest

import pandas as pd

from ex04_pandas_cleaning import (
    apply_cleaning_rules,
    clean_price,
    fill_missing,
    fit_cleaning_rules,
    remove_outliers,
)


class CleaningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = pd.DataFrame(
            {
                "order_id": ["A", "B", "C", "D", "E"],
                "order_date": ["2025-01-01"] * 5,
                "region": ["Seoul", None, "Busan", "Seoul", "Busan"],
                "category": ["Food", "Food", "Home", "Home", "Home"],
                "quantity": [1, 2, 3, 4, 1000],
                "unit_price": [1000, None, 3000, -500, 5000],
                "discount": [0, 0.1, 0, 0, 0.2],
            }
        )

    def test_clean_price_converts_invalid_values(self) -> None:
        result = clean_price(self.raw)
        self.assertTrue(pd.api.types.is_numeric_dtype(result["unit_price"]))
        self.assertTrue(pd.isna(result.loc[3, "unit_price"]))

    def test_fill_missing_uses_category_median(self) -> None:
        result = fill_missing(clean_price(self.raw))
        self.assertEqual(result.loc[1, "unit_price"], 1000)
        self.assertEqual(result.loc[3, "unit_price"], 4000)
        self.assertEqual(result.loc[1, "region"], "Unknown")

    def test_remove_outliers_clips_instead_of_deleting_rows(self) -> None:
        result = remove_outliers(self.raw, {"quantity": (0, 10)}, ("quantity",))
        self.assertEqual(len(result), len(self.raw))
        self.assertEqual(result["quantity"].max(), 10)

    def test_same_rules_can_be_applied_to_new_data(self) -> None:
        rules = fit_cleaning_rules(self.raw)
        new_data = self.raw.iloc[[0]].copy()
        new_data.loc[:, "unit_price"] = float("nan")
        new_data.loc[:, "quantity"] = 9999

        result = apply_cleaning_rules(new_data, rules)

        self.assertEqual(result.loc[0, "unit_price"], rules.price_medians["Food"])
        self.assertLessEqual(
            result.loc[0, "quantity"], rules.outlier_bounds["quantity"][1]
        )
        self.assertEqual(result.isna().sum().sum(), 0)


if __name__ == "__main__":
    unittest.main()
