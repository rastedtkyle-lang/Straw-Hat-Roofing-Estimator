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
- The sample prices in the app are placeholders and must be replaced with your actual pricing before customer use.
- This MVP does not yet save jobs/customers between sessions or have user accounts.
- It is intentionally focused on the EagleView-to-estimate workflow first.
