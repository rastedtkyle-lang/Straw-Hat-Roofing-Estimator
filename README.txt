STRAW HAT ROOFING ESTIMATOR — iPHONE WEB APP

This is a Streamlit web app designed to run in Safari after deployment.

WHAT IT DOES
- Upload an EagleView Premium Report PDF from an iPhone.
- Extract roof area, squares, pitch, penetrations, ridge, hip, valley, rake, eave/starter, drip edge, flashing and step flashing.
- Let you review/edit measurements.
- Apply your own pricing.
- Enter customer information.
- Generate an estimate and download a printable HTML proposal.

DEPLOYMENT
The easiest route is Streamlit Community Cloud:
1. Create/sign into a GitHub account.
2. Create a new repository, e.g. straw-hat-roofing-estimator.
3. Upload app.py, requirements.txt, and the .streamlit folder.
4. Go to https://share.streamlit.io and sign in with GitHub.
5. Create App → choose your repository → app.py → Deploy.
6. Streamlit gives the app a streamlit.app URL that opens in Safari.

IMPORTANT
- Material prices are read from the existing Supabase material_presets table.
- Configure SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in Streamlit Secrets (no section heading). Never put secret values in app.py or Git.
- The publishable key needs SELECT access to material_presets under your existing Supabase permissions/RLS policies. If pricing cannot be loaded or required prices are missing, the app stops instead of estimating with fallback prices.
- Material pricing is cached for up to 60 seconds. Sheathing remains editable per estimate; the penetration allowance defaults to $0 and is independent of its nullable database column. The app does not write to Supabase.
- Run offline calculation checks with: python -m unittest test_estimator
- This MVP does not yet save jobs/customers between sessions or have user accounts.
- It is intentionally focused on the EagleView-to-estimate workflow first.
