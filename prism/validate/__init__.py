"""MVP3 P2 — Calibration & Validation.

prism.validate.backtest    — replay real events (Maria/Fiona/Apr-2024 blackout)
                              against PRISM's resilience rankings.
prism.validate.sensitivity — sweep load-bearing assumptions (VOLL, discount
                              rate, outage hours, feeder-assignment confidence,
                              hazard probability curve) and report ranking
                              stability.
prism.validate.model_cards — merge config/model_cards.yml with
                              config/confidence.yml + live backtest/sensitivity
                              results for the Trust Center.
"""
