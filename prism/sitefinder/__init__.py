"""Site Finder — multi-criteria suitability scoring for industrial siting.

Scores candidate parcels (industrial-zoned, from CRIM/JP `pr_zoning`) against the
existing PRISM layers — grid proximity + resilience, flood safety, water access,
road access, and (reserved) port access — to answer "where should a business build?"

The dual of the public-investment portfolio: same weighted-overlay engine, scoring
existing locations for a private/PRIDCO actor instead of routing public capital.
"""
