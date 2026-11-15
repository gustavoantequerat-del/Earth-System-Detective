import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from uma import validation
from uma.safeguarded import audit_suspects, finalize

def dataset():
    rng = np.random.default_rng(9)
    years = np.arange(1985, 2025)
    rain = rng.uniform(300, 900, len(years))
    temp = rng.normal(15, 1, len(years))
    oni = rng.normal(0, .5, len(years))
    water = 1000 + rain*2 - 20*temp + rng.normal(0, 20, len(years))
    return pd.DataFrame({"body_id": "a", "year": years, "precip_mm": rain, "temp_c": temp,
                         "oni": oni, "water_ha": water, "nodata_pct": 0.})

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = validation.policy()
        self.cfg["bootstrap_draws"] = 35

    def test_future_water_cannot_change_model_or_intervals(self):
        a = validation.prepare(dataset())
        b = a.copy(); b.loc[2001:, "water_ha"] *= .1
        x = validation.fit_selected(a, 2000, self.cfg)
        y = validation.fit_selected(b, 2000, self.cfg)
        self.assertEqual(x["selected"], y["selected"])
        pd.testing.assert_series_equal(x["expected"], y["expected"])
        pd.testing.assert_series_equal(x["lower"], y["lower"])
        pd.testing.assert_series_equal(x["upper"], y["upper"])
        self.assertNotEqual(x["backtest"]["mae_ha"], y["backtest"]["mae_ha"])

    def test_imputed_water_is_excluded_from_fit(self):
        a = dataset(); a.loc[a.year.eq(1990), "nodata_pct"] = 60
        b = a.copy(); b.loc[b.year.eq(1990), "water_ha"] = 1e10
        x = validation.fit_selected(validation.prepare(a), 2000, self.cfg)
        y = validation.fit_selected(validation.prepare(b), 2000, self.cfg)
        pd.testing.assert_series_equal(x["expected"], y["expected"])
        self.assertEqual(x["base_n"], 14)

    def test_first_lag_is_not_fabricated_and_gaps_fail(self):
        a = dataset()
        self.assertTrue(np.isnan(validation.prepare(a).iloc[0].precip_lag1))
        with self.assertRaises(ValueError): validation.prepare(a.loc[a.year.ne(1990)])
        with self.assertRaises(ValueError): validation.prepare(pd.concat([a, a.iloc[:1]]))

    def test_unreviewed_control_cannot_pass(self):
        a = validation.prepare(dataset()).iloc[1:]
        fit = {"reliable": True, "backtest": {"mae_pct": 1., "coverage": .9}}
        result = validation.control_assessment(a, a, fit, "candidate", 2000, self.cfg)
        self.assertFalse(result["eligible"])
        self.cfg["control_reviews"]["candidate"] = {"approved": True, "source": "independent-report", "reviewer": "analyst"}
        self.assertTrue(validation.control_assessment(a, a, fit, "candidate", 2000, self.cfg)["eligible"])

    def test_positive_association_cannot_be_human_evidence(self):
        rng = np.random.default_rng(11)
        years = np.arange(1980, 2040)
        pressure = pd.Series(np.cumsum(rng.uniform(1, 4, 60)), index=years)
        sus = pd.DataFrame({"body_id": "a", "year": years, "suspect": "mining_ha", "value": pressure.values})
        audit = audit_suspects(pd.DataFrame(index=years), pressure * 2, sus, 2012, 2000)
        self.assertGreater(audit[0]["rho"], .9)
        self.assertFalse(audit[0]["eligible"])

    def test_missing_pressure_is_not_zero(self):
        years = np.arange(1980, 2020)
        sus = pd.DataFrame({"body_id": "a", "year": years, "suspect": "mining_ha", "value": [np.nan]*35 + [1,2,3,4,5]})
        self.assertEqual(audit_suspects(pd.DataFrame(index=years), pd.Series(np.arange(40), index=years), sus, 2000, 1990), [])

    def test_two_tests_do_not_override_climatic_gate(self):
        r = {"quality": {"eligible": True}, "model_validation": {"reliable": True},
             "tests": {"clima": {"pass": False}, "control": {"pass": True}, "coincidencia": {"pass": True}}, "independent_evidence": []}
        self.assertEqual(finalize(r)["state"], "Sin perdida anomala detectada")
        r["quality"]["eligible"] = False
        self.assertEqual(finalize(r)["state"], "Evidencia insuficiente")

    def test_short_baseline_and_bands(self):
        result = validation.fit_selected(validation.prepare(dataset()), 1992, self.cfg)
        self.assertFalse(result["reliable"])
        self.assertEqual(result["selected"], "climatologia")
        mask = result["lower"].notna()
        self.assertTrue((result["lower"][mask] <= result["upper"][mask]).all())
        self.assertTrue((result["lower"][mask] >= 0).all())

    def test_climatology_alone_cannot_support_human_attribution(self):
        r = {"quality": {"eligible": True}, "model_validation": {"reliable": True, "climate_attribution_eligible": False},
             "tests": {k: {"pass": True} for k in ["clima", "control", "coincidencia"]}, "independent_evidence": []}
        self.assertEqual(finalize(r)["state"], "Perdida no explicada")
        r["model_validation"]["climate_attribution_eligible"] = True
        self.assertEqual(finalize(r)["state"], "Indicios de intervencion humana")

if __name__ == "__main__": unittest.main()
